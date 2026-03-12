import os
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parent.parent.parent
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/cryptotrader_chat_policy_test.db")

from services.chat_policy import ChatPolicyEngine


def _base_context() -> dict:
    return {
        "timeframe_used": "session",
        "stale_context": False,
        "incomplete_context": False,
        "missing_fields": [],
        "refusal_reasons": [],
        "risk_snapshot": {
            "status": "ok",
            "risk_ratio": 0.42,
        },
    }


def test_policy_requires_clarification_for_broad_prompt():
    engine = ChatPolicyEngine()
    payload = engine.evaluate(prompt="How am I doing?", context=_base_context())

    assert payload["mode"] == "clarify"
    assert payload["depth"] == "medium"
    assert payload["clarifying_question"]
    assert payload["include_confidence"] is False


def test_policy_refuses_when_context_is_stale_or_incomplete():
    engine = ChatPolicyEngine()
    context = _base_context()
    context["stale_context"] = True
    context["incomplete_context"] = True
    context["missing_fields"] = ["risk.updated_at"]
    context["refusal_reasons"] = ["missing_risk_reference_timestamp"]

    payload = engine.evaluate(prompt="Should I buy BTC now?", context=context)

    assert payload["mode"] == "refuse"
    assert payload["guardrail"]["stale_context"] is True
    assert payload["guardrail"]["incomplete_context"] is True
    assert payload["guardrail"]["refusal_reason"] == "missing_risk_reference_timestamp"


def test_policy_defaults_to_hold_under_elevated_risk_and_aggressive_prompt():
    engine = ChatPolicyEngine()
    context = _base_context()
    context["risk_snapshot"] = {"status": "alert", "risk_ratio": 0.92}

    payload = engine.evaluate(
        prompt="Should I go all in with high leverage right now?",
        context=context,
    )

    assert payload["mode"] == "answer"
    assert payload["guardrail"]["elevated_risk"] is True
    assert payload["guardrail"]["aggressive_request"] is True
    assert payload["recommendations"]["primary"]["action"] == "hold"
    assert payload["recommendations"]["backup"]["action"] == "reduce_exposure"
    assert "reduced" in payload["recommendations"]["portfolio_impact"].lower()


def test_policy_only_emits_confidence_when_requested():
    engine = ChatPolicyEngine()

    normal = engine.evaluate(prompt="Explain this trade outcome.", context=_base_context())
    explicit = engine.evaluate(prompt="Explain this trade and include confidence.", context=_base_context())

    assert normal["include_confidence"] is False
    assert explicit["include_confidence"] is True
