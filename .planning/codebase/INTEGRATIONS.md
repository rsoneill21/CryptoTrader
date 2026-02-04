# External Integrations

**Analysis Date:** 2025-03-04

## APIs & External Services

**Trading:**
- Kraken Exchange - Primary source for market data and trade execution.
  - SDK/Client: `krakenex`
  - Implementation: `backend/services/kraken.py`
  - Auth: `KRAKEN_API_KEY`, `KRAKEN_API_SECRET`

**AI/LLM:**
- OpenAI - GPT-4 and GPT-4o-mini for strategy analysis and market sentiment.
  - SDK/Client: `openai`
  - Implementation: `backend/services/ai_models.py`
  - Auth: `OPENAI_API_KEY`
- Anthropic - Claude 3.5 Sonic for alternative AI modeling.
  - SDK/Client: `anthropic`
  - Implementation: `backend/services/ai_models.py`
  - Auth: `ANTHROPIC_API_KEY`
- Ollama - Local AI model execution support.
  - Client: `httpx` (Async)
  - Implementation: `backend/services/ai_models.py`
  - Connection: `OLLAMA_BASE_URL`

**Communication:**
- Slack - Used for notifications and "triad" channel management.
  - Implementation: `backend/core/settings.py` and `scripts/slack_post.sh`.
  - Auth: `SLACK_BOT_TOKEN`, `TRIAD_SLACK_CHANNEL`

## Data Storage

**Databases:**
- SQLite (Local)
  - Primary DB: `backend/cryptotrader.db`
  - Features DB: `features.db`
  - Triad DB: `triad.db`
  - Connection: `DATABASE_URL` (env) or default path.
  - Client: `SQLAlchemy` (ORM)

**File Storage:**
- Local filesystem for database backups.
  - Location: `backups/` (configurable via `DATABASE_BACKUP_DIR`)

**Caching:**
- Redis - Used as the message broker and result backend for Celery.
  - Service: `redis-server`
  - Connection: `REDIS_URL`

## Authentication & Identity

**Auth Provider:**
- Custom Session-based Auth
  - Implementation: `backend/core/auth.py`
  - Approach: Database-backed session tokens stored in `sessions` table.
  - Support: Bearer tokens and HTTP-only Cookies.

## Monitoring & Observability

**Error Tracking:**
- System Logs - Internal database table for structured error reporting.
  - Implementation: `backend/db/database.py` (`log_system_error`)

**Logs:**
- Filesystem logs: `frontend.log`, `worker.log`, `error.txt`, `output.txt`.

## CI/CD & Deployment

**Hosting:**
- Manual deployment via scripts (`init.sh`, `stop.sh`).

**CI Pipeline:**
- Not explicitly detected in the repository (no `.github/workflows` or similar).

## Environment Configuration

**Required env vars:**
- `DATABASE_URL` - SQLite connection string.
- `REDIS_URL` - Redis connection string.
- `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` - Kraken credentials.
- `OPENAI_API_KEY` - OpenAI API access.
- `ANTHROPIC_API_KEY` - Anthropic API access.
- `SLACK_BOT_TOKEN` - Slack integration.

**Secrets location:**
- Stored in a local `.env` file (excluded from git).

## Webhooks & Callbacks

**Incoming:**
- Not detected.

**Outgoing:**
- Slack Notifications - Sent to configured channels.
- Webhook Alerts - Configurable in `backend/core/settings.py` (`NOTIFICATION_WEBHOOK_ENABLED`).

---

*Integration audit: 2025-03-04*
