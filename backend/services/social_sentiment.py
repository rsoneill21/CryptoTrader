"""Social media sentiment integration via Twitter/X and Reddit APIs."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

import httpx
from httpx import BasicAuth
from pydantic import BaseModel, BaseSettings, Field, validator

logger = logging.getLogger(__name__)

POSITIVE_KEYWORDS = [
    "bull",
    "bullish",
    "pump",
    "moon",
    "breakout",
    "green",
    "surge",
    "rally",
    "support",
    "long",
]

NEGATIVE_KEYWORDS = [
    "bear",
    "bearish",
    "dump",
    "crash",
    "selloff",
    "drop",
    "resistance",
    "short",
    "rejection",
    "liquidate",
]

DEFAULT_SYMBOL_KEYWORDS = {
    "BTC": ["bitcoin"],
    "ETH": ["ethereum"],
    "SOL": ["solana"],
    "ADA": ["cardano"],
    "XRP": ["ripple"],
    "DOGE": ["dogecoin"],
    "LTC": ["litecoin"],
    "AVAX": ["avalanche"],
    "LINK": ["chainlink"],
}

DEFAULT_REDDIT_SUBREDDITS = ["CryptoCurrency", "CryptoMarkets"]

DEFAULT_TWITTER_ADDITIONAL_TERMS = ["crypto", "defi", "onchain", "web3"]


class SocialMention(BaseModel):
    """Lightweight structure describing a social media mention."""

    source: str
    text: str
    symbol: Optional[str]
    sentiment_score: float
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SocialSentimentSettings(BaseSettings):
    """Configuration for the social sentiment service."""

    twitter_bearer_token: Optional[str] = Field(None, env="TWITTER_BEARER_TOKEN")
    twitter_query: Optional[str] = Field(None)
    twitter_max_results: int = Field(25, ge=5, le=100)
    twitter_recent_minutes: int = Field(60, ge=1, le=1440)

    reddit_client_id: Optional[str] = Field(None, env="REDDIT_CLIENT_ID")
    reddit_client_secret: Optional[str] = Field(None, env="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field("CryptoTrader/1.0", env="REDDIT_USER_AGENT")
    reddit_subreddits: List[str] = Field(default_factory=lambda: DEFAULT_REDDIT_SUBREDDITS.copy())
    reddit_post_limit: int = Field(25, ge=5, le=100)

    tracked_symbols: List[str] = Field(default_factory=lambda: list(DEFAULT_SYMBOL_KEYWORDS.keys()))
    tracked_keywords: List[str] = Field(default_factory=lambda: DEFAULT_TWITTER_ADDITIONAL_TERMS.copy())

    class Config:  # noqa: D106
        env_file = ".env"
        extra = "ignore"

    @validator("tracked_symbols", pre=True)
    def _normalize_symbols(cls, value: Any) -> List[str]:
        if isinstance(value, str):
            parsed = [segment.strip().upper() for segment in value.split(",") if segment.strip()]
            return parsed
        if isinstance(value, Iterable):
            normalized: List[str] = []
            for segment in value:
                if not segment:
                    continue
                normalized.append(str(segment).strip().upper())
            return normalized
        return []

    @validator("tracked_keywords", pre=True)
    def _normalize_keywords(cls, value: Any) -> List[str]:
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
            entry = str(item).strip().lower()
            if entry and entry not in normalized:
                normalized.append(entry)
        return normalized

    @validator("reddit_subreddits", pre=True)
    def _normalize_subreddits(cls, value: Any) -> List[str]:
        if isinstance(value, str):
            segments = [value]
        elif isinstance(value, Iterable):
            segments = value
        else:
            return []
        normalized: List[str] = []
        for segment in segments:
            if not segment:
                continue
            cleaned = str(segment).strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized

    @property
    def twitter_query_final(self) -> str:
        if self.twitter_query and self.twitter_query.strip():
            return self.twitter_query.strip()
        symbol_terms: List[str] = []
        seen: set[str] = set()
        for symbol in self.tracked_symbols:
            if not symbol:
                continue
            for variant in self._symbol_variants(symbol):
                normalized = variant.lower()
                if normalized in seen:
                    continue
                seen.add(normalized)
                symbol_terms.append(variant)
        for keyword in self.tracked_keywords:
            normalized = keyword.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            symbol_terms.append(keyword)
        if not symbol_terms:
            return "crypto"
        return " OR ".join(symbol_terms)

    @property
    def twitter_enabled(self) -> bool:
        return bool(self.twitter_bearer_token and self.twitter_query_final)

    @property
    def reddit_enabled(self) -> bool:
        return bool(self.reddit_client_id and self.reddit_client_secret)

    @staticmethod
    def _symbol_variants(symbol: str) -> List[str]:
        base = symbol.strip().upper()
        variants: List[str] = [base, f"${base}"]
        for alias in DEFAULT_SYMBOL_KEYWORDS.get(base, []):
            alias_str = alias.strip()
            if alias_str:
                variants.append(alias_str)
        return list(dict.fromkeys(variants))


class SocialSentimentService:
    """Async service that pulls mentions from Twitter/X and Reddit."""

    def __init__(self, settings: Optional[SocialSentimentSettings] = None) -> None:
        self.settings = settings or SocialSentimentSettings()
        self._client = httpx.AsyncClient(timeout=10.0)
        self._reddit_token: Optional[str] = None
        self._reddit_token_expires: Optional[datetime] = None

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception as exc:
            logger.debug("Failed to close HTTP client: %s", exc)

    async def collect_mentions(self) -> List[SocialMention]:
        tasks = [self.fetch_twitter_mentions(), self.fetch_reddit_mentions()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        mentions: List[SocialMention] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Social mention gatherer raised: %s", result)
                continue
            mentions.extend(result)
        return mentions

    async def fetch_twitter_mentions(self) -> List[SocialMention]:
        if not self.settings.twitter_enabled:
            logger.debug("Twitter integration not configured; skipping fetch")
            return []

        url = "https://api.twitter.com/2/tweets/search/recent"
        start_time = (
            datetime.utcnow() - timedelta(minutes=self.settings.twitter_recent_minutes)
        ).replace(microsecond=0).isoformat() + "Z"
        params = {
            "query": f"({self.settings.twitter_query_final}) lang:en -is:retweet",
            "max_results": str(self.settings.twitter_max_results),
            "start_time": start_time,
            "tweet.fields": "created_at,author_id,public_metrics,entities",
        }
        headers = {"Authorization": f"Bearer {self.settings.twitter_bearer_token}"}

        try:
            response = await self._client.get(url, headers=headers, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Twitter fetch failed: %s", exc)
            return []

        payload = response.json()
        tweets = payload.get("data", []) or []
        mentions: List[SocialMention] = []
        for tweet in tweets:
            text = tweet.get("text") or ""
            if not text.strip():
                continue
            mention = SocialMention(
                source="twitter",
                text=text,
                symbol=self._extract_symbol(text),
                sentiment_score=self._score_text(text),
                timestamp=self._parse_iso_timestamp(tweet.get("created_at")),
                metadata={
                    "tweet_id": tweet.get("id"),
                    "author_id": tweet.get("author_id"),
                    "public_metrics": tweet.get("public_metrics"),
                    "entities": tweet.get("entities"),
                },
            )
            mentions.append(mention)
        return mentions

    async def fetch_reddit_mentions(self) -> List[SocialMention]:
        if not self.settings.reddit_enabled:
            logger.debug("Reddit integration not configured; skipping fetch")
            return []

        token = await self._ensure_reddit_token()
        if not token:
            return []

        headers = {
            "Authorization": f"bearer {token}",
            "User-Agent": self.settings.reddit_user_agent,
        }
        mentions: List[SocialMention] = []
        for subreddit in self.settings.reddit_subreddits:
            url = f"https://oauth.reddit.com/r/{subreddit}/new"
            params = {"limit": self.settings.reddit_post_limit}
            try:
                response = await self._client.get(url, headers=headers, params=params)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Reddit fetch for %s failed: %s", subreddit, exc)
                continue

            payload = response.json()
            posts = payload.get("data", {}).get("children", []) or []
            mentions.extend(self._normalize_reddit_posts(posts, subreddit))
        return mentions

    async def _ensure_reddit_token(self) -> Optional[str]:
        now = datetime.utcnow()
        if self._reddit_token and self._reddit_token_expires and now < self._reddit_token_expires:
            return self._reddit_token
        auth_url = "https://www.reddit.com/api/v1/access_token"
        if not (self.settings.reddit_client_id and self.settings.reddit_client_secret):
            return None
        data = {"grant_type": "client_credentials"}
        auth = BasicAuth(self.settings.reddit_client_id, self.settings.reddit_client_secret)
        try:
            response = await self._client.post(
                auth_url,
                data=data,
                auth=auth,
                headers={"User-Agent": self.settings.reddit_user_agent},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Reddit auth failed: %s", exc)
            return None

        payload = response.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not token:
            logger.warning("Reddit auth response missing token: %s", payload)
            return None
        self._reddit_token = token
        self._reddit_token_expires = now + timedelta(seconds=max(0, expires_in - 5))
        return token

    def _normalize_reddit_posts(self, posts: List[Dict[str, Any]], subreddit: str) -> List[SocialMention]:
        mentions: List[SocialMention] = []
        for child in posts:
            data = child.get("data") or {}
            title = data.get("title", "")
            body = data.get("selftext", "")
            text = "\n".join(part for part in (title, body) if part).strip()
            if not text:
                continue
            mention = SocialMention(
                source="reddit",
                text=text,
                symbol=self._extract_symbol(text),
                sentiment_score=self._score_text(text),
                timestamp=self._utc_from_epoch(data.get("created_utc")),
                metadata={
                    "subreddit": subreddit,
                    "post_id": data.get("id"),
                    "author": data.get("author"),
                    "permalink": data.get("permalink"),
                    "score": data.get("score"),
                },
            )
            mentions.append(mention)
        return mentions

    def _extract_symbol(self, text: str) -> Optional[str]:
        normalized = text.lower()
        for symbol in self.settings.tracked_symbols:
            if not symbol:
                continue
            for term in self._symbol_match_terms(symbol):
                if term and term in normalized:
                    return symbol
        return None

    @staticmethod
    def _symbol_match_terms(symbol: str) -> List[str]:
        base = symbol.lower()
        variants = {base, f"${base}"}
        for alias in DEFAULT_SYMBOL_KEYWORDS.get(symbol.upper(), []):
            alias_clean = alias.lower().strip()
            if alias_clean:
                variants.add(alias_clean)
        return list(variants)

    @staticmethod
    def _score_text(text: str) -> float:
        tokens = re.findall(r"\b\w+\b", text.lower())
        if not tokens:
            return 0.0
        pos_hits = sum(1 for token in tokens if token in POSITIVE_KEYWORDS)
        neg_hits = sum(1 for token in tokens if token in NEGATIVE_KEYWORDS)
        magnitude = max(1, pos_hits + neg_hits)
        raw_score = (pos_hits - neg_hits) / magnitude
        return max(-1.0, min(1.0, raw_score))

    @staticmethod
    def _parse_iso_timestamp(value: Optional[str]) -> datetime:
        if not value:
            return datetime.utcnow()
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[: -1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return datetime.utcnow()

    @staticmethod
    def _utc_from_epoch(value: Any) -> datetime:
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return datetime.utcnow()
        return datetime.utcfromtimestamp(timestamp)


social_sentiment_service = SocialSentimentService()
