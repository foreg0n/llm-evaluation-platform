from __future__ import annotations

import uuid
from typing import Annotated, Any, TypeVar

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import CurrentUserDependency
from backend.api.ownership import (
    get_owned_dataset,
    get_owned_dataset_item,
    get_owned_project,
    get_owned_variant,
)
from backend.db.models import Dataset, DatasetItem, Project, Variant
from backend.db.session import get_db_session
from backend.dataset_import import (
    MAX_DATASET_FILE_BYTES,
    DatasetImportError,
    default_dataset_name,
    parse_dataset_file,
)
from backend.schemas import (
    DatasetCreate,
    DatasetImportRead,
    DatasetItemCreate,
    DatasetItemRead,
    DatasetItemUpdate,
    DatasetRead,
    DatasetUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    VariantCreate,
    VariantRead,
    VariantUpdate,
)

router = APIRouter(prefix="/api/v1")
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
ModelT = TypeVar("ModelT", Project, Dataset, DatasetItem, Variant)


async def _commit(session: AsyncSession, conflict_detail: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=conflict_detail,
        ) from exc


async def _create(
    session: AsyncSession,
    model: type[ModelT],
    values: dict[str, Any],
    conflict_detail: str,
) -> ModelT:
    instance = model(**values)
    session.add(instance)
    await _commit(session, conflict_detail)
    await session.refresh(instance)
    return instance


async def _update(
    session: AsyncSession,
    instance: ModelT,
    payload: BaseModel,
    conflict_detail: str,
) -> ModelT:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(instance, field, value)
    await _commit(session, conflict_detail)
    await session.refresh(instance)
    return instance


async def _delete(
    session: AsyncSession,
    instance: ModelT,
    conflict_detail: str,
) -> None:
    await session.delete(instance)
    await _commit(session, conflict_detail)


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
async def create_project(
    payload: ProjectCreate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Project:
    return await _create(
        session,
        Project,
        payload.model_dump() | {"owner_id": current_user.id},
        "You already have a project with this name",
    )


@router.get("/projects", response_model=list[ProjectRead], tags=["projects"])
async def list_projects(
    session: SessionDependency,
    current_user: CurrentUserDependency,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[Project]:
    result = await session.scalars(
        select(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(Project.created_at, Project.id)
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


@router.get("/projects/{project_id}", response_model=ProjectRead, tags=["projects"])
async def get_project(
    project_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Project:
    return await get_owned_project(session, current_user.id, project_id)


@router.patch(
    "/projects/{project_id}", response_model=ProjectRead, tags=["projects"]
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Project:
    project = await get_owned_project(session, current_user.id, project_id)
    return await _update(
        session,
        project,
        payload,
        "You already have a project with this name",
    )


@router.delete(
    "/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["projects"]
)
async def delete_project(
    project_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Response:
    project = await get_owned_project(session, current_user.id, project_id)
    await _delete(session, project, "Project is referenced by existing data")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
    tags=["datasets"],
)
async def create_dataset(
    project_id: uuid.UUID,
    payload: DatasetCreate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Dataset:
    await get_owned_project(session, current_user.id, project_id)
    values = payload.model_dump() | {"project_id": project_id}
    return await _create(
        session,
        Dataset,
        values,
        "A dataset with this name already exists in the project",
    )


@router.get(
    "/projects/{project_id}/datasets",
    response_model=list[DatasetRead],
    tags=["datasets"],
)
async def list_datasets(
    project_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[Dataset]:
    await get_owned_project(session, current_user.id, project_id)
    result = await session.scalars(
        select(Dataset)
        .where(Dataset.project_id == project_id)
        .order_by(Dataset.created_at, Dataset.id)
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


@router.post(
    "/projects/{project_id}/datasets/import",
    response_model=DatasetImportRead,
    status_code=status.HTTP_201_CREATED,
    tags=["datasets"],
)
async def import_dataset_file(
    project_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
    file: Annotated[UploadFile, File(description="JSON, JSONL, or NDJSON dataset")],
    name: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
) -> DatasetImportRead:
    await get_owned_project(session, current_user.id, project_id)
    filename = file.filename or "dataset.jsonl"
    content = await file.read(MAX_DATASET_FILE_BYTES + 1)
    await file.close()
    try:
        parsed = parse_dataset_file(filename, content)
        dataset_payload = DatasetCreate(
            name=name or parsed.name or default_dataset_name(filename),
            description=description if description is not None else parsed.description,
        )
    except (DatasetImportError, ValidationError) as exc:
        detail = str(exc)
        if isinstance(exc, ValidationError):
            detail = exc.errors()[0]["msg"]
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        ) from exc

    dataset = Dataset(
        project_id=project_id,
        name=dataset_payload.name,
        description=dataset_payload.description,
    )
    dataset.items = [
        DatasetItem(
            external_id=item.external_id,
            input=item.input,
            expected_output=item.expected_output,
            keywords=item.keywords,
        )
        for item in parsed.items
    ]
    session.add(dataset)
    await _commit(
        session,
        "A dataset with this name already exists in the project",
    )
    await session.refresh(dataset)
    return DatasetImportRead(
        dataset=DatasetRead.model_validate(dataset),
        item_count=len(parsed.items),
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetRead, tags=["datasets"])
async def get_dataset(
    dataset_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Dataset:
    return await get_owned_dataset(session, current_user.id, dataset_id)


@router.patch(
    "/datasets/{dataset_id}", response_model=DatasetRead, tags=["datasets"]
)
async def update_dataset(
    dataset_id: uuid.UUID,
    payload: DatasetUpdate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Dataset:
    dataset = await get_owned_dataset(session, current_user.id, dataset_id)
    return await _update(
        session,
        dataset,
        payload,
        "A dataset with this name already exists in the project",
    )


@router.delete(
    "/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["datasets"]
)
async def delete_dataset(
    dataset_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Response:
    dataset = await get_owned_dataset(session, current_user.id, dataset_id)
    await _delete(session, dataset, "Dataset is referenced by an evaluation run")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/datasets/{dataset_id}/items",
    response_model=DatasetItemRead,
    status_code=status.HTTP_201_CREATED,
    tags=["dataset items"],
)
async def create_dataset_item(
    dataset_id: uuid.UUID,
    payload: DatasetItemCreate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> DatasetItem:
    await get_owned_dataset(session, current_user.id, dataset_id)
    values = payload.model_dump() | {"dataset_id": dataset_id}
    return await _create(
        session,
        DatasetItem,
        values,
        "An item with this external_id already exists in the dataset",
    )


@router.get(
    "/datasets/{dataset_id}/items",
    response_model=list[DatasetItemRead],
    tags=["dataset items"],
)
async def list_dataset_items(
    dataset_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[DatasetItem]:
    await get_owned_dataset(session, current_user.id, dataset_id)
    result = await session.scalars(
        select(DatasetItem)
        .where(DatasetItem.dataset_id == dataset_id)
        .order_by(DatasetItem.created_at, DatasetItem.id)
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


@router.get(
    "/dataset-items/{item_id}", response_model=DatasetItemRead, tags=["dataset items"]
)
async def get_dataset_item(
    item_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> DatasetItem:
    return await get_owned_dataset_item(session, current_user.id, item_id)


@router.patch(
    "/dataset-items/{item_id}", response_model=DatasetItemRead, tags=["dataset items"]
)
async def update_dataset_item(
    item_id: uuid.UUID,
    payload: DatasetItemUpdate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> DatasetItem:
    item = await get_owned_dataset_item(session, current_user.id, item_id)
    return await _update(
        session,
        item,
        payload,
        "An item with this external_id already exists in the dataset",
    )


@router.delete(
    "/dataset-items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["dataset items"],
)
async def delete_dataset_item(
    item_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Response:
    item = await get_owned_dataset_item(session, current_user.id, item_id)
    await _delete(session, item, "Dataset item is referenced by an evaluation result")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/variants",
    response_model=VariantRead,
    status_code=status.HTTP_201_CREATED,
    tags=["variants"],
)
async def create_variant(
    project_id: uuid.UUID,
    payload: VariantCreate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Variant:
    await get_owned_project(session, current_user.id, project_id)
    values = payload.model_dump() | {"project_id": project_id}
    return await _create(
        session,
        Variant,
        values,
        "A variant with this name already exists in the project",
    )


@router.get(
    "/projects/{project_id}/variants",
    response_model=list[VariantRead],
    tags=["variants"],
)
async def list_variants(
    project_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
    offset: Offset = 0,
    limit: Limit = 50,
) -> list[Variant]:
    await get_owned_project(session, current_user.id, project_id)
    result = await session.scalars(
        select(Variant)
        .where(Variant.project_id == project_id)
        .order_by(Variant.created_at, Variant.id)
        .offset(offset)
        .limit(limit)
    )
    return list(result.all())


@router.get("/variants/{variant_id}", response_model=VariantRead, tags=["variants"])
async def get_variant(
    variant_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Variant:
    return await get_owned_variant(session, current_user.id, variant_id)


@router.patch(
    "/variants/{variant_id}", response_model=VariantRead, tags=["variants"]
)
async def update_variant(
    variant_id: uuid.UUID,
    payload: VariantUpdate,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Variant:
    variant = await get_owned_variant(session, current_user.id, variant_id)
    return await _update(
        session,
        variant,
        payload,
        "A variant with this name already exists in the project",
    )


@router.delete(
    "/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["variants"]
)
async def delete_variant(
    variant_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Response:
    variant = await get_owned_variant(session, current_user.id, variant_id)
    await _delete(session, variant, "Variant is referenced by an evaluation result")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
