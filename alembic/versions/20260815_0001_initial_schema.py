"""Create the initial evaluation schema.

Revision ID: 20260815_0001
Revises:
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("name", name=op.f("uq_projects_name")),
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_datasets_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint("project_id", "name", name="uq_datasets_project_name"),
    )
    op.create_index(op.f("ix_datasets_project_id"), "datasets", ["project_id"])
    op.create_table(
        "dataset_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], name=op.f("fk_dataset_items_dataset_id_datasets"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_items")),
        sa.UniqueConstraint("dataset_id", "external_id", name="uq_dataset_items_external_id"),
    )
    op.create_index(op.f("ix_dataset_items_dataset_id"), "dataset_items", ["dataset_id"])
    op.create_table(
        "variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("model", sa.String(length=300), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("max_retries >= 0", name=op.f("ck_variants_nonnegative_retries")),
        sa.CheckConstraint("timeout_seconds > 0", name=op.f("ck_variants_positive_timeout")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_variants_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variants")),
        sa.UniqueConstraint("project_id", "name", name="uq_variants_project_name"),
    )
    op.create_index(op.f("ix_variants_project_id"), "variants", ["project_id"])
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("concurrency > 0", name=op.f("ck_evaluation_runs_positive_concurrency")),
        sa.CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'cancelled')", name=op.f("ck_evaluation_runs_valid_status")),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], name=op.f("fk_evaluation_runs_dataset_id_datasets"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_evaluation_runs_project_id_projects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_runs")),
    )
    op.create_index(op.f("ix_evaluation_runs_dataset_id"), "evaluation_runs", ["dataset_id"])
    op.create_index(op.f("ix_evaluation_runs_project_id"), "evaluation_runs", ["project_id"])
    op.create_index(op.f("ix_evaluation_runs_status"), "evaluation_runs", ["status"])
    op.create_table(
        "evaluation_run_variants",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], name=op.f("fk_evaluation_run_variants_run_id_evaluation_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], name=op.f("fk_evaluation_run_variants_variant_id_variants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id", "variant_id", name=op.f("pk_evaluation_run_variants")),
    )
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_item_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=300), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("retry_count >= 0", name=op.f("ck_evaluation_results_nonnegative_retry_count")),
        sa.ForeignKeyConstraint(["dataset_item_id"], ["dataset_items.id"], name=op.f("fk_evaluation_results_dataset_item_id_dataset_items"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], name=op.f("fk_evaluation_results_run_id_evaluation_runs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["variant_id"], ["variants.id"], name=op.f("fk_evaluation_results_variant_id_variants"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_results")),
        sa.UniqueConstraint("run_id", "dataset_item_id", "variant_id", name="uq_evaluation_results_run_item_variant"),
    )
    op.create_index(op.f("ix_evaluation_results_dataset_item_id"), "evaluation_results", ["dataset_item_id"])
    op.create_index(op.f("ix_evaluation_results_run_id"), "evaluation_results", ["run_id"])
    op.create_index(op.f("ix_evaluation_results_variant_id"), "evaluation_results", ["variant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_results_variant_id"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_run_id"), table_name="evaluation_results")
    op.drop_index(op.f("ix_evaluation_results_dataset_item_id"), table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_run_variants")
    op.drop_index(op.f("ix_evaluation_runs_status"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_project_id"), table_name="evaluation_runs")
    op.drop_index(op.f("ix_evaluation_runs_dataset_id"), table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
    op.drop_index(op.f("ix_variants_project_id"), table_name="variants")
    op.drop_table("variants")
    op.drop_index(op.f("ix_dataset_items_dataset_id"), table_name="dataset_items")
    op.drop_table("dataset_items")
    op.drop_index(op.f("ix_datasets_project_id"), table_name="datasets")
    op.drop_table("datasets")
    op.drop_table("projects")
