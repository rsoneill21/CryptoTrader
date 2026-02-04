# External Integrations

**Analysis Date:** 2026-02-04

## APIs & External Services

**Cryptocurrency Exchanges:**

- **Kraken** - Primary exchange for market data and trading
  - SDK/Client: `krakenex` 2.2.1
  - Auth: `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` (environment variables)
  - Services: `backend/services/kraken.py` (REST API calls), `backend/services/kraken_ws.py` (WebSocket feeds)
  - Data: Ticker, OHLC, orderbook, balance, order management
  - WebSocket: Connects to Kraken WS API for real-time ticker/trade updates

**AI/LLM Providers:**

- **OpenAI** - Primary AI provider for chat and analysis
  - SDK/Client: `openai` 1.9.0+
  - Auth: `OPENAI_API_KEY` (environment variable)
  - Services: `backend/services/ai_models.py`, `backend/api/ai.py`
  - Models: GPT-4, GPT-4o, GPT-4o-mini (configurable via `AI_MODELS_OPENAI_MODEL`)
  - Features: Chat completions, streaming responses

- **Anthropic Claude** - Secondary AI provider (fallback/alternative)
  - SDK/Client: `anthropic` 0.15.0+
  - Auth: `ANTHROPIC_API_KEY` (environment variable, optional)
  - Services: `backend/services/ai_models.py`, `backend/api/ai.py`
  - Models: Claude 3.5 Sonic (configurable via `AI_MODELS_CLAUDE_MODEL`)
  - Features: Chat completions, streaming responses

- **Ollama** - Local LLM alternative
  - HTTP Client: `httpx` 0.26.0
  - Base URL: `http://localhost:11434/api` (configurable via `OLLAMA_BASE_URL`)
  - Model: Configurable via `AI_MODELS_OLLAMA_MODEL` (default: `gemma3`)
  - No auth required (local deployment)

**Communication & Notifications:**

- **Slack** - Bot notifications and alerts
  - Token: `SLACK_BOT_TOKEN` (environment variable)
  - Channel: `TRIAD_SLACK_CHANNEL` (environment variable, default: `triad-cryptotrader`)
  - Configuration: Loaded in `backend/core/settings.py` (lines 67-68)
  - Status: Optional (no implementation found in main codebase, configured for future use)

## Data Storage

**Databases:**

- **SQLite** (development default)
  - Connection: `DATABASE_URL=sqlite:///./cryptotrader.db`
  - Client: SQLAlchemy ORM
  - Location: `backend/db/database.py` (line 21)
  - Migrations: Alembic in `backend/alembic/`
  - Backup: Enabled by default (30-day retention, configured in `backend/core/settings.py` lines 72-76)

- **PostgreSQL** (production-ready but not default)
  - Connection: Support via SQLAlchemy (any `DATABASE_URL` string)
  - Client: SQLAlchemy ORM (database-agnostic)

**File Storage:**

- Local filesystem only
- Database backups stored in `./backups/` (configurable via `DATABASE_BACKUP_DIR`)
- Prefix: `cryptotrader` (configurable via `DATABASE_BACKUP_PREFIX`)

**Caching:**

- **Redis** - Task queue and Celery broker
  - Connection: `redis://` (configured in requirements, used by Celery)
  - Purpose: Celery message broker for distributed tasks
  - Not used for HTTP caching (no cache config detected)

## Authentication & Identity

**Auth Provider:**

- Custom authentication (no external OAuth/SSO detected)
- Implementation: `backend/api/auth_router` (imported in `main.py`)
- Method: JWT tokens via `python-jose[cryptography]`
- Session Management:
  - HttpOnly cookies (token no longer in headers, `frontend/src/services/api.js` line 77 note)
  - Session timeout: 1800 seconds (30 minutes, configurable)
  - Idle warning: 120 seconds before timeout
  - Password: Hashed via bcrypt (`passlib[bcrypt]`)
  - MFA support: Optional flag in `User` model (`backend/db/models.py` line 21)

**User Roles:**

- Basic role system in `User` model
- MFA optional per user
- Session-based permissions (no explicit role column detected at initial scan)

## Monitoring & Observability

**Error Tracking:**

- Not detected (no Sentry, Rollbar, or similar integration)
- Errors logged via Python `logging` module
- Exception handlers registered in `backend/api/errors.py`

**Logs:**

- Python `logging` module (see imports in most backend files)
- SystemLog model in `backend/db/models.py` (lines 294-300) for application events
- Log levels: debug, info, warning, error, critical
- Logged to console and database

**Alerts:**

- Alert model in `backend/db/models.py` for system notifications
- Types: `kraken_api_error`, custom alerts
- Stored in database, accessible via `/api/alerts` endpoint

## CI/CD & Deployment

**Hosting:**

- Not explicitly configured
- Backend: Runs via `uvicorn` on configurable host/port (default 0.0.0.0:8000)
- Frontend: Static assets served via reverse proxy (Vite build output)

**CI Pipeline:**

- Not detected
- No GitHub Actions, GitLab CI, or similar configuration found

**Orchestration:**

- Triad agent framework in `backend/agents/` for autonomous trading logic
- Worker process: `triad/run_worker.sh` for background job execution
- Agent types: orchestrator, trade_executor, market_analyst, risk_monitor, sentiment_agent, strategy_optimizer

## Environment Configuration

**Required env vars:**

- `KRAKEN_API_KEY` - Kraken exchange access (optional, required for live trading)
- `KRAKEN_API_SECRET` - Kraken exchange secret (optional, required for live trading)
- `OPENAI_API_KEY` - OpenAI API access (required for AI chat)
- `ANTHROPIC_API_KEY` - Claude API access (optional, fallback)
- `SLACK_BOT_TOKEN` - Slack notifications (optional)
- `TRIAD_SLACK_CHANNEL` - Slack channel name (optional, if using Slack)
- `DATABASE_URL` - Database connection string (default: `sqlite:///./cryptotrader.db`)
- `BACKEND_HOST` - Backend server host (default: `0.0.0.0`)
- `BACKEND_PORT` - Backend server port (default: `8000`)
- `VITE_API_URL` - Frontend API endpoint (default: `http://127.0.0.1:8000`)
- `VITE_WS_URL` - WebSocket endpoint (default: `ws://127.0.0.1:8000`)

**Secrets location:**

- `.env` file at project root (see `.env.example` for template)
- Loaded by `python-dotenv` on backend startup
- Never committed to git (added to `.gitignore`)

**AI Configuration:**

- `AI_MODELS_OPENAI_MODEL` - OpenAI model selection (default: `gpt-4o-mini`)
- `AI_MODELS_CLAUDE_MODEL` - Claude model selection (default: `claude-3.5-sonic`)
- `AI_MODELS_OLLAMA_MODEL` - Ollama model selection (default: `gemma3`)
- `AI_MODELS_DEFAULT_PROVIDER` - Default AI provider (default: `openai`)
- `AI_MODELS_SYSTEM_PROMPT` - System prompt for AI (default: "You are CryptoTrader's AI assistant.")
- `OLLAMA_BASE_URL` - Ollama API endpoint (default: `http://localhost:11434/api`)
- `CHAT_AI_PROVIDER` - Active chat provider selection (environment variable in `backend/api/ai.py`)

## Webhooks & Callbacks

**Incoming:**

- Not detected
- No webhook endpoints for external services

**Outgoing:**

- **Kraken error callbacks**: `backend/main.py` line 66-67 - Error alerts registered via `kraken_service.on_error()`
- System logs and alerts stored in database (can be queried via API)

## Data Models & API Integration Points

**Key integrations in models (`backend/db/models.py`):**

- `AISettings` (lines 271-278) - Stores active AI provider selection
- `StrategyPerformance` (lines 81-98) - Records AI model used for analysis
- `ChatHistory` (referenced in `backend/api/ai.py` line 27) - Stores conversation turns
- `SystemLog` (lines 294-300) - Application event logging
- `Alert` (referenced in `backend/main.py` line 22, `backend/api/ai.py` line 31) - Notification storage

**Exchange Data Flow:**

1. `backend/services/kraken.py` - REST API calls for market data, account info
2. `backend/services/kraken_ws.py` - WebSocket subscription to real-time feeds
3. `backend/api/market_router` - HTTP endpoints exposing market data
4. Frontend (`frontend/src/services/api.js`) - axios calls to market endpoints

**AI Integration Flow:**

1. Frontend chat UI (`frontend/src/pages/AIChat.js`) - User message input
2. `backend/api/ai.py` - Chat request handling, provider selection
3. `backend/services/ai_models.py` - Provider abstraction and model execution
4. OpenAI/Claude/Ollama - LLM inference
5. Response streamed to frontend via StreamingResponse

---

*Integration audit: 2026-02-04*
