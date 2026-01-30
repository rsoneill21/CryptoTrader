"""
CryptoTrader - FastAPI Backend Entry Point
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from contextlib import asynccontextmanager

from api.errors import register_exception_handlers
from db.database import init_db
from services.kraken_ws import start_kraken_ws, stop_kraken_ws
from core.settings import get_app_settings
from api import auth_router, market_router, system_router
from api.alerts import router as alerts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    print("Starting CryptoTrader Backend...")
    init_db()
    await start_kraken_ws()
    yield
    # Shutdown
    await stop_kraken_ws()
    print("Shutting down CryptoTrader Backend...")


settings = get_app_settings()


class HSTSMiddleware(BaseHTTPMiddleware):
    """Attach a Strict-Transport-Security header when TLS is active."""

    def __init__(self, app: FastAPI, header_value: str | None):
        super().__init__(app)
        self.header_value = header_value

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        if self.header_value:
            response.headers.setdefault("Strict-Transport-Security", self.header_value)
        return response


app = FastAPI(
    title="CryptoTrader API",
    description="AI-powered cryptocurrency trading platform API",
    version="0.1.0",
    lifespan=lifespan
)

register_exception_handlers(app)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.hsts_header_value and settings.tls_enabled:
    app.add_middleware(HSTSMiddleware, header_value=settings.hsts_header_value)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "CryptoTrader API", "status": "running"}


# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(system_router, prefix="/api/system", tags=["System"])
app.include_router(market_router, prefix="/api/market", tags=["Market"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["Alerts"])

# Future routers (to be implemented in later phases)
# from api.strategies import router as strategies_router
# from api.trades import router as trades_router
# from api.ai import router as ai_router
# from api.market import router as market_router
# from api.risk import router as risk_router
# from api.export import router as export_router
# app.include_router(strategies_router, prefix="/api/strategies", tags=["Strategies"])
# app.include_router(trades_router, prefix="/api/trades", tags=["Trades"])
# app.include_router(ai_router, prefix="/api/ai", tags=["AI"])
# app.include_router(market_router, prefix="/api/market", tags=["Market"])
# app.include_router(risk_router, prefix="/api/risk", tags=["Risk"])
# app.include_router(export_router, prefix="/api/export", tags=["Export"])


if __name__ == "__main__":
    import uvicorn

    uvicorn_kwargs: dict[str, Any] = {
        "app": app,
        "host": settings.host,
        "port": settings.port,
    }

    if settings.tls_enabled:
        uvicorn_kwargs.update({
            "ssl_certfile": settings.tls_certfile,
            "ssl_keyfile": settings.tls_keyfile,
        })
        if settings.tls_ca_bundle:
            uvicorn_kwargs["ssl_ca_certs"] = settings.tls_ca_bundle

    uvicorn.run(**uvicorn_kwargs)
