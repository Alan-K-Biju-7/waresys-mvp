"""add uom & hsn to bill_lines

Revision ID: c4be9fd78357
Revises: dbbb2bd92015
Create Date: 2025-10-01 10:22:01.793753

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4be9fd78357'
down_revision: Union[str, Sequence[str], None] = 'dbbb2bd92015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
