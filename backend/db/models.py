from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


evaluation_run_variants = Table(
    "evaluation_run_variants",
    Base.metadata,
    Column(
        "run_id",
        Uuid(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "variant_id",
        Uuid(as_uuid=True),
        ForeignKey("variants.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_projects_owner_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    owner: Mapped[User] = relationship(back_populates="projects")
    datasets: Mapped[list[Dataset]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    variants: Mapped[list[Variant]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    runs: Mapped[list[EvaluationRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    provider_credentials: Mapped[list[ProviderCredential]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    refresh_sessions: Mapped[list[RefreshSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="RefreshSession.user_id",
    )
    account_action_tokens: Mapped[list[AccountActionToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AccountActionToken(Base):
    __tablename__ = "account_action_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name="valid_purpose",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="account_action_tokens")


class RefreshSession(TimestampMixin, Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"),
    )

    user: Mapped[User] = relationship(
        back_populates="refresh_sessions",
        foreign_keys=[user_id],
    )


class ProviderCredential(TimestampMixin, Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "name",
            name="uq_provider_credentials_user_provider_name",
        ),
        CheckConstraint(
            "status IN ('untested', 'connected', 'invalid')",
            name="valid_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(200))
    encrypted_payload: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default="untested")
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="provider_credentials")
    variants: Mapped[list[Variant]] = relationship(
        back_populates="credential", passive_deletes=True
    )


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="datasets")
    items: Mapped[list[DatasetItem]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )
    runs: Mapped[list[EvaluationRun]] = relationship(back_populates="dataset")


class DatasetItem(TimestampMixin, Base):
    __tablename__ = "dataset_items"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "external_id", name="uq_dataset_items_external_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(200))
    input: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)

    dataset: Mapped[Dataset] = relationship(back_populates="items")
    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="dataset_item"
    )


class Variant(TimestampMixin, Base):
    __tablename__ = "variants"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_variants_project_name"),
        CheckConstraint("timeout_seconds > 0", name="positive_timeout"),
        CheckConstraint("max_retries >= 0", name="nonnegative_retries"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_credentials.id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    model: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(100), default="litellm")
    temperature: Mapped[float] = mapped_column(Float, default=0.0)
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=30.0)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)

    project: Mapped[Project] = relationship(back_populates="variants")
    credential: Mapped[ProviderCredential | None] = relationship(
        back_populates="variants"
    )
    runs: Mapped[list[EvaluationRun]] = relationship(
        secondary=evaluation_run_variants, back_populates="variants"
    )
    results: Mapped[list[EvaluationResult]] = relationship(back_populates="variant")


class EvaluationRun(TimestampMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="valid_status",
        ),
        CheckConstraint("concurrency > 0", name="positive_concurrency"),
        CheckConstraint("total_tasks >= 0", name="nonnegative_total_tasks"),
        CheckConstraint(
            "completed_tasks >= 0", name="nonnegative_completed_tasks"
        ),
        CheckConstraint(
            "completed_tasks <= total_tasks", name="valid_task_progress"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    concurrency: Mapped[int] = mapped_column(Integer, default=3)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship(back_populates="runs")
    dataset: Mapped[Dataset] = relationship(back_populates="runs")
    variants: Mapped[list[Variant]] = relationship(
        secondary=evaluation_run_variants, back_populates="runs"
    )
    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "dataset_item_id",
            "variant_id",
            name="uq_evaluation_results_run_item_variant",
        ),
        CheckConstraint("retry_count >= 0", name="nonnegative_retry_count"),
        Index(
            "ix_evaluation_results_run_dataset_item_variant",
            "run_id",
            "dataset_item_id",
            "variant_id",
            "id",
        ),
        Index(
            "ix_evaluation_results_run_variant",
            "run_id",
            "variant_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    dataset_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_items.id", ondelete="RESTRICT"), index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("variants.id", ondelete="RESTRICT"), index=True
    )

    model: Mapped[str] = mapped_column(String(300))
    provider: Mapped[str] = mapped_column(String(100))
    input: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    metrics: Mapped[dict[str, float] | None] = mapped_column(JSON)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
    dataset_item: Mapped[DatasetItem] = relationship(back_populates="results")
    variant: Mapped[Variant] = relationship(back_populates="results")
