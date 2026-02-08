import os
import sys
from pathlib import Path

import pytest

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/cryptotrader_chat_response_test.db")

from services.chat_response import ChatResponseNormalizer


def _context() -> dict:
    return {"timeframe_used": "session"}


def _answer_policy(*, include_confidence: bool = False) -> dict:
    return {
        "mode": "answer",
        "include_confidence": include_confidence,
        "guardrail": {
            "stale_context": False,
            "incomplete_context": False,
            "elevated_risk": False,
            "refusal_reason": None,
        },
        "recommendations": {
            "primary": {"action": "adjust", "rationale": "Scale in carefully."},
            "backup": {"action": "hold", "rationale": "Wait for better confirmation."},
            "portfolio_impact": "Increases directional exposure.",
        },
    }


def test_normalizer_rejects_missing_summary_paragraph():
    normalizer = ChatResponseNormalizer()
    with pytest.raises(ValueError, match="summary_paragraph"):
        normalizer.normalize(
            policy=_answer_policy(),
            context=_context(),
            model_output={"bullets": ["A", "B"]},
        )


def test_normalizer_enforces_why_trade_required_fields():
    normalizer = ChatResponseNormalizer()
    with pytest.raises(ValueError, match="thesis"):
        normalizer.normalize(
            policy=_answer_policy(),
            context=_context(),
            prompt="Why did you make this trade?",
            model_output={
                "summary_paragraph": "Trade rationale review.",
                "bullets": [{"label": "Signal", "text": "Momentum confirmation."}],
                "trade_explanation": {
                    "market_signals": ["RSI recovered above 50"],
                    "risk_checks": ["Exposure below max"],
                    "counterfactual": "Would not enter without volume expansion.",
                },
            },
        )


def test_normalizer_omits_confidence_unless_requested():
    normalizer = ChatResponseNormalizer()
    model_output = {
        "summary_paragraph": "Position remains controlled with moderate upside.",
        "bullets": ["Momentum remains positive."],
        "trade_explanation": {
            "thesis": "Breakout continuation setup.",
            "market_signals": ["Higher highs", "Positive momentum"],
            "risk_checks": ["Exposure within limits"],
            "counterfactual": "Break below support invalidates the setup.",
            "confidence": 0.73,
        },
    }

    without_confidence = normalizer.normalize(
        policy=_answer_policy(include_confidence=False),
        context=_context(),
        prompt="Why did you make this trade?",
        model_output=model_output,
    )
    with_confidence = normalizer.normalize(
        policy=_answer_policy(include_confidence=True),
        context=_context(),
        prompt="Why did you make this trade and include confidence?",
        model_output=model_output,
    )

    assert without_confidence["trade_explanation"]["confidence"] is None
    assert with_confidence["trade_explanation"]["confidence"] == 0.73


def test_renderer_preserves_clarify_and_refuse_payloads():
    normalizer = ChatResponseNormalizer()

    clarify_contract = normalizer.normalize(
        policy={
            "mode": "clarify",
            "clarifying_question": "Do you want session or weekly context?",
            "guardrail": {},
        },
        context=_context(),
        model_output={},
    )
    refuse_contract = normalizer.normalize(
        policy={
            "mode": "refuse",
            "guardrail": {"refusal_reason": "expired_portfolio_snapshot"},
        },
        context=_context(),
        model_output={},
    )

    assert normalizer.render_hybrid(clarify_contract) == "Do you want session or weekly context?"
    assert "expired_portfolio_snapshot" in normalizer.render_hybrid(refuse_contract)
