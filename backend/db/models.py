"""
SQLAlchemy database models for CryptoTrader.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(255), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime, nullable=True)
    session_timeout_minutes = Column(Integer, default=60)
    preferences_json = Column(JSON, default=dict)

    sessions = relationship("Session", back_populates="user")


class Session(Base):
    """User session model."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="sessions")


class Strategy(Base):
    """Trading strategy model."""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    rules_json = Column(JSON, nullable=False)
    source = Column(String(50), default="manual")  # ai_generated, github, manual
    status = Column(String(50), default="paper")  # paper, live, paused, archived
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    github_url = Column(String(500), nullable=True)
    ai_modifications_json = Column(JSON, nullable=True)
    promoted_at = Column(DateTime, nullable=True)
    promoted_by_recommendation = Column(Boolean, default=False)

    performance = relationship("StrategyPerformance", back_populates="strategy")
    trades = relationship("Trade", back_populates="strategy")


class StrategyPerformance(Base):
    """Strategy performance metrics."""
    __tablename__ = "strategy_performance"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, nullable=True)
    ai_model_used = Column(String(100), nullable=True)

    strategy = relationship("Strategy", back_populates="performance")


class Trade(Base):
    """Trade record model."""
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    ai_model_used = Column(String(100), nullable=True)
    is_paper = Column(Boolean, default=True)
    is_manual = Column(Boolean, default=False)
    symbol = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)  # buy, sell
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    fees = Column(Float, default=0.0)
    entry_time = Column(DateTime, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    entry_reasoning_json = Column(JSON, nullable=True)
    exit_reasoning_json = Column(JSON, nullable=True)
    market_conditions_json = Column(JSON, nullable=True)
    indicators_json = Column(JSON, nullable=True)

    strategy = relationship("Strategy", back_populates="trades")
    orders = relationship("Order", back_populates="trade")


class Order(Base):
    """Exchange order model."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    exchange_order_id = Column(String(100), nullable=True)
    status = Column(String(50), default="pending")
    order_type = Column(String(50), nullable=False)  # market, limit, stop
    side = Column(String(10), nullable=False)
    price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    filled_quantity = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    error_message = Column(Text, nullable=True)

    trade = relationship("Trade", back_populates="orders")


class AIDecision(Base):
    """AI decision logging model."""
    __tablename__ = "ai_decisions"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(100), nullable=False)
    decision_type = Column(String(100), nullable=False)
    reasoning_json = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)
    action_taken = Column(String(255), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())
    related_strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    related_trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    near_miss = Column(Boolean, default=False)
    near_miss_reason = Column(Text, nullable=True)


class Alert(Base):
    """Alert/notification model."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    severity = Column(String(50), default="info")  # info, warning, critical
    status = Column(String(50), default="new")  # new, viewed, dismissed, actioned
    related_strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    related_trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    actioned_at = Column(DateTime, nullable=True)
    action_taken = Column(String(255), nullable=True)
    ai_confidence = Column(Float, nullable=True)


class ChatHistory(Base):
    """Chat conversation history."""
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    timestamp = Column(DateTime, server_default=func.now())
    related_alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    context_json = Column(JSON, nullable=True)
    learned_preferences_json = Column(JSON, nullable=True)


class MarketData(Base):
    """Market price data storage."""
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    source = Column(String(50), default="kraken")
    timeframe = Column(String(20), default="1m")


class SentimentData(Base):
    """Social/news sentiment data."""
    __tablename__ = "sentiment_data"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(50), nullable=False)  # twitter, reddit, news, onchain
    symbol = Column(String(50), nullable=True)
    sentiment_score = Column(Float, nullable=True)
    summary = Column(Text, nullable=True)
    raw_data_json = Column(JSON, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())


class RiskSettings(Base):
    """Risk management settings."""
    __tablename__ = "risk_settings"

    id = Column(Integer, primary_key=True, index=True)
    max_position_size_pct = Column(Float, default=5.0)
    max_concurrent_positions = Column(Integer, default=3)
    daily_loss_limit = Column(Float, default=500.0)
    max_drawdown_pct = Column(Float, default=10.0)
    max_risk_score = Column(Float, default=80.0)
    current_risk_score = Column(Float, default=0.0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    last_ai_recommendation_json = Column(JSON, nullable=True)
    pending_ai_adjustment = Column(Boolean, default=False)


class ModelPerformance(Base):
    """AI model performance tracking."""
    __tablename__ = "model_performance"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(100), nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    total_decisions = Column(Integer, default=0)
    correct_decisions = Column(Integer, default=0)
    accuracy = Column(Float, nullable=True)
    total_pnl = Column(Float, default=0.0)
    win_rate = Column(Float, nullable=True)
    avg_confidence = Column(Float, nullable=True)


class DataSourceConfig(Base):
    """Data source configuration."""
    __tablename__ = "data_source_config"

    id = Column(Integer, primary_key=True, index=True)
    source_name = Column(String(100), nullable=False, unique=True)
    enabled = Column(Boolean, default=True)
    api_key_encrypted = Column(String(500), nullable=True)
    last_fetch = Column(DateTime, nullable=True)
    fetch_interval_seconds = Column(Integer, default=60)
    config_json = Column(JSON, nullable=True)


class SystemLog(Base):
    """System logging."""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(String(20), nullable=False)  # debug, info, warning, error, critical
    source = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    details_json = Column(JSON, nullable=True)
    timestamp = Column(DateTime, server_default=func.now())
