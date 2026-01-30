"""Conversation memory helpers for AI chat interactions."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from db.models import ChatHistory

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_LIMIT = 5
MAX_MEMORY_LIMIT = 25
DEFAULT_SNIPPET_LENGTH = 1200
MIN_SNIPPET_LENGTH = 300
MAX_SNIPPET_LENGTH = 5000


class ChatMemoryEntryCreate(BaseModel):
    """Payload required to persist a chat conversation."""

    user_message: str = Field(..., min_length=1)
    ai_response: str = Field(..., min_length=1)
    context_json: Optional[Dict[str, Any]] = None
    learned_preferences_json: Optional[Dict[str, Any]] = None
    related_alert_id: Optional[int] = None


class StoredChatMemoryEntry(BaseModel):
    """Lightweight representation of a stored chat conversation."""

    id: int
    user_message: str
    ai_response: str
    timestamp: datetime
    related_alert_id: Optional[int]
    context_json: Optional[Dict[str, Any]]
    learned_preferences_json: Optional[Dict[str, Any]]

    model_config = ConfigDict(from_attributes=True)


class ChatMemoryService:
    """Provides persistence and recall helpers for chat history."""

    async def store_entry(
        self, db: Session, entry: ChatMemoryEntryCreate
    ) -> StoredChatMemoryEntry:
        """Persist a single conversation turn and return the saved row."""

        record = ChatHistory(
            user_message=entry.user_message,
            ai_response=entry.ai_response,
            context_json=entry.context_json,
            learned_preferences_json=entry.learned_preferences_json,
            related_alert_id=entry.related_alert_id,
        )
        try:
            db.add(record)
            db.commit()
            db.refresh(record)
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("Unable to persist chat memory entry: %s", exc)
            raise
        return StoredChatMemoryEntry.from_orm(record)

    async def recall_entries(
        self,
        db: Session,
        *,
        limit: int = DEFAULT_MEMORY_LIMIT,
        related_alert_id: Optional[int] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> List[StoredChatMemoryEntry]:
        """Return past conversations that match the supplied criteria."""

        sanitized_limit = self._clamp_limit(limit)
        query = select(ChatHistory)
        if related_alert_id is not None:
            query = query.where(ChatHistory.related_alert_id == related_alert_id)

        patterns = self._keyword_patterns(keywords)
        if patterns:
            query = query.where(self._build_keyword_filter(patterns))

        query = query.order_by(desc(ChatHistory.timestamp)).limit(sanitized_limit)

        try:
            rows = db.execute(query).scalars().all()
        except SQLAlchemyError as exc:
            logger.exception("Failed to load chat memory: %s", exc)
            raise

        return [StoredChatMemoryEntry.from_orm(row) for row in rows]

    async def build_context_snippet(
        self,
        db: Session,
        *,
        limit: int = 3,
        related_alert_id: Optional[int] = None,
        keywords: Optional[Sequence[str]] = None,
        max_length: int = DEFAULT_SNIPPET_LENGTH,
        include_metadata: bool = True,
    ) -> str:
        """Create a textual snippet of relevant conversation history."""

        snippet_length = self._clamp_snippet_length(max_length)
        entries = await self.recall_entries(
            db,
            limit=limit,
            related_alert_id=related_alert_id,
            keywords=keywords,
        )
        if not entries:
            return ""

        sections: List[str] = []
        for memory in reversed(entries):
            header = memory.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            lines = [f"[{header}] User: {memory.user_message}", f"AI: {memory.ai_response}"]
            if include_metadata:
                if memory.related_alert_id:
                    lines.append(f"Alert ID: {memory.related_alert_id}")
                if memory.context_json:
                    lines.append(self._format_snapshot("Context", memory.context_json))
                if memory.learned_preferences_json:
                    lines.append(
                        self._format_snapshot("Preferences", memory.learned_preferences_json)
                    )
            sections.append("\n".join(lines))

        snippet = "\n\n".join(sections).strip()
        if len(snippet) > snippet_length:
            snippet = snippet[: snippet_length - 3] + "..."
        return snippet

    @staticmethod
    def _format_snapshot(label: str, payload: Dict[str, Any]) -> str:
        """Render JSON payloads into a concise string for context snippets."""

        snapshot = json.dumps(payload, default=str, indent=2)
        if len(snapshot) > 600:
            snapshot = snapshot[:600] + "..."
        return f"{label}: {snapshot}"

    @staticmethod
    def _keyword_patterns(keywords: Optional[Sequence[str]]) -> List[str]:
        """Prepare SQL wildcard patterns from user-provided keywords."""

        if not keywords:
            return []

        patterns: List[str] = []
        for keyword in keywords:
            cleaned = (keyword or "").strip()
            if not cleaned:
                continue
            sanitized = cleaned.replace("%", "").replace("_", "")
            if not sanitized:
                continue
            patterns.append(f"%{sanitized}%")
            if len(patterns) >= 5:
                break
        return patterns

    @staticmethod
    def _build_keyword_filter(patterns: Sequence[str]) -> Any:
        """Build an OR filter covering user and AI messages."""

        clauses = []
        for pattern in patterns:
            clauses.append(ChatHistory.user_message.ilike(pattern))
            clauses.append(ChatHistory.ai_response.ilike(pattern))
        return or_(*clauses)

    @staticmethod
    def _clamp_limit(value: int) -> int:
        """Clamp the requested memory window to a reasonable range."""

        return max(1, min(value, MAX_MEMORY_LIMIT))

    @staticmethod
    def _clamp_snippet_length(value: int) -> int:
        """Ensure the snippet length stays within configured bounds."""

        return max(MIN_SNIPPET_LENGTH, min(value, MAX_SNIPPET_LENGTH))

