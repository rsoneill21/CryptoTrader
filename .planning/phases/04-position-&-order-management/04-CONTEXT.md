# Phase 4: Position & Order Management - Context

**Gathered:** 2026-02-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver position and order management so users can open and close long/short positions with market and limit orders, and monitor open positions with real-time P&L. This phase focuses on entry, close, and outcome UX within existing risk-enforced constraints.

</domain>

<decisions>
## Implementation Decisions

### Order Entry Flow
- Order type uses a smart default with a quick Market/Limit toggle.
- Ticket remembers the user's last selected side (Buy/Sell) as default.
- Limit orders prefill price from current market price.
- Submitting an order always goes through a review modal confirmation.

### Positions View
- Desktop uses a table-first view with expandable detail sections.
- P&L emphasizes dollar value first, with percent secondary.
- Gain/loss coloring follows standard green/red convention.
- Mobile rows prioritize symbol, side, and P&L.

### Close Position UX
- Each position exposes an inline Close action.
- Partial close is supported using quick quantity entry.
- Closing always requires confirmation.
- Close failures show toast feedback with a retry prompt.

### Order Outcomes
- Order status appears in both ticket-local status area and global activity feed.
- Pending orders appear in a separate pending section (not mixed into open positions).
- Rejections show human-readable reason plus short reason code.
- Successful fills trigger toast plus temporary row highlight.

### Claude's Discretion
- Exact copywriting tone and microcopy text for status/review dialogs.
- Animation timing and visual transition details.
- Non-critical spacing, typography, and iconography choices within existing app style.

</decisions>

<specifics>
## Specific Ideas

- Keep workflows fast for operator execution while still requiring review modal confirmations.
- Preserve clear at-a-glance signal on mobile by reducing row density to symbol/side/P&L.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 04-position-&-order-management*
*Context gathered: 2026-02-06*
