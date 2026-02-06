# Phase 03: Core Risk Management - Research

**Researched:** 2025-02-13
**Domain:** Risk Management, Kraken API, Rate Limiting
**Confidence:** HIGH

## Summary

Phase 3 implements the "Guardrails" for the trading system. While Phase 2 established the autonomous loop, Phase 3 ensures that the agent cannot blow up the account or get banned by the exchange. Research focused on translating the high-level requirements (RISK-01 to RISK-07) into technical implementations using the existing stack (`krakenex`, FastAPI, Redis, SQLAlchemy).

**Primary recommendation:** Centralize all risk enforcement into a `RiskService` that acts as a gatekeeper for both the `TradeExecutor` (live) and `PaperTradingEngine` (paper). Use Redis for cross-process rate limiting and frequency tracking.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `krakenex` | 2.2.1 | Exchange API | Low-level, lightweight wrapper for Kraken. |
| `redis` | 5.0.1 | State tracking | Used for rate limiting and trade frequency counters. |
| `pybreaker` | 1.0.0 | Circuit Breaking | Already in use; prevents cascading failures when Redis or Kraken is down. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `pydantic` | 2.5.3 | Validation | Enforcing risk configuration schema. |
| `aiolimiter` | (Optional) | Async limiting | If `krakenex` wrapper becomes too complex, `aiolimiter` provides standard async rate limiting. |

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── core/
│   ├── risk.py          # NEW: Core RiskService logic
│   ├── rate_limit.py    # UPDATED: Enhanced for Kraken Call Counter
├── agents/
│   ├── risk_monitor.py  # UPDATED: From passive monitor to active enforcer
├── db/
│   ├── models.py        # UPDATED: RiskSettings expanded
```

### Pattern 1: Intercepting Execution
The `RiskService` should be injected into `TradeExecutor` and `PaperTradingEngine`. Before sending any order to an exchange (or simulating one), `validate_trade(symbol, quantity, side)` is called. If it fails, a structured `RiskLimitException` is raised.

### Pattern 2: Redis-based Call Counter
Kraken uses a decaying counter system. Implementing this in Redis allows multiple workers (Celery, API, Agents) to share the same rate-limit state.
- Key: `kraken_call_counter:{api_key}`
- Logic: `INCRBY counter cost` -> `EXPIRE counter 60` (or manual decay logic using timestamps).

### Anti-Patterns to Avoid
- **Hardcoded Limits:** Never hardcode risk values; they must be fetched from `RiskSettings` in the DB.
- **Fail-Open Rate Limiting:** If the rate limiter fails (Redis down), it should block trading (`FAIL-CLOSED`), not allow it.
- **Client-Side Only Stop-Loss:** Relying solely on the bot to close positions is risky. Always place an exchange-side stop-loss order if possible.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stop-Loss Tracking | Manual Price Checks | Kraken `stop-loss` orders | Exchange-side orders execute even if the bot is down or disconnected. |
| Rate Limiting | Global variables | Redis `incr` + `expire` | Workers run in separate processes; global variables won't share state. |
| Precision/Rounding | String formatting | `decimal.Decimal` | Floating point errors in crypto quantity/price can cause order rejections. |

## Common Pitfalls

### Pitfall 1: Kraken "Call Counter" Nuances
**What goes wrong:** Hitting "Rate limit exceeded" even when under the "requests per minute" limit.
**Why it happens:** Kraken weights calls differently (e.g., `AddOrder` might cost 1, while `TradesHistory` costs 2).
**How to avoid:** Implement the "Call Counter" logic precisely as defined in Kraken's tier documentation (Starter vs. Intermediate vs. Pro).

### Pitfall 2: Stop-Loss Slippage
**What goes wrong:** Stop-loss triggers but fills at a much worse price.
**How to avoid:** Use `stop-loss-limit` orders instead of `stop-loss` (market) if price certainty is more important than execution certainty, or implement a "Max Slippage" check.

### Pitfall 3: Position Size Race Conditions
**What goes wrong:** Two agents open positions simultaneously, together exceeding the 5% cap.
**How to avoid:** Use a database transaction or Redis lock when calculating current exposure + new position size.

## Code Examples

### Kraken Stop-Loss Order (Live)
```python
# Source: Kraken API Docs
# Placing an entry with a linked stop-loss (Simplified)
result = k.query_private('AddOrder', {
    'pair': 'XBTUSD',
    'type': 'buy',
    'ordertype': 'limit',
    'price': '45000',
    'volume': '0.1',
    'close[ordertype]': 'stop-loss',
    'close[price]': '44000'
})
```

### Redis Frequency Limiting (RISK-05)
```python
async def check_frequency_limit(user_id: int, limit_per_hour: int):
    key = f"trade_freq:{user_id}:{datetime.now().hour}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 3600)
    if count > limit_per_hour:
        raise FrequencyLimitExceeded()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Passive Monitoring | Active Enforcement | Current Phase | Prevents errors before they occur rather than alerting after. |
| Sleep-based Limiting | Token Bucket / Counter | 2024 | More efficient use of API bandwidth; handles bursts better. |

## Open Questions

1. **Liquidity Thresholds:** What is a "standard" liquidity multiplier for Kraken?
   - *Recommendation:* Research suggests checking the top 10 levels of the order book. If the order size is > 10% of the available volume within 1% of the mid-price, reject or warn.
2. **Paper Trading Stop-Loss:** Should we simulate exchange-side stop-losses or let the `RiskMonitorAgent` handle it?
   - *Recommendation:* Implement in `PaperTradingEngine.update_market_price` for immediate response without network latency.

## Sources

### Primary (HIGH confidence)
- [Kraken API Documentation](https://docs.kraken.com/rest/) - Rate limits and order types.
- [krakenex GitHub](https://github.com/veox/python3-krakenex) - Library capabilities.

### Secondary (MEDIUM confidence)
- [CCXT Rate Limiter Implementation](https://github.com/ccxt/ccxt/blob/master/python/ccxt/base/exchange.py) - For reference on robust counter logic.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Libraries are well-established.
- Architecture: HIGH - Interceptor pattern is standard for risk.
- Pitfalls: HIGH - Kraken rate limits are a well-known hurdle.

**Research date:** 2025-02-13
**Valid until:** 2025-03-15
