---
phase: 07-ai-chat-integration
status: gaps_found
score: 4/7
gaps:
  - "Recommendations Rendering: The backend generates primary and backup recommendations, but the ChatWindow.js component does not render them."
  - "Why-trade Structural Enforcement: The requirement for thesis, market signals, etc., is defined in the normalizer but bypassed by the orchestrator, and not rendered in the UI."
  - "Portfolio Impact Rendering: Calculated on the backend but ignored by the UI."
---

# Phase 7: AI Chat Integration - Verification Report

**Phase Goal:** Users can query trading context and get recommendations via AI assistant.

## Gaps Found

3 gaps blocking goal achievement:

1. **Recommendations Rendering** — The backend generates primary and backup recommendations, but the `ChatWindow.js` component does not render them.
   - Missing: JSX in `ChatWindow.js` to display `message.structuredResponse.recommendations`.
2. **Why-trade Structural Enforcement** — The requirement for thesis, market signals, etc., is defined in the normalizer but bypassed by the orchestrator, and not rendered in the UI.
   - Missing: Orchestrator logic to parse/instruct AI for structured output; UI rendering for `trade_explanation`.
3. **Portfolio Impact Rendering** — Calculated on the backend but ignored by the UI.
   - Missing: UI rendering for `portfolio_impact`.

## Artifact Status

- `backend/api/ai.py`: ✓ VERIFIED (Substantive, correctly wired)
- `backend/services/chat_context.py`: ✓ VERIFIED (Correct logic for freshness)
- `backend/services/chat_policy.py`: ✓ VERIFIED (Correct policy branching)
- `backend/services/chat_response.py`: ✓ VERIFIED (Correct contract definition)
- `frontend/src/components/ChatWindow.js`: ⚠️ PARTIAL (Implemented SSE, but ignores structured recommendations and explanations)

## Requirements Coverage

- Broad prompts return clarifying follow-up: ✓ SATISFIED
- Stale/incomplete context refusal: ✓ SATISFIED
- Recommendation primary/backup: ✗ BLOCKED (Not visible to user)
- Elevated-risk mode default hold: ✓ SATISFIED (Backend logic)
- Why-trade structured responses: ✗ BLOCKED (Not enforced or rendered)
- Confidence on request only: ✓ SATISFIED
- Portfolio impact visibility: ✗ BLOCKED (Not visible to user)
