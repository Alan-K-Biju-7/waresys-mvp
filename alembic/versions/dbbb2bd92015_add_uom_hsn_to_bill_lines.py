"""add uom & hsn to bill_lines"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'dbbb2bd92015'
down_revision = '8df4e1ec9b7f'  # <-- keep your actual previous migration ID
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('bill_lines', sa.Column('uom', sa.String(32), nullable=True))
    op.add_column('bill_lines', sa.Column('hsn', sa.String(32), nullable=True))

def downgrade() -> None:
    op.drop_column('bill_lines', 'hsn')
    op.drop_column('bill_lines', 'uom')

