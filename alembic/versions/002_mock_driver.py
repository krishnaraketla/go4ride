"""Mock driver profile (Phase 1.5)

Revision ID: 002
Revises: 001
Create Date: 2026-05-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'driver'"))
    op.create_table(
        "driver_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_model", sa.String(64), nullable=False),
        sa.Column("vehicle_plate", sa.String(32), nullable=False),
        sa.Column("vehicle_color", sa.String(32), nullable=False),
        sa.Column("current_lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("current_lng", sa.Numeric(10, 7), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("driver_profiles")
