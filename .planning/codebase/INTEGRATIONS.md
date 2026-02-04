# External Integrations

**Analysis Date:** 2026-02-04

## APIs & External Services

**Cryptocurrency Exchange:**
- Kraken - Real-time market data, account info, trading
  - SDK/Client: `krakenex` 2.2.1+
  - Auth: `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`
  - Implementation: `backend/services/kraken.py`, `backend/services/kraken_ws.py`
  - WebSocket feed: Real-time ticker, OHLC, trades, spreads, order book
  - Async interface with error callback mechanism for alert generation

**AI/LLM Providers:**
- OpenAI (GPT-4, GPT-4o, GPT-4o-mini models)
  - SDK/Client: `openai` 1.9.0+
  - Auth: `OPENAI_API_KEY` environment variable
  - Implementation: `backend/services/ai_models.py`, `backend/api/ai.py`
  - Chat completions for market analysis, strategy recommendations

- Anthropic Claude (Claude 3.5-sonic)
  - SDK/Client: `anthropic` 0.15.0+
  - Auth: `ANTHROPIC_API_KEY` environment variable
  - Implementation: `backend/services/ai_models.py`
  - Alternative to OpenAI for conversational AI

- Ollama (Local models - Gemma3, Llama2, etc.)
  - Base URL: `http://localhost:11434/api` (configurable via `OLLAMA_BASE_URL`)
  - Auth: Optional `OLLAMA_API_KEY` environment variable
  - Model: Configurable via `AI_MODELS_OLLAMA_MODEL` (default: gemma3)
  - Implementation: `backend/services/ai_models.py`
  - Fully local alternative for private AI inference

**Groq (Inference Acceleration):**
- API Token: `GROQ_API_TOKEN` environment variable
- Status: Configured in `.env` but not actively used in backend code (may be for future features)

## Data Storage

**Databases:**
- SQLite 3.x (development default)
  - Connection: `DATABASE_URL` env var (default: `sqlite:///./cryptotrader.db`)
  - Client: SQLAlchemy ORM 2.0.25+
  - Tables: Users, Sessions, Alerts, ChatHistory, StrategyPerformance, SystemLogs, AISettings, Trades, Portfolio, etc.

**File Storage:**
- Local filesystem only
- Database backup files in `./backups/` (configurable via `DATABASE_BACKUP_DIR`)
- No cloud storage (S3, GCS) integration detected

**Caching:**
- Redis 5.0.1+
  - Primary use: Celery broker and result backend
  - Connection: `REDIS_URL` env var (default: `redis://localhost:6379/0`)
  - Used for rate limiting: `backend/core/rate_limit.py` via `redis.asyncio`

## Authentication & Identity

**Auth Provider:**
- Custom JWT-based implementation
  - Library: `python-jose[cryptography]` 3.3.0+
  - Password hashing: `passlib[bcrypt]` 1.7.4+
  - Implementation: `backend/core/auth.py`

**Session Management:**
- Cookie-based sessions with configurable security:
  - `SESSION_COOKIE_NAME`: "cryptotrader_session"
  - `SESSION_COOKIE_SECURE`: TLS enforcement
  - `SESSION_COOKIE_SAMESITE`: "lax" (configurable)
  - Timeout: `SESSION_TIMEOUT_SECONDS` (default: 1800 seconds / 30 minutes)
  - Idle warning: `SESSION_IDLE_WARNING_SECONDS` (default: 120 seconds)

**Password Reset:**
- Token-based flow in `backend/services/password_reset.py`
- Tokens stored in database with expiration
- Email delivery: See Email section below

## Email & Notifications

**Email Service:**
- Implementation: `backend/services/email.py`
- Current: Mock implementation for development
- Sends: Password reset links, MFA verification codes
- Logging: Tokens logged only if `MOCK_EMAIL_LOG_TOKENS` enabled
- Production path: Extend for SMTP, SendGrid, Mailgun, etc.

**Notification Channels:**
- Email: `NOTIFICATION_EMAIL_ENABLED` (default: true)
- SMS: `NOTIFICATION_SMS_ENABLED` (default: false)
- Webhook: `NOTIFICATION_WEBHOOK_ENABLED` (default: true)
- Digest mode: `NOTIFICATION_DIGEST_MINUTES` (default: 60 minutes)
- Do Not Disturb (DND): `NOTIFICATION_DND_START` and `NOTIFICATION_DND_END` (optional)

## Monitoring & Observability

**Logging:**
- Standard Python logging module
- Per-module loggers: `cryptotrader.kraken_alerts`, `cryptotrader.ai`, etc.
- Error tracking via database alerts: `backend/db/models.py` Alert model
- System logs: `SystemLog` table for audit trail

**Alerts:**
- Alert system: `backend/api/alerts.py`, `backend/db/models.py`
- Alert types: Kraken API errors, trade notifications, system events
- Storage: `Alert` table with severity, status, type fields
- API: `/api/alerts/` endpoints for CRUD operations

**Error Handling:**
- Custom exception handlers in `backend/api/errors.py`
- Kraken service error callback mechanism for automatic alert creation
- HTTPException standardization across API routes

## CI/CD & Deployment

**Hosting:**
- Self-hosted ASGI server (Uvicorn) on configurable host:port
- Vite dev server for frontend development (port 5173)
- Docker support: Not detected in codebase (can be added)

**CI Pipeline:**
- Not detected - no GitHub Actions, GitLab CI, or other CI config files present
- Testing framework ready: pytest configured for backend, Testing Library for frontend

**Initialization Scripts:**
- `backend/init_db.py` - Database schema initialization
- `init.sh` - Full project initialization
- `start.bat` / `start.sh` - Start backend and frontend

## Slack Integration

**Triad Framework Integration:**
- Slack Bot Token: `SLACK_BOT_TOKEN` environment variable
- Channel: `TRIAD_SLACK_CHANNEL` (default: "triad-cryptotrader")
- Purpose: Slack channel for triad agent coordination and notifications
- Implementation: Used by `backend/core/settings.py`, not fully integrated into main backend
- SDK: `slack_sdk` (if installed) or `tqdm.contrib.slack`

## Webhooks & Callbacks

**Incoming:**
- Not detected in current codebase

**Outgoing:**
- Notification webhook support: `NOTIFICATION_WEBHOOK_ENABLED` flag
- Implementation: Not fully coded yet, framework ready in settings
- Potential use: Sending alerts to external systems (Discord, custom servers)

**Kraken Callbacks:**
- Error callback mechanism: `kraken_service.on_error()` in `backend/main.py`
- Callback creates Alert records on API errors

## Environment Configuration

**Required env vars (critical):**
- `KRAKEN_API_KEY` - Exchange trading access
- `KRAKEN_API_SECRET` - Exchange API secret
- `OPENAI_API_KEY` - OpenAI GPT access (if using OpenAI)
- `DATABASE_URL` - Database connection string (defaults to SQLite)

**Optional env vars (features):**
- `ANTHROPIC_API_KEY` - Anthropic Claude access
- `GROQ_API_TOKEN` - Groq inference acceleration
- `OLLAMA_API_KEY` - Local Ollama authentication
- `SLACK_BOT_TOKEN` - Slack integration
- `OPENAI_API_KEY` - OpenAI LLM models
- `REDIS_URL` - Redis broker for Celery
- `VITE_API_URL` - Frontend API endpoint (default: http://127.0.0.1:8000)
- `VITE_WS_URL` - WebSocket endpoint (default: ws://127.0.0.1:8000)

**Security & Deployment:**
- `TLS_CERTFILE`, `TLS_KEYFILE`, `TLS_CA_BUNDLE` - SSL/TLS support
- `FRONTEND_ORIGINS` - CORS whitelist (comma-separated)
- `SESSION_COOKIE_SECURE` - Enforce HTTPS for cookies
- `ALLOW_INSECURE_COOKIES` - Allow non-HTTPS cookies in dev
- `ALLOW_EMAIL_ENUMERATION` - Security setting for auth endpoints

**Secrets location:**
- `.env` file in project root (git-ignored)
- Template: `.env.example` for reference
- Development: Secrets can be exposed; production requires secure management (vaults, k8s secrets, etc.)

## Data Flow Integration Points

**Market Data → Frontend:**
1. Kraken WebSocket connects and subscribes to ticker/OHLC feeds
2. Real-time updates broadcast via `/ws` endpoint
3. Frontend receives and renders in charts (lightweight-charts library)

**User → API → Database:**
1. Frontend sends API requests via Axios
2. FastAPI routes to appropriate handler
3. Database layer via SQLAlchemy ORM for persistence
4. Response streamed or returned as JSON

**AI Processing:**
1. User message → `/api/ai/chat` endpoint
2. Route selects active AI provider (OpenAI/Claude/Ollama)
3. Stream response via Server-Sent Events (SSE)
4. Store conversation in ChatHistory table

**Background Tasks:**
1. Celery worker pulls tasks from Redis queue
2. Executes trade sync, health monitoring, model training
3. Results stored back in Redis or database

---

*Integration audit: 2026-02-04*
