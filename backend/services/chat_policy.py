"""Policy engine for chat guardrails and response modes."""

from __future__ import annotations

from typing import Any, Dict, List


class ChatPolicyEngine:
    """Evaluates prompt + context and emits deterministic chat policy decisions."""

    def evaluate(self, *, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        text = prompt.strip()
        normalized = text.lower()

        stale_context = bool(context.get("stale_context"))
        incomplete_context = bool(context.get("incomplete_context"))
        refusal_reasons = list(context.get("refusal_reasons") or [])
        missing_fields = list(context.get("missing_fields") or [])

        elevated_risk = self._is_elevated_risk(context)
        is_broad_prompt = self._is_broad_prompt(normalized)
        recommendation_request = self._is_recommendation_request(normalized)
        aggressive_request = self._is_aggressive_request(normalized)
        include_confidence = self._wants_confidence(normalized)
        tone_marker = self._tone_marker(normalized)

        if stale_context or incomplete_context:
            return {
                "mode": "refuse",
                "depth": "medium",
                "clarifying_question": None,
                "recommendations": None,
                "trade_explanation_style": tone_marker,
                "guardrail": {
                    "stale_context": stale_context,
                    "incomplete_context": incomplete_context,
                    "elevated_risk": elevated_risk,
                    "aggressive_request": aggressive_request,
                    "refusal_reason": self._refusal_reason(refusal_reasons),
                    "missing_fields": missing_fields,
                },
                "include_confidence": False,
            }

        if is_broad_prompt:
            return {
                "mode": "clarify",
                "depth": "medium",
                "clarifying_question": (
                    "Do you want a tactical session update or a 24h/7d performance breakdown?"
                ),
                "recommendations": None,
                "trade_explanation_style": tone_marker,
                "guardrail": {
                    "stale_context": False,
                    "incomplete_context": False,
                    "elevated_risk": elevated_risk,
                    "aggressive_request": aggressive_request,
                    "refusal_reason": None,
                    "missing_fields": [],
                },
                "include_confidence": False,
            }

        recommendations = self._recommendations(
            recommendation_request=recommendation_request,
            elevated_risk=elevated_risk,
            aggressive_request=aggressive_request,
        )

        return {
            "mode": "answer",
            "depth": "medium",
            "clarifying_question": None,
            "recommendations": recommendations,
            "trade_explanation_style": tone_marker,
            "guardrail": {
                "stale_context": False,
                "incomplete_context": False,
                "elevated_risk": elevated_risk,
                "aggressive_request": aggressive_request,
                "refusal_reason": None,
                "missing_fields": [],
            },
            "include_confidence": include_confidence,
        }

    def _is_broad_prompt(self, prompt: str) -> bool:
        broad_patterns = (
            "how am i doing",
            "what should i do",
            "what do you think",
            "update me",
            "status update",
        )
        return any(pattern in prompt for pattern in broad_patterns)

    def _is_recommendation_request(self, prompt: str) -> bool:
        keywords = (
            "should i",
            "recommend",
            "buy",
            "sell",
            "what should",
            "take action",
        )
        return any(keyword in prompt for keyword in keywords)

    def _is_aggressive_request(self, prompt: str) -> bool:
        aggressive_keywords = (
            "all in",
            "double down",
            "high leverage",
            "max leverage",
            "full size",
            "yolo",
            "aggressive",
        )
        return any(keyword in prompt for keyword in aggressive_keywords)

    def _wants_confidence(self, prompt: str) -> bool:
        return "confidence" in prompt or "how sure" in prompt

    def _tone_marker(self, prompt: str) -> str:
        if any(token in prompt for token in ("losing", "loss", "down", "underwater")):
            return "clinical_factual"
        return "standard"

    def _is_elevated_risk(self, context: Dict[str, Any]) -> bool:
        snapshot = context.get("risk_snapshot") or {}
        status = str(snapshot.get("status") or "").lower()
        ratio = float(snapshot.get("risk_ratio") or 0.0)
        return status == "alert" or ratio >= 0.85

    def _refusal_reason(self, refusal_reasons: List[str]) -> str:
        if not refusal_reasons:
            return "missing_required_context"
        return sorted(set(refusal_reasons))[0]

    def _recommendations(
        self,
        *,
        recommendation_request: bool,
        elevated_risk: bool,
        aggressive_request: bool,
    ) -> Dict[str, Any]:
        if elevated_risk:
            primary = {
                "action": "hold",
                "rationale": "Risk posture is elevated, so preserving capital is the default action.",
            }
            backup = {
                "action": "reduce_exposure",
                "rationale": (
                    "Trim weaker positions and wait for risk metrics to normalize before adding risk."
                    if aggressive_request
                    else "If action is required, reduce exposure in the most volatile position first."
                ),
            }
            return {
                "primary": primary,
                "backup": backup,
                "portfolio_impact": "Lower net exposure and reduced downside variance.",
            }

        if recommendation_request:
            primary = {
                "action": "adjust",
                "rationale": "Scale into the highest-conviction setup using existing risk limits.",
            }
            backup = {
                "action": "hold",
                "rationale": "Wait for additional confirmation if momentum weakens.",
            }
            return {
                "primary": primary,
                "backup": backup,
                "portfolio_impact": "May increase position size and directional exposure.",
            }

        return {
            "primary": {"action": "hold", "rationale": "No position change requested."},
            "backup": {"action": "observe", "rationale": "Monitor market conditions for clearer setups."},
            "portfolio_impact": None,
        }
