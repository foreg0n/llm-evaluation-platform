"""Add email verification and account recovery tokens.

Revision ID: 20260825_0006
Revises: 20260824_0005
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260825_0006"
down_revision: str | None = "20260824_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing accounts predate verification and must keep working after upgrade.
    op.execute(sa.text("UPDATE users SET email_verified_at = CURRENT_TIMESTAMP"))
    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')",
            name=op.f("ck_account_action_tokens_valid_purpose"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_account_action_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_action_tokens")),
    )
    op.create_index(
        op.f("ix_account_action_tokens_expires_at"),
        "account_action_tokens",
        ["expires_at"],
    )
    op.create_index(
        op.f("ix_account_action_tokens_purpose"),
        "account_action_tokens",
        ["purpose"],
    )
    op.create_index(
        op.f("ix_account_action_tokens_token_hash"),
        "account_action_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_account_action_tokens_user_id"),
        "account_action_tokens",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_account_action_tokens_user_id"),
        table_name="account_action_tokens",
    )
    op.drop_index(
        op.f("ix_account_action_tokens_token_hash"),
        table_name="account_action_tokens",
    )
    op.drop_index(
        op.f("ix_account_action_tokens_purpose"),
        table_name="account_action_tokens",
    )
    op.drop_index(
        op.f("ix_account_action_tokens_expires_at"),
        table_name="account_action_tokens",
    )
    op.drop_table("account_action_tokens")
    op.drop_column("users", "email_verified_at")
