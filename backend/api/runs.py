from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.auth import CurrentUserDependency
from backend.api.ownership import (
    get_owned_dataset,
    get_owned_project,
    get_owned_run,
)
from backend.db.models import (
    DatasetItem,
    EvaluationResult as DatabaseEvaluationResult,
    EvaluationRun,
    Project,
    Variant as DatabaseVariant,
)
from backend.db.session import get_db_session
from backend.schemas import (
    EvaluationResultRead,
    EvaluationRunCreate,
    EvaluationRunDetail,
    EvaluationRunRead,
)
from backend.services.schedulers import RunScheduler, get_run_scheduler
from evals.models import (
    EvaluationResult as CoreEvaluationResult,
    MetricScores,
    Variant as CoreVariant,
)
from evals.runner import summarize_results

router = APIRouter(prefix="/api/v1", tags=["evaluation runs"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SchedulerDependency = Annotated[RunScheduler, Depends(get_run_scheduler)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


async def _load_run_or_404(
    session: AsyncSession, owner_id: uuid.UUID, run_id: uuid.UUID
) -> EvaluationRun:
    query = (
        select(EvaluationRun)
        .join(Project)
        .where(EvaluationRun.id == run_id, Project.owner_id == owner_id)
        .options(
            selectinload(EvaluationRun.variants),
            selectinload(EvaluationRun.results),
        )
    )
    run = (await session.scalars(query)).one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run


def _core_variant(variant: DatabaseVariant) -> CoreVariant:
    return CoreVariant(
        name=variant.name,
        model=variant.model,
        provider=variant.provider,
        temperature=variant.temperature,
        max_tokens=variant.max_tokens,
        system_prompt=variant.system_prompt,
        timeout_seconds=variant.timeout_seconds,
        max_retries=variant.max_retries,
    )


def _run_detail(run: EvaluationRun) -> EvaluationRunDetail:
    ordered_variants = sorted(
        run.variants, key=lambda value: (value.name, str(value.id))
    )
    ordered_results = sorted(
        run.results,
        key=lambda value: (str(value.dataset_item_id), str(value.variant_id)),
    )
    variants_by_id = {variant.id: variant for variant in ordered_variants}
    core_variants = [_core_variant(variant) for variant in ordered_variants]
    core_results = [
        CoreEvaluationResult(
            item_id=str(result.dataset_item_id),
            variant_name=variants_by_id[result.variant_id].name,
            model=result.model,
            provider=result.provider,
            input=result.input,
            expected_output=result.expected_output,
            output=result.output,
            latency_ms=result.latency_ms or 0.0,
            metrics=(
                MetricScores.model_validate(result.metrics)
                if result.metrics is not None
                else None
            ),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            estimated_cost=(
                float(result.estimated_cost)
                if result.estimated_cost is not None
                else None
            ),
            retry_count=result.retry_count,
            error=result.error,
        )
        for result in ordered_results
    ]
    summaries = summarize_results(core_results, core_variants)

    return EvaluationRunDetail(
        id=run.id,
        project_id=run.project_id,
        dataset_id=run.dataset_id,
        status=run.status,
        concurrency=run.concurrency,
        total_tasks=run.total_tasks,
        completed_tasks=run.completed_tasks,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        variant_ids=[variant.id for variant in ordered_variants],
        summary=[summary.model_dump() for summary in summaries],
        results=[
            EvaluationResultRead.model_validate(result)
            for result in ordered_results
        ],
    )


@router.post(
    "/runs",
    response_model=EvaluationRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_evaluation_run(
    payload: EvaluationRunCreate,
    session: SessionDependency,
    scheduler: SchedulerDependency,
    current_user: CurrentUserDependency,
) -> EvaluationRunRead:
    await get_owned_project(session, current_user.id, payload.project_id)

    dataset = await get_owned_dataset(session, current_user.id, payload.dataset_id)
    if dataset.project_id != payload.project_id:
        raise HTTPException(
            status_code=409,
            detail="Dataset does not belong to the selected project",
        )

    items = list(
        (
            await session.scalars(
                select(DatasetItem).where(
                    DatasetItem.dataset_id == payload.dataset_id
                )
            )
        ).all()
    )
    if not items:
        raise HTTPException(status_code=409, detail="Dataset contains no items")

    variants = list(
        (
            await session.scalars(
                select(DatabaseVariant).where(
                    DatabaseVariant.id.in_(payload.variant_ids),
                    DatabaseVariant.project_id == payload.project_id,
                )
            )
        ).all()
    )
    if len(variants) != len(payload.variant_ids):
        raise HTTPException(status_code=404, detail="One or more variants not found")
    if any(variant.max_retries > 10 for variant in variants):
        raise HTTPException(
            status_code=409,
            detail="Every variant must have max_retries between 0 and 10",
        )

    variants_by_id = {variant.id: variant for variant in variants}
    ordered_variants = [variants_by_id[variant_id] for variant_id in payload.variant_ids]
    run = EvaluationRun(
        project_id=payload.project_id,
        dataset_id=payload.dataset_id,
        status="pending",
        concurrency=payload.concurrency,
        total_tasks=len(items) * len(ordered_variants),
        completed_tasks=0,
        variants=ordered_variants,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    try:
        await scheduler.schedule(run.id)
    except Exception as exc:
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error = f"{type(exc).__name__}: {exc}"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evaluation run could not be scheduled",
        ) from exc

    return EvaluationRunRead.model_validate(run)


@router.get("/runs", response_model=list[EvaluationRunRead])
async def list_evaluation_runs(
    session: SessionDependency,
    current_user: CurrentUserDependency,
    project_id: uuid.UUID | None = None,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[EvaluationRun]:
    query = (
        select(EvaluationRun)
        .join(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(EvaluationRun.created_at.desc(), EvaluationRun.id)
    )
    if project_id is not None:
        await get_owned_project(session, current_user.id, project_id)
        query = query.where(EvaluationRun.project_id == project_id)
    runs = await session.scalars(query.offset(offset).limit(limit))
    return list(runs.all())


@router.get("/runs/{run_id}", response_model=EvaluationRunDetail)
async def get_evaluation_run(
    run_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> EvaluationRunDetail:
    return _run_detail(
        await _load_run_or_404(session, current_user.id, run_id)
    )


@router.get("/runs/{run_id}/results", response_model=list[EvaluationResultRead])
async def list_evaluation_results(
    run_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[DatabaseEvaluationResult]:
    await get_owned_run(session, current_user.id, run_id)
    results = await session.scalars(
        select(DatabaseEvaluationResult)
        .where(DatabaseEvaluationResult.run_id == run_id)
        .order_by(
            DatabaseEvaluationResult.dataset_item_id,
            DatabaseEvaluationResult.variant_id,
        )
        .offset(offset)
        .limit(limit)
    )
    return list(results.all())


@router.post("/runs/{run_id}/cancel", response_model=EvaluationRunRead)
async def cancel_evaluation_run(
    run_id: uuid.UUID,
    session: SessionDependency,
    scheduler: SchedulerDependency,
    current_user: CurrentUserDependency,
) -> EvaluationRun:
    # rollback() expires every ORM object attached to this session, including
    # current_user. Keep the scalar UUID so later ownership checks never cause
    # an implicit async database load (which would raise MissingGreenlet).
    owner_id = current_user.id
    existing_run = await get_owned_run(session, owner_id, run_id)
    if existing_run.status not in {"pending", "running"}:
        raise HTTPException(
            status_code=409,
            detail=f"Run with status '{existing_run.status}' cannot be cancelled",
        )

    # Finish the read transaction, then atomically claim cancellation only if
    # the worker has not reached a terminal state in the meantime.
    await session.rollback()
    cancelled_id = (
        await session.execute(
            update(EvaluationRun)
            .where(
                EvaluationRun.id == run_id,
                EvaluationRun.status.in_({"pending", "running"}),
                EvaluationRun.project_id.in_(
                    select(Project.id).where(Project.owner_id == owner_id)
                ),
            )
            .values(
                status="cancelled",
                finished_at=datetime.now(UTC),
                error="Cancelled by user",
            )
            .returning(EvaluationRun.id)
        )
    ).scalar_one_or_none()
    await session.commit()
    if cancelled_id is None:
        current_run = await get_owned_run(session, owner_id, run_id)
        raise HTTPException(
            status_code=409,
            detail=f"Run with status '{current_run.status}' cannot be cancelled",
        )

    try:
        await scheduler.cancel(run_id)
    except Exception:
        # PostgreSQL is the source of truth. A queued or running worker will
        # observe the cancelled state even if Redis revoke is unavailable.
        pass

    return await get_owned_run(session, owner_id, run_id)
