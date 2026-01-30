"""News feed integration service for CryptoTrader."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence

import httpx
import openai
from anthropic import AI_PROMPT, Anthropic, HUMAN_PROMPT
from pydantic import BaseModel, BaseSettings, Field, HttpUrl, validator

logger = logging.getLogger(__name__)

DEFAULT_TRACKED_SYMBOLS = [
    "BTC",
    "ETH",
    "SOL",
    "ADA",
    "XRP",
    "LTC",
    "AVAX",
]


class NewsAIProvider(str, Enum):
    """Supported AI vendors for news relevance summaries."""

    OPENAI = "openai"
    CLAUDE = "claude"


def _env_provider() -> NewsAIProvider:
    candidate = os.getenv("NEWS_FEED_AI_PROVIDER", NewsAIProvider.OPENAI.value).lower()
    try:
        return NewsAIProvider(candidate)
    except ValueError:
        logger.warning(
            "Unknown NEWS_FEED_AI_PROVIDER=%s; defaulting to %s",
            candidate,
            NewsAIProvider.OPENAI.value,
        )
        return NewsAIProvider.OPENAI


class ApiKeyLocation(str, Enum):
    HEADER = "header"
    QUERY = "query"


class NewsSourceConfig(BaseModel):
    """Configuration for a single news source."""

    name: str
    url: HttpUrl
    method: Literal["GET", "POST"] = "GET"
    enabled: bool = True
    headers: Dict[str, str] = Field(default_factory=dict)
    params: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(10.0, gt=0)
    article_path: str = Field("articles")
    title_path: str = Field("title")
    description_path: str = Field("description")
    published_path: str = Field("publishedAt")
    url_path: str = Field("url")
    source_path: str = Field("source.name")
    api_key_env: Optional[str] = None
    api_key_name: str = Field("apiKey")
    api_key_location: ApiKeyLocation = ApiKeyLocation.QUERY
    max_articles: int = Field(10, ge=1, le=50)

    @validator("name", pre=True, always=True)
    def _strip_name(cls, value: str) -> str:
        return value.strip()

    @validator("headers", "params", pre=True)
    def _ensure_string_maps(cls, value: Any) -> Dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items() if k is not None}
        raise ValueError("headers/params must be dictionaries")


class NewsFeedSettings(BaseSettings):
    """Settings that control how news sources are fetched and summarized."""

    news_sources: List[NewsSourceConfig] = Field(default_factory=list)
    tracked_symbols: List[str] = Field(default_factory=lambda: DEFAULT_TRACKED_SYMBOLS.copy())
    request_timeout_seconds: float = Field(10.0, gt=0)
    summary_article_limit: int = Field(5, ge=1, le=15)
    summary_highlight_limit: int = Field(3, ge=1, le=10)

    class Config:  # noqa: D106
        env_file = ".env"
        extra = "ignore"

    @validator("tracked_symbols", pre=True)
    def _normalize_symbols(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, Iterable):
            items = value
        else:
            return []
        normalized: List[str] = []
        for item in items:
            if not item:
                continue
            symbol = str(item).strip().upper()
            if symbol and symbol not in normalized:
                normalized.append(symbol)
        return normalized


class NewsArticle(BaseModel):
    """Lightweight representation of a collected news item."""

    source: str
    title: str
    url: str = Field(..., min_length=1)
    summary: Optional[str] = None
    published_at: Optional[datetime] = None
    symbols: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:  # noqa: D106
        anystr_strip_whitespace = True


class NewsRelevanceSummary(BaseModel):
    summary: str
    signal: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    highlighted_symbols: List[str] = Field(default_factory=list)
    highlights: List[str] = Field(default_factory=list)
    provider: NewsAIProvider
    raw_response: str


class NewsFeedSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    articles: List[NewsArticle] = Field(default_factory=list)
    summary: Optional[NewsRelevanceSummary] = None


class NewsRelevanceAIService:
    """Wraps AI providers to summarize the relevance of a news batch."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        default_provider: Optional[NewsAIProvider] = None,
    ) -> None:
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self._anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self._default_provider = default_provider or _env_provider()
        self._openai_model = os.getenv("NEWS_FEED_AI_OPENAI_MODEL", "gpt-4o-mini")
        self._claude_model = os.getenv("NEWS_FEED_AI_CLAUDE_MODEL", "claude-3.5-sonic")

        if self._openai_api_key:
            openai.api_key = self._openai_api_key

        self._anthropic_client = (
            Anthropic(api_key=self._anthropic_api_key)
            if self._anthropic_api_key
            else None
        )

    async def summarize_articles(
        self,
        articles: Sequence[NewsArticle],
        focus_symbols: Sequence[str],
        max_articles: int,
        max_highlights: int,
    ) -> NewsRelevanceSummary:
        if not articles:
            raise ValueError("No articles provided to summarize")

        provider = self._select_provider()
        trimmed = list(articles)[:max_articles]
        prompt = self._build_prompt(trimmed, focus_symbols, max_highlights)
        if provider == NewsAIProvider.OPENAI:
            raw_response = await self._call_openai(prompt)
        else:
            raw_response = await self._call_claude(prompt)

        return self._build_summary(raw_response, provider, focus_symbols, max_highlights)

    def _select_provider(self, candidate: Optional[NewsAIProvider] = None) -> NewsAIProvider:
        preferred = candidate or self._default_provider
        if preferred and self._is_provider_available(preferred):
            return preferred

        for provider in NewsAIProvider:
            if self._is_provider_available(provider):
                return provider

        raise RuntimeError("No AI provider configured for news relevance summaries")

    def _is_provider_available(self, provider: NewsAIProvider) -> bool:
        if provider == NewsAIProvider.OPENAI:
            return bool(self._openai_api_key)
        if provider == NewsAIProvider.CLAUDE:
            return bool(self._anthropic_api_key and self._anthropic_client)
        return False

    async def _call_openai(self, prompt: str) -> str:
        if not self._openai_api_key:
            raise RuntimeError("OpenAI API key is not configured for news summaries")

        system_prompt = (
            "You are CryptoTrader's news relevance analyst. "
            "Rate the importance of recent summaries and return a concise JSON payload."
        )

        try:
            completion = await openai.ChatCompletion.acreate(
                model=self._openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.25,
                max_tokens=450,
            )
            return completion.choices[0].message.content.strip()
        except Exception as exc:
            logger.exception("OpenAI news summary failed: %s", exc)
            raise

    async def _call_claude(self, prompt: str) -> str:
        if not self._anthropic_client:
            raise RuntimeError("Anthropic client is not configured for news summaries")

        full_prompt = f"{HUMAN_PROMPT}{prompt}{AI_PROMPT}"
        try:
            response = await asyncio.to_thread(
                self._anthropic_client.completions.create,
                model=self._claude_model,
                prompt=full_prompt,
                max_tokens_to_sample=450,
                temperature=0.25,
            )
            return response.completion.strip()
        except Exception as exc:
            logger.exception("Claude news summary failed: %s", exc)
            raise

    def _build_prompt(
        self,
        articles: Sequence[NewsArticle],
        focus_symbols: Sequence[str],
        max_highlights: int,
    ) -> str:
        lines: List[str] = [
            "CryptoTrader News Relevance Summary",
            "Review the listed articles, prioritize the focus symbols,",
            "and return an actionable ranking.",
            "",
            f"Focus symbols: {', '.join(focus_symbols) if focus_symbols else 'None'}",
            "",
            "Articles:",
        ]

        for index, article in enumerate(articles, start=1):
            published = article.published_at.isoformat() if article.published_at else "unknown time"
            summary = article.summary or "No summary provided."
            lines.extend(
                [
                    f"{index}. {article.title}",
                    f"   Source: {article.source}",
                    f"   Published: {published}",
                    f"   Summary: {summary}",
                    f"   Link: {article.url}",
                ]
            )

        lines.extend(
            [
                "",
                "Return a JSON object with the keys:",
                "  summary (string)",
                "  signal (string describing directional tilt or urgency)",
                "  relevant_symbols (array of strings)",
                f"  highlights (array of up to {max_highlights} strings)",
                "  confidence (number between 0 and 1)",
                "Do not wrap the JSON in markdown fences or additional text.",
            ]
        )
        return "\n".join(lines)

    def _build_summary(
        self,
        raw_response: str,
        provider: NewsAIProvider,
        focus_symbols: Sequence[str],
        highlight_limit: int,
    ) -> NewsRelevanceSummary:
        payload: Dict[str, Any] = {}
        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("News summary AI returned non-JSON text")

        summary_text = (payload.get("summary") or raw_response).strip()
        signal = payload.get("signal")
        highlights = payload.get("highlights") or []
        if isinstance(highlights, str):
            highlights = [highlights]
        highlights = [str(item) for item in highlights][:highlight_limit]

        raw_symbols = payload.get("relevant_symbols") or payload.get("symbols") or []
        highlighted_symbols = self._normalize_symbol_list(raw_symbols, focus_symbols)
        confidence = self._safe_confidence(payload.get("confidence"))

        return NewsRelevanceSummary(
            summary=summary_text,
            signal=signal,
            confidence=confidence,
            highlighted_symbols=highlighted_symbols,
            highlights=highlights,
            provider=provider,
            raw_response=raw_response,
        )

    def _normalize_symbol_list(
        self,
        symbols: Any,
        focus_symbols: Sequence[str],
    ) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for symbol in focus_symbols:
            candidate = symbol.strip().upper()
            if candidate and candidate not in seen:
                normalized.append(candidate)
                seen.add(candidate)
        if isinstance(symbols, (list, tuple)):
            iterable = symbols
        else:
            iterable = [symbols]
        for entry in iterable:
            if not entry:
                continue
            candidate = str(entry).strip().upper()
            if candidate and candidate not in seen:
                normalized.append(candidate)
                seen.add(candidate)
        return normalized

    def _safe_confidence(self, value: Any) -> Optional[float]:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(confidence):
            return None
        if confidence < 0:
            return 0.0
        if confidence > 1:
            return 1.0
        return confidence


class NewsFeedService:
    """Periodically pulls news from configured sources and summarizes relevance."""

    def __init__(
        self,
        settings: Optional[NewsFeedSettings] = None,
        ai_service: Optional[NewsRelevanceAIService] = None,
    ) -> None:
        self.settings = settings or NewsFeedSettings()
        self._client = httpx.AsyncClient(timeout=self.settings.request_timeout_seconds)
        self._ai_service = ai_service or NewsRelevanceAIService()

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception as exc:
            logger.debug("Failed to close news feed HTTP client: %s", exc)

    async def collect(self) -> NewsFeedSnapshot:
        articles = await self.fetch_articles()
        summary: Optional[NewsRelevanceSummary] = None
        if articles:
            try:
                summary = await self._ai_service.summarize_articles(
                    articles,
                    focus_symbols=self.settings.tracked_symbols,
                    max_articles=self.settings.summary_article_limit,
                    max_highlights=self.settings.summary_highlight_limit,
                )
            except Exception as exc:
                logger.exception("News relevance summarization failed: %s", exc)
        return NewsFeedSnapshot(articles=articles, summary=summary)

    async def fetch_articles(self) -> List[NewsArticle]:
        if not self.settings.news_sources:
            return []
        tasks = [self._fetch_from_source(source) for source in self.settings.news_sources if source.enabled]
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        articles: List[NewsArticle] = []
        for result in results:
            if isinstance(result, Exception):
                logger.exception("News source fetch raised: %s", result)
                continue
            articles.extend(result)
        return articles

    async def _fetch_from_source(self, source: NewsSourceConfig) -> List[NewsArticle]:
        params = {k: str(v) for k, v in source.params.items()}
        headers = {k: str(v) for k, v in source.headers.items()}
        api_key = self._resolve_api_key(source)
        if api_key:
            if source.api_key_location == ApiKeyLocation.HEADER:
                headers[source.api_key_name] = api_key
            else:
                params[source.api_key_name] = api_key

        try:
            response = await self._client.request(
                source.method,
                str(source.url),
                params=params or None,
                headers=headers or None,
                timeout=source.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("Failed to fetch news from %s: %s", source.name, exc)
            return []

        try:
            payload = response.json()
        except ValueError as exc:
            logger.exception("News source %s returned invalid JSON: %s", source.name, exc)
            return []

        raw_articles = self._traverse_path(payload, source.article_path)
        if not isinstance(raw_articles, list):
            return []

        collected: List[NewsArticle] = []
        for entry in raw_articles[: source.max_articles]:
            if not isinstance(entry, dict):
                continue
            title = self._extract_string(entry, source.title_path) or source.name
            article_url = self._extract_string(entry, source.url_path)
            if not article_url:
                continue
            description = self._extract_string(entry, source.description_path)
            published_at = self._parse_datetime(self._extract_string(entry, source.published_path))
            source_label = self._extract_string(entry, source.source_path) or source.name
            symbols = self._infer_symbols(entry, title, description)
            collected.append(
                NewsArticle(
                    source=source_label,
                    title=title,
                    url=article_url,
                    summary=description,
                    published_at=published_at,
                    symbols=symbols,
                    metadata={"source_config": source.name, "raw": entry},
                )
            )
        return collected

    def _resolve_api_key(self, source: NewsSourceConfig) -> Optional[str]:
        if not source.api_key_env:
            return None
        value = os.getenv(source.api_key_env)
        return value.strip() if value and value.strip() else None

    def _traverse_path(self, payload: Any, path: str) -> Any:
        if not path:
            return payload
        current: Any = payload
        for segment in path.split("."):
            if segment == "":
                continue
            if isinstance(current, dict):
                current = current.get(segment)
            else:
                return None
        return current

    def _extract_string(self, payload: Dict[str, Any], path: str) -> Optional[str]:
        value = self._traverse_path(payload, path)
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text if text else None
        return str(value).strip() or None

    def _parse_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z") and "+" not in text:
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            try:
                return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                return None

    def _infer_symbols(
        self,
        entry: Dict[str, Any],
        title: str,
        description: Optional[str],
    ) -> List[str]:
        matches: List[str] = []
        seen: set[str] = set()
        text = " ".join(filter(None, [title, description or ""]))
        for symbol in self.settings.tracked_symbols:
            if not symbol:
                continue
            pattern = rf"\b{re.escape(symbol)}\b"
            if re.search(pattern, text, flags=re.IGNORECASE):
                if symbol not in seen:
                    matches.append(symbol)
                    seen.add(symbol)
        for key in ("symbols", "tickers", "coins"):
            raw = entry.get(key)
            if not raw:
                continue
            candidates = raw if isinstance(raw, list) else [raw]
            for candidate in candidates:
                if not candidate:
                    continue
                normalized = str(candidate).strip().upper()
                if normalized and normalized not in seen:
                    matches.append(normalized)
                    seen.add(normalized)
        return matches
