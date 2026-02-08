# Phase 7: AI Chat Integration - Context

**Gathered:** 2026-02-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver conversational AI chat that answers trading-context questions, explains trade decisions, provides risk-aware recommendations, and handles strategy-adjustment requests using existing system context. This phase defines interaction behavior and response expectations for chat; new capabilities beyond chat integration are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Answer style and depth
- Default response depth is medium.
- Default format is hybrid: short paragraph followed by bullets.
- For broad prompts (for example, "How am I doing?"), ask a clarifying follow-up before giving the full answer.
- Use balanced metrics: include key numbers when relevant, but do not make every answer data-heavy.

### "Why this trade?" explanations
- Explanations must include trade thesis, market signals, and risk checks.
- Confidence level is shown only when the user asks for it.
- Include brief counterfactual trigger conditions (what would have changed the decision).
- For losing outcomes, use a clinical/factual tone (no coaching style by default).

### Recommendation behavior
- Provide a top recommendation plus one backup option.
- In elevated-risk conditions, default to hold/no-action.
- If user requests an aggressive action that conflicts with risk posture, offer a safer alternative with rationale.
- Include portfolio impact only for recommendations that change position state.

### Context visibility and timeframe
- Use adaptive timeframe selection: session context for tactical questions; 24h/7d context for performance questions.
- Default portfolio detail is summary plus top positions.
- Include a quick historical baseline comparison (for example, vs prior day/session).
- If context is stale or incomplete, refuse to answer and request fresh context.

### Claude's Discretion
- Exact wording of clarifying follow-up questions.
- Exact bullet schema/ordering in hybrid responses.
- Exact threshold/rules used to classify a question as tactical vs performance-oriented.

</decisions>

<specifics>
## Specific Ideas

- No external product/style references were provided.
- Emphasis is on concise-but-structured replies with explicit safety behavior under stale context or elevated risk.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 07-ai-chat-integration*
*Context gathered: 2026-02-08*
