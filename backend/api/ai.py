"""AI chat API routes."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

import openai
from anthropic import AI_PROMPT, Anthropic, HUMAN_PROMPT
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.database import get_db
from db.models import ChatHistory, StrategyPerformance
from services.ai_models import AIModelDescriptor, AIModelsService, AIProvider

logger = logging.getLogger(__name__)

router = APIRouter()

CHUNK_SIZE = 160


class ChatProvider(str, Enum):
    """Supported AI providers for the chat conversation."""

    OPENAI = "openai"
    CLAUDE = "claude"


def _env_provider() -> ChatProvider:
    candidate = os.getenv("CHAT_AI_PROVIDER", ChatProvider.OPENAI.value).lower()
    try:
        return ChatProvider(candidate)
    except ValueError:
        logger.warning("Unknown CHAT_AI_PROVIDER=%s; defaulting to openai", candidate)
        return ChatProvider.OPENAI


class ChatRequest(BaseModel):
    """Payload that seeds the user side of the conversation."""

    message: str = Field(..., min_length=1)
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
        else:
            self._last_model = self._claude_model
            async for piece in self._stream_claude(request):
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
            logger.exception("OpenAI chat request failed: %s", exc)
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
        return False

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> Iterator[str]:
        for i in range(0, len(text), chunk_size):
            yield text[i : i + chunk_size]


def _prepare_context_snapshot(
    request: ChatRequest, provider: ChatProvider, model: Optional[str]
) -> Optional[Dict[str, Any]]:
    base = copy.deepcopy(request.context_json) if request.context_json else {}
    meta: Dict[str, Any] = {
        "provider": provider.value,
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
    db: Session,
    request: ChatRequest,
    ai_response: str,
    provider: ChatProvider,
    model: Optional[str],
) -> None:
    context_snapshot = _prepare_context_snapshot(request, provider, model)
    preferences_snapshot = copy.deepcopy(request.preferences_json) if request.preferences_json else None
    entry = ChatHistory(
        user_message=request.message,
        ai_response=ai_response,
        related_alert_id=request.related_alert_id,
        context_json=context_snapshot,
        learned_preferences_json=preferences_snapshot,
    )
    try:
        db.add(entry)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Failed to persist chat history: %s", exc)


async def _streaming_chat_response(
    request: ChatRequest,
    service: ChatAIService,
    db: Session,
) -> AsyncIterator[str]:
    accumulator: List[str] = []
    try:
        async for chunk in service.stream_response(request):
            accumulator.append(chunk)
            payload = {"chunk": chunk}
            yield f"data: {json.dumps(payload)}\n\n"
    except Exception as exc:
        logger.exception("Chat stream error: %s", exc)
        error_payload = {"error": "AI chat request failed", "details": str(exc)}
        yield f"data: {json.dumps(error_payload)}\n\n"
        raise
    finally:
        if accumulator and service.last_provider:
            final_response = "".join(accumulator).strip()
            await _persist_chat_history(
                db,
                request,
                final_response,
                service.last_provider,
                service.last_model,
            )


@router.post("/chat")
async def chat_stream(
    payload: ChatRequest, db: Session = Depends(get_db)
) -> StreamingResponse:
    """Stream the AI chat response while persisting the conversation."""
    service = ChatAIService()
    generator = _streaming_chat_response(payload, service, db)
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
    db: Session = Depends(get_db),
) -> ChatHistoryList:
    """Return the most recent chat entries."""
    try:
        query = db.query(ChatHistory)
        if before_id:
            query = query.filter(ChatHistory.id < before_id)
        total = query.count()
        entries = (
            query.order_by(desc(ChatHistory.timestamp))
            .limit(limit)
            .all()
        )
    except SQLAlchemyError as exc:
        logger.exception("Failed to query chat history: %s", exc)
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


def _fetch_model_performance_stats(db: Session, model_name: str) -> Dict[str, Any]:
    row = (
        db.query(
            func.count(StrategyPerformance.id).label("strategy_count"),
            func.sum(StrategyPerformance.total_trades).label("total_trades"),
            func.sum(StrategyPerformance.winning_trades).label("winning_trades"),
            func.sum(StrategyPerformance.losing_trades).label("losing_trades"),
            func.avg(StrategyPerformance.win_rate).label("average_win_rate"),
            func.sum(StrategyPerformance.total_pnl).label("total_pnl"),
        )
        .filter(StrategyPerformance.ai_model_used == model_name)
        .one()
    )
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
    db: Session = Depends(get_db),
) -> ModelComparisonResponse:
    """Provide per-provider stats that support the model comparison UI."""
    service = AIModelsService()
    try:
        inventory = service.list_model_inventory()
        comparison_entries: List[ModelComparisonEntry] = []
        for descriptor in inventory:
            stats = _fetch_model_performance_stats(db, descriptor.model)
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
        logger.exception("Failed to query model comparison data: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load AI model comparison data",
        ) from exc
    finally:
        await service.close()
