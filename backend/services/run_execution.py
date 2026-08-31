from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from backend.credential_security import CredentialCipher, get_credential_cipher
from backend.db.models import (
    DatasetItem,
    EvaluationRun,
)
from backend.db.models import (
    EvaluationResult as DatabaseEvaluationResult,
)
from backend.db.models import (
    Variant as DatabaseVariant,
)
from backend.error_monitoring import capture_exception, set_error_context
from backend.metrics import (
    EVALUATION_RUNS_IN_PROGRESS,
    observe_evaluation_run,
)
from backend.network_security import validate_provider_endpoint
from evals.models import (
    DatasetItem as CoreDatasetItem,
)
from evals.models import (
    EvaluationResult as CoreEvaluationResult,
)
from evals.models import (
    Variant as CoreVariant,
)
from evals.runner import GenerateFunction, run_evaluation

logger = logging.getLogger(__name__)


class RunCancelledError(RuntimeError):
    """Stop new work after the API records cooperative cancellation."""


@dataclass(slots=True)
class _PreparedRun:
    run: EvaluationRun
    core_items: list[CoreDatasetItem]
    core_variants: list[CoreVariant]
    item_ids: dict[str, uuid.UUID]
    variant_ids: dict[str, uuid.UUID]
    completed_pairs: set[tuple[str, str]]


def _core_variant(
    variant: DatabaseVariant,
    cipher: CredentialCipher,
) -> CoreVariant:
    api_key: SecretStr | None = None
    api_base: str | None = None
    if variant.credential is not None:
        payload = cipher.decrypt(variant.credential.encrypted_payload)
        api_key = SecretStr(payload["api_key"])
        api_base = payload["api_base"]
    return CoreVariant(
        name=variant.name,
        model=variant.model,
        provider=variant.provider,
        temperature=variant.temperature,
        max_tokens=variant.max_tokens,
        system_prompt=variant.system_prompt,
        timeout_seconds=variant.timeout_seconds,
        max_retries=variant.max_retries,
        api_key=api_key,
        api_base=api_base,
    )


def _database_result(
    run_id: uuid.UUID,
    result: CoreEvaluationResult,
    item_ids: dict[str, uuid.UUID],
    variant_ids: dict[str, uuid.UUID],
) -> DatabaseEvaluationResult:
    return DatabaseEvaluationResult(
        run_id=run_id,
        dataset_item_id=item_ids[result.item_id],
        variant_id=variant_ids[result.variant_name],
        model=result.model,
        provider=result.provider,
        input=result.input,
        expected_output=result.expected_output,
        output=result.output,
        latency_ms=result.latency_ms,
        metrics=(
            result.metrics.model_dump() if result.metrics is not None else None
        ),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        total_tokens=result.total_tokens,
        estimated_cost=result.estimated_cost,
        retry_count=result.retry_count,
        error=result.error,
    )


async def _set_terminal_state(
    session: AsyncSession,
    run_id: uuid.UUID,
    terminal_status: str,
    error: str | None,
) -> None:
    await session.rollback()
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        return
    run.status = terminal_status
    run.finished_at = datetime.now(UTC)
    run.error = error
    await session.commit()


async def _validate_core_variant_endpoints(
    variants: list[CoreVariant],
) -> None:
    api_bases = {
        variant.api_base
        for variant in variants
        if variant.api_base is not None
    }
    await asyncio.gather(
        *(
            asyncio.to_thread(validate_provider_endpoint, api_base)
            for api_base in api_bases
        )
    )


async def _prepare_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    credential_cipher: CredentialCipher,
) -> _PreparedRun | None:
    run_query = (
        select(EvaluationRun)
        .where(EvaluationRun.id == run_id)
        .options(
            selectinload(EvaluationRun.project),
            selectinload(EvaluationRun.variants).selectinload(
                DatabaseVariant.credential
            ),
        )
    )
    run = (await session.scalars(run_query)).one()
    if run.status in {"completed", "cancelled"}:
        return None

    items = list(
        (
            await session.scalars(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == run.dataset_id)
                .order_by(DatasetItem.created_at, DatasetItem.id)
            )
        ).all()
    )
    ordered_variants = sorted(
        run.variants,
        key=lambda value: (value.name, str(value.id)),
    )
    if not items or not ordered_variants:
        raise RuntimeError("Run inputs are no longer available")
    if any(
        variant.credential is not None
        and variant.credential.user_id != run.project.owner_id
        for variant in ordered_variants
    ):
        raise RuntimeError("Run contains a credential owned by another user")

    existing_results = list(
        (
            await session.scalars(
                select(DatabaseEvaluationResult).where(
                    DatabaseEvaluationResult.run_id == run_id
                )
            )
        ).all()
    )
    variants_by_id = {variant.id: variant for variant in ordered_variants}
    completed_pairs = {
        (
            str(result.dataset_item_id),
            variants_by_id[result.variant_id].name,
        )
        for result in existing_results
        if result.variant_id in variants_by_id
    }

    core_variants = [
        _core_variant(variant, credential_cipher)
        for variant in ordered_variants
    ]
    await _validate_core_variant_endpoints(core_variants)

    run.status = "running"
    run.started_at = run.started_at or datetime.now(UTC)
    run.total_tasks = len(items) * len(ordered_variants)
    run.completed_tasks = len(existing_results)
    run.error = None
    used_at = datetime.now(UTC)
    for variant in ordered_variants:
        if variant.credential is not None:
            variant.credential.last_used_at = used_at
    await session.commit()

    return _PreparedRun(
        run=run,
        core_items=[
            CoreDatasetItem(
                id=str(item.id),
                input=item.input,
                expected_output=item.expected_output,
                keywords=item.keywords,
            )
            for item in items
        ],
        core_variants=core_variants,
        item_ids={str(item.id): item.id for item in items},
        variant_ids={
            variant.name: variant.id for variant in ordered_variants
        },
        completed_pairs=completed_pairs,
    )


async def _execute_prepared_run(
    session: AsyncSession,
    prepared: _PreparedRun,
    generate_function: GenerateFunction,
) -> None:
    run = prepared.run

    async def persist_result(result: CoreEvaluationResult) -> None:
        await session.refresh(
            run,
            attribute_names=["status", "completed_tasks"],
        )
        if run.status == "cancelled":
            raise RunCancelledError("Cancelled by user")
        session.add(
            _database_result(
                run.id,
                result,
                prepared.item_ids,
                prepared.variant_ids,
            )
        )
        run.completed_tasks += 1
        await session.commit()

    await run_evaluation(
        dataset=prepared.core_items,
        variants=prepared.core_variants,
        generate_function=generate_function,
        concurrency=run.concurrency,
        on_result=persist_result,
        skip_pairs=prepared.completed_pairs,
    )
    await session.refresh(run, attribute_names=["status"])
    if run.status == "cancelled":
        raise RunCancelledError("Cancelled by user")
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    run.error = None
    await session.commit()


async def execute_evaluation_run(
    run_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    generate_function: GenerateFunction,
) -> None:
    """Execute one persisted run outside the request-scoped DB session."""

    execution_started_at = time.perf_counter()
    credential_cipher = get_credential_cipher()
    set_error_context(run_id=run_id)
    metrics_active = False
    async with session_factory() as session:
        try:
            prepared = await _prepare_run(
                session,
                run_id,
                credential_cipher,
            )
            if prepared is None:
                return
            EVALUATION_RUNS_IN_PROGRESS.inc()
            metrics_active = True
            logger.info(
                "evaluation_run_started",
                extra={
                    "event": "evaluation_run_started",
                    "run_id": str(run_id),
                    "total_tasks": prepared.run.total_tasks,
                    "completed_tasks": prepared.run.completed_tasks,
                },
            )
            await _execute_prepared_run(
                session,
                prepared,
                generate_function,
            )
            observe_evaluation_run(
                outcome="completed",
                duration_seconds=time.perf_counter() - execution_started_at,
            )
            logger.info(
                "evaluation_run_completed",
                extra={
                    "event": "evaluation_run_completed",
                    "run_id": str(run_id),
                    "total_tasks": prepared.run.total_tasks,
                    "completed_tasks": prepared.run.completed_tasks,
                },
            )
        except (asyncio.CancelledError, RunCancelledError):
            await _set_terminal_state(
                session, run_id, "cancelled", "Cancelled by user"
            )
            observe_evaluation_run(
                outcome="cancelled",
                duration_seconds=time.perf_counter() - execution_started_at,
            )
            logger.info(
                "evaluation_run_cancelled",
                extra={
                    "event": "evaluation_run_cancelled",
                    "run_id": str(run_id),
                },
            )
        except Exception as exc:
            capture_exception(exc, run_id=run_id)
            await _set_terminal_state(
                session,
                run_id,
                "failed",
                f"{type(exc).__name__}: {exc}",
            )
            observe_evaluation_run(
                outcome="failed",
                duration_seconds=time.perf_counter() - execution_started_at,
            )
            logger.exception(
                "evaluation_run_failed",
                extra={
                    "event": "evaluation_run_failed",
                    "run_id": str(run_id),
                },
            )
        finally:
            if metrics_active:
                EVALUATION_RUNS_IN_PROGRESS.dec()
