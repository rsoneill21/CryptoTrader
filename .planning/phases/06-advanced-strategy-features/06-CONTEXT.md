# Phase 6: Advanced Strategy Features - Context

**Gathered:** 2026-02-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver advanced strategy behavior where strategies can use multi-timeframe rules, AI can generate strategy suggestions, users can customize AI-proposed strategies through a guided flow, approved strategies can be promoted from paper to live, and the system can auto-adjust parameters when performance degrades.

</domain>

<decisions>
## Implementation Decisions

### AI strategy suggestion format
- Present suggestions in structured sections (thesis, entry, exits, risk, confidence) rather than a single card or chat-only narrative.
- Use moderate rationale depth: include key driving factors and risk caveat, without full factor-by-factor analysis.
- Display confidence as both a label and percentage.
- Include two ranked alternative setups with each primary recommendation.

### Customization workflow for AI proposals
- Allow users to edit numeric parameters and rule thresholds/indicator parameters.
- Use mixed guardrails: block critical unsafe violations and show warnings for non-critical issues.
- Use a step-by-step wizard flow (Review -> Edit -> Validate -> Save).
- Let users choose to save as a new strategy or overwrite an existing draft.

### Promotion and auto-adjust lifecycle
- Promotion to live is auto-eligible when thresholds are met but still requires explicit user confirmation.
- Promotion review packet includes core metrics, risk compliance status, and recent trade samples.
- Use balanced degradation sensitivity for auto-adjust triggers.
- Apply small, bounded parameter adjustments automatically and log all adjustments.

### Claude's Discretion
- Define allowed multi-timeframe combination policy (fixed pair set vs flexible selectable set) within phase scope.
- Define conflict resolution behavior when timeframe signals disagree.
- Define default UI depth for multi-timeframe visibility.
- Define fail behavior when one timeframe feed is stale or missing.

</decisions>

<specifics>
## Specific Ideas

- Preference for structured, operator-friendly strategy review over conversational-only output.
- Preference for safe autonomy: bounded automatic adjustment with explicit promotion confirmation.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 06-advanced-strategy-features*
*Context gathered: 2026-02-07*
