"""Cascade delete ride-dependent analytics rows

Revision ID: 009
Revises: 008
Create Date: 2026-06-17

"""

from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "driver_ride_actions_ride_id_fkey", "driver_ride_actions", type_="foreignkey"
    )
    op.create_foreign_key(
        "driver_ride_actions_ride_id_fkey",
        "driver_ride_actions",
        "rides",
        ["ride_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("ride_ratings_ride_id_fkey", "ride_ratings", type_="foreignkey")
    op.create_foreign_key(
        "ride_ratings_ride_id_fkey",
        "ride_ratings",
        "rides",
        ["ride_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "driver_ride_actions_ride_id_fkey", "driver_ride_actions", type_="foreignkey"
    )
    op.create_foreign_key(
        "driver_ride_actions_ride_id_fkey",
        "driver_ride_actions",
        "rides",
        ["ride_id"],
        ["id"],
    )

    op.drop_constraint("ride_ratings_ride_id_fkey", "ride_ratings", type_="foreignkey")
    op.create_foreign_key(
        "ride_ratings_ride_id_fkey",
        "ride_ratings",
        "rides",
        ["ride_id"],
        ["id"],
    )
