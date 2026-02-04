# Architecture

**Analysis Date:** 2026-02-04

## Pattern Overview

**Overall:** Layered architecture with service-oriented backend and component-based frontend

**Key Characteristics:**
- **Separation of concerns**: API routes, business logic services, and data layer cleanly separated
- **Multi-agent system**: Backend orchestrates autonomous trading agents that operate independently
- **FastAPI with Pydantic validation**: Type-safe endpoints with validation at boundaries
- **React SPA frontend**: Client-side routing with context-based state management
- **Database persistence**: SQLAlchemy ORM with Alembic migrations
- **Async-first backend**: AsyncIO and async/await patterns throughout
- **Modular services**: Business logic isolated in service modules with focused responsibilities

## Layers

**API Layer (Routes):**
- Purpose: HTTP request handling, input validation, authorization checks, response formatting
- Location: `backend/api/`
- Contains: Route definitions using FastAPI's APIRouter
- Depends on: Services layer, database, authentication
- Used by: Frontend clients via HTTP/REST
- Router files:
  - `auth.py`: Registration, login, MFA, password reset
  - `market.py`: Market data, portfolio queries
  - `trades.py`: Trade execution and management
  - `strategies.py`: Strategy CRUD and backtesting
  - `ai.py`: AI chat endpoints with streaming support
  - `risk.py`: Risk analysis and monitoring
  - `alerts.py`: Alert management
  - `export.py`: Data export in various formats
  - `system.py`: Health checks, connection status, system logs

**Services Layer (Business Logic):**
- Purpose: Core business logic, external API integration, data transformation
- Location: `backend/services/`
- Contains: Service classes with focused domain responsibilities
- Depends on: Database, external APIs, configuration
- Used by: API routes, agents, core modules
- Key services:
  - `ai_models.py`: AI provider management (OpenAI, Claude, Ollama)
  - `strategy_ai.py`: AI-driven strategy generation and analysis
  - `risk_ai.py`: Risk scoring and monitoring using AI
  - `kraken.py`: Exchange API client for Kraken
  - `kraken_ws.py`: WebSocket connection for live market data
  - `market_data.py`: Market data aggregation and caching
  - `trade_sync.py`: Syncing trades with exchange
  - `alert_service.py`: Alert creation and notification logic
  - `chat_memory.py`: Conversation history management
  - `news_feed.py`: News aggregation and sentiment analysis
  - `social_sentiment.py`: Social media sentiment tracking
  - `portfolio.py`: Portfolio calculations
  - `email.py`: Email sending

**Agents Layer (Autonomous Workers):**
- Purpose: Independent agents that monitor, analyze, and execute trading decisions
- Location: `backend/agents/`
- Contains: Agent implementations extending BaseAgent abstract class
- Depends on: Services layer, database
- Used by: Orchestrator agent for coordination
- Key agents:
  - `base.py`: BaseAgent abstract class, AgentRegistry for lifecycle management
  - `orchestrator.py`: Coordinates all agents and handles inter-agent messaging
  - `market_analyst.py`: Analyzes market conditions and trends
  - `sentiment_agent.py`: Processes sentiment data from news and social
  - `risk_monitor.py`: Monitors portfolio risk and generates alerts
  - `strategy_optimizer.py`: Evaluates and optimizes strategies
  - `trade_executor.py`: Executes trades based on signals

**Core Layer (Infrastructure & Configuration):**
- Purpose: Cross-cutting concerns, shared utilities, environment configuration
- Location: `backend/core/`
- Contains: Settings, security, authentication, task scheduling, audit logging
- Depends on: Database, external services
- Used by: All layers
- Key modules:
  - `settings.py`: Pydantic-based configuration from environment
  - `auth.py`: JWT/session validation, dependency injection for current user
  - `security.py`: Password hashing, token generation, MFA (TOTP)
  - `celery_app.py`: Celery instance configuration for async task queue
  - `tasks.py`: Background tasks (session cleanup, trade sync, logging)
  - `rate_limit.py`: Rate limiting middleware
  - `trading_control.py`: Trading controls and safeguards
  - `audit.py`: Audit logging for compliance
  - `indicators.py`: Technical indicator calculations
  - `patterns.py`: Chart pattern recognition
  - `paper_trading.py`: Paper trading simulation engine
  - `message_queue.py`: Inter-service messaging

**Database Layer (Persistence):**
- Purpose: Data storage and retrieval using SQLAlchemy ORM
- Location: `backend/db/`
- Contains: Models, migrations, database utilities
- Depends on: SQLite/database engine
- Used by: All business logic layers
- Key components:
  - `models.py`: SQLAlchemy model definitions
  - `database.py`: SQLAlchemy engine, session factory, initialization
  - `migrations.py`: Alembic migration runner

**Frontend - Component Layer:**
- Purpose: UI rendering and user interaction
- Location: `frontend/src/components/`
- Contains: Reusable React components
- Depends on: Context providers, API service, custom hooks
- Used by: Page components, Layout wrapper
- Component categories:
  - Layout: `Layout.js`, `Header.js`, `Sidebar.js`
  - Trading: `PositionManager.js`, `ExportPanel.js`
  - Charting: `Chart.js`, `ChartIndicators.js`, `ChartAnnotations.js`
  - Analysis: `RiskDashboard.js`, `ModelComparison.js`, `SentimentPanel.js`
  - Communication: `ChatWindow.js`, `AlertNotification.js`
  - Authentication: `LoginForm.js`, `RegisterForm.js`

**Frontend - Pages/Routes:**
- Purpose: Full-page views for distinct features
- Location: `frontend/src/pages/`
- Contains: Route components with page-level logic
- Depends on: Components, context, API services
- Used by: React Router in App.jsx
- Pages:
  - `Login.js`, `Register.js`, `ForgotPassword.js`: Auth flows
  - `Dashboard.js`: Main overview page
  - `LiveTrading.js`: Real-time trading interface
  - `StrategyLab.js`: Strategy creation and testing
  - `AIChat.js`: AI conversation interface
  - `Alerts.js`: Alert management
  - `SystemLogs.js`: System event logging
  - `Settings.js`: User preferences

**Frontend - Context & Hooks:**
- Purpose: Global state management and reusable logic
- Location: `frontend/src/context/`, `frontend/src/hooks/`
- Context providers:
  - `AuthContext.js`: User authentication state and methods
  - `ThemeContext.js`: Dark/light theme toggle
- Custom hooks:
  - `useAuth.js`: Access to auth context
  - `useWebSocket.js`: WebSocket connection for live updates
  - `useAlerts.js`: Alert subscription and management

**Frontend - Services:**
- Purpose: HTTP API communication
- Location: `frontend/src/services/`
- Contains: Axios instance with interceptors and API clients
- Key exports:
  - `authAPI`: Login, register, session, password reset
  - `systemAPI`: Health checks, logs, connection status
  - `marketAPI`: Prices, OHLC, portfolio, orderbook
  - `tradesAPI`: Trade CRUD, order management
  - `aiAPI`: AI model listing, chat history

## Data Flow

**Authentication Flow:**
1. User submits credentials via `LoginForm.js`
2. Component calls `authAPI.login()` → POST `/api/auth/login`
3. Backend validates credentials in `auth.py` route handler
4. Route calls `core.auth.verify_password()` and creates session via services
5. Session token returned to frontend and stored in localStorage
6. Token included in subsequent requests (via axios interceptors)
7. `get_current_user` dependency validates token on protected routes

**Trading Flow:**
1. User initiates trade in `PositionManager.js` or `LiveTrading.js`
2. Component calls `tradesAPI.createTrade()` → POST `/api/trades/`
3. `trades.py` route validates request with Pydantic models
4. Route delegates to service layer (trade validation, execution)
5. Service interacts with `kraken_service` to place order on exchange
6. Trade record saved to database via SQLAlchemy ORM
7. WebSocket subscription in `useWebSocket` hook pushes live updates to frontend
8. Frontend subscribes to trade status changes and updates `LiveTrading.js` state

**AI Analysis Flow:**
1. User submits message in `AIChat.js` page
2. Component calls `aiAPI` or direct POST to `/api/ai/chat/stream`
3. `ai.py` route receives ChatRequest with provider selection
4. Route initializes appropriate AI service (OpenAI/Claude/Ollama) from `ai_models.py`
5. Orchestrator agent (`agents/orchestrator.py`) receives request
6. Agent queries other agents (market_analyst, sentiment_agent, risk_monitor)
7. Services gather context (market data, sentiment, portfolio risk)
8. AI provider generates response with streamed chunks
9. Frontend receives SSE/streaming response and updates chat history

**Real-time Market Data Flow:**
1. Backend establishes WebSocket to Kraken via `kraken_ws.py` at startup
2. `market_data.py` service subscribes to price tickers and order book updates
3. Agents poll or react to market data changes
4. Risk monitor checks positions against market movements
5. Alerts generated if risk thresholds exceeded
6. Frontend WebSocket listeners in `useWebSocket` receive updates
7. Components like `Chart.js` re-render with new price data

**State Management:**
- **Global auth state**: React Context in `AuthContext.js` (user, loading, error states)
- **Theme state**: React Context in `ThemeContext.js` (dark/light mode)
- **Component local state**: useState in individual page/component files
- **Derived/async state**: Via custom hooks (useAlerts, useWebSocket)
- **Server state**: API responses cached client-side when applicable
- **Backend state**: SQLAlchemy models + in-memory agent state

## Key Abstractions

**BaseAgent:**
- Purpose: Template for autonomous agents with lifecycle management
- Location: `backend/agents/base.py`
- Pattern: Abstract base class with hooks for start, stop, pause, resume
- Concrete implementations: Orchestrator, MarketAnalyst, SentimentAgent, etc.
- Communication: Inter-agent messaging via AgentMessage dataclass

**APIRouter (FastAPI):**
- Purpose: Organize related endpoints with shared dependencies
- Location: `backend/api/*`
- Pattern: Each module creates `router = APIRouter()` and includes routes
- Example: `auth.py` has routes for register, login, MFA, password reset
- Main app aggregates routers in `main.py`

**Service Classes:**
- Purpose: Encapsulate business logic and external integrations
- Location: `backend/services/`
- Pattern: Classes with well-defined public methods
- Examples:
  - `AIModelsService`: Manages AI provider activation and switching
  - `KrakenService`: REST API calls to exchange
  - `MarketDataService`: Market data aggregation
- Dependency injection: Services created once and reused across requests

**Pydantic Models:**
- Purpose: Request/response validation and serialization
- Usage: All API payloads validated against BaseModel subclasses
- Example: `ChatRequest`, `LoginRequest`, `TradeResponse`
- Benefit: Type safety, automatic OpenAPI documentation

**SQLAlchemy ORM Models:**
- Purpose: Object-relational mapping to database tables
- Location: `backend/db/models.py`
- Core models: User, Session, Strategy, Trade, Order, AIDecision, Alert, etc.
- Relationships: Models define FK relationships (back_populates for bidirectional)

**React Hooks (Custom):**
- Purpose: Encapsulate stateful logic and side effects
- Examples: `useAuth()` extracts auth context logic, `useAlerts()` subscribes to alert stream
- Pattern: Custom hooks return object/tuple of state + methods

**API Service Clients:**
- Purpose: Organize HTTP calls by domain
- Location: `frontend/src/services/api.js`
- Pattern: Objects with methods that return axios promises
- Example: `authAPI.login()`, `marketAPI.getTicker()`

## Entry Points

**Backend:**
- Location: `backend/main.py`
- Triggers: `python -m backend.main` or uvicorn
- Responsibilities:
  1. Create FastAPI app instance
  2. Register exception handlers via `register_exception_handlers()`
  3. Configure CORS middleware with settings
  4. Initialize database via `init_db()` (runs Alembic migrations)
  5. Start Kraken WebSocket connection
  6. Register all API routers (auth, market, trades, ai, etc.)
  7. Start Celery tasks for background work
  8. Provide `/ai-chat` HTML page for chat interface

**Frontend:**
- Location: `frontend/src/main.jsx`
- Triggers: `npm run dev` (Vite) or build process
- Responsibilities:
  1. Mount React app to DOM root element
  2. Render `<App />` component (in StrictMode for development)

**Frontend App Root:**
- Location: `frontend/src/App.jsx`
- Responsibilities:
  1. Set up routing with React Router
  2. Wrap routes with `ThemeProvider` and `AuthProvider`
  3. Define public routes (login, register, forgot password)
  4. Define protected routes using `ProtectedRoute` wrapper
  5. Wrap authenticated pages in `Layout` (sidebar, header, content area)
  6. Set redirect for unauthenticated users

## Error Handling

**Strategy:** Centralized error handlers in API with structured error responses

**Patterns:**
- **API errors**: All endpoints return `APIErrorResponse` with code, message, details
- **Validation errors**: Pydantic raises RequestValidationError → converted to structured error
- **HTTP exceptions**: FastAPI HTTPException caught and formatted consistently
- **Database errors**: SQLAlchemy exceptions caught in services, mapped to meaningful errors
- **Unhandled exceptions**: Global exception handler in `errors.py` logs and returns 500

**Frontend error handling:**
- Axios interceptor catches 401 responses and redirects to login
- Error components display user-friendly messages
- Forms show field-level validation errors from API responses
- Console logging for debugging in development

## Cross-Cutting Concerns

**Logging:**
- Backend: Python logging module throughout, structured logs in `database.py`
- Frontend: Console logging for debugging

**Validation:**
- Backend: Pydantic models at route boundaries
- Frontend: React form libraries (basic HTML5 validation)

**Authentication:**
- Backend: JWT-style session tokens + HTTPOnly cookies
- Frontend: AuthContext provides user state and login/logout methods
- Dependency: `get_current_user` on protected routes

**Authorization:**
- Backend: Currently user-based (no role-based access control visible)
- Checks: Implicit via authentication requirement on protected routes

**Database transactions:**
- Backend: SQLAlchemy ORM manages transactions
- Pattern: Session provides automatic rollback on error

**Rate limiting:**
- Backend: `core/rate_limit.py` provides RateLimiter class
- Usage: Can be applied to routes to prevent abuse

**Audit logging:**
- Backend: `core/audit.py` logs sensitive actions
- Storage: SystemLog model persists audit trail

---

*Architecture analysis: 2026-02-04*
