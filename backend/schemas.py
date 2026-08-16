from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

Name = Annotated[str, Field(min_length=1, max_length=200)]
LongName = Annotated[str, Field(min_length=1, max_length=300)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RejectNullFields(BaseModel):
    reject_null_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> RejectNullFields:
        null_fields = sorted(
            field
            for field in self.reject_null_fields.intersection(self.model_fields_set)
            if getattr(self, field) is None
        )
        if null_fields:
            names = ", ".join(null_fields)
            raise ValueError(f"These fields cannot be null: {names}")
        return self


class ProjectCreate(BaseModel):
    name: Name
    description: str | None = None


class ProjectUpdate(RejectNullFields):
    reject_null_fields = frozenset({"name"})

    name: Name | None = None
    description: str | None = None


class ProjectRead(ORMModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class UserRegister(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class UserLogin(UserRegister):
    pass


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class DatasetCreate(BaseModel):
    name: Name
    description: str | None = None


class DatasetUpdate(RejectNullFields):
    reject_null_fields = frozenset({"name"})

    name: Name | None = None
    description: str | None = None


class DatasetRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class DatasetItemCreate(BaseModel):
    external_id: Name
    input: Annotated[str, Field(min_length=1)]
    expected_output: str
    keywords: list[str] = Field(default_factory=list)


class DatasetItemUpdate(RejectNullFields):
    reject_null_fields = frozenset(
        {"external_id", "input", "expected_output", "keywords"}
    )

    external_id: Name | None = None
    input: Annotated[str, Field(min_length=1)] | None = None
    expected_output: str | None = None
    keywords: list[str] | None = None


class DatasetItemRead(ORMModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    external_id: str
    input: str
    expected_output: str
    keywords: list[str]
    created_at: datetime
    updated_at: datetime


class VariantCreate(BaseModel):
    name: Name
    model: LongName
    provider: Annotated[str, Field(min_length=1, max_length=100)] = "litellm"
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    max_tokens: Annotated[int, Field(gt=0)] | None = None
    system_prompt: str | None = None
    timeout_seconds: Annotated[float, Field(gt=0)] = 30.0
    max_retries: Annotated[int, Field(ge=0, le=10)] = 2


class VariantUpdate(RejectNullFields):
    reject_null_fields = frozenset(
        {
            "name",
            "model",
            "provider",
            "temperature",
            "timeout_seconds",
            "max_retries",
        }
    )

    name: Name | None = None
    model: LongName | None = None
    provider: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    temperature: Annotated[float, Field(ge=0, le=2)] | None = None
    max_tokens: Annotated[int, Field(gt=0)] | None = None
    system_prompt: str | None = None
    timeout_seconds: Annotated[float, Field(gt=0)] | None = None
    max_retries: Annotated[int, Field(ge=0, le=10)] | None = None


class VariantRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    model: str
    provider: str
    temperature: float
    max_tokens: int | None
    system_prompt: str | None
    timeout_seconds: float
    max_retries: int
    created_at: datetime
    updated_at: datetime


class EvaluationRunCreate(BaseModel):
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    variant_ids: Annotated[list[uuid.UUID], Field(min_length=1)]
    concurrency: Annotated[int, Field(ge=1, le=20)] = 3

    @model_validator(mode="after")
    def require_unique_variants(self) -> EvaluationRunCreate:
        if len(set(self.variant_ids)) != len(self.variant_ids):
            raise ValueError("variant_ids must be unique")
        return self


class EvaluationRunRead(ORMModel):
    id: uuid.UUID
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    status: str
    concurrency: int
    total_tasks: int
    completed_tasks: int
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class EvaluationResultRead(ORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    dataset_item_id: uuid.UUID
    variant_id: uuid.UUID
    model: str
    provider: str
    input: str
    expected_output: str
    output: str | None
    latency_ms: float | None
    metrics: dict[str, float] | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost: Decimal | None
    retry_count: int
    error: str | None
    created_at: datetime


class EvaluationVariantSummary(BaseModel):
    variant_name: str
    average_exact_match: float
    average_normalized_exact_match: float
    average_keyword_score: float
    average_quality: float
    average_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_estimated_cost: float
    total_retries: int
    error_count: int


class EvaluationRunDetail(EvaluationRunRead):
    variant_ids: list[uuid.UUID]
    summary: list[EvaluationVariantSummary]
    results: list[EvaluationResultRead]
