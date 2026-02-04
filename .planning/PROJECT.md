# CryptoTrader

## What This Is

An autonomous AI-powered cryptocurrency day trading engine. Multiple AI agents work together to analyze market conditions, identify trading opportunities, manage risk, and execute trades through the Kraken exchange. The web UI provides monitoring, configuration, and intervention controls. Paper trading first, live trading later.

## Core Value

The AI autonomously makes profitable trading decisions — watching markets, detecting signals, executing trades, and managing risk — without requiring constant human intervention.

## Requirements

### Validated

- ✓ User authentication (login, register, sessions, MFA, password reset) — existing
- ✓ React frontend with dark theme, sidebar navigation, routing — existing
- ✓ FastAPI backend with structured API routes — existing
- ✓ Kraken API connection and WebSocket market data feed — existing
- ✓ Agent framework with base class, message queue, lifecycle methods — existing
- ✓ Agent scaffolding (orchestrator, market analyst, strategy optimizer, trade executor, risk monitor, sentiment) — existing
- ✓ AI chat interface with multi-provider support (OpenAI, Claude, Ollama) — existing
- ✓ Strategy CRUD endpoints and UI shell — existing
- ✓ Paper trading engine structure — existing
- ✓ Alert system and notification framework — existing
- ✓ Risk monitoring agent and dashboard structure — existing
- ✓ Technical indicators module (RSI, MACD, Bollinger, MA) — existing
- ✓ Pattern detection module — existing
- ✓ Database schema with Alembic migrations — existing
- ✓ System health monitoring and logging — existing
- ✓ Data export endpoints — existing
- ✓ Rate limiting, CORS, security hardening — existing

### Active

- [ ] Autonomous trading loop — agents actively run on schedule/triggers, analyze markets, and make trade decisions without manual intervention
- [ ] Functional paper trading — simulated order placement, position tracking, and P&L calculation with realistic fills
- [ ] Market data pipeline — real-time Kraken data flows into agents for continuous analysis
- [ ] Signal-driven decisions — technical indicators and pattern detection actually drive agent trade recommendations
- [ ] Risk enforcement — configurable position limits, daily loss limits, max drawdown thresholds that actually halt trading
- [ ] Order management — place, track, and cancel paper orders (market, limit, stop)
- [ ] Position management — view open positions, close positions, adjust stop-loss/take-profit
- [ ] Live dashboard — real portfolio data, P&L, agent status, active positions replacing placeholders
- [ ] AI chat with trading context — AI references current positions, market state, and its own reasoning
- [ ] Configurable autonomy — settings to control aggressiveness, signal weights, approval requirements
- [ ] Real alerts — notifications when AI takes action, risk limits approached, or market conditions change
- [ ] Strategy execution — strategies the AI actually follows when paper trading, with measurable performance
- [ ] Exchange abstraction layer — Kraken implementation behind an interface for future exchange support

### Out of Scope

- Multiple exchanges — Kraken only for v1, architecture should support adding others later
- Stock/equity trading — crypto only for v1, broader asset classes deferred
- Multi-user deployment — single user, but code on GitHub for others to fork
- Live trading with real money — paper trading only until AI proves profitable
- Mobile native app — responsive web only
- Social/community features — single-user tool

## Context

- Substantial codebase exists (~300 files across backend and frontend) with all scaffolding in place
- Previous automation attempt (triad) produced structure but not functional features
- All pages render but show static/placeholder data — the trading engine doesn't actually run
- Agents exist as classes but don't autonomously execute or make real decisions
- Paper trading engine exists but isn't wired into the agent loop
- The gap is between "skeleton" and "functional autonomous trading system"
- Kraken API integration exists but order placement isn't connected to agent decisions
- Known tech debt: fail-open rate limiting, sync DB queries in async routes, no pagination, bare exception handling, paper trading state not persisted

## Constraints

- **Exchange**: Kraken only — but abstracted for future exchanges
- **AI Providers**: OpenAI, Anthropic Claude, Ollama (local) — already integrated
- **Stack**: Python 3.12 / FastAPI / SQLAlchemy / React 18 / Vite / Tailwind — established, no migration
- **Database**: SQLite for development — PostgreSQL-ready via SQLAlchemy
- **Task Queue**: Celery + Redis for background agent execution
- **Paper First**: No real money trades until paper trading is validated
- **Single User**: No multi-tenancy concerns for v1

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Paper trading before live | Validate AI decisions risk-free before committing real capital | — Pending |
| Kraken as first exchange | User's primary exchange; good API documentation | — Pending |
| Exchange abstraction layer | Future support for Coinbase, Binance, stock brokers | — Pending |
| Keep existing stack | Large codebase already built on FastAPI/React; no reason to migrate | ✓ Good |
| Multi-provider AI | OpenAI, Claude, Ollama already integrated; flexibility to compare | ✓ Good |
| Configurable autonomy | User controls how aggressive AI trades, what needs approval | — Pending |

---
*Last updated: 2026-02-04 after initialization*
