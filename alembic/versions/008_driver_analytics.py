"""Driver analytics: ratings, online sessions, ride actions

Revision ID: 008
Revises: 007
Create Date: 2026-06-17

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

rater_role = postgresql.ENUM("rider", "driver", name="raterrole", create_type=False)
driver_ride_action_type = postgresql.ENUM(
    "accepted", "rejected", name="driverrideactiontype", create_type=False
)


def upgrade() -> None:
    rater_role.create(op.get_bind(), checkfirst=True)
    driver_ride_action_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "ride_ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ride_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rides.id"), nullable=False),
        sa.Column("rater_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ratee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rater_role", rater_role, nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("ride_id", "rater_role", name="uq_ride_ratings_ride_role"),
    )
    op.create_index("ix_ride_ratings_ride_id", "ride_ratings", ["ride_id"])

    op.create_table(
        "driver_online_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_driver_online_sessions_driver_id", "driver_online_sessions", ["driver_id"])

    op.create_table(
        "driver_ride_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ride_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rides.id"), nullable=False),
        sa.Column("action", driver_ride_action_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_driver_ride_actions_driver_id", "driver_ride_actions", ["driver_id"])
    op.create_index("ix_driver_ride_actions_ride_id", "driver_ride_actions", ["ride_id"])


def downgrade() -> None:
    op.drop_index("ix_driver_ride_actions_ride_id", table_name="driver_ride_actions")
    op.drop_index("ix_driver_ride_actions_driver_id", table_name="driver_ride_actions")
    op.drop_table("driver_ride_actions")

    op.drop_index("ix_driver_online_sessions_driver_id", table_name="driver_online_sessions")
    op.drop_table("driver_online_sessions")

    op.drop_index("ix_ride_ratings_ride_id", table_name="ride_ratings")
    op.drop_table("ride_ratings")

    driver_ride_action_type.drop(op.get_bind(), checkfirst=True)
    rater_role.drop(op.get_bind(), checkfirst=True)
