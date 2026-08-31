from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select, update
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
    EvaluationRun,
    Project,
)
from backend.db.models import (
    EvaluationResult as DatabaseEvaluationResult,
)
from backend.db.models import (
    Variant as DatabaseVariant,
)
from backend.db.session import get_db_session
from backend.schemas import (
    EvaluationResultPage,
    EvaluationResultRead,
    EvaluationRunCreate,
    EvaluationRunDetail,
    EvaluationRunRead,
    EvaluationVariantSummary,
)
from backend.services.schedulers import RunScheduler, get_run_scheduler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["evaluation runs"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
SchedulerDependency = Annotated[RunScheduler, Depends(get_run_scheduler)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
ResultStatus = Literal["all", "successful", "errors", "low-quality"]
ResultSort = Literal[
    "default",
    "quality-asc",
    "quality-desc",
    "latency-asc",
    "latency-desc",
    "tokens-asc",
    "tokens-desc",
]


async def _load_run_or_404(
    session: AsyncSession,
    owner_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    include_results: bool,
) -> EvaluationRun:
    options = [selectinload(EvaluationRun.variants)]
    if include_results:
        options.append(selectinload(EvaluationRun.results))
    query = (
        select(EvaluationRun)
        .join(Project)
        .where(EvaluationRun.id == run_id, Project.owner_id == owner_id)
        .options(*options)
    )
    run = (await session.scalars(query)).one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run


async def _summarize_database_results(
    session: AsyncSession,
    run: EvaluationRun,
) -> list[EvaluationVariantSummary]:
    result = DatabaseEvaluationResult
    exact_match = result.metrics["exact_match"].as_float()
    normalized_exact_match = result.metrics["normalized_exact_match"].as_float()
    keyword_score = result.metrics["keyword_score"].as_float()
    quality = (exact_match + normalized_exact_match + keyword_score) / 3.0
    row_query = (
        select(
            result.variant_id.label("variant_id"),
            func.count(result.id).label("result_count"),
            func.avg(exact_match).label("average_exact_match"),
            func.avg(normalized_exact_match).label(
                "average_normalized_exact_match"
            ),
            func.avg(keyword_score).label("average_keyword_score"),
            func.avg(quality).label("average_quality"),
            func.avg(func.coalesce(result.latency_ms, 0.0)).label(
                "average_latency_ms"
            ),
            func.sum(func.coalesce(result.input_tokens, 0)).label(
                "total_input_tokens"
            ),
            func.sum(func.coalesce(result.output_tokens, 0)).label(
                "total_output_tokens"
            ),
            func.sum(func.coalesce(result.total_tokens, 0)).label("total_tokens"),
            func.sum(func.coalesce(result.estimated_cost, 0)).label(
                "total_estimated_cost"
            ),
            func.sum(result.retry_count).label("total_retries"),
            func.sum(case((result.error.is_not(None), 1), else_=0)).label(
                "error_count"
            ),
        )
        .where(result.run_id == run.id)
        .group_by(result.variant_id)
    )
    rows = {
        row.variant_id: row
        for row in (await session.execute(row_query)).all()
    }
    ordered_variants = sorted(
        run.variants, key=lambda value: (value.name, str(value.id))
    )
    summaries: list[EvaluationVariantSummary] = []
    for variant in ordered_variants:
        row = rows.get(variant.id)
        if row is None:
            summaries.append(
                EvaluationVariantSummary(
                    variant_name=variant.name,
                    result_count=0,
                    average_exact_match=0,
                    average_normalized_exact_match=0,
                    average_keyword_score=0,
                    average_quality=0,
                    average_latency_ms=0,
                    total_input_tokens=0,
                    total_output_tokens=0,
                    total_tokens=0,
                    total_estimated_cost=0,
                    total_retries=0,
                    error_count=0,
                )
            )
            continue
        summaries.append(
            EvaluationVariantSummary(
                variant_name=variant.name,
                result_count=int(row.result_count),
                average_exact_match=float(row.average_exact_match or 0),
                average_normalized_exact_match=float(
                    row.average_normalized_exact_match or 0
                ),
                average_keyword_score=float(row.average_keyword_score or 0),
                average_quality=float(row.average_quality or 0),
                average_latency_ms=float(row.average_latency_ms or 0),
                total_input_tokens=int(row.total_input_tokens or 0),
                total_output_tokens=int(row.total_output_tokens or 0),
                total_tokens=int(row.total_tokens or 0),
                total_estimated_cost=float(row.total_estimated_cost or 0),
                total_retries=int(row.total_retries or 0),
                error_count=int(row.error_count or 0),
            )
        )
    return summaries


async def _run_detail(
    session: AsyncSession,
    run: EvaluationRun,
    *,
    include_results: bool,
) -> EvaluationRunDetail:
    ordered_variants = sorted(
        run.variants, key=lambda value: (value.name, str(value.id))
    )
    ordered_results = (
        sorted(
            run.results,
            key=lambda value: (str(value.dataset_item_id), str(value.variant_id)),
        )
        if include_results
        else []
    )
    summaries = await _summarize_database_results(session, run)

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
        summary=summaries,
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
    include_results: bool = Query(default=True),
) -> EvaluationRunDetail:
    run = await _load_run_or_404(
        session,
        current_user.id,
        run_id,
        include_results=include_results,
    )
    return await _run_detail(session, run, include_results=include_results)


def _filtered_results_query(
    run_id: uuid.UUID,
    *,
    search: str | None,
    variant_id: uuid.UUID | None,
    result_status: ResultStatus,
):
    result = DatabaseEvaluationResult
    query = select(result).where(result.run_id == run_id)
    if search:
        query = query.where(
            func.lower(result.input).contains(
                search.strip().lower(), autoescape=True
            )
        )
    if variant_id is not None:
        query = query.where(result.variant_id == variant_id)
    if result_status == "successful":
        query = query.where(result.error.is_(None))
    elif result_status == "errors":
        query = query.where(result.error.is_not(None))
    elif result_status == "low-quality":
        quality = (
            result.metrics["exact_match"].as_float()
            + result.metrics["normalized_exact_match"].as_float()
            + result.metrics["keyword_score"].as_float()
        ) / 3.0
        query = query.where(result.metrics.is_not(None), quality < 0.67)
    return query


def _order_results(query, sort: ResultSort):
    result = DatabaseEvaluationResult
    quality = (
        result.metrics["exact_match"].as_float()
        + result.metrics["normalized_exact_match"].as_float()
        + result.metrics["keyword_score"].as_float()
    ) / 3.0
    orders = {
        "quality-asc": (quality.is_(None), quality.asc()),
        "quality-desc": (quality.is_(None), quality.desc()),
        "latency-asc": (result.latency_ms.is_(None), result.latency_ms.asc()),
        "latency-desc": (result.latency_ms.is_(None), result.latency_ms.desc()),
        "tokens-asc": (result.total_tokens.is_(None), result.total_tokens.asc()),
        "tokens-desc": (result.total_tokens.is_(None), result.total_tokens.desc()),
    }
    if sort in orders:
        query = query.order_by(*orders[sort])
    else:
        query = query.order_by(result.dataset_item_id, result.variant_id)
    return query.order_by(result.id)


@router.get(
    "/runs/{run_id}/results/page",
    response_model=EvaluationResultPage,
)
async def get_evaluation_result_page(
    run_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
    offset: Offset = 0,
    limit: Limit = 25,
    search: Annotated[str | None, Query(max_length=200)] = None,
    variant_id: uuid.UUID | None = None,
    result_status: ResultStatus = "all",
    sort: ResultSort = "default",
) -> EvaluationResultPage:
    await get_owned_run(session, current_user.id, run_id)
    filtered = _filtered_results_query(
        run_id,
        search=search,
        variant_id=variant_id,
        result_status=result_status,
    )
    total = int(
        (
            await session.scalar(
                select(func.count()).select_from(filtered.order_by(None).subquery())
            )
        )
        or 0
    )
    items = list(
        (
            await session.scalars(
                _order_results(filtered, sort).offset(offset).limit(limit)
            )
        ).all()
    )
    return EvaluationResultPage(
        items=[EvaluationResultRead.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + len(items) < total,
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
    except Exception as exc:
        # PostgreSQL is the source of truth. A queued or running worker will
        # observe the cancelled state even if Redis revoke is unavailable.
        logger.warning(
            "evaluation_run_scheduler_cancel_failed",
            extra={
                "event": "evaluation_run_scheduler_cancel_failed",
                "run_id": str(run_id),
                "error_type": type(exc).__name__,
            },
        )

    return await get_owned_run(session, owner_id, run_id)
