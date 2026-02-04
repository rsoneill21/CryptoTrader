# Architecture

**Analysis Date:** 2026-02-04

## Pattern Overview

**Overall:** Layered monolithic architecture with AI agents coordinating trading operations

**Key Characteristics:**
- FastAPI REST API backend with async/await patterns
- React SPA frontend with hooks and context API
- Message queue-based inter-agent communication (Celery + Redis)
- SQLite database with Alembic migrations
- WebSocket support for real-time market data and chat
- Separation between AI decision agents and trade execution
- Paper trading mode for risk-free strategy validation

## Layers

**Presentation Layer (Frontend):**
- Purpose: User interface for authentication, trading operations, strategy management, real-time alerts, and AI chat
- Location: `frontend/src/`
- Contains: React components, pages, services (API client), context providers, custom hooks
- Depends on: REST API endpoints, WebSocket connections for market data and chat
- Used by: End users accessing the application through browser

**API Layer:**
- Purpose: Handle HTTP requests and WebSocket connections, coordinate request routing to services
- Location: `backend/api/`
- Contains: Route handlers organized by domain (auth.py, market.py, trades.py, ai.py, alerts.py, strategies.py, risk.py, export.py, system.py)
- Depends on: Database models, services, core utilities
- Used by: Frontend clients, external integrations

**Service Layer:**
- Purpose: Business logic implementation, external API integration, data transformation
- Location: `backend/services/`
- Contains: Market data service, Kraken exchange integration, AI model routing, chat memory, portfolio management, risk calculations, alert management, password reset, health monitoring
- Depends on: Database access, external APIs (Kraken), third-party ML services
- Used by: API routes, agents, other services

**Agent Layer:**
- Purpose: Autonomous AI decision-making for trading strategies, market analysis, risk management, sentiment analysis, and orchestration
- Location: `backend/agents/`
- Contains: Base agent framework, orchestrator (main coordinator), market analyst, strategy optimizer, trade executor, risk monitor, sentiment agent
- Depends on: Services layer, message queue, database
- Used by: API routes (for chat), periodic tasks, message queue events

**Core Layer:**
- Purpose: Cross-cutting infrastructure: authentication, authorization, rate limiting, settings, task queues, message broadcasting, audit logging
- Location: `backend/core/`
- Contains: Security utilities, Celery task definitions, message queue, rate limiting, trading control, indicators, paper trading, audit logging, settings management
- Depends on: Database, environment configuration
- Used by: All other layers

**Data Access Layer:**
- Purpose: Database abstraction and schema management
- Location: `backend/db/`
- Contains: SQLAlchemy ORM models, database initialization, session factory, migrations via Alembic
- Depends on: SQLite, Alembic for schema versioning
- Used by: Services, API routes, agents

## Data Flow

**User Authentication Flow:**

1. User submits email/password on Login page (`frontend/src/pages/Login.js`)
2. Frontend calls `POST /api/auth/login` via axios client (`frontend/src/services/api.js`)
3. Backend route handler validates credentials, checks MFA requirement (`backend/api/auth.py`)
4. Success returns JWT token in response; frontend stores in localStorage and sets cookie
5. Subsequent requests include auth token in headers
6. `get_current_user` dependency in `backend/core/auth.py` verifies token on protected endpoints
7. User profile and session timeout settings loaded from database

**Market Data Flow:**

1. User navigates to Dashboard or LiveTrading page
2. Frontend WebSocket handler (`frontend/src/hooks/useWebSocket.js`) connects to `/ws/market`
3. Backend WebSocket endpoint initiates Kraken WebSocket feed via `backend/services/kraken_ws.py`
4. Market data stream continuously updates database and broadcasts to connected clients
5. Frontend renders real-time charts using lightweight-charts library (`frontend/src/components/Chart.js`)
6. Backend rate limits and caches data to avoid overloading Kraken API

**Trading Decision Flow:**

1. User creates/edits strategy in StrategyLab or system recommends optimization
2. Strategy rules stored in database with JSON schema
3. Market analyst agent (`backend/agents/market_analyst.py`) analyzes market conditions
4. Orchestrator agent (`backend/agents/orchestrator.py`) evaluates strategy against market conditions
5. Risk monitor agent (`backend/agents/risk_monitor.py`) validates position sizing and drawdown limits
6. Decision sent to frontend via WebSocket or stored for user review
7. Trade executor agent (`backend/agents/trade_executor.py`) places orders via Kraken API if live trading enabled
8. Order status and P&L tracked in database, pushed to frontend

**AI Chat Flow:**

1. User types message in AIChat page (`frontend/src/pages/AIChat.js`)
2. Frontend sends WebSocket message to `/ws/ai-chat` endpoint
3. Backend ChatAIService (`backend/services/ai_models.py`) routes message to configured provider (OpenAI, Claude, Groq)
4. Provider response augmented with market context from agents
5. Response streamed back to frontend via WebSocket
6. Chat history persisted in `backend/services/chat_memory.py`
7. User can review reasoning, market conditions, and model selection in UI panels

**Alert Generation Flow:**

1. Trade execution, market condition change, or system event triggers alert creation
2. Alert persisted to database with type, severity, message
3. Background task (`backend/core/tasks.py`) picks up alerts
4. Alert service (`backend/services/alert_service.py`) determines notification channels (email, SMS, webhook)
5. Notifications dispatched respecting user preferences (digest frequency, do-not-disturb window)
6. Frontend polls/WebSocket receives alert updates for display in AlertNotification component

**State Management:**

- **Database State:** Users, sessions, strategies, trades, orders, alerts, AI decisions, performance metrics - single source of truth
- **In-Memory State:** Frontend uses React Context (AuthContext for user/session, ThemeContext for UI preferences)
- **Cache/Session:** Message queue (Redis) handles Celery task queues and pub/sub for agent-to-frontend communication
- **Local Storage:** Frontend stores auth token, user preferences for offline access

## Key Abstractions

**BaseAgent:**
- Purpose: Common interface for all AI agents with lifecycle methods
- Examples: `backend/agents/orchestrator.py`, `backend/agents/market_analyst.py`, `backend/agents/risk_monitor.py`
- Pattern: Abstract base class with `setup()`, `execute()`, `shutdown()` lifecycle; agents subscribe to message queue channels and publish decisions

**APIRouter:**
- Purpose: FastAPI route grouping by domain, dependency injection of services
- Examples: `backend/api/auth.py` (auth_router), `backend/api/market.py` (market_router), `backend/api/trades.py` (trades_router)
- Pattern: Pydantic models for request/response validation, HTTPException for error handling, Depends() for injecting database sessions and auth

**Service Pattern:**
- Purpose: Encapsulate domain business logic separate from route handling
- Examples: `backend/services/kraken.py` (KrakenService), `backend/services/portfolio.py` (PortfolioService)
- Pattern: Stateful service classes initialized once and used across requests; consistent error handling with custom exceptions

**Celery Task:**
- Purpose: Asynchronous background work triggered by events or schedules
- Examples: `backend/core/tasks.py` - cleanup_expired_sessions, sync_manual_trades
- Pattern: Define with @celery_app.task decorator; scheduled via beat_schedule; errors logged and retried

**Message Queue Pattern:**
- Purpose: Decouple agents from frontend, enable pub/sub communication
- Examples: `backend/core/message_queue.py` with Channels enum for different topics
- Pattern: Agents publish decisions to channels; frontend WebSocket handler subscribes to push updates

## Entry Points

**Backend Entry Point:**
- Location: `backend/main.py`
- Triggers: Server startup with `uvicorn main:app --host 0.0.0.0 --port 8000`
- Responsibilities: FastAPI app initialization, CORS middleware setup, exception handler registration, database initialization via lifespan context manager, Kraken WebSocket startup, router registration (auth, market, system, alerts, ai, export, risk, strategies, trades)

**Frontend Entry Point:**
- Location: `frontend/src/main.jsx`
- Triggers: Browser navigation to http://localhost:3000
- Responsibilities: React app bootstrap, root component rendering (App.jsx), theme and auth provider wrapping, routing setup

**Database Initialization:**
- Location: `backend/init_db.py`, triggered by `backend/db/database.py::init_db()`
- Triggers: On application startup
- Responsibilities: Run Alembic migrations, register SQLAlchemy event listeners for audit logging

**Celery Worker:**
- Location: `backend/core/celery_app.py`
- Triggers: Manual `celery -A core.celery_app worker --loglevel=info`
- Responsibilities: Pick up tasks from Redis queue, execute background work (session cleanup, manual trade sync), publish results

## Error Handling

**Strategy:**
- Explicit error types with Pydantic models, HTTP exception codes mapped to user-friendly messages
- Async exception handlers registered globally to catch and format errors
- Database rollback on transaction failure
- Validation errors caught before database operations

**Patterns:**

- **API Layer:** HTTPException with status_code and detail, caught by FastAPI error handlers (`backend/api/errors.py`)
- **Service Layer:** Custom exceptions (e.g., KrakenAPIError, StrategyValidationError) raised with context, caught by API layer
- **Database Layer:** SQLAlchemy IntegrityError for constraint violations, SQLAlchemyError for connection issues - logged and re-raised as HTTP 500
- **Agent Layer:** Decision errors logged to audit table; trading halted if critical agent fails; user notified via alerts

## Cross-Cutting Concerns

**Logging:**
- Structured logging via Python logging module
- Logger names follow module path convention (e.g., `cryptotrader.auth`, `cryptotrader.kraken_alerts`)
- Sensitive data filtered (passwords, tokens, API keys) via `_SENSITIVE_DETAIL_PARTS` in `backend/db/database.py`
- System events logged to database for audit trail via `backend/core/audit.py`

**Validation:**
- Frontend: React component-level validation (required fields, format checks)
- API: Pydantic models enforce schema and types; HTTPException raised for invalid input
- Database: SQLAlchemy constraints (unique, not null, foreign key)
- Business Logic: Service methods validate state before executing (e.g., check if strategy in paper mode before promoting)

**Authentication:**
- Session token generated on login, stored in database with expiry
- Token verified on protected endpoints via `get_current_user` dependency
- MFA optional: TOTP secret stored, verified on login if enabled
- Password hashing via bcrypt in `backend/core/security.py`
- Session timeout and idle warning configurable via settings

**Rate Limiting:**
- Per-endpoint rate limits defined in `backend/core/rate_limit.py`
- RateLimiter checks request frequency, returns 429 if exceeded
- Email verification endpoints rate limited to prevent abuse
- Kraken API calls rate limited to respect exchange limits

**Authorization:**
- No role-based access control visible in codebase; all authenticated users have same permissions
- Admin operations (system logs, settings) accessible to all authenticated users
- Trade operations restricted to user's own strategies and trades via implicit user context

---

*Architecture analysis: 2026-02-04*
