"""add volatility to performance snapshots"""
revision = 'f10fbf4942d1'
down_revision = 'a1634ee503fa'
branch_labels = None
depend_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Apply upgrade migrations."""
    op.add_column('performance_snapshots', sa.Column('volatility', sa.Float(), nullable=True))


def downgrade() -> None:
    """Reverse upgrade migrations."""
    op.drop_column('performance_snapshots', 'volatility')
