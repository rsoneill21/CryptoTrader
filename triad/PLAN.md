# PLAN — CryptoTrader

> This file is owned by Claude. Codex implements tasks exactly as written here.

## Objective

Build an AI-powered cryptocurrency trading platform with multi-agent architecture. The system enables autonomous market analysis, strategy creation/testing via paper trading, and live trading execution with user approval. Target: 230 features across 11 implementation phases.

## Current Phase

**Phase 1: Foundation & Infrastructure** ✅ COMPLETE

All 20 tasks completed:
- ✅ Backend: Auth system (register, login, logout, sessions, password reset)
- ✅ Backend: API router structure with auth/system routes
- ✅ Backend: Celery/Redis background task infrastructure
- ✅ Backend: Base agent class and message queue interface
- ✅ Frontend: Auth context, hooks, protected routes
- ✅ Frontend: Login/Register pages with forms
- ✅ Frontend: Layout shell (sidebar, header, theme toggle)
- ✅ Frontend: Dashboard with system health check

**Ready for Phase 2: Exchange Integration & Trade Executor Agent**

---

## Tasks

### Phase 1: Foundation & Infrastructure

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 1.1 | Create base API router structure | ✅ done | `backend/api/__init__.py`, `backend/api/auth.py`, `backend/api/system.py` | Router files created with empty route stubs; routers imported and mounted in `main.py` |
| 1.2 | Implement user registration endpoint | ✅ done | `backend/api/auth.py`, `backend/core/security.py` | `POST /api/auth/register` accepts email/password, hashes password with bcrypt, creates user in DB, returns user ID |
| 1.3 | Implement login endpoint with session creation | ✅ done | `backend/api/auth.py`, `backend/core/security.py` | `POST /api/auth/login` validates credentials, creates session token (UUID), stores in sessions table with expiry, returns token |
| 1.4 | Implement logout endpoint | ✅ done | `backend/api/auth.py` | `POST /api/auth/logout` invalidates session token, removes from DB |
| 1.5 | Create authentication middleware/dependency | ✅ done | `backend/core/auth.py` | FastAPI dependency that extracts token from Authorization header, validates session, returns current user or 401 |
| 1.6 | Implement session validation endpoint | ✅ done | `backend/api/auth.py` | `GET /api/auth/session` returns current user info if valid session, 401 if expired/invalid |
| 1.7 | Add auto-logout on session timeout | ✅ done | `backend/core/auth.py` | Middleware checks session expiry against `session_timeout_minutes` in user prefs; expired sessions return 401 |
| 1.8 | Implement password reset flow | ✅ done | `backend/api/auth.py`, `backend/services/email.py`, `backend/services/password_reset.py` | `POST /api/auth/password/reset` generates reset token, stores it, sends email (mock for now); `POST /api/auth/password/reset/confirm` validates token and updates password |
| 1.9 | Create React auth context and hooks | ✅ done | `frontend/src/context/AuthContext.js`, `frontend/src/hooks/useAuth.js` | Context stores user/token; `useAuth` hook provides login/logout/register functions; persists token in localStorage |
| 1.10 | Build Login page component | ✅ done | `frontend/src/pages/Login.js`, `frontend/src/components/LoginForm.js` | Login form with email/password inputs, error display, submit calls API, redirects to dashboard on success |
| 1.11 | Build Registration page component | ✅ done | `frontend/src/pages/Register.js`, `frontend/src/components/RegisterForm.js` | Registration form with email/password/confirm, validation, submit calls API, redirects to login on success |
| 1.12 | Create protected route wrapper | ✅ done | `frontend/src/components/ProtectedRoute.js` | Component that checks auth state; redirects to /login if not authenticated; renders children if authenticated |
| 1.13 | Build main app layout shell | ✅ done | `frontend/src/components/Layout.js`, `frontend/src/components/Sidebar.js`, `frontend/src/components/Header.js`, `frontend/src/context/ThemeContext.js` | Layout with collapsible sidebar (pop in/out, state persisted), top nav bar (user info, alerts icon, AI status), main content area; dark/light theme toggle with dark as default |
| 1.14 | Integrate layout with routes | ✅ done | `frontend/src/App.js` | All authenticated routes wrapped in Layout component; Login/Register use minimal layout; ProtectedRoute enforces auth |
| 1.15 | Create API client service | ✅ done | `frontend/src/services/api.js` | Axios instance with base URL, interceptors for auth token header, 401 handling (redirect to login) |
| 1.16 | Implement basic dashboard page | ✅ done | `frontend/src/pages/Dashboard.js` | Dashboard shows: system health status, quick stats placeholders, navigation cards to main features |
| 1.17 | Set up Celery/Redis for background tasks | ✅ done | `backend/core/celery_app.py`, `backend/core/tasks.py` | Celery app configured with Redis broker; basic test task works; documented in README |
| 1.18 | Create base agent class structure | ✅ done | `backend/agents/base.py`, `backend/agents/__init__.py` | Abstract `BaseAgent` class with: `async run()`, `process_message()`, `send_message()` methods; agent registry pattern |
| 1.19 | Implement agent message queue interface | ✅ done | `backend/core/message_queue.py` | Redis pub/sub wrapper for agent communication; methods: `publish(channel, message)`, `subscribe(channel, callback)` |
| 1.20 | Add system logs endpoint | ✅ done | `backend/api/system.py` | `GET /api/system/logs` returns paginated logs from system_logs table with filtering by level/source |

### Phase 2: Exchange Integration & Trade Executor Agent

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 2.1 | Create Kraken API service wrapper | pending | `backend/services/kraken.py` | Wrapper class for krakenex library; methods: `get_ticker()`, `get_ohlc()`, `get_balance()`, `place_order()`, `cancel_order()`, `get_order_status()` |
| 2.2 | Implement real-time price WebSocket | pending | `backend/services/kraken_ws.py`, `backend/api/market.py` | WebSocket connection to Kraken; broadcasts price updates to connected clients via FastAPI WebSocket endpoint |
| 2.3 | Build market data endpoints | pending | `backend/api/market.py` | `GET /api/market/prices`, `GET /api/market/orderbook/{symbol}`, `GET /api/market/candles/{symbol}` |
| 2.4 | Create Trade Executor Agent | pending | `backend/agents/trade_executor.py` | Agent that: receives trade signals, places orders via Kraken, handles retries/errors, logs all actions |
| 2.5 | Implement order management endpoints | pending | `backend/api/trades.py` | `GET /api/trades/active`, `POST /api/trades/{id}/close`, `PUT /api/trades/{id}/adjust` |
| 2.6 | Add portfolio/balance tracking | pending | `backend/services/portfolio.py`, `backend/api/market.py` | Service that fetches/caches balance from Kraken; endpoint returns current holdings |
| 2.7 | Implement manual trade detection | pending | `backend/services/trade_sync.py` | Background task compares Kraken trade history with DB; flags trades not initiated by system as `is_manual=True` |

### Phase 3: Market Analyst Agent & Data Infrastructure

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 3.1 | Implement Market Analyst Agent | pending | `backend/agents/market_analyst.py` | Agent monitors price data, calculates indicators, detects patterns, publishes insights to message queue |
| 3.2 | Build technical indicators module | pending | `backend/core/indicators.py` | Functions for: RSI, MACD, Bollinger Bands, SMA, EMA; uses pandas-ta or custom implementation |
| 3.3 | Create pattern detection module | pending | `backend/core/patterns.py` | Functions to detect: support/resistance levels, trend lines, common candlestick patterns |
| 3.4 | Build real-time chart component | pending | `frontend/src/components/Chart.js` | TradingView lightweight-charts integration; displays candlesticks, supports multiple timeframes |
| 3.5 | Add indicator overlay to charts | pending | `frontend/src/components/ChartIndicators.js` | Component to render selected indicators on chart; checkbox UI to toggle each indicator |
| 3.6 | Implement market data storage | pending | `backend/services/market_data.py` | Service to store OHLCV data in market_data table; retention policy for old data |

### Phase 4: AI Strategy Lab Dashboard

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 4.1 | Build strategy CRUD endpoints | pending | `backend/api/strategies.py` | Full REST API: GET list, GET single, POST create, PUT update, DELETE; filter by status |
| 4.2 | Implement AI strategy proposal | pending | `backend/services/strategy_ai.py` | Integration with OpenAI/Claude to propose strategies based on market analysis |
| 4.3 | Build GitHub strategy import | pending | `backend/services/github_import.py` | Parse strategy files from GitHub URL; AI analyzes and suggests modifications |
| 4.4 | Create paper trading engine | pending | `backend/core/paper_trading.py` | Simulates trades against historical/live data; tracks virtual positions and P&L |
| 4.5 | Implement Strategy Optimizer Agent | pending | `backend/agents/strategy_optimizer.py` | Agent that tunes strategy parameters via paper trading simulations |
| 4.6 | Build Strategy Lab page | pending | `frontend/src/pages/StrategyLab.js` | Strategy list, detail view, performance metrics, paper trading controls |
| 4.7 | Add strategy promotion workflow | pending | `backend/api/strategies.py` | `POST /api/strategies/{id}/promote` endpoint with confirmation; updates status to live |

### Phase 5: Live Trading Dashboard

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 5.1 | Build Live Trading page | pending | `frontend/src/pages/LiveTrading.js` | Large chart, AI annotations overlay, positions list, reasoning panel |
| 5.2 | Implement AI annotations layer | pending | `frontend/src/components/ChartAnnotations.js` | Draws support/resistance, patterns, entry/exit zones on chart; toggleable via checkboxes |
| 5.3 | Create AI reasoning panel | pending | `frontend/src/components/ReasoningPanel.js` | Shows current AI thinking, recent decisions, confidence scores |
| 5.4 | Build position management UI | pending | `frontend/src/components/PositionManager.js` | Active positions list with close/adjust controls; P&L display |
| 5.5 | Add WebSocket price updates | pending | `frontend/src/hooks/useWebSocket.js` | Hook for WebSocket connection; real-time price updates to chart |

### Phase 6: Risk Monitor Agent & Risk System

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 6.1 | Implement Risk Monitor Agent | pending | `backend/agents/risk_monitor.py` | Continuously calculates risk score; triggers alerts/pause when thresholds breached |
| 6.2 | Build risk settings endpoints | pending | `backend/api/risk.py` | `GET /api/risk/settings`, `PUT /api/risk/settings`, `GET /api/risk/score` |
| 6.3 | Create risk dashboard component | pending | `frontend/src/components/RiskDashboard.js` | Visual risk score gauge, individual factor breakdown, settings form |
| 6.4 | Implement trading pause functionality | pending | `backend/core/trading_control.py` | Global flag to pause/resume trading; Risk Monitor can trigger automatically |
| 6.5 | Add AI risk adjustment recommendations | pending | `backend/services/risk_ai.py` | AI analyzes risk state and recommends parameter changes; stored in risk_settings |

### Phase 7: AI Chat Dashboard & Orchestrator

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 7.1 | Build chat endpoints | pending | `backend/api/ai.py` | `POST /api/ai/chat`, `GET /api/ai/chat/history`; streams responses |
| 7.2 | Implement Orchestrator Agent | pending | `backend/agents/orchestrator.py` | Main AI that coordinates other agents, handles user chat, makes trading decisions |
| 7.3 | Create chat UI component | pending | `frontend/src/pages/AIChat.js`, `frontend/src/components/ChatWindow.js` | Message history, input box, streaming responses, context panel |
| 7.4 | Add conversation memory | pending | `backend/services/chat_memory.py` | Stores chat history; retrieves relevant past conversations for context |
| 7.5 | Implement preference learning | pending | `backend/services/preference_learning.py` | Tracks user preferences from chat; applies to future interactions |

### Phase 8: Alerts & Activity Log Dashboard

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 8.1 | Build alerts endpoints | pending | `backend/api/alerts.py` | Full REST API for alerts; filtering, status updates, bulk operations |
| 8.2 | Create alert generation service | pending | `backend/services/alert_service.py` | Central service that all agents use to create alerts; handles severity, deduplication |
| 8.3 | Build Alerts page | pending | `frontend/src/pages/Alerts.js` | Filterable alert list, detail panel, quick actions, activity log tab |
| 8.4 | Add alert-to-chat linking | pending | `frontend/src/components/AlertItem.js` | Click alert to open chat with context pre-loaded |
| 8.5 | Implement alert notifications | pending | `frontend/src/components/AlertNotification.js`, `frontend/src/hooks/useAlerts.js` | Real-time alert popup, badge count in header |

### Phase 9: Sentiment/News Agent & Data Sources

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 9.1 | Implement Sentiment/News Agent | pending | `backend/agents/sentiment_agent.py` | Monitors configured data sources, calculates sentiment, publishes to queue |
| 9.2 | Build social media integration | pending | `backend/services/social_sentiment.py` | Twitter/X and Reddit API integration; extracts crypto mentions, sentiment |
| 9.3 | Add news feed integration | pending | `backend/services/news_feed.py` | Fetches crypto news from configured sources; AI summarizes relevance |
| 9.4 | Create data sources config UI | pending | `frontend/src/pages/Settings.js` (partial) | Enable/disable data sources, configure API keys, view fetch status |
| 9.5 | Build sentiment display component | pending | `frontend/src/components/SentimentPanel.js` | Shows current sentiment score, recent sentiment data, source breakdown |

### Phase 10: AI Model Management & Comparison

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 10.1 | Create multi-model service | pending | `backend/services/ai_models.py` | Unified interface for OpenAI, Claude, Ollama; model switching |
| 10.2 | Build model selection endpoints | pending | `backend/api/ai.py` | `GET /api/ai/models`, `PUT /api/ai/models/active`, `GET /api/ai/models/comparison` |
| 10.3 | Implement model performance tracking | pending | `backend/services/model_tracking.py` | Tracks decisions/accuracy per model; stores in model_performance table |
| 10.4 | Create model comparison UI | pending | `frontend/src/components/ModelComparison.js` | Side-by-side performance metrics, selection dropdowns |

### Phase 11: Export, Polish & Error Handling

| ID | Task | Status | Files | Acceptance Criteria |
|----|------|--------|-------|---------------------|
| 11.1 | Build export endpoints | pending | `backend/api/export.py` | `GET /api/export/trades` (CSV), `GET /api/export/strategies` with date range filters |
| 11.2 | Create export UI | pending | `frontend/src/components/ExportPanel.js` | Date range selector, format options, download button |
| 11.3 | Implement comprehensive error handling | pending | Multiple files | API returns consistent error format; frontend shows user-friendly messages |
| 11.4 | Add connection failure recovery | pending | `backend/services/kraken.py`, `frontend/src/hooks/useWebSocket.js` | Auto-reconnect on connection loss; queue requests during outage |
| 11.5 | Build system health monitoring | pending | `backend/services/health_monitor.py` | Tracks service status; endpoint returns detailed health info |
| 11.6 | UI polish and responsive design | pending | Multiple frontend files | All pages responsive; consistent styling; loading states; animations |

---

## Completed Tasks

### Phase 1: Foundation & Infrastructure (20/20 tasks)
- 1.1-1.8: Backend auth system complete
- 1.9-1.16: Frontend auth and UI shell complete
- 1.17-1.20: Agent infrastructure complete

---

## Architecture Decisions

1. **Authentication**: Session-based with UUID tokens stored in DB (not JWT) for easy revocation and session management
2. **Agent Communication**: Redis pub/sub for inter-agent messaging; Celery for background task scheduling
3. **Real-time Updates**: WebSocket for price data and alerts; polling fallback for less critical data
4. **AI Integration**: Unified interface supporting multiple providers (OpenAI, Claude, Ollama) with per-agent configuration
5. **Database**: SQLite for simplicity; schema supports migration to PostgreSQL if needed
6. **Theme**: Dark theme default, light theme option; user preference stored in DB
7. **Navigation**: Collapsible sidebar (pop in/out) + top nav bar; sidebar state persisted
8. **Exchange**: Kraken first; architecture supports adding Binance, Coinbase later

---

## Dependencies Between Phases

```
Phase 1 ──┬── Phase 2 ──── Phase 3 ──── Phase 4 ──── Phase 5
          │                                │
          └── Phase 6 ◄────────────────────┘
                │
Phase 7 ◄───────┴── Phase 8
   │
Phase 9 ◄───────────┘
   │
Phase 10 ◄──────────┘
   │
Phase 11 ◄──────────┘
```

- Phase 1 (Foundation) must complete before any other phase
- Phase 2 (Exchange) and Phase 6 (Risk) can proceed in parallel after Phase 1
- Phase 4 (Strategy Lab) depends on Phase 3 (Market Analyst)
- Phase 5 (Live Trading) depends on Phase 4
- Phase 7 (Chat) depends on Phase 6 completing
- Phases 8-11 build on earlier phases incrementally

---

## Notes

- Project analyzed on: 2026-01-29
- Last updated: 2026-01-29
- Feature count target: 230 features
- Technology stack: React + FastAPI + SQLite + Redis/Celery
- Primary exchange: Kraken API
- AI providers: OpenAI (GPT-4), Anthropic (Claude), Ollama (future)

---

## For Codex

When implementing tasks:
1. Read the full task description and acceptance criteria
2. Only modify files listed in the "Files" column
3. Run tests if specified
4. Update AGENTS_STATE.md with progress
5. Create a descriptive commit message

If a task is unclear, stop and flag it in AGENTS_STATE.md rather than guessing.

### Coding Standards

- **Python**: Use type hints, async/await for IO operations, Pydantic for validation
- **React**: Functional components with hooks, PropTypes or TypeScript for props
- **Styling**: TailwindCSS utility classes, dark theme as default
- **Error Handling**: All API calls wrapped in try/catch, user-friendly error messages
- **Testing**: Write tests for critical paths (auth, trading, risk calculations)
