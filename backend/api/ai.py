"""AI chat API routes."""

from __future__ import annotations

import asyncio
import copy
import httpx
import json
import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

import openai
from openai import AsyncOpenAI
from anthropic import AI_PROMPT, Anthropic, HUMAN_PROMPT
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
import pydantic as _pydantic
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_async_db
from db.models import Alert, ChatHistory, StrategyPerformance, SystemLog

from services.ai_models import AIModelDescriptor, AIModelsService, AIProvider
from services.chat_context import ChatContextAssembler
from services.chat_policy import ChatPolicyEngine
from services.chat_response import ChatResponseNormalizer

from api.alerts import AlertResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class _OpenAIChatCompletionCompat:
    """Bridge that maps the legacy ChatCompletion API calls to AsyncOpenAI."""

    def _collect_client_kwargs(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        for attr in ("api_key", "api_base", "api_type", "api_version", "organization"):
            value = getattr(openai, attr, None)
            if value is not None:
                params[attr] = value
        return params

    async def acreate(self, **kwargs: Any) -> Any:
        if AsyncOpenAI is None:
            raise RuntimeError("openai.AsyncOpenAI is required for ChatCompletion.acreate().")
        client = AsyncOpenAI(**self._collect_client_kwargs())
        try:
            return await client.chat.completions.create(**kwargs)
        finally:
            await client.aclose()


openai.ChatCompletion = _OpenAIChatCompletionCompat()

CHUNK_SIZE = 160


class ChatProvider(str, Enum):
    """Supported AI providers for the chat conversation."""

    OPENAI = "openai"
    CLAUDE = "claude"
    OLLAMA = "ollama"


def _env_provider() -> ChatProvider:
    candidate = os.getenv("CHAT_AI_PROVIDER", ChatProvider.OPENAI.value).lower()
    try:
        return ChatProvider(candidate)
    except ValueError:
        logger.warning("Unknown CHAT_AI_PROVIDER=%s; defaulting to openai", candidate)
        return ChatProvider.OPENAI


class ChatRequest(BaseModel):
    """Payload that seeds the user side of the conversation."""

    message: Optional[str] = Field(
        None,
        min_length=1,
        description="Primary user prompt text",
        alias="prompt",
    )
    temperature: Optional[float] = Field(
        None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0-2)",
    )
    max_tokens: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum tokens to generate",
    )
    tone: Optional[str] = Field(None, description="Desired communication style")
    context_json: Optional[Dict[str, Any]] = Field(
        None, description="Optional structured context shared with the AI"
    )
    preferences_json: Optional[Dict[str, Any]] = Field(
        None, description="Learned preferences to inform the reply"
    )
    related_alert_id: Optional[int] = Field(
        None, description="Optional alert ID that spawned the chat"
    )
    provider: Optional[ChatProvider] = Field(
        None, description="Override the configured AI provider"
    )

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    @model_validator(mode="after")
    def _ensure_message(self) -> "ChatRequest":
        if self.message is None:
            raise ValueError("Either 'message' or 'prompt' is required")
        return self


class ChatHistoryEntry(BaseModel):
    """Representation of a stored chat entry."""

    id: int
    user_message: str
    ai_response: str
    timestamp: datetime
    related_alert_id: Optional[int]
    context_json: Optional[Dict[str, Any]]
    learned_preferences_json: Optional[Dict[str, Any]]

    model_config = ConfigDict(from_attributes=True)


class ChatHistoryList(BaseModel):
    """List wrapper returned by the history endpoint."""

    history: List[ChatHistoryEntry]
    total: int

    model_config = ConfigDict(from_attributes=True)


class AIModelInventoryResponse(BaseModel):
    """Wrapper for API responses that list configured AI models."""

    models: List[AIModelDescriptor]


class AIModelActivationRequest(BaseModel):
    """Request body used to change the active provider."""

    provider: AIProvider


class AIModelActivationResponse(BaseModel):
    """Confirmation payload after activating a provider."""

    active_provider: AIProvider
    models: List[AIModelDescriptor]


class ModelComparisonEntry(BaseModel):
    provider: AIProvider
    model: str
    description: str
    available: bool
    active: bool
    strategy_count: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    average_win_rate: Optional[float]
    total_pnl: float


class ModelComparisonResponse(BaseModel):
    comparisons: List[ModelComparisonEntry]


class ActivityLogEntry(BaseModel):
    id: int
    level: str
    source: str
    message: str
    details: Optional[dict[str, Any]] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


def _map_system_log_to_activity(record: SystemLog) -> ActivityLogEntry:
    return ActivityLogEntry(
        id=record.id,
        level=record.level,
        source=record.source,
        message=record.message,
        details=record.details_json,
        timestamp=record.timestamp,
    )


class AlertsActivityResponse(BaseModel):
    alerts: List[AlertResponse]
    alerts_total: int
    alerts_page: int
    alerts_page_size: int
    unread_alerts: int
    activity: List[ActivityLogEntry]
    activity_total: int
    activity_page: int
    activity_page_size: int


def _apply_alert_filters(
    stmt,
    severity: Optional[str],
    status_filter: Optional[str],
    alert_type: Optional[str],
    search: Optional[str],
    since: Optional[datetime],
    until: Optional[datetime],
):
    if severity:
        stmt = stmt.where(Alert.severity == severity)
    if status_filter:
        stmt = stmt.where(Alert.status == status_filter)
    if alert_type:
        stmt = stmt.where(Alert.type == alert_type)
    if search:
        trimmed = search.strip()
        if trimmed:
            pattern = f"%{trimmed}%"
            stmt = stmt.where(
                or_(
                    Alert.title.ilike(pattern),
                    Alert.message.ilike(pattern),
                )
            )
    if since:
        stmt = stmt.where(Alert.created_at >= since)
    if until:
        stmt = stmt.where(Alert.created_at <= until)
    return stmt


def _apply_activity_filters(
    stmt,
    log_level: Optional[str],
    log_source: Optional[str],
):
    if log_level:
        stmt = stmt.where(SystemLog.level == log_level)
    if log_source:
        stmt = stmt.where(SystemLog.source.ilike(f"%{log_source}%"))
    return stmt


@router.get("/alerts-activity", response_model=AlertsActivityResponse)
async def alerts_activity(
    severity: Optional[str] = Query(None, description="Filter by alert severity (info|warning|critical)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by alert status"),
    alert_type: Optional[str] = Query(None, alias="type", description="Filter by alert type"),
    search: Optional[str] = Query(None, description="Search alert titles or messages"),
    since: Optional[datetime] = Query(None, description="Return alerts created after this timestamp"),
    until: Optional[datetime] = Query(None, description="Return alerts created before this timestamp"),
    alerts_page: int = Query(1, ge=1, description="Alerts page number"),
    alerts_page_size: int = Query(12, ge=1, le=100, description="Number of alerts per page"),
    log_level: Optional[str] = Query(None, description="Filter activity log level (info|warning|error|critical)"),
    log_source: Optional[str] = Query(None, description="Filter activity log source/component"),
    activity_page: int = Query(1, ge=1, description="Activity log page number"),
    activity_page_size: int = Query(25, ge=1, le=100, description="Number of activity entries per page"),
    db: AsyncSession = Depends(get_async_db),
) -> AlertsActivityResponse:
    """Return a combined alerts feed and activity log for the dashboard."""
    try:
        alert_stmt = _apply_alert_filters(
            select(Alert),
            severity,
            status_filter,
            alert_type,
            search,
            since,
            until,
        )
        alerts_count_stmt = _apply_alert_filters(
            select(func.count(Alert.id)).select_from(Alert),
            severity,
            status_filter,
            alert_type,
            search,
            since,
            until,
        )
        alerts_total = int((await db.execute(alerts_count_stmt)).scalar_one() or 0)
        paginated_alerts = (
            alert_stmt.order_by(desc(Alert.created_at))
            .offset((alerts_page - 1) * alerts_page_size)
            .limit(alerts_page_size)
        )
        alert_rows = (await db.execute(paginated_alerts)).scalars().all()
        unread_stmt = select(func.count(Alert.id)).where(Alert.status == "new")
        unread_alerts = int((await db.execute(unread_stmt)).scalar_one() or 0)
    except SQLAlchemyError as exc:
        logger.error("Unable to query alerts for activity feed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load alerts data",
        ) from exc

    try:
        activity_stmt = _apply_activity_filters(select(SystemLog), log_level, log_source)
        activity_count_stmt = _apply_activity_filters(
            select(func.count(SystemLog.id)).select_from(SystemLog),
            log_level,
            log_source,
        )
        activity_total = int((await db.execute(activity_count_stmt)).scalar_one() or 0)
        paginated_activity = (
            activity_stmt.order_by(desc(SystemLog.timestamp))
            .offset((activity_page - 1) * activity_page_size)
            .limit(activity_page_size)
        )
        activity_records = (await db.execute(paginated_activity)).scalars().all()
    except SQLAlchemyError as exc:
        logger.error("Unable to query activity log entries", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load activity log data",
        ) from exc

    return AlertsActivityResponse(
        alerts=[AlertResponse.from_orm(record) for record in alert_rows],
        alerts_total=alerts_total,
        alerts_page=alerts_page,
        alerts_page_size=alerts_page_size,
        unread_alerts=unread_alerts,
        activity=[_map_system_log_to_activity(record) for record in activity_records],
        activity_total=activity_total,
        activity_page=activity_page,
        activity_page_size=activity_page_size,
    )


class ChatAIService:
    """Handles prompts, provider selection, and streaming responses."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_provider: Optional[ChatProvider] = None,
    ) -> None:
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self._default_provider = default_provider or _env_provider()
        self._openai_model = os.getenv("CHAT_OPENAI_MODEL", "gpt-4o-mini")
        self._claude_model = os.getenv("CHAT_CLAUDE_MODEL", "claude-3.5-sonic")
        self._system_prompt = os.getenv(
            "CHAT_AI_SYSTEM_PROMPT",
            "You are CryptoTrader's conversational trading assistant."
        )
        self._last_provider: Optional[ChatProvider] = None
        self._last_model: Optional[str] = None

        if self._openai_api_key:
            openai.api_key = self._openai_api_key

        self._anthropic_client = (
            Anthropic(api_key=self._anthropic_api_key)
            if self._anthropic_api_key
            else None
        )

        self._ollama_model = os.getenv("CHAT_OLLAMA_MODEL", "gemma3")
        self._ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api").rstrip("/")
        self._ollama_api_key = os.getenv("OLLAMA_API_KEY")
        ollama_headers: Dict[str, str] = {}
        if self._ollama_api_key:
            ollama_headers["Authorization"] = f"Bearer {self._ollama_api_key}"
        self._ollama_client = httpx.AsyncClient(
            base_url=self._ollama_base_url,
            headers=ollama_headers,
            timeout=httpx.Timeout(20.0, connect=5.0, read=5.0),
        )

    @property
    def last_provider(self) -> Optional[ChatProvider]:
        return self._last_provider

    @property
    def last_model(self) -> Optional[str]:
        return self._last_model

    async def stream_response(self, request: ChatRequest) -> AsyncIterator[str]:
        """Yield AI message fragments while tracking the chosen provider/model."""
        provider = self._select_provider(request.provider)
        self._last_provider = provider

        if provider == ChatProvider.OPENAI:
            self._last_model = self._openai_model
            async for piece in self._stream_openai(request):
                yield piece
        elif provider == ChatProvider.CLAUDE:
            self._last_model = self._claude_model
            async for piece in self._stream_claude(request):
                yield piece
        else:
            self._last_model = self._ollama_model
            async for piece in self._stream_ollama(request):
                yield piece

    async def _stream_openai(self, request: ChatRequest) -> AsyncIterator[str]:
        messages = self._build_openai_messages(request)
        try:
            completion = await openai.ChatCompletion.acreate(
                model=self._openai_model,
                messages=messages,
                temperature=0.25,
                max_tokens=600,
                stream=True,
            )
        except Exception as exc:
            logger.error("OpenAI chat request failed", exc_info=True)
            raise

        async for chunk in completion:
            choice = chunk.choices[0]
            content = choice.delta.get("content")
            if content:
                yield content

    async def _stream_claude(self, request: ChatRequest) -> AsyncIterator[str]:
        if not self._anthropic_client:
            raise RuntimeError("Anthropic client not configured")

        prompt = self._build_claude_prompt(request)
        response = await asyncio.to_thread(
            self._anthropic_client.completions.create,
            model=self._claude_model,
            prompt=prompt,
            max_tokens_to_sample=600,
            temperature=0.25,
        )
        text = (response.completion or "").strip()
        for chunk in self._chunk_text(text):
            await asyncio.sleep(0)
            yield chunk

    async def _stream_ollama(self, request: ChatRequest) -> AsyncIterator[str]:
        if not self._ollama_client:
            raise RuntimeError("Ollama client not configured")

        payload: Dict[str, Any] = {
            "model": self._ollama_model,
            "prompt": self._compose_user_prompt(request),
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens:
            payload["num_predict"] = request.max_tokens

        response = await self._ollama_client.post("/generate", json=payload)
        response.raise_for_status()
        parsed = response.json()
        text = (parsed.get("response") or "").strip()
        for chunk in self._chunk_text(text):
            await asyncio.sleep(0)
            yield chunk

    def _build_openai_messages(self, request: ChatRequest) -> List[Dict[str, str]]:
        payload = self._compose_user_prompt(request)
        return [
            {"role": "system", "content": self._system_prompt.strip()},
            {"role": "user", "content": payload},
        ]

    def _build_claude_prompt(self, request: ChatRequest) -> str:
        return f"{HUMAN_PROMPT}{self._compose_user_prompt(request)}{AI_PROMPT}"

    def _compose_user_prompt(self, request: ChatRequest) -> str:
        sections: List[str] = []
        if request.context_json:
            sections.append(
                f"Context:\n{json.dumps(request.context_json, default=str, indent=2)}"
            )
        if request.preferences_json:
            sections.append(
                f"Learned preferences:\n{json.dumps(request.preferences_json, default=str, indent=2)}"
            )
        
        # Detect if trade rationale is requested
        msg_lower = request.message.lower()
        if any(kw in msg_lower for kw in ("why", "trade", "rationale")):
            rationale_instr = (
                "\n\nIf providing a trade rationale, append a JSON block formatted exactly as: "
                "<rationale>{\"thesis\": \"...\", \"market_signals\": [], \"risk_checks\": [], \"counterfactual\": \"...\"}</rationale>"
            )
            sections.append(request.message.strip() + rationale_instr)
        else:
            sections.append(request.message.strip())
            
        prompt = "\n\n".join(sections)
        if request.tone:
            prompt = f"[Tone: {request.tone}]\n{prompt}"
        return prompt

    def _select_provider(self, candidate: Optional[ChatProvider]) -> ChatProvider:
        preferred = candidate or self._default_provider
        if preferred and self._is_provider_available(preferred):
            return preferred

        for provider in ChatProvider:
            if self._is_provider_available(provider):
                return provider

        raise RuntimeError("No AI provider configured for chat responses")

    def _is_provider_available(self, provider: ChatProvider) -> bool:
        if provider == ChatProvider.OPENAI:
            return bool(self._openai_api_key)
        if provider == ChatProvider.CLAUDE:
            return bool(self._anthropic_api_key and self._anthropic_client)
        if provider == ChatProvider.OLLAMA:
            return bool(self._ollama_client)
        return False

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> Iterator[str]:
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]


def _prepare_context_snapshot(
    request: ChatRequest,
    provider: Optional[ChatProvider],
    model: Optional[str],
    context_json: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    # Use explicitly passed context_json (the assembled one) or fall back to request context
    base = (
        copy.deepcopy(context_json)
        if context_json
        else (copy.deepcopy(request.context_json) if request.context_json else {})
    )
    meta: Dict[str, Any] = {
        "provider": provider.value if provider else None,
        "model": model,
        "tone": request.tone,
        "generated_at": datetime.utcnow().isoformat(),
    }
    existing_meta = base.get("_meta")
    if existing_meta and isinstance(existing_meta, dict):
        base["_meta"] = {**existing_meta, **meta}
    else:
        base["_meta"] = meta
    return base


async def _persist_chat_history(
    db: AsyncSession,
    request: ChatRequest,
    ai_response: str,
    provider: Optional[ChatProvider],
    model: Optional[str],
    context_json: Optional[Dict[str, Any]] = None,
) -> None:
    context_snapshot = _prepare_context_snapshot(request, provider, model, context_json)
    preferences_snapshot = (
        copy.deepcopy(request.preferences_json) if request.preferences_json else None
    )
    entry = ChatHistory(
        user_message=request.message,
        ai_response=ai_response,
        related_alert_id=request.related_alert_id,
        context_json=context_snapshot,
        learned_preferences_json=preferences_snapshot,
    )
    try:
        db.add(entry)
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("Failed to persist chat history", exc_info=True)


async def _streaming_chat_response(
    request: ChatRequest,
    db: AsyncSession,
) -> AsyncIterator[str]:
    # 1. Assemble context via ChatContextAssembler
    assembler = ChatContextAssembler()
    context = await assembler.build(
        db=db, prompt=request.message, context_json=request.context_json
    )

    # 2. Evaluate policy via ChatPolicyEngine
    policy_engine = ChatPolicyEngine()
    policy = policy_engine.evaluate(prompt=request.message, context=context)

    normalizer = ChatResponseNormalizer()

    # 3. Handle refuse/clarify branches before provider streaming
    if policy["mode"] in ("refuse", "clarify"):
        contract = normalizer.normalize(
            policy=policy, context=context, prompt=request.message
        )

        # Emit normalized contract metadata
        meta_payload = {
            "mode": contract["mode"],
            "timeframe_used": contract["timeframe_used"],
            "guardrail": contract["guardrail"],
            "meta": contract["meta"],
        }
        yield f"data: {json.dumps(meta_payload)}\n\n"

        # Emit deterministic chunk (clarifying question or refusal summary)
        yield f"data: {json.dumps({'chunk': contract['summary_paragraph']})}\n\n"

        # Finalize
        yield f"data: {json.dumps({'done': True})}\n\n"

        # Persist normalized chat context metadata
        await _persist_chat_history(
            db=db,
            request=request,
            ai_response=contract["summary_paragraph"],
            provider=None,
            model=None,
            context_json=context,
        )
        return

    # 4. Answer mode: Start with policy-driven recommendations
    service = ChatAIService()

    # Send initial metadata including recommendations and guardrails
    initial_meta = {
        "mode": policy["mode"],
        "timeframe_used": context.get("timeframe_used"),
        "guardrail": policy.get("guardrail"),
        "recommendations": policy.get("recommendations"),
        "include_confidence": policy.get("include_confidence"),
    }
    yield f"data: {json.dumps(initial_meta)}\n\n"

    accumulator: List[str] = []
    try:
        async for chunk in service.stream_response(request):
            accumulator.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        # At the end, normalize while preserving final contract metadata
        final_text = "".join(accumulator).strip()
        
        # Extract rationale if present
        trade_explanation = None
        summary_paragraph = final_text
        if "<rationale>" in final_text and "</rationale>" in final_text:
            try:
                start_tag = "<rationale>"
                end_tag = "</rationale>"
                start_idx = final_text.find(start_tag) + len(start_tag)
                end_idx = final_text.find(end_tag)
                rationale_json = final_text[start_idx:end_idx].strip()
                trade_explanation = json.loads(rationale_json)
                
                # Strip rationale from summary_paragraph
                prefix = final_text[:final_text.find(start_tag)].strip()
                suffix = final_text[end_idx + len(end_tag):].strip()
                summary_paragraph = f"{prefix} {suffix}".strip()
            except Exception as exc:
                logger.warning("Failed to parse AI rationale JSON: %s", exc)

        model_output = {
            "summary_paragraph": summary_paragraph,
            "trade_explanation": trade_explanation,
            "provider": service.last_provider,
            "model": service.last_model,
        }

        # Try to normalize to capture generated at/provider/model meta
        try:
            contract = normalizer.normalize(
                policy=policy,
                context=context,
                model_output=model_output,
                prompt=request.message,
            )
            
            # Emit final meta frame with trade_explanation and portfolio_impact
            final_meta = {
                "meta": contract["meta"],
                "trade_explanation": contract["trade_explanation"],
                "portfolio_impact": (contract.get("recommendations") or {}).get("portfolio_impact"),
                "done": True,
            }
            yield f"data: {json.dumps(final_meta)}\n\n"
        except (ValueError, KeyError) as exc:
            logger.warning("Final contract normalization skipped: %s", exc)
            yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as exc:
        logger.error("Chat stream error", exc_info=True)
        error_payload = {"error": "AI chat request failed", "details": str(exc)}
        yield f"data: {json.dumps(error_payload)}\n\n"
        raise
    finally:
        if accumulator:
            final_response = "".join(accumulator).strip()
            await _persist_chat_history(
                db=db,
                request=request,
                ai_response=final_response,
                provider=service.last_provider,
                model=service.last_model,
                context_json=context,
            )


@router.post("/chat")
async def chat_stream(
    payload: ChatRequest, db: AsyncSession = Depends(get_async_db)
) -> StreamingResponse:
    """Stream the AI chat response while persisting the conversation."""
    generator = _streaming_chat_response(payload, db)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        status_code=status.HTTP_200_OK,
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/chat/history", response_model=ChatHistoryList)
async def chat_history(
    limit: int = Query(50, ge=1, le=100, description="Maximum entries to return"),
    before_id: Optional[int] = Query(
        None, description="Return entries with ID less than this value"
    ),
    db: AsyncSession = Depends(get_async_db),
) -> ChatHistoryList:
    """Return the most recent chat entries."""
    try:
        conditions = []
        if before_id:
            conditions.append(ChatHistory.id < before_id)

        count_stmt = select(func.count(ChatHistory.id)).select_from(ChatHistory)
        for condition in conditions:
            count_stmt = count_stmt.where(condition)
        total = int((await db.execute(count_stmt)).scalar_one() or 0)

        entries_stmt = select(ChatHistory)
        for condition in conditions:
            entries_stmt = entries_stmt.where(condition)
        entries_stmt = entries_stmt.order_by(desc(ChatHistory.timestamp)).limit(limit)
        entries = (await db.execute(entries_stmt)).scalars().all()
    except SQLAlchemyError as exc:
        logger.error("Failed to query chat history", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load chat history",
        ) from exc

    return ChatHistoryList(history=entries, total=total)


def _normalize_int(value: Optional[Any]) -> int:
    if value is None:
        return 0
    return int(value)


def _normalize_float(value: Optional[Any]) -> float:
    if value is None:
        return 0.0
    return float(value)


def _normalize_optional_float(value: Optional[Any]) -> Optional[float]:
    if value is None:
        return None
    return float(value)


async def _fetch_model_performance_stats(db: AsyncSession, model_name: str) -> Dict[str, Any]:
    stmt = (
        select(
            func.count(StrategyPerformance.id).label("strategy_count"),
            func.sum(StrategyPerformance.total_trades).label("total_trades"),
            func.sum(StrategyPerformance.winning_trades).label("winning_trades"),
            func.sum(StrategyPerformance.losing_trades).label("losing_trades"),
            func.avg(StrategyPerformance.win_rate).label("average_win_rate"),
            func.sum(StrategyPerformance.total_pnl).label("total_pnl"),
        )
        .where(StrategyPerformance.ai_model_used == model_name)
    )
    row = (await db.execute(stmt)).one()
    return {
        "strategy_count": _normalize_int(row.strategy_count),
        "total_trades": _normalize_int(row.total_trades),
        "winning_trades": _normalize_int(row.winning_trades),
        "losing_trades": _normalize_int(row.losing_trades),
        "average_win_rate": _normalize_optional_float(row.average_win_rate),
        "total_pnl": _normalize_float(row.total_pnl),
    }


@router.get("/models", response_model=AIModelInventoryResponse)
async def list_ai_models() -> AIModelInventoryResponse:
    """Return the configured AI model inventory."""
    service = AIModelsService()
    try:
        models = service.list_model_inventory()
        return AIModelInventoryResponse(models=models)
    finally:
        await service.close()


@router.put("/models/active", response_model=AIModelActivationResponse)
async def set_active_ai_model(
    payload: AIModelActivationRequest,
) -> AIModelActivationResponse:
    """Switch the active AI provider for downstream requests."""
    service = AIModelsService()
    try:
        service.set_active_provider(payload.provider)
        inventory = service.list_model_inventory()
        return AIModelActivationResponse(
            active_provider=payload.provider,
            models=inventory,
        )
    except RuntimeError as exc:
        logger.warning(
            "Failed to set active AI provider %s: %s",
            payload.provider.value,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    finally:
        await service.close()


@router.get("/models/comparison", response_model=ModelComparisonResponse)
async def model_comparison(
    db: AsyncSession = Depends(get_async_db),
) -> ModelComparisonResponse:
    """Provide per-provider stats that support the model comparison UI."""
    service = AIModelsService()
    try:
        inventory = service.list_model_inventory()
        comparison_entries: List[ModelComparisonEntry] = []
        for descriptor in inventory:
            stats = await _fetch_model_performance_stats(db, descriptor.model)
            comparison_entries.append(
                ModelComparisonEntry(
                    provider=descriptor.provider,
                    model=descriptor.model,
                    description=descriptor.description,
                    available=descriptor.available,
                    active=descriptor.active,
                    strategy_count=stats["strategy_count"],
                    total_trades=stats["total_trades"],
                    winning_trades=stats["winning_trades"],
                    losing_trades=stats["losing_trades"],
                    average_win_rate=stats["average_win_rate"],
                    total_pnl=stats["total_pnl"],
                )
            )
        return ModelComparisonResponse(comparisons=comparison_entries)
    except SQLAlchemyError as exc:
        logger.error("Failed to query model comparison data", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load AI model comparison data",
        ) from exc
    finally:
        await service.close()
