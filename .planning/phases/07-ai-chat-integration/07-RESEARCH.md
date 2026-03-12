# Phase 07: AI Chat Integration - Research

**Researched:** 2026-02-08  
**Domain:** Trading-grounded conversational AI on existing FastAPI + React stack  
**Confidence:** HIGH

## Summary

Phase 7 should be planned as a **chat-orchestration and grounding phase**, not a new AI-provider phase. The codebase already has streaming chat (`POST /api/ai/chat`), model inventory/activation, trade/risk/market APIs, and alert-to-chat handoff, but the current chat path is mostly ungrounded and does not enforce the locked behavior decisions (hybrid response shape, adaptive timeframe, explicit refusal on stale/incomplete context, elevated-risk hold bias).

The standard approach for this repo is to keep provider calls inside backend services, assemble context with async-safe data access, and return stable API payloads that the frontend can stream/render. Planning should prioritize a **server-side chat context assembler + policy engine + response contract** so frontend changes stay thin.

**Primary recommendation:** Implement a backend `ChatContextAssembler` + `ChatPolicyEngine` and make `/api/ai/chat` enforce structured, risk-aware, freshness-gated responses before streaming text to the UI.

## Current-State Findings

### Existing chat surfaces (already in repo)

- `backend/api/ai.py` exposes `POST /api/ai/chat` (SSE stream), `GET /api/ai/chat/history`, `GET /api/ai/models`, `PUT /api/ai/models/active`, `GET /api/ai/models/comparison`.
- `ChatRequest` already supports `context_json`, `preferences_json`, `tone`, `related_alert_id`, and provider override.
- Chat history persistence already stores `user_message`, `ai_response`, and `context_json` snapshots.

### Grounding data surfaces to reuse (locked requirement #1)

- **Trade rationale + decision trail:** `GET /api/trades/{trade_id}/reasoning` in `backend/api/trades.py` (includes entry/exit reasoning, market conditions, indicators, AI decisions, recent candles, analyst insights).
- **Open positions and unrealized P&L:** `GET /api/trades/active` in `backend/api/trades.py`.
- **Order lifecycle + reconciliation metadata:** `GET /api/trades/orders/pending`, `GET /api/trades/orders/{order_id}/status` (reason codes/messages from reconciliation).
- **Risk posture:** `GET /api/risk/score`, `GET /api/risk/settings`, `GET /api/risk/settings/ai/context`.
- **Portfolio snapshot:** `GET /api/market/portfolio` (contains `fetched_at`, `expires_at`, holdings).
- **Market analyst outputs:** `GET /api/market/analysis/{symbol}`, plus analyst insights used in trade reasoning.
- **Strategy settings/state:** `GET /api/strategies`, `GET /api/strategies/{id}`, `GET /api/strategies/comparison`.
- **Alert handoff context:** `GET /api/alerts/{alert_id}/chat-context`.

### Frontend state and gaps

- `frontend/src/pages/AIChat.js` already injects tone + optional alert context into `/api/ai/chat` request body.
- `frontend/src/components/ChatWindow.js` currently sends only `{ prompt }` and does not parse SSE events correctly (it appends raw stream text, while backend emits `data: {"chunk": ...}\n\n`).
- History mapping in `ChatWindow` expects generic `role/content` records, but backend returns paired entries (`user_message` + `ai_response`).

## Recommended Approach

## Standard Stack

The established libraries/tools for this phase:

### Core
| Library/Module | Version/State | Purpose | Why Standard Here |
|---|---|---|---|
| FastAPI + StreamingResponse | Existing | Stream chat responses (SSE) | Already used by `/api/ai/chat`; no new transport needed |
| SQLAlchemy AsyncSession | Existing | Context/data fetch + persistence | Repo standard for API routes |
| Pydantic v2 models | Existing | Request/response contracts | Repo already uses `model_validator`, `ConfigDict` |
| Existing AI provider services (`ChatAIService`, `AIModelsService`) | Existing | Provider selection/calls | Avoid duplicate provider abstractions |

### Supporting
| Library/Module | Purpose | When to Use |
|---|---|---|
| `services.market_data`, `agents.market_analyst` | Symbol technical and insight grounding | Tactical and symbol-specific questions |
| `services.risk_ai` context path | Risk profile + style profile context | Recommendation and risk-aware responses |
| `api/errors` typed error envelope | Consistent API error payloads | Refusals and dependency failures |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|---|---|---|
| Reusing existing APIs/services | New custom analytics/chat DB tables | Higher complexity, duplicates existing truth sources |
| SSE endpoint | WebSocket chat protocol | Unnecessary migration cost; SSE already implemented |
| Server-side context assembly | Frontend assembles context_json | Harder to trust freshness/integrity; leaks policy to UI |

## Architecture Patterns

### Recommended Project Structure

```
backend/
├── api/ai.py                     # Keep endpoint + stream orchestration
├── services/chat_context.py      # NEW: gather/normalize trading context
├── services/chat_policy.py       # NEW: classify intent, guardrails, refusal logic
├── services/chat_response.py     # NEW: contract schema + formatter helpers
└── tests/
    ├── api/test_ai_chat_integration.py
    └── services/test_chat_context.py

frontend/src/
├── components/ChatWindow.js      # Fix SSE parsing + contract rendering
├── pages/AIChat.js               # Keep tone/model/alert controls
└── services/api.js               # Optional typed helper for chat stream bootstrap
```

### Pattern 1: Server-side context assembly with adaptive windows
**What:** Build context on backend per prompt type (tactical vs performance) and attach freshness metadata.
**When to use:** Every chat request before provider call.

```python
# Source: repository pattern derived from backend/api/trades.py + backend/api/risk.py + backend/api/market.py
class TimeWindow(str, Enum):
    SESSION = "session"
    H24 = "24h"
    D7 = "7d"

def classify_window(prompt: str) -> TimeWindow:
    text = prompt.lower()
    if any(k in text for k in ["how am i doing", "performance", "p&l", "week", "day"]):
        return TimeWindow.H24 if "week" not in text else TimeWindow.D7
    return TimeWindow.SESSION

async def assemble_context(db: AsyncSession, prompt: str) -> dict:
    window = classify_window(prompt)
    # Reuse existing services/endpoints internally; avoid duplicate SQL logic.
    return {
        "window": window,
        "positions": await load_active_positions(db),
        "risk": await load_risk_snapshot(db),
        "portfolio": await load_portfolio_snapshot(),
        "market": await load_market_analysis_for_top_symbols(db, window),
        "freshness": build_freshness_flags(),
    }
```

### Pattern 2: Policy-first response planning
**What:** Compute `response_mode` before LLM call: `clarify`, `answer`, `refuse`, `recommend_hold`.
**When to use:** Always; it enforces locked behavior decisions.

### Pattern 3: Structured model output -> deterministic renderer
**What:** Ask model for JSON contract; render hybrid text (paragraph + bullets) server-side.
**When to use:** All non-refusal replies.

### Anti-Patterns to Avoid
- **Direct free-form prompt-only answering:** bypasses grounding and violates stale-context refusal requirement.
- **Frontend-only policy enforcement:** creates inconsistent behavior across clients.
- **Inline SQL in route for every context branch:** harder to test and maintain; use a service layer.

## Guardrails and Refusal Triggers

Use these explicit server-side triggers:

1. **Stale context refusal (hard fail):**
   - `portfolio.expires_at < now` OR missing `fetched_at`.
   - no recent market timestamp for symbols involved.
   - risk snapshot missing `updated_at`/`reference_time`.
   - response: refuse with `code="stale_context"` and request refresh action.

2. **Incomplete context refusal (hard fail):**
   - recommendation question with no positions/risk/portfolio context.
   - “why this trade” with unknown/missing trade ID or no rationale payload.
   - response: refuse with `code="incomplete_context"` and specific missing fields.

3. **Elevated-risk recommendation mode (soft gate):**
   - if `risk.status == "alert"` OR `risk.ratio >= 0.85` => default primary recommendation is `hold/no-action`.
   - if user requests aggressive action during elevated risk => return safer alternative as backup with rationale.

4. **Broad prompt clarification gate:**
   - prompts like “How am I doing?” trigger one clarifying question before full answer.

## Response Contract (locked requirement #4)

Use a stable server-side contract from policy/LLM output:

```json
{
  "mode": "clarify|answer|refuse",
  "timeframe_used": "session|24h|7d",
  "summary_paragraph": "string",
  "bullets": [
    {"label": "Key point", "text": "string"}
  ],
  "recommendations": {
    "primary": {"action": "hold|buy|sell|adjust", "rationale": "string"},
    "backup": {"action": "hold|buy|sell|adjust", "rationale": "string"},
    "portfolio_impact": "string|null"
  },
  "trade_explanation": {
    "thesis": "string",
    "market_signals": ["..."],
    "risk_checks": ["..."],
    "counterfactual": "string",
    "confidence": null
  },
  "guardrail": {
    "elevated_risk": false,
    "stale_context": false,
    "incomplete_context": false,
    "refusal_reason": null
  },
  "meta": {
    "provider": "openai|claude|ollama",
    "model": "string",
    "generated_at": "ISO-8601"
  }
}
```

Contract rules to enforce:
- Default depth `medium`.
- Default style = one short paragraph + bullets.
- Show confidence **only** when user explicitly asks.
- For losing outcomes, wording must be clinical/factual.
- Include portfolio impact only when recommendation changes position state.

## Don’t Hand-Roll

| Problem | Don’t Build | Use Instead | Why |
|---|---|---|---|
| Streaming transport | Custom websocket protocol | Existing SSE `/api/ai/chat` | Already wired end-to-end in backend |
| Order reconciliation logic | New reconciliation parser | `order_lifecycle_sync_service` + reason parsing | Existing reason_code/reason_message contract |
| Market/risk summarization from scratch | New ad-hoc calculations in route | `market_data_service.summarize_symbol`, `/api/risk/*` | Reuses tested domain logic |
| Error envelope formatting | Per-route custom error JSON | `BaseAppException` + `api/errors` handlers | Keeps frontend error parsing consistent |

**Key insight:** In this repo, most hard domain work already exists. Phase 7 should compose and enforce behavior, not recreate analytics.

## Integration Points (Planner-ready)

### Backend file targets
- `backend/api/ai.py`
  - Inject auth dependency if Phase 7 requires user-scoped chat.
  - Call new context/policy services before provider streaming.
  - Emit structured SSE events (`chunk`, `meta`, `guardrail`, `done`) or keep `chunk` plus persist normalized final contract.
- `backend/services/chat_context.py` (new)
  - Adaptive window selection + context freshness checks.
  - Context assembly from existing surfaces listed above.
- `backend/services/chat_policy.py` (new)
  - Intent classification (tactical vs performance + broad prompt detection).
  - Guardrails/refusal rules and recommendation gating.
- `backend/services/chat_response.py` (new)
  - Parse/provider output validation, JSON schema normalization, and hybrid text rendering.

### Frontend file targets
- `frontend/src/components/ChatWindow.js`
  - Parse SSE `data:` frames correctly (similar to parser embedded in `backend/main.py` demo page).
  - Map history entries as turn pairs (`user_message`, `ai_response`) instead of generic role/content assumptions.
  - Render hybrid response paragraph + bullet list consistently.
- `frontend/src/pages/AIChat.js`
  - Keep tone/model controls; optionally pass explicit question hints if planner chooses.
- `frontend/src/services/api.js`
  - Add explicit helper for chat stream bootstrap and typed error extraction if needed.

## Common Pitfalls (repo-specific)

### Pitfall 1: Async DB/session misuse
**What goes wrong:** Blocking DB/service code runs inside async route without thread handoff.
**Why it happens:** Repo has both `AsyncSession` and sync `SessionLocal` patterns.
**How to avoid:** Keep route-level data fetches async; isolate sync-only logic in service methods that already use `asyncio.to_thread`.
**Warning signs:** event loop stalls, flaky stream timing, timeout spikes.

### Pitfall 2: Error payload drift
**What goes wrong:** Route raises raw `HTTPException(detail="...")`, frontend misses `error.code/details`.
**Why it happens:** Mixed legacy and typed exception usage.
**How to avoid:** Raise `BaseAppException` subclasses (`DatabaseException`, `ServiceUnavailableException`) for operational failures.
**Warning signs:** inconsistent UI errors and missing retry logic.

### Pitfall 3: SSE protocol mismatch in React chat
**What goes wrong:** Frontend appends raw stream bytes, showing `data:` fragments or broken text.
**Why it happens:** `ChatWindow.js` currently does not parse SSE frames.
**How to avoid:** Parse by `\n\n` frame boundary and JSON `data:` payload extraction.
**Warning signs:** garbled chat output, missing final message persistence.

### Pitfall 4: Missing freshness gating
**What goes wrong:** Chat gives recommendations from stale portfolio/market context.
**Why it happens:** Current chat flow accepts optional `context_json` but does not validate freshness.
**How to avoid:** Make freshness validation mandatory before recommendation/explanation generation.
**Warning signs:** advice contradicts current positions or recent fills.

## Code Examples

### Example: Guarded chat request flow

```python
# Source: pattern aligned to backend/api/ai.py streaming route + repo exception handlers
@router.post("/chat")
async def chat_stream(payload: ChatRequest, db: AsyncSession = Depends(get_async_db)):
    context = await chat_context_assembler.build(db=db, request=payload)
    policy = chat_policy_engine.evaluate(prompt=payload.message, context=context)

    if policy.refuse:
        raise ServiceUnavailableException(
            service="chat_context",
            details={"code": policy.refusal_code, "missing": policy.missing_fields},
        )

    stream = stream_structured_chat(payload=payload, context=context, policy=policy, db=db)
    return StreamingResponse(stream, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
```

### Example: SSE parsing fix pattern (frontend)

```javascript
// Source: parser pattern already present in backend/main.py AI chat demo script
const parseSSE = (raw) => {
  const dataLines = raw
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('data:'));
  if (!dataLines.length) return null;
  return JSON.parse(dataLines.map((l) => l.replace(/^data:\s*/, '')).join(''));
};
```

## Validation

### Suggested automated checks

```bash
cd backend && pytest tests/api/test_trades_order_lifecycle.py tests/api/test_risk_api.py
cd backend && pytest tests/api/test_trades_order_entry.py
cd frontend && npm run lint
```

### New tests planner should add
- `backend/tests/api/test_ai_chat_integration.py`
  - broad prompt => clarify mode
  - stale context => refusal
  - elevated risk => primary hold + safer backup
  - “why trade” includes thesis/signals/risk/counterfactual
  - confidence only when requested
- `backend/tests/services/test_chat_context.py`
  - session vs 24h vs 7d classifier
  - freshness/incomplete detection
  - context assembly includes top positions + baseline comparison
- `frontend` chat regression test (if harness enabled)
  - SSE frame parsing + hybrid rendering + history turn mapping

### Manual verification scenarios
- Ask: “How am I doing?” => receives clarifying question first.
- Ask: “Why did you make this trade?” with valid trade context => includes required explanation fields.
- Trigger elevated risk (`/api/risk/score` ratio high) and ask for aggressive action => primary hold + safer backup.
- Force stale data (expired portfolio snapshot) => refusal with explicit refresh request.

## Sources

### Primary (HIGH confidence)
- Code inspection in:
  - `backend/api/ai.py`
  - `backend/api/trades.py`
  - `backend/api/risk.py`
  - `backend/api/market.py`
  - `backend/api/strategies.py`
  - `backend/api/alerts.py`
  - `backend/services/portfolio.py`
  - `backend/services/market_data.py`
  - `backend/services/trade_sync.py`
  - `backend/core/exceptions.py`
  - `backend/api/errors.py`
  - `frontend/src/pages/AIChat.js`
  - `frontend/src/components/ChatWindow.js`

### Secondary (MEDIUM confidence)
- None.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - fully derived from existing codebase modules/endpoints.
- Architecture: HIGH - aligns with established service/route patterns in repo.
- Pitfalls: HIGH - validated against current frontend/backend mismatches and exception/session conventions.

**Research date:** 2026-02-08  
**Valid until:** 2026-03-10

## Planner Handoff Checklist

- [ ] Add tasks for backend `chat_context`, `chat_policy`, and response-contract implementation.
- [ ] Add task to update `backend/api/ai.py` to enforce freshness/incomplete guardrails and elevated-risk recommendation mode.
- [ ] Add task to wire existing grounding surfaces (trades, risk, market analysis, strategies, alerts) into context assembly.
- [ ] Add frontend task to fix SSE parsing and history mapping in `frontend/src/components/ChatWindow.js`.
- [ ] Add tests for clarify/refuse/recommendation behavior and contract compliance (including optional confidence).
- [ ] Add verification steps for stale-context refusal, elevated-risk hold default, and trade explanation completeness.
