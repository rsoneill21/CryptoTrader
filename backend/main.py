"""
CryptoTrader - FastAPI Backend Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    print("Starting CryptoTrader Backend...")
    init_db()
    yield
    # Shutdown
    print("Shutting down CryptoTrader Backend...")


app = FastAPI(
    title="CryptoTrader API",
    description="AI-powered cryptocurrency trading platform API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "CryptoTrader API", "status": "running"}


@app.get("/api/system/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "0.1.0",
        "services": {
            "database": "connected",
            "agents": "initializing"
        }
    }


# Import and include routers (to be implemented)
# from api import auth, strategies, trades, ai, alerts, market, risk, export, system
# app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
# app.include_router(strategies.router, prefix="/api/strategies", tags=["Strategies"])
# app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
# app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
# app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
# app.include_router(market.router, prefix="/api/market", tags=["Market"])
# app.include_router(risk.router, prefix="/api/risk", tags=["Risk"])
# app.include_router(export.router, prefix="/api/export", tags=["Export"])
# app.include_router(system.router, prefix="/api/system", tags=["System"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
