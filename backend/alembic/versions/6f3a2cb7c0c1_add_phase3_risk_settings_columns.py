"""Add Phase 3 risk settings columns.

Revision ID: 6f3a2cb7c0c1
Revises: b4d0904be68c
Create Date: 2026-02-06 15:55:00
"""

from alembic import op
import sqlalchemy as sa


revision = "6f3a2cb7c0c1"
down_revision = "b4d0904be68c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_settings",
        sa.Column("max_asset_exposure", sa.Float(), nullable=False, server_default=sa.text("10000.0")),
    )
    op.add_column(
        "risk_settings",
        sa.Column("max_trades_per_hour", sa.Integer(), nullable=False, server_default=sa.text("10")),
    )
    op.add_column(
        "risk_settings",
        sa.Column("max_trades_per_day", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )
    op.add_column(
        "risk_settings",
        sa.Column("min_liquidity_threshold", sa.Float(), nullable=False, server_default=sa.text("1000.0")),
    )
    op.add_column(
        "risk_settings",
        sa.Column("kraken_tier", sa.String(length=50), nullable=False, server_default=sa.text("'starter'")),
    )
    op.add_column(
        "risk_settings",
        sa.Column("default_stop_loss_pct", sa.Float(), nullable=False, server_default=sa.text("2.0")),
    )


def downgrade() -> None:
    op.drop_column("risk_settings", "default_stop_loss_pct")
    op.drop_column("risk_settings", "kraken_tier")
    op.drop_column("risk_settings", "min_liquidity_threshold")
    op.drop_column("risk_settings", "max_trades_per_day")
    op.drop_column("risk_settings", "max_trades_per_hour")
    op.drop_column("risk_settings", "max_asset_exposure")
