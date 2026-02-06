# Phase 04: Position & Order Management - Research

**Researched:** 2026-02-06
**Domain:** Order entry/close UX, position lifecycle, partial fills, real-time P&L
**Confidence:** HIGH

## Summary

This phase should be planned as a lifecycle integration phase, not a greenfield build. The project already has most primitives needed: Kraken order placement/status (`backend/services/kraken.py`), centralized risk gating (`backend/core/risk.py`), paper position accounting and stop-loss behavior (`backend/core/paper_trading.py`), and a live market stream feeding paper mark-to-market updates (`backend/services/kraken_ws.py`). The planning focus is orchestrating these into the locked UX decisions (review modal, table-first positions, pending section, close confirmations, and dual outcome surfacing).

The standard approach in this codebase is: keep execution/risk logic server-side, keep frontend state simple/local (React hooks), and surface asynchronous outcomes through existing log/alert channels. For POS-01..POS-07, the highest-risk planning area is order lifecycle consistency: ensure pending/partial/filled/rejected states are represented explicitly and reconciled against exchange/order-status updates without conflating them with open positions.

Kraken ecosystem direction also supports this approach: WebSocket v2 `executions` provides granular states (`pending_new`, `new`, `trade`, `filled`, `canceled`, `expired`, `partially_filled`) and cumulative fill fields (`cum_qty`, `avg_price`) suitable for partial-fill reconciliation, while REST remains usable for simpler polling-based status checks.

**Primary recommendation:** Plan Phase 4 around a single order lifecycle model (`pending -> partially_filled -> filled/rejected/canceled`) shared across backend API, DB rows, and UI sections, with RiskService gating every submit/close action.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 18.2.0 (`frontend/package.json`) | Ticket/positions UI state and interactions | Already used across frontend; aligns with current hook-based patterns. |
| Axios | 1.6.5 | API calls for order submit/close/status | Existing interceptor/error normalization used app-wide. |
| FastAPI | >=0.109.0 | Order/position API endpoints | Existing backend API framework and auth/session middleware. |
| SQLAlchemy | >=2.0.25 | `trades`/`orders` persistence and reconciliation | Existing transaction model and async session patterns. |
| Pydantic v2 | >=2.5.3 | Request/response validation | Existing model validators and API contracts. |
| krakenex + KrakenService wrapper | >=2.2.1 | Exchange order placement/status lookup | Existing wrapper already maps Kraken responses and errors. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| websockets | >=12.0 | Live market feed and future execution stream adoption | Use for real-time P&L and optional order-event push model. |
| Tailwind CSS | 3.4.1 | Table/row responsive UI and visual status states | Use for table-first desktop and compact mobile rows. |
| Redis (message queue) | >=5.0.1 | Trade executor telemetry/activity feed events | Use when showing global order outcomes beyond local ticket. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Existing local React state + axios | React Query/SWR | Better caching, but adds phase scope and migration overhead; not needed for Phase 4.
| Polling `QueryOrders` via REST | Kraken WS v2 `executions` channel | Better granularity and lower latency, but requires auth-token stream plumbing not present yet.
| Reusing existing alerts/log timeline | New custom event system | More control but duplicates existing hooks and increases coordination cost.

**Installation:**
```bash
# No new dependencies required for baseline Phase 4.
# Use existing frontend/backend stacks.
```

## Architecture Patterns

### Recommended Project Structure
```
frontend/src/
├── components/
│   ├── PositionManager.js        # Extend to table-first positions + pending section
│   ├── OrderTicket.js            # New ticket with market/limit toggle + review modal
│   └── OrderOutcomeFeed.js       # New local/global outcome surface
├── services/
│   └── api.js                    # Add explicit order endpoints wrappers

backend/
├── api/
│   └── trades.py                 # Extend manual order entry/close/pending endpoints
├── core/
│   ├── risk.py                   # Keep centralized RiskService gating
│   └── paper_trading.py          # Source of truth for position/P&L behavior
├── services/
│   ├── kraken.py                 # Exchange order placement/status mapping
│   └── trade_sync.py             # Reconciliation helpers for order status/fills
└── db/
    └── models.py                 # `orders`/`trades` schema is already present
```

### Pattern 1: Confirmed Order Ticket Flow
**What:** Ticket edits local draft state, then always passes through review modal before submit.
**When to use:** Every open/close action (locked decision: confirmations are mandatory).
**Example:**
```javascript
// Source: project pattern from frontend/src/components/PositionManager.js
const [draft, setDraft] = useState({ side: 'buy', orderType: 'market', quantity: '' });
const [reviewOpen, setReviewOpen] = useState(false);

const onPrimarySubmit = (event) => {
  event.preventDefault();
  setReviewOpen(true); // do not submit to API yet
};

const onConfirm = async () => {
  await tradesAPI.createTrade(draft);
  setReviewOpen(false);
};
```

### Pattern 2: Split Position and Pending Order Surfaces
**What:** Open positions and pending orders are rendered as separate collections.
**When to use:** Always (locked decision: pending orders are not mixed into positions).
**Example:**
```python
# Source: backend/db/models.py + backend/api/trades.py
# Position rows are trades with exit_time is NULL and (filled/open semantics)
active_trades = select(Trade).where(Trade.exit_time.is_(None))

# Pending orders are rows in orders table with non-terminal status
pending_orders = select(Order).where(Order.status.in_(["pending", "open"]))
```

### Pattern 3: Dual Outcome Publication
**What:** Surface status updates both in ticket-local area and global feed.
**When to use:** Submit, fill, rejection, and close failures.
**Example:**
```python
# Source: backend/agents/trade_executor.py
self._log_system_event("info", "Order placed via Kraken", details)
self._log_system_event("warning", "Kraken API error while placing order", details)
self._log_system_event("info", "Order reached terminal status", details)
```

### Pattern 4: Partial Fill Reconciliation
**What:** Track requested vs filled quantities and transition to `partially_filled` before `filled`.
**When to use:** Any non-market-perfect fill path and all limit orders.
**Example:**
```python
# Source: Kraken status mapping in backend/services/kraken.py
info = await kraken_service.get_order_status(exchange_order_id)
filled_qty = float(info.filled_volume)  # Kraken vol_exec mapped here
is_partial = 0 < filled_qty < requested_qty
```

### Anti-Patterns to Avoid
- **Direct UI-to-exchange calls:** Always go through backend API + RiskService gate.
- **Close without confirmation:** Violates locked phase decisions and increases misfire risk.
- **Derived P&L from stale static entry-only data:** Use latest market stream/ticker path for mark-to-market.
- **Single list for all states:** Mixing pending and open positions causes operator mistakes.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Risk checks before submit/close | Client-side if/else risk checks | `RiskService.validate_trade` in backend | Phase 3 established centralized fail-closed enforcement.
| Order status enum parsing | Custom string parsing scattered across UI/API | `OrderStatus` / `OrderType` in `backend/services/kraken.py` | Prevents inconsistent state labels and transition bugs.
| Real-time price feed plumbing | New socket service for P&L | Existing `kraken_ws` + `paper_trading_engine.update_market_price` | Already integrated at backend startup and in market stream path.
| Global notifications | New custom toast bus | Existing alerts/log pipeline (`useAlerts`, `AlertNotification`, system logs) | Reuses existing polling + popup behavior and timeline pages.
| Partial-close bookkeeping | Manual arithmetic in UI only | Server-side quantity accounting (`_close_positions` in paper engine) | Handles remaining quantity, realized/unrealized updates, and guardrails correctly.

**Key insight:** Most Phase 4 complexity is lifecycle consistency; custom parallel implementations (especially in frontend) create divergence from risk/execution truth.

## Common Pitfalls

### Pitfall 1: Price Drift Between Prefill and Confirm
**What goes wrong:** Limit order prefills from market price, but execution validation uses later price and can reject unexpectedly.
**Why it happens:** Prefill/confirm timestamps are separated in fast markets.
**How to avoid:** Snapshot `prefill_price` and show delta at review; revalidate with latest price server-side and show explicit reason code on reject.
**Warning signs:** Frequent rejections with "price/size invalid" immediately after confirmation.

### Pitfall 2: Pending Orders Counted as Open Positions
**What goes wrong:** UI overstates exposure/P&L by including unfilled orders in positions table.
**Why it happens:** Shared fetch endpoint with no state partitioning.
**How to avoid:** Keep distinct queries/sections: positions from open trades, pending from non-terminal orders.
**Warning signs:** Position count jumps before any fill event.

### Pitfall 3: Partial Fill Misaccounting
**What goes wrong:** System marks order as fully done after first fill, then later fills drift exposure/P&L.
**Why it happens:** No explicit `requested_qty` vs `filled_qty` reconciliation loop.
**How to avoid:** Persist both quantities and only terminal when `filled_qty >= requested_qty` or canceled/expired/rejected.
**Warning signs:** Closed order with non-zero unfilled remainder and mismatched trade quantity.

### Pitfall 4: Duplicate Submits from Retries
**What goes wrong:** UI retry creates duplicate orders for same intent.
**Why it happens:** No idempotent client identifier crossing retries.
**How to avoid:** Send `client_order_id`/`signal_id` and treat retries as same logical order.
**Warning signs:** Multiple exchange order IDs for one review confirmation.

### Pitfall 5: Close Race Against Price Stream
**What goes wrong:** User closes partially while ticker updates trigger concurrent recalcs; resulting P&L flicker or mismatch.
**Why it happens:** Async update and close mutation race.
**How to avoid:** Mutations under lock server-side (already present in `PaperTradingEngine`) and optimistic UI with authoritative refresh after close.
**Warning signs:** Temporary negative/positive spikes and row jitter post-close.

## Code Examples

Verified patterns from current code and official docs:

### Risk Gate Before Execution
```python
# Source: backend/agents/trade_executor.py
async with AsyncSessionLocal() as session:
    await RiskService.validate_trade(
        db=session,
        symbol=signal.symbol,
        quantity=float(signal.volume),
        price=float(price),
        side=signal.side.value,
    )
```

### Partial Close Logic (Server-Side)
```python
# Source: backend/core/paper_trading.py
closing_qty = min(position.quantity, remaining)
position.quantity -= closing_qty
remaining -= closing_qty

if position.quantity <= 0:
    symbol_positions.pop(0)
```

### Kraken Execution States For Outcome Mapping
```text
# Source: https://docs.kraken.com/api/docs/websocket-v2/executions
exec_type: pending_new | new | trade | filled | canceled | expired | restated | status
order_status: pending_new | new | partially_filled | filled | canceled | expired
```

### Existing Outcome Feed Hook (Global Notifications)
```javascript
// Source: frontend/src/hooks/useAlerts.js
const response = await api.get('/api/alerts', { params: { page: 1, page_size: 12 } });
alertStore.pendingPopups = [...alertStore.pendingPopups, ...uniqueAlerts];
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling-only order lifecycle visibility | WS v2 `executions` supports granular order events and partial fill fields | WS v2 matured 2023-2025 (Kraken changelog) | Better real-time pending/partial/fill UX when adopted.
| Legacy trigger fields (`stop_price`, `trigger`) | Structured trigger objects (`triggers`) in Kraken WS v2 | Deprecated in newer docs | Cleaner order schema and fewer ambiguous params.
| No amend audit visibility | `OrderAmends` REST endpoint available | 2024-09 Kraken changelog | Enables operator audit trail for changed pending orders.

**Deprecated/outdated:**
- `no_mpp` parameter: deprecated by Kraken (2025-09 changelog); do not add to new phase APIs.
- Treating fills as binary open/closed only: outdated for modern exchange event models; Phase 4 should model partial fill explicitly.

## Open Questions

1. **Manual order path: paper engine vs exchange-first for UI ticket?**
   - What we know: current `POST /api/trades/` creates DB trade rows without exchange placement.
   - What's unclear: whether Phase 4 manual ticket should execute through `TradeExecutor`/Kraken or through paper engine simulation endpoint.
   - Recommendation: Keep Phase 4 paper-first with lifecycle-complete model; defer live-exchange manual ticket wiring to a dedicated follow-up if needed.

2. **Source of truth for pending orders section**
   - What we know: DB `orders` table exists and can be refreshed from Kraken status endpoints.
   - What's unclear: whether to include exchange open orders not yet mirrored locally.
   - Recommendation: Use DB as source of truth, plus explicit sync endpoint to reconcile from Kraken before rendering pending section.

3. **Global activity feed channel for outcomes**
   - What we know: both alerts and system logs exist, and trade executor writes system logs.
   - What's unclear: whether phase UX wants user-facing outcomes in alerts, logs, or both.
   - Recommendation: Use ticket-local status + lightweight order event list in Live Trading; mirror critical failures/rejections to alerts.

## Sources

### Primary (HIGH confidence)
- `frontend/package.json` - frontend stack versions (React/Vite/Axios/Tailwind).
- `backend/requirements.txt` - backend stack versions (FastAPI/SQLAlchemy/Pydantic/krakenex/websockets/redis).
- `backend/core/risk.py` - centralized pre-trade risk gating and account-balance-based limit checks.
- `backend/core/paper_trading.py` - position lifecycle, partial close logic, and P&L calculations.
- `backend/api/trades.py` - current trade/order API shape and status handling.
- `backend/services/kraken.py` - order placement/status mapping and enums.
- `backend/services/kraken_ws.py` - real-time ticker integration and paper-engine mark-to-market updates.
- https://docs.kraken.com/api/docs/websocket-v2/executions - execution event model, partial fill fields/statuses.
- https://docs.kraken.com/api/docs/websocket-v2/add_order - supported order types, trigger/time-in-force semantics.
- https://docs.kraken.com/api/docs/change-log - chronology for order/execution API evolution and deprecations.

### Secondary (MEDIUM confidence)
- https://docs.kraken.com/api/docs/rest-api/add-order - confirms endpoint existence/permissions (limited schema visibility via static fetch).
- https://docs.kraken.com/api/docs/rest-api/get-orders-info - confirms endpoint usage for order detail lookup.
- https://docs.kraken.com/api/docs/rest-api/get-order-amends - confirms amend audit endpoint availability.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - derived from project manifests and existing implementation.
- Architecture: HIGH - aligned with existing backend/frontend code paths and locked phase decisions.
- Pitfalls: HIGH - based on current code behavior plus Kraken execution model docs.

**Research date:** 2026-02-06
**Valid until:** 2026-03-08
