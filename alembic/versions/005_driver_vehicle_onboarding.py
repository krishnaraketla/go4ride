"""Driver vehicle details and onboarding status fields

Revision ID: 005
Revises: 004
Create Date: 2026-06-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

vehicletype = postgresql.ENUM("auto", "taxi", "cab", name="vehicletype", create_type=False)
onboardingstatus = postgresql.ENUM(
    "pending", "documents_uploaded", "vehicle_submitted", "under_review", "approved", "rejected",
    name="onboardingstatus", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM("auto", "taxi", "cab", name="vehicletype").create(bind, checkfirst=True)
    postgresql.ENUM(
        "pending", "documents_uploaded", "vehicle_submitted", "under_review", "approved", "rejected",
        name="onboardingstatus",
    ).create(bind, checkfirst=True)

    # Add not_uploaded value to existing documentstatus enum
    bind.execute(sa.text("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'not_uploaded'"))

    op.add_column(
        "driver_profiles",
        sa.Column("vehicle_type", vehicletype, nullable=True),
    )
    op.add_column(
        "driver_profiles",
        sa.Column("vehicle_make", sa.String(64), nullable=True),
    )
    op.add_column(
        "driver_profiles",
        sa.Column("vehicle_year", sa.Integer(), nullable=True),
    )
    op.add_column(
        "driver_profiles",
        sa.Column(
            "onboarding_status",
            onboardingstatus,
            nullable=False,
            server_default="pending",
        ),
    )


def downgrade() -> None:
    op.drop_column("driver_profiles", "onboarding_status")
    op.drop_column("driver_profiles", "vehicle_year")
    op.drop_column("driver_profiles", "vehicle_make")
    op.drop_column("driver_profiles", "vehicle_type")

    bind = op.get_bind()
    postgresql.ENUM(name="onboardingstatus").drop(bind, checkfirst=True)
    postgresql.ENUM(name="vehicletype").drop(bind, checkfirst=True)
