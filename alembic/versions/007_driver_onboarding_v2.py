"""Driver onboarding v2: new status enum, cities, profile extensions

Revision ID: 007
Revises: 006
Create Date: 2026-06-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "cities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_cities_slug", "cities", ["slug"], unique=True)

    # Consolidate legacy onboarding values before renaming enum members.
    bind.execute(
        sa.text(
            "UPDATE driver_profiles SET onboarding_status = 'pending' "
            "WHERE onboarding_status = 'documents_uploaded'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE driver_profiles SET onboarding_status = 'pending' "
            "WHERE onboarding_status = 'pending'"
        )
    )

    bind.execute(sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'pending' TO 'step1'"))
    bind.execute(
        sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'vehicle_submitted' TO 'step2'")
    )
    bind.execute(
        sa.text(
            "ALTER TYPE onboardingstatus RENAME VALUE 'under_review' TO 'application_submitted'"
        )
    )
    bind.execute(
        sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'approved' TO 'kyc_approved'")
    )
    bind.execute(
        sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'rejected' TO 'kyc_rejected'")
    )

    op.alter_column("driver_profiles", "vehicle_model", existing_type=sa.String(64), nullable=True)
    op.alter_column("driver_profiles", "vehicle_plate", existing_type=sa.String(32), nullable=True)
    op.alter_column("driver_profiles", "vehicle_color", existing_type=sa.String(32), nullable=True)

    op.alter_column(
        "driver_profiles",
        "onboarding_status",
        server_default="step1",
    )

    op.add_column("driver_profiles", sa.Column("application_id", sa.String(64), nullable=True))
    op.add_column(
        "driver_profiles",
        sa.Column("city_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cities.id"), nullable=True),
    )
    op.add_column(
        "driver_profiles", sa.Column("vehicle_photo_front_key", sa.String(512), nullable=True)
    )
    op.add_column(
        "driver_profiles", sa.Column("vehicle_photo_back_key", sa.String(512), nullable=True)
    )
    op.add_column(
        "driver_profiles", sa.Column("vehicle_photo_left_key", sa.String(512), nullable=True)
    )
    op.add_column(
        "driver_profiles", sa.Column("vehicle_photo_right_key", sa.String(512), nullable=True)
    )
    op.add_column(
        "driver_profiles", sa.Column("face_verification_file_key", sa.String(512), nullable=True)
    )
    op.add_column(
        "driver_profiles",
        sa.Column("face_verification_completed", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "driver_profiles", sa.Column("kyc_rejection_reason", sa.String(255), nullable=True)
    )
    op.add_column(
        "driver_profiles",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_column("driver_profiles", "submitted_at")
    op.drop_column("driver_profiles", "kyc_rejection_reason")
    op.drop_column("driver_profiles", "face_verification_completed")
    op.drop_column("driver_profiles", "face_verification_file_key")
    op.drop_column("driver_profiles", "vehicle_photo_right_key")
    op.drop_column("driver_profiles", "vehicle_photo_left_key")
    op.drop_column("driver_profiles", "vehicle_photo_back_key")
    op.drop_column("driver_profiles", "vehicle_photo_front_key")
    op.drop_column("driver_profiles", "city_id")
    op.drop_column("driver_profiles", "application_id")

    op.alter_column("driver_profiles", "vehicle_color", existing_type=sa.String(32), nullable=False)
    op.alter_column("driver_profiles", "vehicle_plate", existing_type=sa.String(32), nullable=False)
    op.alter_column("driver_profiles", "vehicle_model", existing_type=sa.String(64), nullable=False)

    bind.execute(
        sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'kyc_rejected' TO 'rejected'")
    )
    bind.execute(
        sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'kyc_approved' TO 'approved'")
    )
    bind.execute(
        sa.text(
            "ALTER TYPE onboardingstatus RENAME VALUE 'application_submitted' TO 'under_review'"
        )
    )
    bind.execute(sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'step2' TO 'vehicle_submitted'"))
    bind.execute(sa.text("ALTER TYPE onboardingstatus RENAME VALUE 'step1' TO 'pending'"))

    op.alter_column(
        "driver_profiles",
        "onboarding_status",
        server_default="pending",
    )

    op.drop_index("ix_cities_slug", table_name="cities")
    op.drop_table("cities")
