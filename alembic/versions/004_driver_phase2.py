"""Driver phase 2: extend driver_profiles + add driver_documents table

Revision ID: 004
Revises: 003
Create Date: 2026-05-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define enums with create_type=False so SQLAlchemy never auto-creates them
# inside create_table / add_column — we create them explicitly below.
driverstatus = postgresql.ENUM(
    "offline", "online", "on_ride", name="driverstatus", create_type=False
)
kycstatus = postgresql.ENUM(
    "pending", "submitted", "approved", "rejected", name="kycstatus", create_type=False
)
documenttype = postgresql.ENUM(
    "license", "registration", "insurance", "profile_photo",
    name="documenttype", create_type=False,
)
documentstatus = postgresql.ENUM(
    "pending", "approved", "rejected", name="documentstatus", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()

    # Create enum types (checkfirst=True is safe even if they already exist)
    postgresql.ENUM(
        "offline", "online", "on_ride", name="driverstatus"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "pending", "submitted", "approved", "rejected", name="kycstatus"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "license", "registration", "insurance", "profile_photo", name="documenttype"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "pending", "approved", "rejected", name="documentstatus"
    ).create(bind, checkfirst=True)

    # Extend driver_profiles with new columns
    op.add_column(
        "driver_profiles",
        sa.Column(
            "ride_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ride_types.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "driver_profiles",
        sa.Column("driver_status", driverstatus, nullable=False, server_default="offline"),
    )
    op.add_column(
        "driver_profiles",
        sa.Column("kyc_status", kycstatus, nullable=False, server_default="pending"),
    )
    op.add_column(
        "driver_profiles",
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
    )
    op.add_column(
        "driver_profiles",
        sa.Column("total_rides", sa.Integer(), nullable=False, server_default="0"),
    )

    # Create driver_documents table — use the create_type=False enums here
    op.create_table(
        "driver_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "driver_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("driver_profiles.user_id"),
            nullable=False,
        ),
        sa.Column("document_type", documenttype, nullable=False),
        sa.Column("file_key", sa.String(512), nullable=False),
        sa.Column("status", documentstatus, nullable=False, server_default="pending"),
        sa.Column("rejection_reason", sa.String(255), nullable=True),
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
    )
    op.create_index("ix_driver_documents_driver_user_id", "driver_documents", ["driver_user_id"])


def downgrade() -> None:
    op.drop_index("ix_driver_documents_driver_user_id", table_name="driver_documents")
    op.drop_table("driver_documents")

    op.drop_column("driver_profiles", "total_rides")
    op.drop_column("driver_profiles", "rating")
    op.drop_column("driver_profiles", "kyc_status")
    op.drop_column("driver_profiles", "driver_status")
    op.drop_column("driver_profiles", "ride_type_id")

    bind = op.get_bind()
    postgresql.ENUM(name="documentstatus").drop(bind, checkfirst=True)
    postgresql.ENUM(name="documenttype").drop(bind, checkfirst=True)
    postgresql.ENUM(name="kycstatus").drop(bind, checkfirst=True)
    postgresql.ENUM(name="driverstatus").drop(bind, checkfirst=True)
