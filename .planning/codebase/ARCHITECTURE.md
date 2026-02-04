# Architecture

**Analysis Date:** 2024-05-24

## Pattern Overview

**Overall:** Multi-Agent System (MAS) with Centralized Orchestration.

**Key Characteristics:**
- **Asynchronous Communication:** Agents communicate primarily through a Redis-backed message queue (Pub/Sub), allowing for loose coupling and scalability.
- **Role-Based Specialization:** Distinct agents handle specific domains such as market analysis, sentiment tracking, risk monitoring, and trade execution.
- **Hybrid API/Agent Architecture:** A FastAPI backend serves as both the REST API for the frontend and the hosting environment for the agent runtimes.

## Layers

**API Layer:**
- Purpose: Provides RESTful endpoints for the frontend and external clients.
- Location: `backend/api/`
- Contains: FastAPI routers, request/response schemas (Pydantic), and endpoint handlers.
- Depends on: `backend/db/`, `backend/services/`, `backend/core/`
- Used by: React Frontend, Orchestrator (via `ChatAIService`)

**Agent Layer:**
- Purpose: Implements autonomous trading logic and AI-driven decision making.
- Location: `backend/agents/`
- Contains: Agent implementations (`market_analyst.py`, `risk_monitor.py`, etc.) inheriting from `BaseAgent`.
- Depends on: `backend/core/message_queue.py`, `backend/services/`, `backend/db/`
- Used by: System background processes (started by the main application).

**Service Layer:**
- Purpose: Encapsulates business logic and external integrations.
- Location: `backend/services/`
- Contains: Kraken API clients, AI model connectors, market data processors, and portfolio management logic.
- Depends on: `backend/db/`, `backend/core/`
- Used by: API Layer, Agent Layer.

**Database Layer:**
- Purpose: Persistence of system state, history, and configuration.
- Location: `backend/db/`
- Contains: SQLAlchemy models (`models.py`), database session management (`database.py`), and migrations.
- Depends on: Core settings.
- Used by: All backend layers.

**Frontend Layer:**
- Purpose: User interface for monitoring and controlling the trading system.
- Location: `frontend/src/`
- Contains: React components, pages, hooks, and state management.
- Depends on: Backend API.
- Used by: End users.

## Data Flow

**Trading Decision Flow:**

1. **Market Data Acquisition:** `backend/services/kraken_ws.py` receives real-time data and publishes it to the `MARKET_DATA` channel via `message_queue`.
2. **Signal Generation:** `MarketAnalystAgent` (in `backend/agents/market_analyst.py`) consumes market data, performs technical analysis, and publishes insights to the `AI_DECISIONS` channel.
3. **Orchestration:** `OrchestratorAgent` (in `backend/agents/orchestrator.py`) consumes insights and risk alerts, evaluates them against the current strategy, and publishes `TRADE_SIGNALS`.
4. **Execution:** `TradeExecutorAgent` (in `backend/agents/trade_executor.py`) consumes trade signals and executes orders via the `KrakenService`.

**AI Chat Flow:**

1. **Request:** Frontend sends a message to `/api/ai/chat`.
2. **Orchestration:** `ChatAIService` (in `backend/api/ai.py`) uses the `OrchestratorAgent`'s context to generate a prompt.
3. **Response:** The AI model (GPT/Claude) generates a response which is streamed back to the frontend and persisted in `ChatHistory`.

**State Management:**
- **Server State:** Handled via SQLAlchemy models in PostgreSQL.
- **Agent State:** Maintained in-memory by individual agent instances and partially synchronized via the message queue.
- **Frontend State:** Managed using React Context (`AuthContext`, `ThemeContext`) and standard React hooks.

## Key Abstractions

**BaseAgent:**
- Purpose: Abstract base class providing common lifecycle and communication logic for all agents.
- Examples: `backend/agents/base.py`
- Pattern: Template Method.

**MessageQueue:**
- Purpose: Abstraction over Redis Pub/Sub for inter-agent communication.
- Examples: `backend/core/message_queue.py`
- Pattern: Publisher-Subscriber.

**KrakenService:**
- Purpose: Interface for interacting with the Kraken exchange.
- Examples: `backend/services/kraken.py`
- Pattern: Service Object / Adapter.

## Entry Points

**Backend API:**
- Location: `backend/main.py`
- Triggers: HTTP Requests from Frontend/Users.
- Responsibilities: Routing, Auth, Middleware, starting background services (WebSocket, DB init).

**Frontend UI:**
- Location: `frontend/src/main.jsx`
- Triggers: Browser loading the application.
- Responsibilities: Rendering the React tree, setting up routing and context providers.

**Agent Runtime:**
- Location: `backend/agents/orchestrator.py` (and other agents)
- Triggers: Started during application lifespan or via separate worker processes.
- Responsibilities: Main agent run loops, message handling.

## Error Handling

**Strategy:** Multi-tiered error handling with centralized logging and alerting.

**Patterns:**
- **FastAPI Exception Handlers:** Centralized in `backend/api/errors.py` to return consistent JSON errors.
- **Kraken Error Alert Callback:** `backend/main.py` registers `_kraken_error_alert` to persist exchange errors as system alerts.
- **Agent Error Hooks:** `BaseAgent.on_error` provides a hook for agents to handle their own runtime failures and log them via `log_system_event`.

## Cross-Cutting Concerns

**Logging:** Centralized system logging using `backend/core/tasks.py` (`log_system_event`) and stored in the `SystemLog` table.
**Validation:** Request/Response validation using Pydantic models in `backend/api/`.
**Authentication:** JWT-based authentication implemented in `backend/core/auth.py` and applied via FastAPI dependencies.
**Rate Limiting:** Implemented in `backend/core/rate_limit.py` to protect both the API and external exchange integrations.

---

*Architecture analysis: 2024-05-24*
