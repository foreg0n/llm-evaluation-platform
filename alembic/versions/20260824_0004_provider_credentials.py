"""Add encrypted provider credentials and attach them to variants.

Revision ID: 20260824_0004
Revises: 20260815_0003
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260824_0004"
down_revision: str | None = "20260815_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("key_hint", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('untested', 'connected', 'invalid')",
            name=op.f("ck_provider_credentials_valid_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_provider_credentials_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_credentials")),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            "name",
            name="uq_provider_credentials_user_provider_name",
        ),
    )
    op.create_index(
        op.f("ix_provider_credentials_provider"),
        "provider_credentials",
        ["provider"],
    )
    op.create_index(
        op.f("ix_provider_credentials_user_id"),
        "provider_credentials",
        ["user_id"],
    )

    op.add_column("variants", sa.Column("credential_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_variants_credential_id_provider_credentials"),
        "variants",
        "provider_credentials",
        ["credential_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_variants_credential_id"),
        "variants",
        ["credential_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_variants_credential_id"), table_name="variants")
    op.drop_constraint(
        op.f("fk_variants_credential_id_provider_credentials"),
        "variants",
        type_="foreignkey",
    )
    op.drop_column("variants", "credential_id")
    op.drop_index(
        op.f("ix_provider_credentials_user_id"),
        table_name="provider_credentials",
    )
    op.drop_index(
        op.f("ix_provider_credentials_provider"),
        table_name="provider_credentials",
    )
    op.drop_table("provider_credentials")
