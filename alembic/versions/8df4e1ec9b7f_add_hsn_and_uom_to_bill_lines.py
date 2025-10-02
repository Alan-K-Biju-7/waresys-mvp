"""add hsn and uom to bill_lines

Revision ID: 8df4e1ec9b7f
Revises: 091b034bb08c
Create Date: 2025-10-01 06:28:56.074345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8df4e1ec9b7f'
down_revision: Union[str, Sequence[str], None] = '091b034bb08c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
