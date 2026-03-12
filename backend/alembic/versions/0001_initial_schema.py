"""Initial schema for CryptoTrader.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-01-30 00:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depend_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("mfa_secret", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("session_timeout_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("preferences_json", sa.JSON(), nullable=True),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "strategies",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'paper'")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("github_url", sa.String(length=500), nullable=True),
        sa.Column("ai_modifications_json", sa.JSON(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(), nullable=True),
        sa.Column("promoted_by_recommendation", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "strategy_performance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("winning_trades", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("losing_trades", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("win_rate", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("total_pnl", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("max_drawdown", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("sharpe_ratio", sa.Float(), nullable=True),
        sa.Column("ai_model_used", sa.String(length=100), nullable=True),
    )

    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=True),
        sa.Column("ai_model_used", sa.String(length=100), nullable=True),
        sa.Column("is_paper", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_manual", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("fees", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("entry_time", sa.DateTime(), nullable=True),
        sa.Column("exit_time", sa.DateTime(), nullable=True),
        sa.Column("entry_reasoning_json", sa.JSON(), nullable=True),
        sa.Column("exit_reasoning_json", sa.JSON(), nullable=True),
        sa.Column("market_conditions_json", sa.JSON(), nullable=True),
        sa.Column("indicators_json", sa.JSON(), nullable=True),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=True),
        sa.Column("exchange_order_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("order_type", sa.String(length=50), nullable=False),
        sa.Column("side", sa.String(length=10), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("filled_quantity", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "ai_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("agent_name", sa.String(length=100), nullable=False),
        sa.Column("decision_type", sa.String(length=100), nullable=False),
        sa.Column("reasoning_json", sa.JSON(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("action_taken", sa.String(length=255), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("related_strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=True),
        sa.Column("related_trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=True),
        sa.Column("near_miss", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("near_miss_reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=50), nullable=False, server_default=sa.text("'info'")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default=sa.text("'new'")),
        sa.Column("related_strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=True),
        sa.Column("related_trade_id", sa.Integer(), sa.ForeignKey("trades.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("actioned_at", sa.DateTime(), nullable=True),
        sa.Column("action_taken", sa.String(length=255), nullable=True),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
    )

    op.create_table(
        "chat_history",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("ai_response", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("related_alert_id", sa.Integer(), sa.ForeignKey("alerts.id"), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("learned_preferences_json", sa.JSON(), nullable=True),
    )

    op.create_table(
        "market_data",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default=sa.text("'kraken'")),
        sa.Column("timeframe", sa.String(length=20), nullable=False, server_default=sa.text("'1m'")),
    )

    op.create_index(op.f("ix_market_data_symbol"), "market_data", ["symbol"], unique=False)
    op.create_index(op.f("ix_market_data_timestamp"), "market_data", ["timestamp"], unique=False)

    op.create_table(
        "sentiment_data",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("raw_data_json", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "risk_settings",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("max_position_size_pct", sa.Float(), nullable=False, server_default=sa.text("5.0")),
        sa.Column("max_concurrent_positions", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("daily_loss_limit", sa.Float(), nullable=False, server_default=sa.text("500.0")),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=False, server_default=sa.text("10.0")),
        sa.Column("max_risk_score", sa.Float(), nullable=False, server_default=sa.text("80.0")),
        sa.Column("current_risk_score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_ai_recommendation_json", sa.JSON(), nullable=True),
        sa.Column("pending_ai_adjustment", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

    op.create_table(
        "model_performance",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("strategy_id", sa.Integer(), sa.ForeignKey("strategies.id"), nullable=True),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("total_decisions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("correct_decisions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("total_pnl", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("avg_confidence", sa.Float(), nullable=True),
    )

    op.create_table(
        "data_source_config",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("api_key_encrypted", sa.String(length=500), nullable=True),
        sa.Column("last_fetch", sa.DateTime(), nullable=True),
        sa.Column("fetch_interval_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("config_json", sa.JSON(), nullable=True),
    )

    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_market_data_timestamp"), table_name="market_data")
    op.drop_index(op.f("ix_market_data_symbol"), table_name="market_data")
    op.drop_table("system_logs")
    op.drop_table("data_source_config")
    op.drop_table("model_performance")
    op.drop_table("risk_settings")
    op.drop_table("sentiment_data")
    op.drop_table("market_data")
    op.drop_table("chat_history")
    op.drop_table("alerts")
    op.drop_table("ai_decisions")
    op.drop_table("orders")
    op.drop_table("trades")
    op.drop_table("strategy_performance")
    op.drop_table("strategies")
    op.drop_table("sessions")
    op.drop_table("users")
