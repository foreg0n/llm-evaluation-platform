"""Add users, authentication storage, and project ownership.

Revision ID: 20260815_0003
Revises: 20260815_0002
Create Date: 2026-08-15
"""

import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260815_0003"
down_revision: str | None = "20260815_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"])

    users = sa.table(
        "users",
        sa.column("id", sa.Uuid()),
        sa.column("email", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        users,
        [
            {
                "id": LEGACY_USER_ID,
                "email": "legacy-import@local.invalid",
                "password_hash": "!",
                "is_active": False,
            }
        ],
    )

    op.add_column("projects", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.update(sa.table("projects", sa.column("owner_id", sa.Uuid())))
        .values(owner_id=LEGACY_USER_ID)
    )
    op.alter_column("projects", "owner_id", nullable=False)
    op.drop_constraint(op.f("uq_projects_name"), "projects", type_="unique")
    op.create_foreign_key(
        op.f("fk_projects_owner_id_users"),
        "projects",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"])
    op.create_unique_constraint(
        "uq_projects_owner_name",
        "projects",
        ["owner_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_projects_owner_name", "projects", type_="unique")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_constraint(
        op.f("fk_projects_owner_id_users"),
        "projects",
        type_="foreignkey",
    )
    op.drop_column("projects", "owner_id")
    op.create_unique_constraint(
        op.f("uq_projects_name"),
        "projects",
        ["name"],
    )
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
