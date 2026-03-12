"""Tracks conversational preference cues and persists them for future chats."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Pattern, Sequence, Set

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import User

logger = logging.getLogger(__name__)

DEFAULT_SYMBOL_WHITELIST: Set[str] = {
    "BTC",
    "ETH",
    "SOL",
    "ADA",
    "XRP",
    "LTC",
    "DOT",
    "LINK",
    "AVAX",
    "FIL",
    "MATIC",
    "ARB",
    "OP",
    "DOGE",
    "ATOM",
    "TRX",
    "BCH",
    "UNI",
    "APE",
    "XLM",
}

TONE_KEYWORDS: Dict[str, Sequence[str]] = {
    "concise": (
        "keep it concise",
        "brief",
        "summary",
        "just the highlights",
        "short and sweet",
        "only the facts",
    ),
    "detailed": (
        "in detail",
        "detailed",
        "deep dive",
        "thorough",
        "explain everything",
    ),
    "conversational": (
        "casual",
        "friendly",
        "like a conversation",
        "talk to me",
        "explain like",
    ),
    "data_driven": ("data-driven", "numbers", "metrics", "statistics"),
}

RISK_KEYWORDS: Dict[str, Sequence[str]] = {
    "conservative": (
        "low risk",
        "conservative",
        "protect capital",
        "capital preservation",
        "cautious",
        "stay safe",
    ),
    "balanced": (
        "balanced",
        "moderate risk",
        "middle ground",
        "neutral",
        "medium risk",
    ),
    "aggressive": (
        "high risk",
        "aggressive",
        "go big",
        "take chances",
        "upside",
    ),
}

FORMAT_KEYWORDS: Dict[str, Sequence[str]] = {
    "bullet_points": ("bullet points", "bullets", "list format", "itemize"),
    "step_by_step": (
        "step by step",
        "walk me through",
        "sequence",
        "process",
        "staged",
    ),
    "visual": ("diagram", "chart", "visual", "plot", "graph"),
    "code": ("code", "sample code", "snippet"),
}

TOPIC_KEYWORDS: Dict[str, Sequence[str]] = {
    "strategy": ("strategy", "plan", "approach", "setup", "idea"),
    "risk": ("risk", "drawdown", "stop loss", "capital preservation"),
    "execution": (
        "entry",
        "exit",
        "order",
        "slippage",
        "timing",
        "execution",
    ),
    "indicators": ("indicator", "macd", "rsi", "moving average", "ema"),
    "alerts": ("alert", "notification", "ping", "be notified"),
    "automation": ("automate", "automation", "bot", "ai", "system"),
    "sentiment": ("sentiment", "news", "social", "macro"),
}

MAX_LIST_ENTRIES = 12


class PreferenceProfile(BaseModel):
    """Structured preference payload that can be persisted as JSON."""

    tone: Optional[str] = None
    risk_appetite: Optional[str] = None
    response_format: Optional[str] = None
    favorite_symbols: List[str] = Field(default_factory=list)
    preferred_topics: List[str] = Field(default_factory=list)
    last_updated_at: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class PreferenceLearningService:
    """Heuristics-based service that tracks conversational cues."""

    def __init__(self, symbol_whitelist: Optional[Iterable[str]] = None) -> None:
        self._symbol_whitelist = {
            symbol.upper() for symbol in symbol_whitelist
        } if symbol_whitelist else DEFAULT_SYMBOL_WHITELIST
        self._symbol_pattern: Pattern[str] = re.compile(r"\$?([A-Z]{2,5})(?:[\/-][A-Z]{2,5})?\b")

    async def learn_from_message(
        self, db: Session, message: str, user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Extracts preferences from a chat turn and merges them with stored data."""

        if not message or not message.strip():
            return await self.recall_preferences(db, user_id)

        profile = self._extract_profile(message)
        updates = profile.model_dump(exclude_none=True, exclude_defaults=True)
        if not updates:
            return await self.recall_preferences(db, user_id)

        existing_preferences = await self.recall_preferences(db, user_id)
        merged = self._merge_preferences(existing_preferences, updates)
        if user_id is None:
            return merged

        await self._save_preferences(db, user_id, merged)
        return merged

    async def recall_preferences(
        self, db: Session, user_id: Optional[int]
    ) -> Dict[str, Any]:
        """Loads the last-known preference payload for a user."""

        if user_id is None:
            return {}

        try:
            user = db.query(User).filter(User.id == user_id).first()
        except SQLAlchemyError as exc:
            logger.exception("Failed to load user %s for preferences: %s", user_id, exc)
            raise

        if not user:
            return {}

        stored = user.preferences_json or {}
        if isinstance(stored, dict):
            return deepcopy(stored)
        return {}

    def _extract_profile(self, message: str) -> PreferenceProfile:
        normalized = message.lower()
        profile = PreferenceProfile(
            tone=self._first_keyword_match(normalized, TONE_KEYWORDS),
            risk_appetite=self._first_keyword_match(normalized, RISK_KEYWORDS),
            response_format=self._first_keyword_match(normalized, FORMAT_KEYWORDS),
            favorite_symbols=self._extract_symbols(message),
            preferred_topics=self._collect_topics(normalized),
            last_updated_at=datetime.utcnow().isoformat(),
        )
        return profile

    def _merge_preferences(
        self, existing: Dict[str, Any], updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = dict(existing)
        for key, value in updates.items():
            if key in ("favorite_symbols", "preferred_topics"):
                base_sequence = self._normalize_sequence(result.get(key))
                update_sequence = self._normalize_sequence(value)
                result[key] = self._merge_lists(base_sequence, update_sequence)
                continue
            result[key] = value
        return result

    async def _save_preferences(self, db: Session, user_id: int, payload: Dict[str, Any]) -> None:
        try:
            user = db.query(User).filter(User.id == user_id).first()
        except SQLAlchemyError as exc:
            logger.exception("Failed to reload user %s for preference persistence: %s", user_id, exc)
            raise

        if not user:
            logger.warning("Preference update requested for unknown user %s", user_id)
            return

        user.preferences_json = payload
        try:
            db.add(user)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("Unable to persist preferences for user %s: %s", user_id, exc)
            raise

    def _first_keyword_match(
        self, normalized: str, candidates: Dict[str, Sequence[str]]
    ) -> Optional[str]:
        for label, keywords in candidates.items():
            for keyword in keywords:
                if keyword in normalized:
                    return label
        return None

    def _collect_topics(self, normalized: str) -> List[str]:
        topics: List[str] = []
        for label, keywords in TOPIC_KEYWORDS.items():
            for keyword in keywords:
                if keyword in normalized:
                    topics.append(label)
                    break
            if len(topics) >= MAX_LIST_ENTRIES:
                break
        return topics

    def _extract_symbols(self, message: str) -> List[str]:
        symbols: List[str] = []
        uppercased = message.upper()
        for match in self._symbol_pattern.findall(uppercased):
            candidate = match.upper()
            if candidate not in self._symbol_whitelist:
                continue
            if candidate in symbols:
                continue
            symbols.append(candidate)
            if len(symbols) >= MAX_LIST_ENTRIES:
                break
        return symbols

    def _merge_lists(
        self, existing: Sequence[str], updates: Sequence[str]
    ) -> List[str]:
        seen: List[str] = []
        for candidate in list(existing) + list(updates):
            if not candidate:
                continue
            normalized = candidate.strip()
            if not normalized:
                continue
            if normalized in seen:
                continue
            seen.append(normalized)
            if len(seen) >= MAX_LIST_ENTRIES:
                break
        return seen

    @staticmethod
    def _normalize_sequence(value: Any) -> Sequence[str]:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            return value
        return []
