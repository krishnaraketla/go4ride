"""Add route_polyline to rides for live map display."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rides", sa.Column("route_polyline", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rides", "route_polyline")
