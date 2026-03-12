# Codebase Structure

**Analysis Date:** 2026-02-04

## Directory Layout

```
CryptoTrader/
├── backend/                         # FastAPI application
│   ├── main.py                      # Application entry point
│   ├── init_db.py                   # Database initialization script
│   ├── api/                         # HTTP request handlers
│   │   ├── auth.py                  # Authentication routes
│   │   ├── market.py                # Market data and WebSocket routes
│   │   ├── trades.py                # Trade management routes
│   │   ├── strategies.py            # Strategy CRUD routes
│   │   ├── alerts.py                # Alert management routes
│   │   ├── ai.py                    # AI chat and decision routes
│   │   ├── risk.py                  # Risk analysis routes
│   │   ├── export.py                # Data export routes
│   │   ├── system.py                # System health, logs routes
│   │   ├── errors.py                # Exception handlers
│   │   └── __init__.py              # Router exports
│   ├── services/                    # Business logic and integrations
│   │   ├── kraken.py                # Kraken exchange API client
│   │   ├── kraken_ws.py             # Kraken WebSocket feed handler
│   │   ├── market_data.py           # Market data aggregation
│   │   ├── portfolio.py             # Portfolio calculations
│   │   ├── ai_models.py             # AI provider routing (OpenAI, Claude, Groq)
│   │   ├── chat_memory.py           # Chat history management
│   │   ├── alert_service.py         # Alert notification dispatch
│   │   ├── risk_ai.py               # Risk assessment AI
│   │   ├── strategy_ai.py           # Strategy optimization AI
│   │   ├── social_sentiment.py      # Sentiment analysis service
│   │   ├── news_feed.py             # News aggregation
│   │   ├── health_monitor.py        # System health checks
│   │   ├── email.py                 # Email sending service
│   │   ├── password_reset.py        # Password reset token management
│   │   ├── paper_trading_service.py # Paper trading backend
│   │   └── __init__.py
│   ├── agents/                      # AI agents for autonomous decisions
│   │   ├── base.py                  # Base agent class and message types
│   │   ├── orchestrator.py          # Main orchestrator agent
│   │   ├── market_analyst.py        # Market analysis agent
│   │   ├── strategy_optimizer.py    # Strategy optimization agent
│   │   ├── trade_executor.py        # Trade execution agent
│   │   ├── risk_monitor.py          # Risk monitoring agent
│   │   ├── sentiment_agent.py       # Sentiment analysis agent
│   │   └── __init__.py
│   ├── core/                        # Infrastructure and cross-cutting concerns
│   │   ├── settings.py              # Application configuration via Pydantic
│   │   ├── security.py              # Password hashing, token generation, MFA
│   │   ├── auth.py                  # Session and token verification
│   │   ├── rate_limit.py            # Rate limiting utilities
│   │   ├── message_queue.py         # Celery message queue and pub/sub
│   │   ├── celery_app.py            # Celery application configuration
│   │   ├── tasks.py                 # Background job definitions
│   │   ├── trading_control.py       # Trading execution control and state
│   │   ├── indicators.py            # Technical analysis indicators
│   │   ├── paper_trading.py         # Paper trading engine
│   │   ├── audit.py                 # Audit logging utilities
│   │   ├── patterns.py              # Trading pattern recognition
│   │   └── __init__.py
│   ├── db/                          # Database layer
│   │   ├── database.py              # SQLAlchemy engine, session factory, initialization
│   │   ├── models.py                # ORM models (User, Trade, Strategy, etc.)
│   │   ├── migrations.py            # Alembic migration runner
│   │   ├── alembic/                 # Database migration files
│   │   │   └── versions/            # Migration scripts (auto-generated)
│   │   └── __init__.py
│   ├── tests/                       # Test suite
│   └── venv/                        # Python virtual environment (excluded from git)
├── frontend/                        # React application
│   ├── src/
│   │   ├── main.jsx                 # React bootstrap entry
│   │   ├── App.jsx                  # Root component with routing
│   │   ├── pages/                   # Full-page components
│   │   │   ├── Login.js             # User login page
│   │   │   ├── Register.js          # User registration page
│   │   │   ├── ForgotPassword.js    # Password reset request page
│   │   │   ├── Dashboard.js         # Main dashboard with stats and features
│   │   │   ├── LiveTrading.js       # Live/paper trading interface
│   │   │   ├── StrategyLab.js       # Strategy creation and management
│   │   │   ├── AIChat.js            # AI conversation interface
│   │   │   ├── Alerts.js            # Alert management and history
│   │   │   ├── SystemLogs.js        # System event logs
│   │   │   └── Settings.js          # User preferences and configuration
│   │   ├── components/              # Reusable React components
│   │   │   ├── Layout.js            # Main layout wrapper with sidebar and header
│   │   │   ├── Header.js            # Top navigation bar
│   │   │   ├── Sidebar.js           # Side navigation menu
│   │   │   ├── Chart.js             # Interactive chart using lightweight-charts
│   │   │   ├── ChartIndicators.js   # Technical indicator overlays
│   │   │   ├── ChartAnnotations.js  # Chart drawing tools
│   │   │   ├── ChatWindow.js        # AI chat message display
│   │   │   ├── PositionManager.js   # Trade/position entry and management
│   │   │   ├── RiskDashboard.js     # Risk metrics and controls
│   │   │   ├── SentimentPanel.js    # Market sentiment display
│   │   │   ├── ReasoningPanel.js    # AI reasoning explanation
│   │   │   ├── ModelComparison.js   # Compare multiple AI model outputs
│   │   │   ├── ExportPanel.js       # Data export interface
│   │   │   ├── AlertItem.js         # Single alert display
│   │   │   ├── AlertNotification.js # Toast-style alert notifications
│   │   │   ├── LoginForm.js         # Reusable login form
│   │   │   ├── RegisterForm.js      # Reusable registration form
│   │   │   └── ProtectedRoute.js    # Route guard for authentication
│   │   ├── context/                 # React Context providers
│   │   │   ├── AuthContext.js       # Authentication state and user data
│   │   │   └── ThemeContext.js      # Theme (light/dark) state
│   │   ├── hooks/                   # Custom React hooks
│   │   │   ├── useAuth.js           # Authentication utilities
│   │   │   ├── useWebSocket.js      # WebSocket connection management
│   │   │   └── useAlerts.js         # Alert subscription and state
│   │   └── services/                # API clients and utilities
│   │       └── api.js               # Axios instance with interceptors
│   ├── public/                      # Static assets
│   ├── package.json                 # NPM dependencies and scripts
│   ├── vite.config.js               # Vite build configuration
│   ├── tailwind.config.js           # Tailwind CSS configuration
│   ├── postcss.config.js            # PostCSS plugins
│   ├── eslint.config.js             # ESLint rules
│   └── dist/                        # Built output (excluded from git)
├── .planning/                       # Planning and analysis documents
│   └── codebase/                    # Generated codebase analysis
│       ├── ARCHITECTURE.md          # (this file) Architectural overview
│       ├── STRUCTURE.md             # (this file) Directory structure
│       ├── CONVENTIONS.md           # Coding patterns and conventions
│       ├── TESTING.md               # Test patterns and framework info
│       ├── STACK.md                 # Technology stack details
│       ├── INTEGRATIONS.md          # External service integrations
│       └── CONCERNS.md              # Technical debt and issues
├── .triad/                          # Triad agent framework files (AI code generation)
├── triad/                           # Triad monorepo submodule
├── prompts/                         # AI agent prompts and specifications
├── scripts/                         # Utility scripts
├── .env.example                     # Example environment configuration
├── README.md                        # Project documentation
└── pyproject.toml / requirements.txt # Backend dependencies
```

## Directory Purposes

**backend/api:**
- Purpose: HTTP request handlers organized by feature domain (auth, market, trades, etc.)
- Contains: FastAPI route definitions with Pydantic request/response models
- Key files: `auth.py` (login/register/MFA), `market.py` (market data WebSocket), `ai.py` (chat endpoint), `trades.py` (trade CRUD)

**backend/services:**
- Purpose: Domain-specific business logic and third-party service integrations
- Contains: Stateful service classes for market data, exchange communication, AI routing, portfolio calculations
- Key files: `kraken.py` (REST API wrapper), `kraken_ws.py` (WebSocket feed), `ai_models.py` (provider routing), `alert_service.py` (notifications)

**backend/agents:**
- Purpose: Autonomous AI agents that make trading decisions and analyze markets
- Contains: Agent subclasses that implement decision algorithms, publish to message queue
- Key files: `orchestrator.py` (main coordinator), `market_analyst.py` (trend analysis), `risk_monitor.py` (position validation)

**backend/core:**
- Purpose: Infrastructure, configuration, and cross-cutting utilities shared across all layers
- Contains: Settings management, security utilities, authentication, rate limiting, task definitions, audit logging
- Key files: `settings.py` (env config), `security.py` (password/token utilities), `tasks.py` (Celery background jobs)

**backend/db:**
- Purpose: Database abstraction layer with ORM models and schema management
- Contains: SQLAlchemy ORM models, database session factory, migration runner
- Key files: `models.py` (User, Trade, Strategy, Alert entities), `database.py` (engine and session setup)

**frontend/src/pages:**
- Purpose: Full-page components that correspond to routes in the application
- Contains: Layout, data fetching, page-specific logic
- Key files: `Dashboard.js` (home), `LiveTrading.js` (trading UI), `StrategyLab.js` (strategy builder), `AIChat.js` (chat interface)

**frontend/src/components:**
- Purpose: Reusable UI components used across multiple pages
- Contains: Chart, forms, modals, notifications, lists, panels
- Key files: `Chart.js` (market chart), `PositionManager.js` (trade entry), `ChatWindow.js` (message list)

**frontend/src/context:**
- Purpose: React Context providers for shared state management
- Contains: Authentication state, theme state, user profile data
- Key files: `AuthContext.js` (user, token), `ThemeContext.js` (dark/light mode)

**frontend/src/hooks:**
- Purpose: Custom React hooks for reusable logic
- Contains: Authentication helpers, WebSocket management, alert subscriptions
- Key files: `useAuth.js` (login/logout), `useWebSocket.js` (connection lifecycle)

## Key File Locations

**Entry Points:**
- `backend/main.py`: FastAPI app initialization, routes registration, middleware setup
- `frontend/src/main.jsx`: React app bootstrap and DOM mounting
- `backend/init_db.py`: Database schema initialization on startup

**Configuration:**
- `backend/core/settings.py`: Environment-based app configuration (port, database URL, API keys, security settings)
- `frontend/vite.config.js`: Build tool configuration (dev server proxy, output paths)
- `frontend/tailwind.config.js`: UI styling configuration

**Core Logic:**
- `backend/agents/orchestrator.py`: Main decision-making orchestrator
- `backend/services/kraken.py`: Exchange API client with rate limiting
- `backend/db/models.py`: Data model definitions (User, Trade, Strategy, etc.)

**Testing:**
- `backend/tests/`: Unit and integration tests (organized by module)
- `frontend/src/**/*.test.js`: Component tests using React Testing Library

## Naming Conventions

**Files:**
- Python: snake_case (e.g., `user_service.py`, `trade_executor.py`)
- JavaScript/React: camelCase for logic files (`useAuth.js`, `api.js`), PascalCase for components (`LoginForm.js`, `Chart.js`)

**Directories:**
- Feature-based grouping: `api/`, `services/`, `agents/`, `core/`, `db/`
- Page routes as directories: `frontend/src/pages/`, `frontend/src/components/`
- Utility grouping: `frontend/src/hooks/`, `frontend/src/context/`

**Classes/Functions:**
- Python: PascalCase for classes (`User`, `Trade`, `KrakenService`), snake_case for functions (`get_current_user()`)
- JavaScript: camelCase for functions (`useAuth()`, `formatPrice()`), PascalCase for components (`<Dashboard />`, `<Chart />`)

**Constants:**
- Python: UPPER_SNAKE_CASE (e.g., `DATABASE_URL`, `SESSION_TIMEOUT_SECONDS`)
- JavaScript: UPPER_SNAKE_CASE for globals (e.g., `API_BASE_URL`, `TOKEN_KEY`)

## Where to Add New Code

**New Feature (e.g., "Add Portfolio Rebalancing"):**

1. **Backend Route:**
   - Create endpoint in `backend/api/` in appropriate file (e.g., `strategies.py` for strategy changes)
   - Define Pydantic request/response models in the same file
   - Use `Depends(get_db)` to inject database session
   - Call service layer for business logic

2. **Business Logic:**
   - Add logic to `backend/services/` (e.g., `portfolio.py` for rebalancing math)
   - Or add to existing agent in `backend/agents/` if it's decision-making

3. **Database:**
   - Add new columns/tables to `backend/db/models.py`
   - Create migration file in `backend/alembic/versions/`
   - Run migration to create schema

4. **Frontend Page:**
   - Create page component in `frontend/src/pages/` (e.g., `PortfolioRebalance.js`)
   - Add route in `frontend/src/App.jsx`
   - Add navigation link in `frontend/src/components/Sidebar.js`

5. **Frontend Components:**
   - Break down page into reusable components in `frontend/src/components/`
   - Use context or custom hooks for shared state

6. **API Integration:**
   - Add methods to `frontend/src/services/api.js` for new endpoints

**New Component/Module:**

- **React Component:** Create in `frontend/src/components/` following PascalCase naming. Export from component file. Import in parent page/component. Use hooks for lifecycle and state.
- **Python Service:** Create class in `backend/services/` with `__init__()` and public methods. Instantiate in-module or inject via FastAPI dependency. Handle errors with try/except and custom exceptions.
- **Agent:** Extend `BaseAgent` in `backend/agents/`, implement `execute()` method, subscribe to message queue channels in constructor.

**Utilities:**

- **Frontend:** `frontend/src/hooks/` for custom hooks (follow `use*` naming), `frontend/src/context/` for shared state
- **Backend:** `backend/core/` for infrastructure utilities, `backend/services/` for domain-specific helpers

## Special Directories

**backend/alembic/:**
- Purpose: Database migration management via Alembic ORM tool
- Generated: Yes (migrations auto-created by `alembic revision --autogenerate`)
- Committed: Yes (versions checked into git for reproducibility)
- Invoke via: `backend/db/migrations.py::run_migrations()` on app startup

**frontend/dist/:**
- Purpose: Built frontend application output from Vite
- Generated: Yes (by `npm run build`)
- Committed: No (build artifact, excluded from git)

**backend/venv/, frontend/node_modules/:**
- Purpose: Project dependencies
- Generated: Yes (installed by `pip install -r requirements.txt` or `npm install`)
- Committed: No (excluded from git via .gitignore)

**backend/.pytest_cache/, frontend/dist/**
- Purpose: Build and test artifacts
- Generated: Yes
- Committed: No

**prompts/, triad/:**
- Purpose: GSD (Generative Software Development) framework for AI-assisted code generation
- Generated: No (manually configured)
- Committed: Yes (contains specifications and templates)

---

*Structure analysis: 2026-02-04*
