"""Initial schema (Phase 0 + Phase 1 — rider only)

Revision ID: 001
Revises:
Create Date: 2026-05-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE userrole AS ENUM ('rider')")
    op.execute("CREATE TYPE otppurpose AS ENUM ('login', 'register')")
    op.execute(
        "CREATE TYPE ridestatus AS ENUM ('requested', 'searching_driver', 'driver_assigned', 'driver_arrived', 'in_progress', 'completed', 'cancelled')"
    )

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("role", sa.Enum("rider", name="userrole", create_type=False), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone"),
    )
    op.create_index("ix_users_phone", "users", ["phone"])

    op.create_table(
        "otp_verifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("purpose", sa.Enum("login", "register", name="otppurpose", create_type=False), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_otp_verifications_phone", "otp_verifications", ["phone"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_table(
        "user_devices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("fcm_token", sa.String(512), nullable=False),
        sa.Column("platform", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ride_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon_url", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "fare_rules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ride_type_id", sa.UUID(), nullable=False),
        sa.Column("base_fare", sa.Numeric(10, 2), nullable=False),
        sa.Column("per_km_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("per_min_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("minimum_fare", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.ForeignKeyConstraint(["ride_type_id"], ["ride_types.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "rides",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("rider_id", sa.UUID(), nullable=False),
        sa.Column("driver_id", sa.UUID(), nullable=True),
        sa.Column("ride_type_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "requested",
                "searching_driver",
                "driver_assigned",
                "driver_arrived",
                "in_progress",
                "completed",
                "cancelled",
                name="ridestatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("pickup_lat", sa.Numeric(10, 7), nullable=False),
        sa.Column("pickup_lng", sa.Numeric(10, 7), nullable=False),
        sa.Column("pickup_address", sa.Text(), nullable=False),
        sa.Column("drop_lat", sa.Numeric(10, 7), nullable=False),
        sa.Column("drop_lng", sa.Numeric(10, 7), nullable=False),
        sa.Column("drop_address", sa.Text(), nullable=False),
        sa.Column("distance_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("duration_min", sa.Numeric(10, 2), nullable=True),
        sa.Column("estimated_fare", sa.Numeric(10, 2), nullable=False),
        sa.Column("final_fare", sa.Numeric(10, 2), nullable=True),
        sa.Column("surge_multiplier", sa.Numeric(4, 2), server_default="1.00"),
        sa.Column("start_otp", sa.String(6), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("driver_assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("driver_arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["rider_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["driver_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ride_type_id"], ["ride_types.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rides_rider_id", "rides", ["rider_id"])
    op.create_index("ix_rides_status", "rides", ["status"])

    op.create_table(
        "ride_status_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("ride_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "requested",
                "searching_driver",
                "driver_assigned",
                "driver_arrived",
                "in_progress",
                "completed",
                "cancelled",
                name="ridestatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("message", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["ride_id"], ["rides.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ride_status_events")
    op.drop_table("rides")
    op.drop_table("fare_rules")
    op.drop_table("ride_types")
    op.drop_table("user_devices")
    op.drop_table("refresh_tokens")
    op.drop_table("otp_verifications")
    op.drop_table("users")
    op.execute("DROP TYPE ridestatus")
    op.execute("DROP TYPE otppurpose")
    op.execute("DROP TYPE userrole")
