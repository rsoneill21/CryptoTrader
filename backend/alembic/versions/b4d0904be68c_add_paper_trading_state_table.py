"""add_paper_trading_state_table"""
revision = 'b4d0904be68c'
down_revision = '150f429d1db6'
branch_labels = None
depend_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Apply upgrade migrations."""
    # Create paper_trading_states table with indexes
    op.create_table('paper_trading_states',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.String(length=100), nullable=False),
    sa.Column('state_json', sa.JSON(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_paper_trading_states_id'), 'paper_trading_states', ['id'], unique=False)
    op.create_index(op.f('ix_paper_trading_states_is_active'), 'paper_trading_states', ['is_active'], unique=False)
    op.create_index(op.f('ix_paper_trading_states_session_id'), 'paper_trading_states', ['session_id'], unique=True)


def downgrade() -> None:
    """Reverse upgrade migrations."""
    # Drop paper_trading_states table and indexes
    op.drop_index(op.f('ix_paper_trading_states_session_id'), table_name='paper_trading_states')
    op.drop_index(op.f('ix_paper_trading_states_is_active'), table_name='paper_trading_states')
    op.drop_index(op.f('ix_paper_trading_states_id'), table_name='paper_trading_states')
    op.drop_table('paper_trading_states')
