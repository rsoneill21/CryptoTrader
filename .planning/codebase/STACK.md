# Technology Stack

**Analysis Date:** 2026-02-04

## Languages

**Primary:**
- Python 3.12 - Backend API, services, and database migrations
- JavaScript (ES6+) - React frontend, UI interactions
- SQL - Database queries via SQLAlchemy ORM

**Secondary:**
- HTML/CSS - Email templates, AI chat interface
- Shell - Initialization and deployment scripts

## Runtime

**Environment:**
- Python 3.12.3 (backend)
- Node.js (frontend, via Vite dev server on port 5173)

**Package Manager:**
- pip (Python)
- npm (Node.js)
- Lockfile: `frontend/package.json` tracked; Python requirements in `backend/requirements.txt`

## Frameworks

**Core:**
- FastAPI 0.109.0+ - REST API framework with async support
- React 18.2.0 - Frontend UI library
- Vite 7.3.1 - Frontend bundler and dev server

**Database & ORM:**
- SQLAlchemy 2.0.25+ - SQL toolkit and ORM
- Alembic 1.13.1+ - Database migration tool
- SQLite 3.x - Default database (development)

**Testing:**
- pytest 7.4.4+ - Python testing framework
- pytest-asyncio 0.23.3+ - Async test support
- Testing Library (@testing-library/react) - Frontend component testing

**Build/Dev:**
- @vitejs/plugin-react 5.1.3+ - React support in Vite
- Tailwind CSS 3.4.1+ - Utility-first CSS framework
- PostCSS 8.4.33+ - CSS processing
- ESLint 9.10.0+ - JavaScript linting with React plugins

## Key Dependencies

**Critical:**
- fastapi & uvicorn - Core web framework and ASGI server
- sqlalchemy & alembic - Data persistence and schema management
- pydantic 2.5.3+ - Data validation and settings management
- pydantic-settings 2.1.0+ - Environment configuration
- httpx 0.26.0+ - Async HTTP client for external API calls
- websockets 12.0+ - WebSocket support for real-time data
- krakenex 2.2.1+ - Kraken cryptocurrency exchange API client

**AI & Machine Learning:**
- openai 1.9.0+ - OpenAI API client for GPT models
- anthropic 0.15.0+ - Anthropic Claude API client
- pandas 2.2.0+ - Data manipulation and analysis
- numpy 1.26.3+ - Numerical computing
- ta 0.11.0+ - Technical analysis indicators for trading

**Authentication & Security:**
- python-jose[cryptography] 3.3.0+ - JWT token generation and verification
- passlib[bcrypt] 1.7.4+ - Password hashing and verification
- email-validator 2.1.0+ - Email format validation

**Task Queue & Caching:**
- celery 5.3.6+ - Distributed task queue for background jobs
- redis 5.0.1+ - In-memory data store (broker and result backend)

**Utilities:**
- python-dotenv 1.0.0+ - Environment variable loading from .env
- pytz 2024.1+ - Timezone support

**Frontend:**
- axios 1.6.5+ - HTTP client for API requests
- react-router-dom 6.21.2+ - Client-side routing
- lightweight-charts 4.1.3+ - Financial charting library
- web-vitals 2.1.4+ - Performance metrics

## Configuration

**Environment:**
- Loaded via `.env` file (see `.env.example` for template)
- Pydantic settings validation in `backend/core/settings.py`
- Environment variables for secrets: KRAKEN_API_KEY, KRAKEN_API_SECRET, OPENAI_API_KEY, ANTHROPIC_API_KEY, SLACK_BOT_TOKEN, GROQ_API_TOKEN, OLLAMA_API_KEY

**Build:**
- `frontend/vite.config.js` - Frontend build config with React support
- `frontend/tailwind.config.js` - Tailwind CSS theme customization
- `frontend/eslint.config.js` - JavaScript linting rules
- `frontend/postcss.config.cjs` - PostCSS plugins for Tailwind

## Database

**Default:**
- SQLite 3.x at `./cryptotrader.db` (local development)
- Configurable via `DATABASE_URL` environment variable
- Connection pooling via SQLAlchemy engine

**Migrations:**
- Alembic for schema versioning
- Migration files in `backend/alembic/versions/`
- Run via `init_db()` on application startup

## Task Queue

**Broker & Backend:**
- Redis (default: `redis://localhost:6379/0`)
- Configurable via `REDIS_URL` environment variable
- Used by Celery for distributed task execution

**Configuration:**
- Celery app in `backend/core/celery_app.py`
- Beat scheduler for periodic tasks (cleanup, monitoring)
- JSON serialization for task payloads

## WebSocket

**Real-time Communication:**
- Kraken WebSocket API for live price feeds (`backend/services/kraken_ws.py`)
- Frontend connects via `/ws` proxy in Vite dev server
- Uses `websockets` 12.0+ library

## Platform Requirements

**Development:**
- Python 3.12+
- Node.js 18+
- Redis server running on localhost:6379 (for Celery)
- Kraken API credentials (optional, for trading features)
- OpenAI/Anthropic API keys (optional, for AI features)

**Production:**
- ASGI-compatible server (Uvicorn with optional SSL/TLS support)
- Relational database (SQLite, PostgreSQL, MySQL compatible via SQLAlchemy)
- Redis instance for task queue
- CORS configured for multiple frontend origins
- HSTS headers for TLS-enabled deployments
- Session cookie security: `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`

## Deployment

**Frontend:**
- Vite build output to `dist/` directory
- Served as static files from FastAPI backend or separate web server
- Development: `npm run dev` on port 5173
- Production: `npm run build`

**Backend:**
- FastAPI with Uvicorn ASGI server
- Default: `0.0.0.0:8000` (configurable via `BACKEND_HOST`, `BACKEND_PORT`)
- Optional TLS via `TLS_CERTFILE`, `TLS_KEYFILE`, `TLS_CA_BUNDLE`
- Startup hook initializes database migrations and Kraken WebSocket connection

---

*Stack analysis: 2026-02-04*
