# CryptoTrader Backend

FastAPI application that exposes the authentication, market, and system APIs for the CryptoTrader platform. The backend ships with database models, Celery configuration, and lightweight services for Kraken, email, and password resets.

## Requirements
- Python 3.11+
- `pip` and virtual environments (`venv`)
- Redis for Celery workers (`redis-server` or a Docker container)
- Optional: Kraken API key/secret, OpenAI/Anthropic API keys for integrations

## Quick setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` or export environment variables before running: 
- `DATABASE_URL` (defaults to `sqlite:///./cryptotrader.db`)
- `KRAKEN_API_KEY`, `KRAKEN_API_SECRET` (optional for authenticated Kraken calls)
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (if you plan to hit the AI agents)
- `REDIS_URL` (defaults to `redis://localhost:6379/0`, used by Celery)

### Database migrations
```bash
cd backend
source venv/bin/activate
alembic upgrade head
```
Alembic now owns the schema. The initial migration lives under `backend/alembic/versions/0001_initial_schema.py`, and `backend/db/database.init_db()` calls `alembic upgrade head` automatically when the API starts, so deployment never reverts the schema. When adding a new model or changing an existing table, run `alembic revision --autogenerate -m "describe change"` and review the generated script before applying it.

### Database initialization
```bash
source venv/bin/activate
python init_db.py
```
This script now triggers Alembic migrations (instead of calling `Base.metadata.create_all`) so your database is brought up to date before the app launches.

## Running the API server
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```
The API docs are available at `http://localhost:8000/docs` once the server starts.

## Celery worker + beat
Celery powered tasks live in `core/tasks.py` and the app is configured via `core/celery_app.py`. Start Redis locally first:
```bash
redis-server
```
Then run the worker (and optionally beat) in separate terminals:
```bash
cd backend
source venv/bin/activate
celery -A core.celery_app.celery_app worker --loglevel=info
celery -A core.celery_app.celery_app beat --loglevel=info
```
The Celery app honors the `REDIS_URL` env var, so you can point it to a Docker/managed Redis instance.

## Tests
```bash
cd backend
source venv/bin/activate
pytest tests/test_auth.py
```
Run `pytest` without arguments to execute the full suite once more tests are added.
