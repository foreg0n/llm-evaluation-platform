"""Add progress counters to evaluation runs.

Revision ID: 20260815_0002
Revises: 20260815_0001
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0002"
down_revision: str | None = "20260815_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "total_tasks", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "evaluation_runs",
        sa.Column(
            "completed_tasks", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_evaluation_runs_nonnegative_total_tasks"),
        "evaluation_runs",
        "total_tasks >= 0",
    )
    op.create_check_constraint(
        op.f("ck_evaluation_runs_nonnegative_completed_tasks"),
        "evaluation_runs",
        "completed_tasks >= 0",
    )
    op.create_check_constraint(
        op.f("ck_evaluation_runs_valid_task_progress"),
        "evaluation_runs",
        "completed_tasks <= total_tasks",
    )
    op.alter_column("evaluation_runs", "total_tasks", server_default=None)
    op.alter_column("evaluation_runs", "completed_tasks", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_evaluation_runs_valid_task_progress"),
        "evaluation_runs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_evaluation_runs_nonnegative_completed_tasks"),
        "evaluation_runs",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_evaluation_runs_nonnegative_total_tasks"),
        "evaluation_runs",
        type_="check",
    )
    op.drop_column("evaluation_runs", "completed_tasks")
    op.drop_column("evaluation_runs", "total_tasks")
