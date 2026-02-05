"""Strategy management endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth import get_current_user
from db.database import get_async_db
from db.models import Strategy, StrategyPerformance, User, AIDecision
from services.github_import import GitHubImportService
from services.paper_trading_service import paper_trading_engine
from core.paper_trading import PaperTradeSignal, PaperPortfolioSnapshot
from api.market import (
    AnalystIndicatorSnapshot,
    TechnicalSnapshot,
    _build_indicator_snapshot,
    _build_recommendations,
    _build_technical_snapshot,
    _normalize_trading_pair,
)
from agents.market_analyst import market_analyst_agent
from agents.sentiment_agent import SentimentSummary, sentiment_agent
from services.market_data import market_data_service
from services.strategy_ai import StrategyProposal, StrategyProposalInput, strategy_ai_service
from services.risk_ai import RiskAIService, RiskContext, RiskRecommendation

logger = logging.getLogger("cryptotrader.strategies")
router = APIRouter()
_FIELD_MISSING = object()

COMPARISON_DEFAULT_STATUSES = ["live", "paper"]

github_import_service = GitHubImportService()

STATUS_HINT = "paper, live, paused, archived"


class GitHubImportRequest(BaseModel):
    """Payload for importing strategies from a GitHub URL."""
    github_url: str = Field(..., description="URL to a GitHub repository or file")


class GitHubImportResponse(BaseModel):
    """Summary of the import operation."""
    imported_count: int
    failed_count: int
    branch: Optional[str]
    message: str


class StrategyCreate(BaseModel):
    """Payload accepted when the UI creates a new strategy."""

    name: str = Field(..., description="Human readable strategy name")
    description: Optional[str] = Field(None, max_length=1024)
    rules: Dict[str, Any] = Field(..., description="Rule definition stored as JSON")
    source: Optional[str] = Field(None, description="Origin of the strategy")
    status: Optional[str] = Field(None, description="Deployment status")
    github_url: Optional[str] = Field(None, description="Associated GitHub reference")
    ai_modifications: Optional[Dict[str, Any]] = Field(
        None,
        description="Ai adjustments applied to the base definition",
        alias="ai_modifications",
    )
    promoted_at: Optional[datetime] = Field(None, description="Timestamp when strategy was promoted")
    promoted_by_recommendation: bool = Field(
        False,
        description="Whether the promotion was driven by the recommendation engine",
    )

    class Config:
        # Pydantic v2 migration: renamed from allow_population_by_field_name
        populate_by_name = True


class StrategyUpdate(BaseModel):
    """Fields that may be updated for an existing strategy."""

    name: Optional[str] = Field(None, description="Human readable strategy name")
    description: Optional[str] = Field(None, max_length=1024)
    rules: Optional[Dict[str, Any]] = Field(None, description="Rule definition stored as JSON")
    source: Optional[str] = Field(None, description="Origin of the strategy")
    status: Optional[str] = Field(None, description="Deployment status")
    github_url: Optional[str] = Field(None, description="Associated GitHub reference")
    ai_modifications: Optional[Dict[str, Any]] = Field(
        None,
        description="Ai adjustments applied to the base definition",
        alias="ai_modifications",
    )
    promoted_at: Optional[datetime] = Field(None, description="Timestamp when strategy was promoted")
    promoted_by_recommendation: Optional[bool] = Field(
        None,
        description="Whether the promotion was driven by the recommendation engine",
    )

    class Config:
        # Pydantic v2 migration: renamed from allow_population_by_field_name
        populate_by_name = True


class StrategyResponse(BaseModel):
    """Serialized strategy response."""

    id: int
    name: str
    description: Optional[str]
    rules: Dict[str, Any]
    source: str
    status: str
    github_url: Optional[str]
    ai_modifications: Optional[Dict[str, Any]]
    promoted_at: Optional[datetime]
    promoted_by_recommendation: bool
    created_at: datetime
    updated_at: datetime


class StrategyPromoteRequest(BaseModel):
    """Payload required to promote a strategy to live."""

    confirm: bool = Field(
        ..., description="Explicit confirmation is required to promote a strategy to live."
    )


class StrategyComparisonMetrics(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: Optional[float]
    ai_model_used: Optional[str]
    period_start: Optional[datetime]
    period_end: Optional[datetime]


class StrategyComparisonEntry(BaseModel):
    strategy_id: int
    name: str
    description: Optional[str]
    source: str
    status: str
    updated_at: datetime
    performance: StrategyComparisonMetrics


class StrategyComparisonResponse(BaseModel):
    strategies: List[StrategyComparisonEntry]
    compared_at: datetime


class StrategySuggestionRequest(BaseModel):
    symbols: List[str] = Field(
        ...,
        min_items=1,
        description="Trading pair(s) (BASE/QUOTE) to analyze for strategy suggestions.",
    )
    timeframe: str = Field(
        "1h",
        min_length=1,
        description="Primary timeframe to consider when asking the AI for ideas.",
    )
    risk_tolerance: str = Field(
        "balanced",
        min_length=1,
        description="Risk appetite descriptor passed to the AI.",
    )
    preferred_indicators: List[str] = Field(
        default_factory=list,
        description="Optional indicators to highlight in the request.",
    )
    target_return_pct: Optional[float] = Field(
        None,
        ge=0,
        description="Optional target return percentage the AI should aim for.",
    )
    max_positions: Optional[int] = Field(
        None,
        ge=1,
        description="Optional maximum concurrent positions to preserve.",
    )
    notes: Optional[str] = Field(
        None,
        description="Additional context or hypotheses to steer the AI.",
    )
    lookback: int = Field(
        20,
        ge=5,
        le=200,
        description="Number of recent candles to include when summarizing technicals.",
    )
    insight_limit: int = Field(
        3,
        ge=1,
        le=6,
        description="How many analyst insights to surface.",
    )
    sentiment_limit: int = Field(
        5,
        ge=1,
        le=20,
        description="How many sentiment samples to summarize.",
    )

    model_config = ConfigDict(extra="ignore")


class StrategySuggestionDetail(BaseModel):
    symbol: str
    market_summary: str
    technical: TechnicalSnapshot
    analyst_indicators: AnalystIndicatorSnapshot
    insights: List[Dict[str, Any]]
    sentiment: Optional[SentimentSummary]
    recommendations: List[str]
    ai_proposal: Optional[StrategyProposal]
    ai_error: Optional[str] = None
    risk_context: Optional[RiskContext] = None
    risk_recommendation: Optional[RiskRecommendation] = None
    risk_summary: str = Field(
        ...,
        description="Human-readable summary of the current risk posture and suggestions.",
    )

    model_config = ConfigDict(from_attributes=True)


class StrategySuggestionResponse(BaseModel):
    generated_at: datetime
    suggestions: List[StrategySuggestionDetail]

    model_config = ConfigDict(from_attributes=True)


def _serialize_strategy(strategy: Strategy) -> StrategyResponse:
    return StrategyResponse(
        id=strategy.id,
        name=strategy.name,
        description=strategy.description,
        rules=strategy.rules_json or {},
        source=strategy.source or "manual",
        status=strategy.status or "paper",
        github_url=strategy.github_url,
        ai_modifications=strategy.ai_modifications_json,
        promoted_at=strategy.promoted_at,
        promoted_by_recommendation=bool(strategy.promoted_by_recommendation),
        created_at=strategy.created_at,
        updated_at=strategy.updated_at,
    )


def _normalize_status_filters(values: Optional[List[str]]) -> List[str]:
    normalized: List[str] = []
    for raw in values or []:
        if not raw:
            continue
        candidate = raw.strip().lower()
        if not candidate:
            continue
        normalized.append(candidate)
    return normalized


def _order_strategies_by_requested_ids(
    strategies: List[Strategy], requested_ids: List[int]
) -> List[Strategy]:
    if not strategies or not requested_ids:
        return strategies

    strategy_map = {strategy.id: strategy for strategy in strategies}
    ordered: List[Strategy] = []
    seen: set[int] = set()
    for strategy_id in requested_ids:
        if strategy_id in seen:
            continue
        seen.add(strategy_id)
        strategy = strategy_map.get(strategy_id)
        if strategy:
            ordered.append(strategy)

    return ordered


def _build_comparison_metrics(performance: Optional[StrategyPerformance]) -> StrategyComparisonMetrics:
    if not performance:
        return StrategyComparisonMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            total_pnl=0.0,
            max_drawdown=0.0,
            sharpe_ratio=None,
            ai_model_used=None,
            period_start=None,
            period_end=None,
        )

    return StrategyComparisonMetrics(
        total_trades=performance.total_trades or 0,
        winning_trades=performance.winning_trades or 0,
        losing_trades=performance.losing_trades or 0,
        win_rate=performance.win_rate or 0.0,
        total_pnl=performance.total_pnl or 0.0,
        max_drawdown=performance.max_drawdown or 0.0,
        sharpe_ratio=performance.sharpe_ratio,
        ai_model_used=performance.ai_model_used,
        period_start=performance.period_start,
        period_end=performance.period_end,
    )


def _decimal_to_str(value: Optional[Decimal], precision: int = 2, default: str = "unknown") -> str:
    if value is None:
        return default
    format_spec = f"{{:.{precision}f}}"
    return format_spec.format(value)


def _price_change_description(
    last_price: Optional[Decimal], previous_price: Optional[Decimal]
) -> str:
    if last_price is None or previous_price is None or previous_price == Decimal("0"):
        return ""
    delta = last_price - previous_price
    percent_change = (delta / previous_price) * Decimal("100")
    return f"{delta:+.2f} ({percent_change:+.2f}%)"


def _compile_market_summary(
    symbol: str,
    technical: TechnicalSnapshot,
    indicators: AnalystIndicatorSnapshot,
    insights: List[Dict[str, Any]],
    sentiment: Optional[SentimentSummary],
) -> str:
    fragments: List[str] = []
    direction = technical.direction or "unclear"
    last_price = _decimal_to_str(technical.last_price)
    summary = f"{symbol} is {direction} at {last_price}."
    change = _price_change_description(technical.last_price, technical.previous_price)
    if change:
        summary += f" Change {change}."
    fragments.append(summary)

    if indicators.momentum is not None:
        fragments.append(f"Momentum {float(indicators.momentum):.3f}.")
    if indicators.volatility is not None:
        fragments.append(f"Volatility {float(indicators.volatility):.3f}.")

    if sentiment:
        tone = "bullish" if sentiment.average_score >= 0.2 else "bearish" if sentiment.average_score <= -0.2 else "neutral"
        fragments.append(f"Sentiment is {tone} (avg {sentiment.average_score:.2f}).")

    if insights:
        first_summary = insights[0].get("summary") or insights[0].get("type")
        if first_summary:
            fragments.append(f"Insight: {first_summary}")

    return " ".join(fragments).strip()


def _format_risk_summary(
    context: Optional[RiskContext],
    recommendation: Optional[RiskRecommendation],
) -> str:
    if not context:
        return "Risk context unavailable."
    pieces: List[str] = []
    if context.max_risk_score > 0:
        pieces.append(
            f"Risk score {context.current_risk_score:.1f}"
            f" / {context.max_risk_score:.1f} threshold"
        )
    else:
        pieces.append(f"Risk score {context.current_risk_score:.1f}")
    pieces.append(
        f"Daily loss ${context.daily_loss:.2f} / limit ${context.daily_loss_limit:.2f}"
    )
    if context.max_drawdown_pct > 0:
        pieces.append(
            f"Drawdown {context.recent_drawdown_pct:.1f}% / "
            f"{context.max_drawdown_pct:.1f}% limit"
        )
    if recommendation and recommendation.adjustments:
        pieces.append(f"Suggested adjustment: {recommendation.summary}")

    return " · ".join(pieces)


def _build_strategy_proposal_input(
    symbol: str,
    payload: StrategySuggestionRequest,
    market_summary: str,
    risk_summary: Optional[str] = None,
) -> StrategyProposalInput:
    indicators = [item.strip() for item in payload.preferred_indicators if item and item.strip()]
    request_kwargs: Dict[str, Any] = {
        "symbols": [symbol],
        "timeframe": payload.timeframe,
        "market_summary": market_summary,
        "risk_tolerance": payload.risk_tolerance,
        "preferred_indicators": indicators,
    }
    if payload.target_return_pct is not None:
        request_kwargs["target_return_pct"] = payload.target_return_pct
    if payload.max_positions is not None:
        request_kwargs["max_positions"] = payload.max_positions
    if payload.notes:
        request_kwargs["notes"] = payload.notes
    if risk_summary:
        notes = request_kwargs.get("notes", "")
        combined = "\n\n".join(
            part
            for part in (notes.strip() if notes else "", risk_summary)
            if part
        )
        request_kwargs["notes"] = combined

    return StrategyProposalInput(**request_kwargs)


async def _build_strategy_suggestion(
    symbol: str,
    payload: StrategySuggestionRequest,
    risk_context: Optional[RiskContext],
    risk_recommendation: Optional[RiskRecommendation],
) -> StrategySuggestionDetail:
    technical_payload = await market_data_service.summarize_symbol(
        symbol, lookback=payload.lookback
    )
    technical_snapshot = _build_technical_snapshot(symbol, technical_payload)
    indicator_payload = await market_analyst_agent.get_indicator_summary(symbol)
    indicator_snapshot = _build_indicator_snapshot(indicator_payload)
    insights = await market_analyst_agent.get_recent_insights(
        symbol, limit=payload.insight_limit
    )
    sentiment_summary = await sentiment_agent.summarize_symbol(
        symbol, limit=payload.sentiment_limit
    )
    recommendations = _build_recommendations(
        symbol,
        technical_snapshot,
        indicator_snapshot,
        insights,
        sentiment_summary,
    )
    market_summary = _compile_market_summary(
        symbol,
        technical_snapshot,
        indicator_snapshot,
        insights,
        sentiment_summary,
    )

    risk_summary = _format_risk_summary(risk_context, risk_recommendation)
    proposal: Optional[StrategyProposal] = None
    ai_error: Optional[str] = None
    try:
        request_payload = _build_strategy_proposal_input(
            symbol,
            payload,
            market_summary,
            risk_summary=risk_summary,
        )
        proposal = await strategy_ai_service.propose_strategy(request_payload)
    except Exception as exc:
        logger.warning("Strategy AI suggestion failed for %s: %s", symbol, exc)
        ai_error = str(exc)

    return StrategySuggestionDetail(
        symbol=symbol,
        market_summary=market_summary,
        technical=technical_snapshot,
        analyst_indicators=indicator_snapshot,
        insights=insights,
        sentiment=sentiment_summary,
        recommendations=recommendations,
        ai_proposal=proposal,
        ai_error=ai_error,
        risk_context=risk_context,
        risk_recommendation=risk_recommendation,
        risk_summary=risk_summary,
    )


@router.post("/suggestions", response_model=StrategySuggestionResponse)
async def suggest_strategies(
    payload: StrategySuggestionRequest,
    current_user: User = Depends(get_current_user),
) -> StrategySuggestionResponse:
    """Generate AI-grounded strategy ideas for the requested market conditions."""
    suggestions: List[StrategySuggestionDetail] = []
    risk_service = RiskAIService()
    risk_context: Optional[RiskContext] = None
    risk_recommendation: Optional[RiskRecommendation] = None
    try:
        risk_context, risk_recommendation = await risk_service.context_and_heuristic()
    except Exception as exc:
        logger.warning("Failed to collect risk context for suggestions: %s", exc)

    for raw_symbol in payload.symbols:
        normalized_symbol = _normalize_trading_pair(raw_symbol, parameter="symbol")

        try:
            suggestion = await _build_strategy_suggestion(
                normalized_symbol,
                payload,
                risk_context,
                risk_recommendation,
            )
            suggestions.append(suggestion)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to generate strategy suggestion for %s: %s", normalized_symbol, exc)

    return StrategySuggestionResponse(
        generated_at=datetime.utcnow(),
        suggestions=suggestions,
    )


@router.get("/", response_model=List[StrategyResponse], status_code=status.HTTP_200_OK)
async def list_strategies(
    status: Optional[List[str]] = Query(
        None,
        alias="status",
        description=f"Return strategies matching a status ({STATUS_HINT}).",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> List[StrategyResponse]:
    """List strategies, optionally filtering by status."""
    filters = _normalize_status_filters(status)
    try:
        query = select(Strategy)
        if filters:
            query = query.where(Strategy.status.in_(filters))
        result = await db.execute(query.order_by(Strategy.updated_at.desc()))
        strategies = list(result.scalars().all())
    except Exception as exc:  # pragma: no cover - defensive DB guard
        logger.error("Strategy list fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve strategies",
        )

    return [_serialize_strategy(strategy) for strategy in strategies]


@router.get("/comparison", response_model=StrategyComparisonResponse)
async def compare_strategies(
    status: Optional[List[str]] = Query(
        None,
        alias="status",
        description=f"Include strategies matching a status ({STATUS_HINT}). Defaults to {', '.join(COMPARISON_DEFAULT_STATUSES)}.",
    ),
    strategy_ids: Optional[List[int]] = Query(
        None,
        alias="strategy_id",
        description="Repeatable filter to limit comparison to specific strategy IDs.",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> StrategyComparisonResponse:
    """Return comparison-ready strategy metadata and latest performance metrics."""
    filters = _normalize_status_filters(status)
    if not filters:
        filters = COMPARISON_DEFAULT_STATUSES

    try:
        query = select(Strategy)
        if filters:
            query = query.where(Strategy.status.in_(filters))
        if strategy_ids:
            query = query.where(Strategy.id.in_(strategy_ids))

        result = await db.execute(query.order_by(Strategy.updated_at.desc()))
        strategies = list(result.scalars().all())
        
        if strategy_ids:
            ordered = _order_strategies_by_requested_ids(strategies, strategy_ids)
            if ordered:
                strategies = ordered

        strategy_ids_list = [strategy.id for strategy in strategies]
        performance_map: Dict[int, StrategyPerformance] = {}
        if strategy_ids_list:
            perf_query = (
                select(StrategyPerformance)
                .where(StrategyPerformance.strategy_id.in_(strategy_ids_list))
                .order_by(
                    StrategyPerformance.strategy_id.asc(),
                    StrategyPerformance.period_end.desc(),
                )
            )
            perf_result = await db.execute(perf_query)
            performance_rows = perf_result.scalars().all()
            
            for row in performance_rows:
                if row.strategy_id not in performance_map:
                    performance_map[row.strategy_id] = row

        comparisons: List[StrategyComparisonEntry] = []
        for strategy in strategies:
            comparisons.append(
                StrategyComparisonEntry(
                    strategy_id=strategy.id,
                    name=strategy.name,
                    description=strategy.description,
                    source=strategy.source or "manual",
                    status=strategy.status or "paper",
                    updated_at=strategy.updated_at,
                    performance=_build_comparison_metrics(
                        performance_map.get(strategy.id)
                    ),
                )
            )

    except Exception as exc:  # pragma: no cover - defensive guard
        logger.error("Strategy comparison fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to build strategy comparison data",
        )

    return StrategyComparisonResponse(
        strategies=comparisons,
        compared_at=datetime.utcnow(),
    )


@router.post("/import/github", response_model=GitHubImportResponse)
async def import_from_github(
    payload: GitHubImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> GitHubImportResponse:
    """Import strategy definitions from a GitHub URL."""
    try:
        report = await github_import_service.import_strategies(payload.github_url)
    except Exception as exc:
        logger.error("GitHub import service failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )

    imported_count = 0
    for candidate in report.candidates:
        try:
            strategy = Strategy(
                name=candidate.name,
                description=candidate.definition.description or f"Imported from {candidate.path}",
                rules_json=candidate.definition.rules,
                source="github",
                status="paper",
                github_url=f"{report.source_url}/blob/{report.branch}/{candidate.path}",
                ai_modifications_json=candidate.ai_insights.dict() if candidate.ai_insights else None,
            )
            db.add(strategy)
            imported_count += 1
        except Exception as exc:
            logger.warning("Failed to save imported strategy %s: %s", candidate.path, exc)

    if imported_count > 0:
        await db.commit()

    return GitHubImportResponse(
        imported_count=imported_count,
        failed_count=len(report.failures),
        branch=report.branch,
        message=f"Successfully imported {imported_count} strategies."
    )


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> StrategyResponse:
    """Return a single strategy by id."""
    try:
        strategy = await db.get(Strategy, strategy_id)
    except Exception as exc:  # pragma: no cover
        logger.error("Failed loading strategy %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    return _serialize_strategy(strategy)


@router.post("/{strategy_id}/promote", response_model=StrategyResponse)
async def promote_strategy(
    strategy_id: int,
    payload: StrategyPromoteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> StrategyResponse:
    """Mark a strategy as live after explicit confirmation."""
    try:
        strategy = await db.get(Strategy, strategy_id)
    except Exception as exc:
        logger.error("Failed loading strategy for promotion %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Promotion requires explicit confirmation",
        )

    if strategy.status == "live":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy is already live",
        )

    strategy.status = "live"
    strategy.promoted_at = datetime.utcnow()
    strategy.promoted_by_recommendation = False

    try:
        await db.commit()
        await db.refresh(strategy)
    except Exception as exc:  # pragma: no cover
        await db.rollback()
        logger.error("Failed to persist strategy promotion %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to promote strategy",
        )

    return _serialize_strategy(strategy)


@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: StrategyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> StrategyResponse:
    """Create a new strategy definition."""
    try:
        strategy = Strategy(
            name=payload.name,
            description=payload.description,
            rules_json=payload.rules,
            source=payload.source or "manual",
            status=payload.status or "paper",
            github_url=payload.github_url,
            ai_modifications_json=payload.ai_modifications,
            promoted_at=payload.promoted_at,
            promoted_by_recommendation=payload.promoted_by_recommendation,
        )
        db.add(strategy)
        await db.commit()
        await db.refresh(strategy)
    except Exception as exc:  # pragma: no cover
        await db.rollback()
        logger.error("Failed to create strategy %s: %s", payload.name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create strategy",
        )

    return _serialize_strategy(strategy)


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    payload: StrategyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> StrategyResponse:
    """Modify a strategy definition."""
    try:
        strategy = await db.get(Strategy, strategy_id)
    except Exception as exc:
        logger.error("Failed loading strategy for update %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    update_data = payload.dict(exclude_unset=True, by_alias=True)
    if not update_data:
        return _serialize_strategy(strategy)

    rules_payload = update_data.pop("rules", _FIELD_MISSING)
    ai_payload = update_data.pop("ai_modifications", _FIELD_MISSING)
    has_changes = False

    if rules_payload is not _FIELD_MISSING:
        if rules_payload is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Strategy rules cannot be null",
            )
        strategy.rules_json = rules_payload
        has_changes = True

    if ai_payload is not _FIELD_MISSING:
        strategy.ai_modifications_json = ai_payload
        has_changes = True

    for attr, value in update_data.items():
        setattr(strategy, attr, value)
        has_changes = True

    if not has_changes:
        return _serialize_strategy(strategy)

    try:
        await db.commit()
        await db.refresh(strategy)
    except Exception as exc:  # pragma: no cover
        await db.rollback()
        logger.error("Failed to persist strategy update %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to update strategy",
        )

    return _serialize_strategy(strategy)


@router.delete("/{strategy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Remove a strategy from the catalog."""
    try:
        strategy = await db.get(Strategy, strategy_id)
    except Exception as exc:
        logger.error("Failed to load strategy for deletion %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load strategy",
        )

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Strategy not found",
        )

    try:
        await db.delete(strategy)
        await db.commit()
    except Exception as exc:  # pragma: no cover
        await db.rollback()
        logger.error("Failed to delete strategy %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete strategy",
        )


@router.post("/{strategy_id}/simulate")
async def simulate_strategy_signal(
    strategy_id: int,
    signal: PaperTradeSignal,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Execute a paper trading signal for a strategy."""
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    signal.strategy_id = strategy_id
    try:
        results = await paper_trading_engine.execute_signal(signal)
        if results:
            await paper_trading_engine.persist_closed_trades(results)
        
        # Log the AI decision for this signal
        decision = AIDecision(
            agent_name="paper_trading_engine",
            decision_type=f"paper_{signal.intent.value}",
            reasoning_json={"signal": signal.dict(), "results_count": len(results)},
            confidence_score=1.0,
            action_taken=f"Executed {signal.side.value if signal.side else 'exit'} for {signal.symbol}",
            related_strategy_id=strategy_id,
        )
        db.add(decision)
        await db.commit()

        return {"status": "success", "results_count": len(results)}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as exc:  # pragma: no cover - defensive guard
        await db.rollback()
        logger.error("Failed to simulate strategy %s: %s", strategy_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process strategy simulation",
        ) from exc


@router.get("/paper-portfolio", response_model=PaperPortfolioSnapshot)
async def get_paper_portfolio(
    current_user: User = Depends(get_current_user),
):
    """Return a snapshot of the current paper trading portfolio."""
    return await paper_trading_engine.snapshot()
