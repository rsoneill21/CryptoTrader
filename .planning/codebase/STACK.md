# Technology Stack

**Analysis Date:** 2025-03-04

## Languages

**Primary:**
- Python 3.10+ - Backend logic, AI agents, and API service.
- JavaScript/JSX - Frontend React application.

**Secondary:**
- SQL (SQLite) - Database schema and queries.
- HTML/CSS - UI structure and styling (via Tailwind).
- Shell (Bash) - Initialization and deployment scripts.

## Runtime

**Environment:**
- Node.js 18+ (Frontend build/dev)
- Python 3.10+ (Backend runtime)

**Package Manager:**
- npm - Frontend dependency management.
- pip - Backend dependency management.
- Lockfiles: `package-lock.json` and `backend/requirements.txt` (no lockfile for pip) are present.

## Frameworks

**Core:**
- FastAPI (v0.109+) - Backend web framework.
- React (v18.2.0) - Frontend UI library.
- Vite (v7.3.1) - Frontend build tool and dev server.

**Testing:**
- pytest (v7.4.4) - Backend testing framework.
- React Testing Library - Frontend component testing.

**Build/Dev:**
- Tailwind CSS (v3.4.1) - Utility-first CSS framework.
- PostCSS / Autoprefixer - CSS processing.
- ESLint - Frontend linting.

## Key Dependencies

**Critical:**
- SQLAlchemy (v2.0+) - Backend ORM.
- Alembic (v1.13+) - Database migrations.
- Pydantic (v2.5+) - Data validation and settings management.
- Celery (v5.3+) - Distributed task queue.
- Krakenex (v2.2+) - Kraken exchange API client.

**Infrastructure:**
- Redis (v5.0+) - Message broker for Celery and caching.
- SQLite - Primary database engine.
- HTTPX - Asynchronous HTTP client for API calls.

## Configuration

**Environment:**
- Configured via `.env` files and `pydantic-settings`.
- Backend config located in `backend/core/settings.py`.

**Build:**
- `frontend/vite.config.js` - Vite build and proxy configuration.
- `backend/alembic.ini` - Database migration configuration.

## Platform Requirements

**Development:**
- Docker (optional, for Redis).
- Python 3.10+ and Node.js 18+.

**Production:**
- Linux-based environment (Ubuntu/Debian recommended).
- Redis server instance.

---

*Stack analysis: 2025-03-04*
