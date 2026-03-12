# Phase 08 Context: Performance Analytics

## Domain Analysis
This phase transforms raw trade and balance data into actionable performance insights. It focuses on how users visualize the "skill" of their autonomous agents and the overall health of their portfolio.

## Implementation Decisions

### 1. Metric Calculation Strategy (Active Trader Model)
*   **Mark-to-Market:** Performance metrics (Win Rate, Sharpe, Drawdown) MUST include the floating P&L of currently open positions to reflect true risk.
*   **Multi-Grain Visibility:** Support Global Portfolio views as well as per-Strategy and per-Asset Pair breakdowns.
*   **Historical Fidelity:** Store historical snapshots of the metrics themselves (e.g., "Sharpe Ratio over time") to identify performance degradation.
*   **Hybrid Querying:** Use on-demand SQL queries for the "Current" view and a `performance_snapshots` table for historical charting.

### 2. Equity Curve History
*   **Frequency:** Record snapshots every hour (time-based) AND immediately following any trade execution (event-based).
*   **Price Source:** Use "Last Known Price" cached in the system (from `MarketAnalyst`) rather than external API calls to avoid rate limits.
*   **Retention:** Implement tiered retention: keep hourly data for 30 days, then condense to daily "Closing" values for long-term history.
*   **Visualization:** Use a Stacked Area Chart showing **Cash vs. Asset Value** to visualize portfolio exposure and liquidity.

### 3. Benchmark Comparison
*   **Relative Baseline:** Compare strategy performance against buying and holding the **specific asset** being traded (e.g., Strategy vs. ETH).
*   **Anchoring:** Benchmarks start at the **Session Start** (when the bot or strategy was activated).
*   **Primary Focus:** Display a single primary baseline line on charts to maintain UI clarity.
*   **Alpha Metric:** Prominently display the "Alpha" (Active Return - Benchmark Return) as a percentage badge in the header.

### 4. Real-time Delivery
*   **Transport:** Reuse the existing **SSE (Server-Sent Events)** infrastructure from Phase 7.
*   **Triggering:** Push updates only on **Trade Executions** and **Hourly Snapshots** to minimize browser/network overhead.
*   **Payload Strategy:** Full dataset on initial load; incremental "new point" updates via SSE.
*   **Broadcast Mode:** Use a global broadcast; the frontend is responsible for filtering data for the specific view (Global vs. Strategy).

## Deferred Ideas (Out of Scope)
*   **Risk-Adjusted Backtest Comparison:** Comparing live performance vs. original backtest expectations (Save for Phase 9/11).
*   **Tax Reporting Export:** Dedicated FIFO/LIFO cost basis reporting (Save for future Milestone).
*   **Correlation Heatmaps:** Visualizing asset correlation across the portfolio.

## Guidance for Researcher/Planner
*   **Investigation:** Research existing Python libraries for financial metric calculation (e.g., `empyrical` or custom math) that work with async flows.
*   **Schema:** Plan for a `performance_snapshots` table that can handle both global and per-strategy metrics.
*   **SSE Wiring:** Ensure the `AgentManager` or `TradeExecutor` can emit events that the SSE stream can pick up for dashboard updates.
