# Technology Stack

**Analysis Date:** 2026-02-04

## Languages

**Primary:**
- Python 3.12.3 - Backend API, services, agents
- JavaScript (ES2022) - React frontend UI
- SQL - Database queries and migrations

**Secondary:**
- Shell scripts - Worker processes, deployment

## Runtime

**Environment:**
- Python 3.12.3 via venv at `backend/venv`
- Node.js v24.13.0 - Frontend dev and build

**Package Manager:**
- pip - Python dependencies
- npm - JavaScript dependencies
- Both projects use lock mechanisms (pip freeze, package-lock.json)

## Frameworks

**Backend:**
- FastAPI 0.109.0+ - HTTP API framework, WebSocket support
- uvicorn[standard] 0.27.0+ - ASGI server
- Starlette - Middleware, exception handling (via FastAPI)

**Frontend:**
- React 18.2.0 - UI library
- React Router 6.21.2 - Client-side routing
- Vite 7.3.1 - Build tool and dev server

**Testing:**
- pytest 7.4.4 - Python test runner
- pytest-asyncio 0.23.3 - Async test support
- Testing Library + Jest DOM - Frontend test utilities

**Database & ORM:**
- SQLAlchemy 2.0.25+ - Python ORM
- Alembic 1.13.1 - Database migrations
- SQLite (development) - Default database via `sqlite:///./cryptotrader.db`

**Task Queue:**
- Celery 5.3.6 - Distributed task processing
- Redis 5.0.1 - Message broker for Celery

**Build/Dev:**
- Vite 7.3.1 - Frontend bundling and dev server
- ESLint 9.10.0 - JavaScript linting
- Tailwind CSS 3.4.1 - Utility-first CSS framework
- PostCSS 8.4.33 - CSS transformation
- Autoprefixer 10.4.17 - CSS vendor prefixes

## Key Dependencies

**Critical:**

- `fastapi` - Core API framework for trading endpoints, WebSocket support
- `sqlalchemy` - ORM for market data, trade history, strategy storage
- `pydantic` / `pydantic-settings` - Data validation and environment configuration
- `krakenex` 2.2.1 - Kraken cryptocurrency exchange API client
- `openai` 1.9.0+ - OpenAI API client for GPT chat and analysis
- `anthropic` 0.15.0+ - Anthropic Claude API client
- `websockets` 12.0 - WebSocket client for Kraken live feeds
- `httpx` 0.26.0 - Async HTTP client

**Data Processing & Analysis:**

- `pandas` 2.2.0 - Time-series data manipulation
- `numpy` 1.26.3 - Numerical computation
- `ta` 0.11.0 - Technical analysis indicators (RSI, MACD, Bollinger Bands, etc.)

**Authentication & Security:**

- `python-jose[cryptography]` 3.3.0+ - JWT token handling
- `passlib[bcrypt]` 1.7.4+ - Password hashing
- `email-validator` 2.1.0+ - Email validation

**Utilities:**

- `python-dotenv` 1.0.0+ - Environment variable loading
- `pytz` 2024.1 - Timezone handling for market data
- `python-multipart` 0.0.6 - Form/multipart parsing

**Frontend:**

- `axios` 1.6.5+ - HTTP client for API calls
- `lightweight-charts` 4.1.3 - Financial charting library
- `web-vitals` 2.1.4 - Performance metrics

## Configuration

**Environment:**

- `.env` file at project root loads via `python-dotenv` and Pydantic `BaseSettings`
- Frontend environment vars prefixed with `VITE_` are accessible at build/runtime
- Backend uses `AppSettings` class in `backend/core/settings.py` for centralized config

**Build:**

- Frontend: `vite build` creates optimized production bundle in `dist/`
- Backend: Runs with uvicorn directly (no build step)
- Database migrations: Alembic handles schema versioning in `backend/alembic/versions/`

**Frontend Dev Server:**

- Vite dev server on port 5173
- Proxies `/api`, `/auth`, `/ws` to backend (configurable via `BACKEND_HOST`, `BACKEND_PORT`)
- HMR enabled for hot module replacement
- Allowed hosts: `['app.packnation.org']` (configured in `vite.config.js`)

## Platform Requirements

**Development:**

- Python 3.12.3+
- Node.js v24.13.0+ (for npm)
- SQLite 3 (bundled with Python)
- Redis 5.0+ (for Celery task queue)
- Kraken API key and secret (optional, for live trading)
- OpenAI API key (for AI features)

**Production:**

- FastAPI backend runs on configurable host/port (default 0.0.0.0:8000)
- Static frontend assets served via reverse proxy or CDN
- SQLite or PostgreSQL-compatible database
- Redis for task queue
- TLS certificates and CA bundle supported (via `TLS_CERTFILE`, `TLS_KEYFILE`, `TLS_CA_BUNDLE`)

**Security:**

- Session cookie configuration (name: `cryptotrader_session`, defaults to `secure: false` in dev)
- HSTS headers enforced (max-age: 31536000 seconds, includes subdomains, preload enabled)
- Session timeout: 1800 seconds (30 minutes) by default
- Email enumeration protection disabled by default

---

*Stack analysis: 2026-02-04*
