"""GitHub strategy import helpers for the AI strategy lab."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, List, NamedTuple, Optional, Sequence
from urllib.parse import unquote, urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.strategy_ai import StrategyProposal, StrategyProposalInput, strategy_ai_service


try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11 should have tomllib but guard just in case
    tomllib = None


try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency for YAML parsing
    yaml = None


logger = logging.getLogger(__name__)


SUPPORTED_EXTENSIONS: Sequence[str] = (".json", ".yml", ".yaml", ".toml", ".strategy", ".rules", ".cfg")
DEFAULT_MAX_FILES = 8
DEFAULT_MAX_FILE_BYTES = 200_000
DEFAULT_TIMEOUT = 15.0


class GitHubImportError(Exception):
    """Raised when parsing or GitHub fetching fails."""


class _ParsedGitHubTarget(NamedTuple):
    owner: str
    repo: str
    branch: Optional[str]
    path: str
    mode: str


class GitHubStrategyDefinition(BaseModel):
    """Normalized representation of an imported strategy definition."""

    model_config = ConfigDict(extra="allow")

    name: Optional[str]
    description: Optional[str]
    rules: Dict[str, Any] = Field(default_factory=dict)
    symbols: List[str] = Field(default_factory=list)
    timeframe: Optional[str]
    risk_tolerance: Optional[str]
    preferred_indicators: List[str] = Field(default_factory=list)
    target_return_pct: Optional[float]
    max_positions: Optional[int]
    notes: Optional[str]


class GitHubStrategyAnalysis(BaseModel):
    """Analysis produced for a single strategy file."""

    path: str
    name: str
    definition: GitHubStrategyDefinition
    ai_insights: Optional[StrategyProposal]
    ai_error: Optional[str]


class GitHubImportReport(BaseModel):
    """Summary of a GitHub strategy import attempt."""

    source_url: str
    branch: Optional[str]
    candidates: List[GitHubStrategyAnalysis] = Field(default_factory=list)
    failures: List[str] = Field(default_factory=list)


class GitHubImportService:
    """Handles fetching strategy files from GitHub and asking the AI for annotations."""

    def __init__(
        self,
        github_token: Optional[str] = None,
        max_file_count: Optional[int] = None,
        max_file_bytes: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._token = github_token or os.getenv("GITHUB_IMPORT_TOKEN") or os.getenv("GITHUB_TOKEN")
        self._max_file_count = self._coerce_positive(max_file_count, DEFAULT_MAX_FILES)
        self._max_file_bytes = self._coerce_positive(max_file_bytes, DEFAULT_MAX_FILE_BYTES)
        self._timeout = timeout or DEFAULT_TIMEOUT

    async def import_strategies(self, github_url: str) -> GitHubImportReport:
        """Fetch strategies under the supplied GitHub URL and request AI adjustments."""
        parsed = self._parse_github_url(github_url)
        report = GitHubImportReport(source_url=github_url, branch=parsed.branch or None)

        async with httpx.AsyncClient(timeout=self._timeout, headers=self._request_headers) as client:
            branch = parsed.branch
            if not branch:
                branch = await self._fetch_default_branch(client, parsed.owner, parsed.repo)
                report.branch = branch

            if parsed.mode == "blob":
                if not parsed.path:
                    report.failures.append("Blob URL must include a file path")
                    return report
                await self._process_file(client, parsed.owner, parsed.repo, branch, parsed.path, report)
                return report

            tree = await self._fetch_tree(client, parsed.owner, parsed.repo, branch)
            candidates = self._collect_candidates(tree, parsed.path)

            for file_path in candidates[: self._max_file_count]:
                await self._process_file(client, parsed.owner, parsed.repo, branch, file_path, report)

        return report

    @property
    def _request_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CryptoTrader GitHub Import",
        }
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    async def _fetch_default_branch(
        self, client: httpx.AsyncClient, owner: str, repo: str
    ) -> str:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        try:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Default branch fetch failed %s/%s: %s", owner, repo, exc)
            raise GitHubImportError("Unable to determine repository default branch") from exc
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Default branch fetch unexpected failure: %s", exc)
            raise GitHubImportError("Unable to determine repository default branch") from exc

        branch = payload.get("default_branch")
        if not branch:
            raise GitHubImportError("Repository metadata lacks a default branch")
        return branch

    async def _fetch_tree(
        self, client: httpx.AsyncClient, owner: str, repo: str, branch: str
    ) -> Dict[str, Any]:
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Tree fetch failed %s/%s@%s: %s", owner, repo, branch, exc)
            raise GitHubImportError("Unable to traverse repository tree") from exc
        except Exception as exc:  # pragma: no cover
            logger.exception("Tree fetch unexpected failure: %s", exc)
            raise GitHubImportError("Unable to traverse repository tree") from exc

    def _collect_candidates(self, tree: Dict[str, Any], prefix: str) -> List[str]:
        entries = tree.get("tree", [])
        normalized_prefix = prefix.strip("/")
        if normalized_prefix:
            normalized_prefix = normalized_prefix.rstrip("/")

        candidates: List[str] = []
        for entry in entries:
            if entry.get("type") != "blob":
                continue
            path = entry.get("path")
            if not path:
                continue
            if normalized_prefix and not path.startswith(normalized_prefix):
                continue
            if not self._is_supported_file(path):
                continue
            if entry.get("size", 0) > self._max_file_bytes:
                continue
            candidates.append(path)
        return candidates

    async def _process_file(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        branch: str,
        file_path: str,
        report: GitHubImportReport,
    ) -> None:
        try:
            raw = await self._fetch_file(client, owner, repo, branch, file_path)
            payload = self._parse_strategy_payload(raw, file_path)
            definition = GitHubStrategyDefinition(**payload)
        except GitHubImportError as exc:
            report.failures.append(f"{file_path}: {exc}")
            return
        except ValidationError as exc:
            report.failures.append(f"{file_path}: Strategy schema invalid ({exc})")
            return

        ai_insights: Optional[StrategyProposal] = None
        ai_error: Optional[str] = None
        try:
            ai_insights = await self._review_with_ai(definition)
        except Exception as exc:  # pragma: no cover - ensure AI failures don't abort import
            ai_error = str(exc)
            logger.warning("AI review failed for %s: %s", file_path, ai_error)

        report.candidates.append(
            GitHubStrategyAnalysis(
                path=file_path,
                name=definition.name or os.path.basename(file_path),
                definition=definition,
                ai_insights=ai_insights,
                ai_error=ai_error,
            )
        )

    async def _fetch_file(
        self, client: httpx.AsyncClient, owner: str, repo: str, branch: str, file_path: str
    ) -> str:
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
        try:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content")
            if not content:
                raise GitHubImportError("File content was empty")
            encoding = payload.get("encoding", "base64")
        except httpx.HTTPStatusError as exc:
            logger.error("Content fetch failed %s/%s@%s:%s: %s", owner, repo, branch, file_path, exc)
            raise GitHubImportError("Unable to download file contents") from exc
        except Exception as exc:  # pragma: no cover
            logger.exception("Content fetch unexpected failure: %s", exc)
            raise GitHubImportError("Unable to download file contents") from exc

        try:
            if encoding.lower() == "base64":
                return base64.b64decode(content).decode("utf-8")
            return content
        except Exception as exc:
            logger.exception("Content decoding failed for %s: %s", file_path, exc)
            raise GitHubImportError("Unable to decode file contents") from exc

    def _parse_strategy_payload(self, raw: str, file_path: str) -> Dict[str, Any]:
        text = raw.strip()
        if not text:
            raise GitHubImportError("File contains no readable characters")

        for parser in (self._safe_json_load, self._safe_toml_load, self._safe_yaml_load):
            data = parser(text)
            if data is not None:
                if isinstance(data, dict):
                    return data
                raise GitHubImportError("Strategy definition must be a JSON/TOML/YAML object")

        raise GitHubImportError("Strategy definition could not be parsed")

    def _safe_json_load(self, text: str) -> Optional[Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _safe_toml_load(self, text: str) -> Optional[Any]:
        if not tomllib:
            return None
        try:
            return tomllib.loads(text)
        except Exception:  # pragma: no cover
            return None

    def _safe_yaml_load(self, text: str) -> Optional[Any]:
        if not yaml:
            return None
        try:
            return yaml.safe_load(text)
        except Exception:  # pragma: no cover
            return None

    async def _review_with_ai(self, definition: GitHubStrategyDefinition) -> StrategyProposal:
        request = self._build_ai_request(definition)
        return await strategy_ai_service.propose_strategy(request)

    def _build_ai_request(self, definition: GitHubStrategyDefinition) -> StrategyProposalInput:
        symbols = definition.symbols or ["UNKNOWN"]
        return StrategyProposalInput(
            symbols=symbols,
            timeframe=definition.timeframe or "1h",
            market_summary=self._compile_summary(definition),
            risk_tolerance=definition.risk_tolerance or "balanced",
            preferred_indicators=definition.preferred_indicators,
            target_return_pct=definition.target_return_pct,
            max_positions=definition.max_positions or 3,
            notes=(definition.notes or "Please review the existing strategy and suggest improvements."),
        )

    def _compile_summary(self, definition: GitHubStrategyDefinition) -> str:
        description = definition.description or "No description provided"
        rules_snapshot = self._format_rules(definition.rules)
        summary = [
            f"Name: {definition.name or 'Unnamed strategy'}",
            f"Description: {description.strip()}",
            f"Symbols: {', '.join(definition.symbols or ['UNKNOWN'])}",
            f"Timeframe: {definition.timeframe or '1h'}",
            f"Risk tolerance: {definition.risk_tolerance or 'balanced'}",
            f"Target return: {definition.target_return_pct or 'unspecified'}",
            f"Max positions: {definition.max_positions or 3}",
            "Rules snapshot:",
            rules_snapshot,
        ]
        return "\n".join(summary)

    def _format_rules(self, rules: Dict[str, Any]) -> str:
        if not rules:
            return "<no structured rules detected>"
        try:
            text = json.dumps(rules, indent=2, default=str)
        except TypeError:
            text = str(rules)
        return self._truncate(text)

    @staticmethod
    def _truncate(text: str, max_length: int = 1400) -> str:
        return text if len(text) <= max_length else f"{text[: max_length - 1]}…"

    @staticmethod
    def _coerce_positive(value: Optional[int], fallback: int) -> int:
        if value is None:
            return fallback
        if value <= 0:
            return fallback
        return value

    @staticmethod
    def _is_supported_file(path: str) -> bool:
        normalized = path.lower()
        return any(normalized.endswith(ext) for ext in SUPPORTED_EXTENSIONS)

    def _parse_github_url(self, github_url: str) -> _ParsedGitHubTarget:
        parsed = urlparse(github_url)
        host = parsed.netloc.lower()
        raw_path = parsed.path or ""
        segments = [unquote(part) for part in raw_path.split("/") if part]

        if "github.com" in host:
            return self._parse_standard_github(segments)
        if "raw.githubusercontent.com" in host:
            return self._parse_raw_github(segments)
        raise GitHubImportError("URL must point to github.com or raw.githubusercontent.com")

    def _parse_standard_github(self, segments: Sequence[str]) -> _ParsedGitHubTarget:
        if len(segments) < 2:
            raise GitHubImportError("GitHub URL must include owner and repository")

        owner = segments[0]
        repo = segments[1].removesuffix(".git")
        branch: Optional[str] = None
        file_path = ""
        mode = "tree"

        if len(segments) >= 4 and segments[2] in {"tree", "blob"}:
            mode = segments[2]
            branch = segments[3]
            file_path = "/".join(segments[4:]).strip("/")
        elif len(segments) > 2:
            file_path = "/".join(segments[2:]).strip("/")

        return _ParsedGitHubTarget(owner=owner, repo=repo, branch=branch, path=file_path, mode=mode)

    def _parse_raw_github(self, segments: Sequence[str]) -> _ParsedGitHubTarget:
        if len(segments) < 4:
            raise GitHubImportError("Raw GitHub URL must include owner, repo, branch, and path")
        owner = segments[0]
        repo = segments[1]
        branch = segments[2]
        file_path = "/".join(segments[3:]).strip("/")
        return _ParsedGitHubTarget(owner=owner, repo=repo, branch=branch, path=file_path, mode="blob")
