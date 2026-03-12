"""Response normalization and rendering for chat payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


class ChatResponseNormalizer:
    """Normalizes policy + model output into a stable chat response contract."""

    def normalize(
        self,
        *,
        policy: Dict[str, Any],
        context: Dict[str, Any],
        model_output: Optional[Dict[str, Any]] = None,
        prompt: str = "",
    ) -> Dict[str, Any]:
        payload = model_output or {}
        mode = policy.get("mode")
        if mode not in {"clarify", "answer", "refuse"}:
            raise ValueError("Policy mode must be one of clarify, answer, or refuse")

        if mode == "clarify":
            question = policy.get("clarifying_question")
            if not question:
                raise ValueError("Clarify mode requires a clarifying question")
            return {
                "mode": "clarify",
                "timeframe_used": context.get("timeframe_used"),
                "summary_paragraph": question,
                "bullets": [],
                "recommendations": None,
                "trade_explanation": None,
                "guardrail": policy.get("guardrail", {}),
                "meta": self._meta(payload),
            }

        if mode == "refuse":
            reason = (policy.get("guardrail") or {}).get("refusal_reason")
            summary = (
                f"I cannot provide a recommendation until context is refreshed ({reason})."
                if reason
                else "I cannot provide a recommendation until context is refreshed."
            )
            return {
                "mode": "refuse",
                "timeframe_used": context.get("timeframe_used"),
                "summary_paragraph": summary,
                "bullets": [],
                "recommendations": None,
                "trade_explanation": None,
                "guardrail": policy.get("guardrail", {}),
                "meta": self._meta(payload),
            }

        summary_paragraph = str(payload.get("summary_paragraph") or "").strip()
        if not summary_paragraph:
            raise ValueError("Answer mode requires summary_paragraph")

        bullets = self._normalize_bullets(payload.get("bullets") or [])
        recommendations = self._normalize_recommendations(policy.get("recommendations") or {})
        trade_explanation = self._normalize_trade_explanation(
            payload.get("trade_explanation") or {},
            prompt=prompt,
            include_confidence=bool(policy.get("include_confidence")),
        )

        return {
            "mode": "answer",
            "timeframe_used": context.get("timeframe_used"),
            "summary_paragraph": summary_paragraph,
            "bullets": bullets,
            "recommendations": recommendations,
            "trade_explanation": trade_explanation,
            "guardrail": policy.get("guardrail", {}),
            "meta": self._meta(payload),
        }

    def render_hybrid(self, contract: Dict[str, Any]) -> str:
        mode = contract.get("mode")
        if mode in {"clarify", "refuse"}:
            return str(contract.get("summary_paragraph") or "")

        lines = [str(contract.get("summary_paragraph") or "").strip()]
        for bullet in contract.get("bullets") or []:
            label = bullet.get("label")
            text = bullet.get("text")
            if label:
                lines.append(f"- {label}: {text}")
            else:
                lines.append(f"- {text}")

        return "\n".join(line for line in lines if line)

    def _normalize_bullets(self, bullets: List[Any]) -> List[Dict[str, str]]:
        normalized: List[Dict[str, str]] = []
        for item in bullets:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    normalized.append({"label": "", "text": text})
                continue

            if not isinstance(item, dict):
                raise ValueError("Bullets must be strings or objects with text")

            text = str(item.get("text") or "").strip()
            if not text:
                raise ValueError("Bullet entries require text")
            normalized.append({"label": str(item.get("label") or "").strip(), "text": text})
        return normalized

    def _normalize_recommendations(self, recommendations: Dict[str, Any]) -> Dict[str, Any]:
        if "primary" not in recommendations or "backup" not in recommendations:
            raise ValueError("Recommendations require primary and backup entries")

        primary = recommendations["primary"]
        backup = recommendations["backup"]
        if not isinstance(primary, dict) or not isinstance(backup, dict):
            raise ValueError("Recommendation entries must be objects")

        primary_action = str(primary.get("action") or "").strip()
        backup_action = str(backup.get("action") or "").strip()
        if not primary_action or not backup_action:
            raise ValueError("Recommendations require action values")

        impact = recommendations.get("portfolio_impact")
        if primary_action in {"hold", "observe"} and backup_action in {"hold", "observe"}:
            impact = None

        return {
            "primary": {
                "action": primary_action,
                "rationale": str(primary.get("rationale") or "").strip(),
            },
            "backup": {
                "action": backup_action,
                "rationale": str(backup.get("rationale") or "").strip(),
            },
            "portfolio_impact": impact,
        }

    def _normalize_trade_explanation(
        self,
        explanation: Dict[str, Any],
        *,
        prompt: str,
        include_confidence: bool,
    ) -> Optional[Dict[str, Any]]:
        if not explanation:
            return None

        if "why" in prompt.lower() and "trade" in prompt.lower():
            required = ("thesis", "market_signals", "risk_checks", "counterfactual")
            for key in required:
                value = explanation.get(key)
                if value in (None, "", []):
                    raise ValueError(f"Missing required why-trade field: {key}")

        normalized = {
            "thesis": explanation.get("thesis"),
            "market_signals": explanation.get("market_signals") or [],
            "risk_checks": explanation.get("risk_checks") or [],
            "counterfactual": explanation.get("counterfactual"),
            "confidence": explanation.get("confidence") if include_confidence else None,
        }
        return normalized

    def _meta(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        provider = payload.get("provider")
        model = payload.get("model")
        generated_at = payload.get("generated_at") or datetime.utcnow().isoformat()
        return {
            "provider": provider,
            "model": model,
            "generated_at": generated_at,
        }
