"""Add indexes for paginated evaluation results.

Revision ID: 20260830_0007
Revises: 20260825_0006
Create Date: 2026-08-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260830_0007"
down_revision: str | None = "20260825_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_evaluation_results_run_dataset_item_variant",
        "evaluation_results",
        ["run_id", "dataset_item_id", "variant_id", "id"],
    )
    op.create_index(
        "ix_evaluation_results_run_variant",
        "evaluation_results",
        ["run_id", "variant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_results_run_variant",
        table_name="evaluation_results",
    )
    op.drop_index(
        "ix_evaluation_results_run_dataset_item_variant",
        table_name="evaluation_results",
    )
