# Codebase Structure

**Analysis Date:** 2026-02-04

## Directory Layout

```
CryptoTrader/
├── backend/                    # FastAPI server + business logic
│   ├── api/                    # HTTP route handlers (routers)
│   ├── agents/                 # Autonomous trading agents
│   ├── core/                   # Infrastructure, config, security
│   ├── db/                     # Database models, migrations, ORM utilities
│   ├── services/               # Business logic + external integrations
│   ├── tests/                  # Backend test suite
│   ├── alembic/                # Database migration files
│   ├── main.py                 # FastAPI app entry point
│   ├── init_db.py              # Database initialization script
│   ├── requirements.txt         # Python dependencies
│   └── cryptotrader.db         # SQLite database file (dev)
│
├── frontend/                   # React SPA client
│   ├── src/
│   │   ├── components/         # Reusable React components
│   │   ├── context/            # React Context providers
│   │   ├── hooks/              # Custom React hooks
│   │   ├── pages/              # Route-level page components
│   │   ├── services/           # HTTP API clients (Axios)
│   │   ├── store/              # State management (if using Redux/Zustand)
│   │   ├── App.jsx             # Root app component with routing
│   │   ├── main.jsx            # React DOM mount point
│   │   └── index.css           # Global styles
│   ├── vite.config.js          # Vite bundler configuration
│   ├── package.json            # Node dependencies
│   └── index.html              # HTML entry point
│
├── prompts/                    # AI specification and project docs
├── .planning/                  # Planning documents
├── .planning/codebase/         # Codebase analysis (ARCHITECTURE.md, etc)
└── [project files]             # Git, docs, config files
```

## Directory Purposes

**`backend/api/`:**
- Purpose: HTTP route handlers organized by domain
- Contains: FastAPI APIRouter instances with endpoint definitions
- Key files: `auth.py`, `market.py`, `trades.py`, `ai.py`, `strategies.py`, `risk.py`, `alerts.py`, `export.py`, `system.py`, `errors.py`
- Pattern: Each file is a logical grouping of related endpoints

**`backend/agents/`:**
- Purpose: Autonomous agent implementations for trading decision-making
- Contains: Agent classes extending BaseAgent abstract class
- Key files: `base.py` (BaseAgent, AgentRegistry), `orchestrator.py`, `market_analyst.py`, `sentiment_agent.py`, `risk_monitor.py`, `strategy_optimizer.py`, `trade_executor.py`
- Pattern: Each agent has distinct responsibility in multi-agent system

**`backend/core/`:**
- Purpose: Cross-cutting concerns and application infrastructure
- Contains: Configuration, authentication, security, task scheduling, utilities
- Key files: `settings.py`, `auth.py`, `security.py`, `celery_app.py`, `tasks.py`, `rate_limit.py`, `audit.py`, `indicators.py`, `patterns.py`, `paper_trading.py`, `message_queue.py`, `trading_control.py`
- Pattern: Modules provide shared functionality across all layers

**`backend/db/`:**
- Purpose: Data access layer with SQLAlchemy ORM
- Contains: Database configuration, models, migrations
- Key files:
  - `database.py`: Engine setup, SessionLocal factory, initialization logic
  - `models.py`: SQLAlchemy model definitions (User, Trade, Strategy, etc.)
  - `migrations.py`: Alembic migration runner
- Pattern: All database operations go through SQLAlchemy ORM

**`backend/services/`:**
- Purpose: Business logic and external API integration
- Contains: Service classes with focused domain responsibilities
- Key files: `ai_models.py`, `strategy_ai.py`, `risk_ai.py`, `kraken.py`, `kraken_ws.py`, `market_data.py`, `trade_sync.py`, `alert_service.py`, `chat_memory.py`, `news_feed.py`, `social_sentiment.py`, `portfolio.py`, `password_reset.py`, `email.py`, `health_monitor.py`, `preference_learning.py`, `github_import.py`, `model_tracking.py`, `paper_trading_service.py`
- Pattern: Service per domain/concern; can be instantiated and injected as dependency

**`backend/tests/`:**
- Purpose: Test suite for backend functionality
- Contains: Test files mirroring backend structure
- Pattern: Tests alongside implementation code (pytest convention)

**`backend/alembic/`:**
- Purpose: Database schema versioning and migrations
- Contains: Version files with up/down migration scripts
- Key file: `versions/` directory with timestamped migration files
- Pattern: Each migration is self-contained and reversible

**`frontend/src/components/`:**
- Purpose: Reusable UI building blocks
- Contains: React functional components with isolated responsibilities
- Component examples:
  - Layout: `Layout.js` (wraps pages), `Header.js`, `Sidebar.js`
  - Forms: `LoginForm.js`, `RegisterForm.js`
  - Charts: `Chart.js`, `ChartIndicators.js`, `ChartAnnotations.js`
  - Trading: `PositionManager.js`, `ExportPanel.js`
  - Dashboards: `RiskDashboard.js`, `ModelComparison.js`
  - Alerts: `AlertNotification.js`, `AlertItem.js`
  - Other: `ChatWindow.js`, `ReasoningPanel.js`, `SentimentPanel.js`
- Pattern: Each component is self-contained with internal state management

**`frontend/src/pages/`:**
- Purpose: Route-level page components (full screens)
- Contains: Page components that compose smaller components
- Key pages:
  - Auth: `Login.js`, `Register.js`, `ForgotPassword.js`
  - Main: `Dashboard.js` (overview)
  - Trading: `LiveTrading.js` (real-time trading)
  - Strategy: `StrategyLab.js` (strategy creation/testing)
  - AI: `AIChat.js` (AI conversation)
  - Admin: `SystemLogs.js` (system events), `Settings.js` (user prefs)
  - Alerts: `Alerts.js` (alert management)
- Pattern: Pages handle route logic and compose components

**`frontend/src/context/`:**
- Purpose: Global state management via React Context API
- Key providers:
  - `AuthContext.js`: Authentication state (user, loading, error, methods)
  - `ThemeContext.js`: Theme state (dark/light mode)
- Pattern: Context + Provider component; consume with useContext

**`frontend/src/hooks/`:**
- Purpose: Reusable stateful logic and side effects
- Custom hooks:
  - `useAuth.js`: Convenience hook to access AuthContext
  - `useWebSocket.js`: WebSocket connection and subscription management
  - `useAlerts.js`: Alert subscription and notification handling
- Pattern: Return state/methods object for use in components

**`frontend/src/services/`:**
- Purpose: HTTP API communication and request handling
- Key file: `api.js`
  - Creates Axios instance with interceptors
  - Implements error normalization
  - Exports API client objects: authAPI, systemAPI, marketAPI, tradesAPI, aiAPI
- Pattern: Objects with methods returning Promise for API calls

**`frontend/src/store/`:**
- Purpose: State management (if using Redux/Zustand)
- Status: Appears minimal; primarily using Context API

## Key File Locations

**Entry Points:**
- Backend: `backend/main.py` - FastAPI app initialization
- Frontend: `frontend/src/main.jsx` - React DOM mount
- Frontend routing: `frontend/src/App.jsx` - React Router setup

**Configuration:**
- Backend: `backend/core/settings.py` - Pydantic BaseSettings with env vars
- Frontend: `frontend/vite.config.js` - Vite build configuration
- Frontend env: `frontend/.env` (if present) - Runtime environment variables

**Core Logic:**
- Authentication: `backend/api/auth.py` (routes), `backend/core/auth.py` (middleware/deps)
- Trading: `backend/api/trades.py` (routes), `backend/services/trade_sync.py` (logic)
- AI: `backend/api/ai.py` (routes), `backend/services/ai_models.py` (provider mgmt), `backend/agents/` (autonomous logic)
- Market data: `backend/services/market_data.py`, `backend/services/kraken_ws.py`

**Testing:**
- Backend: `backend/tests/` - Pytest test files
- Frontend: Tests typically co-located with components (if any)

## Naming Conventions

**Files:**
- Python: `snake_case.py` for modules (e.g., `ai_models.py`, `kraken_ws.py`)
- React: `PascalCase.js(x)` for components (e.g., `LoginForm.js`, `Chart.js`)
- React: `camelCase.js` for hooks/utils (e.g., `useAuth.js`, `api.js`)

**Directories:**
- All lowercase: `api`, `services`, `agents`, `core`, `db`
- Consistent naming: `components`, `pages`, `hooks`, `context`, `services`

**Python Functions & Variables:**
- `snake_case`: All functions, variables, module names
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE` (config values)

**React Components & Hooks:**
- Components: `PascalCase` (e.g., `Dashboard`, `PositionManager`)
- Hooks: `camelCase` starting with `use` (e.g., `useAuth`, `useWebSocket`)
- Context: `PascalCase` for context object (e.g., `AuthContext`)

**Database Tables:**
- Plural, lowercase: `users`, `strategies`, `trades`, `orders`
- Relationship foreign keys: `<table>_id` (e.g., `user_id`, `strategy_id`)

**Routes/APIs:**
- Kebab-case in URL paths: `/api/auth/login`, `/api/market/ticker`
- Resource-oriented: `/api/trades/`, `/api/strategies/`
- Actions: `/api/trades/{id}/close`, `/api/trades/{id}/ai-toggle`

## Where to Add New Code

**New Feature (Backend):**
1. **API Route**: Create endpoint in appropriate file in `backend/api/` (or new file if distinct domain)
   - Example: `backend/api/new_feature.py`
2. **Service Logic**: Implement business logic in `backend/services/` (or core if infrastructure)
   - Example: `backend/services/new_feature_service.py`
3. **Database Model** (if needed): Add SQLAlchemy model to `backend/db/models.py`
4. **Migration** (if DB change): Run `alembic revision --autogenerate -m "description"` and edit migration
5. **Tests**: Add tests to `backend/tests/test_new_feature.py`

**New Feature (Frontend):**
1. **Page Component**: Create new page in `frontend/src/pages/NewFeature.js`
   - Add route in `frontend/src/App.jsx`
2. **Reusable Components**: Create in `frontend/src/components/` if used elsewhere
   - Example: `frontend/src/components/NewFeatureWidget.js`
3. **API Calls**: Add methods to appropriate API object in `frontend/src/services/api.js`
   - Example: Add `featureAPI` or extend existing API objects
4. **State Management**: Add context if global state needed
   - Example: `frontend/src/context/FeatureContext.js`
5. **Hooks**: Extract reusable logic to `frontend/src/hooks/useNewFeature.js`

**New Service/Integration:**
1. Create service module in `backend/services/new_service.py`
2. Implement with clear public interface
3. Use dependency injection in API routes
4. Add configuration to `backend/core/settings.py` if needed (API keys, endpoints)

**New Agent:**
1. Create file in `backend/agents/new_agent.py`
2. Extend `BaseAgent` from `backend/agents/base.py`
3. Register with `AgentRegistry` in `__init__`
4. Integrate with orchestrator if needed

**Utility Functions:**
- Backend: Add to existing service or create in `backend/core/` if cross-cutting
- Frontend: Create in `frontend/src/services/` or as custom hook in `frontend/src/hooks/`

## Special Directories

**`backend/alembic/versions/`:**
- Purpose: Database migration history
- Generated: Yes (by Alembic on schema changes)
- Committed: Yes (part of version control)
- Pattern: Each file is timestamped migration; don't edit directly

**`backend/__pycache__/`, `frontend/node_modules/`:**
- Purpose: Compiled Python bytecode, Node dependencies
- Generated: Yes (automatically)
- Committed: No (.gitignore excluded)

**`backend/venv/`:**
- Purpose: Python virtual environment
- Generated: Yes (created by `python -m venv venv`)
- Committed: No (.gitignore excluded)

**`backend/tests/__pycache__/`:**
- Purpose: Compiled test bytecode
- Generated: Yes (during test runs)
- Committed: No

**`frontend/dist/`:**
- Purpose: Vite build output (production bundle)
- Generated: Yes (`npm run build`)
- Committed: No (.gitignore excluded)

**`frontend/.env*` files:**
- Purpose: Environment variables for different environments
- Generated: No (created manually)
- Committed: `.env.example` only (never `.env` with secrets)
- Usage: `VITE_API_URL`, `VITE_WS_URL`, etc.

**`backend/.env` file:**
- Purpose: Environment variables for backend configuration
- Generated: No (created manually)
- Committed: No (.gitignore excluded)
- Key vars: `DATABASE_URL`, `OPENAI_API_KEY`, `KRAKEN_API_KEY`, etc.

**`prompts/`:**
- Purpose: AI specification and initialization prompts
- Files: `app_spec.txt`, `initializer_prompt.md`, `coding_prompt.md`
- Generated: Yes (by /gsd:create-spec command)
- Committed: Yes

---

*Structure analysis: 2026-02-04*
