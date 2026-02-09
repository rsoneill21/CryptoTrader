# Phase 08: Performance Analytics - Research

**Researched:** 2025-02-10
**Domain:** Financial Analytics & Portfolio Performance
**Confidence:** HIGH

## Summary

Phase 08 focuses on converting raw trade data and real-time market prices into actionable performance metrics. The research confirms that the "Active Trader" model (including floating P&L) is essential for crypto volatility. We will use established Python libraries for the math while implementing a custom tiered snapshotting system for historical fidelity.

**Primary recommendation:** Use `QuantStats` for metric calculations and a single `performance_snapshots` table with a `grain` column for data retention management.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `quantstats` | ^0.0.62 | Performance metrics (Sharpe, Drawdown, Alpha) | Built on Pandas, extremely easy to use for "tear sheets". |
| `pandas` | ^2.2.0 | Data manipulation | Industry standard for time-series financial data. |
| `react-chartjs-2` | ^5.2.0 | Dashboard Visualization | Optimized for React; supports incremental updates via refs. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `decimal` | (Built-in) | Precision math | Always use for currency/P&L to avoid floating point errors. |
| `aiosqlite` | Current | Async Database | Existing project standard for persistence. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `quantstats` | `pyfolio-reloaded` | `quantstats` is easier to integrate into web APIs vs. Jupyter. |
| `quantstats` | Custom Math | Hand-rolling Sharpe/Drawdown is error-prone regarding day-counts and risk-free rates. |

**Installation:**
```bash
pip install quantstats pandas
```

## Architecture Patterns

### Recommended Snapshot Schema
A single table with a `grain` discriminator allows for easy rollups and unified querying.

```sql
CREATE TABLE performance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    strategy_id TEXT, -- NULL for global portfolio
    grain TEXT CHECK(grain IN ('hourly', 'daily', 'event')),
    total_equity DECIMAL,
    cash_balance DECIMAL,
    asset_value DECIMAL, -- Floating value of open positions
    unrealized_pnl DECIMAL,
    realized_pnl DECIMAL,
    drawdown DECIMAL,
    sharpe_ratio DECIMAL,
    alpha DECIMAL -- Relative to benchmark
);
```

### Pattern 1: Mark-to-Market (MtM) Valuation
**What:** Valuing the portfolio based on current market prices before metric calculation.
**When to use:** Every hourly snapshot and trade execution.
**Example:**
```python
# Logic: Total Equity = Cash + Sum(Position.Size * Last_Price)
async def calculate_current_equity(db_session, market_analyst):
    positions = await get_open_positions(db_session)
    asset_value = Decimal("0")
    for pos in positions:
        summary = await market_analyst.get_indicator_summary(pos.symbol)
        last_price = summary.get("last_price")
        asset_value += pos.quantity * last_price
    
    cash = await get_cash_balance(db_session)
    return cash + asset_value
```

### Anti-Patterns to Avoid
- **Point-in-Time Metrics:** Calculating Sharpe only on realized trades. (Ignores "underwater" open positions).
- **Frontend Math:** Calculating complex metrics like Drawdown on the frontend. (Inconsistent and slow for large histories).
- **Global SSE Overload:** Pushing the entire equity curve on every price tick. (Use incremental updates instead).

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sharpe Ratio | `(return - rf) / std` | `qs.stats.sharpe` | Handles annualization and different timeframes correctly. |
| Max Drawdown | Peak-to-trough logic | `qs.stats.max_drawdown` | Standardized implementation used by institutional traders. |
| Alpha | Benchmarking logic | `qs.stats.alpha` | Correctly handles correlation (Beta) if using Jensen's Alpha. |

## Common Pitfalls

### Pitfall 1: Survival Bias in Daily Rollups
**What goes wrong:** Deleting hourly data without ensuring the *last* record of the day is preserved as the "Daily Close".
**Prevention strategy:** When condensing to daily, explicitly select the record closest to `23:59:59` as the daily snapshot.

### Pitfall 2: Async Thread Blocking
**What goes wrong:** `quantstats` and `pandas` are CPU-intensive and synchronous.
**How to avoid:** Run performance calculations in `asyncio.to_thread` to prevent blocking the FastAPI/Agent event loop.

## Code Examples

### Incremental Chart Update (React)
Using a `ref` allows updating the chart without a full component re-mount, ensuring smooth animations.

```typescript
// Source: https://www.chartjs.org/docs/latest/developers/updates.html
const chartRef = useRef<ChartJS>(null);

const handleSSEUpdate = (newPoint: { timestamp: string, cash: number, asset: number }) => {
  const chart = chartRef.current;
  if (chart) {
    chart.data.labels.push(newPoint.timestamp);
    chart.data.datasets[0].data.push(newPoint.cash);
    chart.data.datasets[1].data.push(newPoint.asset);
    
    // Keep only last 100 points for performance
    if (chart.data.labels.length > 100) {
      chart.data.labels.shift();
      chart.data.datasets.forEach(dataset => dataset.data.shift());
    }
    
    chart.update('none'); // Update without animation for real-time feel
  }
};
```

### Calculating Alpha (Python)
```python
import quantstats as qs

# Source: https://github.com/ranaroussi/quantstats
def calculate_metrics(returns_series, benchmark_series):
    # returns_series: pd.Series of daily/hourly pct changes
    alpha = qs.stats.alpha(returns_series, benchmark_series)
    sharpe = qs.stats.sharpe(returns_series)
    return {"alpha": alpha, "sharpe": sharpe}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Close-to-Close | Mark-to-Market | Modern HFT | Reflects real risk of open positions. |
| Manual SQL Rollups | Tiered snapshots | 2020+ | Better balance between storage and historical fidelity. |
| Static Charts | Streaming SSE Charts | React 18+ | Real-time dashboard experience. |

## Open Questions

1. **Benchmark Data Availability:**
   - What we know: We use the `MarketAnalyst` cache for the traded asset.
   - What's unclear: How to handle benchmarking for multi-asset strategies (Weighted average vs. a single primary asset).
   - Recommendation: Follow `CONTEXT.md` - use the *specific asset* being traded. For global views, default to BTC as the benchmark.

## Sources

### Primary (HIGH confidence)
- `quantstats` - [GitHub Repo](https://github.com/ranaroussi/quantstats)
- `Chart.js` - [Performance Documentation](https://www.chartjs.org/docs/latest/general/performance.html)
- `react-chartjs-2` - [Ref usage](https://react-chartjs-2.js.org/docs/working-with-chartjs-instance)

### Secondary (MEDIUM confidence)
- Standard Alpha/Beta calculations for Crypto (Jensen's Alpha vs Simple Outperformance).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Libraries are mature and standard.
- Architecture: HIGH - Tiered retention is a proven pattern.
- Pitfalls: HIGH - Common issues in financial software are well-documented.

**Research date:** 2025-02-10
**Valid until:** 2025-08-10
