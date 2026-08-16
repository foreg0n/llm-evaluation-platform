from __future__ import annotations

import uuid
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.models import Dataset, DatasetItem, EvaluationRun, Project, Variant

OwnedModel = TypeVar("OwnedModel", Project, Dataset, DatasetItem, Variant, EvaluationRun)


async def _owned_or_404(
    session: AsyncSession,
    query,
    resource_name: str,
) -> OwnedModel:
    instance = (await session.scalars(query)).one_or_none()
    if instance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource_name} not found",
        )
    return instance


async def get_owned_project(
    session: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    return await _owned_or_404(
        session,
        select(Project).where(Project.id == project_id, Project.owner_id == owner_id),
        "Project",
    )


async def get_owned_dataset(
    session: AsyncSession, owner_id: uuid.UUID, dataset_id: uuid.UUID
) -> Dataset:
    return await _owned_or_404(
        session,
        select(Dataset)
        .join(Project)
        .where(Dataset.id == dataset_id, Project.owner_id == owner_id),
        "Dataset",
    )


async def get_owned_dataset_item(
    session: AsyncSession, owner_id: uuid.UUID, item_id: uuid.UUID
) -> DatasetItem:
    return await _owned_or_404(
        session,
        select(DatasetItem)
        .join(Dataset)
        .join(Project)
        .where(DatasetItem.id == item_id, Project.owner_id == owner_id),
        "Dataset item",
    )


async def get_owned_variant(
    session: AsyncSession, owner_id: uuid.UUID, variant_id: uuid.UUID
) -> Variant:
    return await _owned_or_404(
        session,
        select(Variant)
        .join(Project)
        .where(Variant.id == variant_id, Project.owner_id == owner_id),
        "Variant",
    )


async def get_owned_run(
    session: AsyncSession, owner_id: uuid.UUID, run_id: uuid.UUID
) -> EvaluationRun:
    return await _owned_or_404(
        session,
        select(EvaluationRun)
        .join(Project)
        .where(EvaluationRun.id == run_id, Project.owner_id == owner_id),
        "Evaluation run",
    )
