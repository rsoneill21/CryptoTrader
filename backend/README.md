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

## Production deployment (HTTPS/TLS)

The development server binds to `0.0.0.0:8000` over plain HTTP. For production, terminate TLS in front of the FastAPI app and configure the API to operate in HTTPS mode with tightly scoped cookies and HSTS headers.

### Reverse proxy (recommended)

- Front the backend with a reverse proxy (Nginx, Caddy, Traefik, etc.) that manages certificates via Let's Encrypt or your corporate CA.
- Proxy `https://crypto.example.com` to the local HTTP endpoint `http://127.0.0.1:8000`, keeping the FastAPI process non-privileged and simplifying DDoS/HTTP/2 tuning.
- Provide the proxy with headers such as `X-Forwarded-Proto` and `X-Forwarded-For` so the backend can learn the original TLS state.

```nginx
server {
    listen 443 ssl http2;
    server_name crypto.example.com;

    ssl_certificate /etc/letsencrypt/live/crypto.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crypto.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### Direct TLS termination (optional)

- When TLS must terminate directly in Uvicorn (e.g., running inside a container without a reverse proxy), pass certificate paths:

```bash
uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --ssl-certfile=/etc/ssl/crypto.crt \
    --ssl-keyfile=/etc/ssl/crypto.key
```

- Supply `--ssl-ca-certs` if your clients need a custom CA bundle. Avoid running Uvicorn as root and rotate short-lived certificates frequently.

### Configuration reference

CryptoTrader exposes these environment variables to control TLS, CORS, cookies, and HSTS:

- `APP_ENV` (`production` enables secure defaults such as `Strict-Transport-Security` and secure cookies).
- `APP_HOST` / `APP_PORT` (backend listener; defaults to `0.0.0.0:8000`).
- `FRONTEND_ORIGINS` (comma-separated list of allowed origins for CORS; defaults to `http://localhost:3000`).
- `TLS_CERTFILE` / `TLS_KEYFILE` (mandatory together for direct TLS termination).
- `TLS_CA_BUNDLE` (optional PEM bundle trusted by clients).
- `HSTS_MAX_AGE_SECONDS` / `HSTS_INCLUDE_SUBDOMAINS` / `HSTS_PRELOAD` (adjust the header applied when TLS is active).
- `SESSION_COOKIE_NAME` / `SESSION_COOKIE_SAMESITE` (defaults to `cryptotrader_session` and `lax`).
- `SESSION_COOKIE_SECURE` and `ALLOW_INSECURE_COOKIES` (production sets secure cookies; override only in non-HTTPS environments).

When direct TLS is configured, the backend automatically adds `Strict-Transport-Security` and marks authentication cookies as secure/httponly to keep credentials safe. Reverse proxies should still forward TLS headers so downstream services know the original scheme.

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
