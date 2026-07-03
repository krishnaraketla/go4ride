"""US localization: currency USD, US cities, mock driver phone

Revision ID: 010
Revises: 009
Create Date: 2026-06-26

"""

from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE fare_rules SET currency = 'USD' WHERE currency = 'INR'")
    op.execute("UPDATE wallets SET currency = 'USD' WHERE currency = 'INR'")


def downgrade() -> None:
    op.execute("UPDATE fare_rules SET currency = 'INR' WHERE currency = 'USD'")
    op.execute("UPDATE wallets SET currency = 'INR' WHERE currency = 'USD'")
