"""
API routers for CryptoTrader.
"""

from api.auth import router as auth_router
from api.market import router as market_router
from api.system import router as system_router
from api.performance import router as performance_router

__all__ = ["auth_router", "market_router", "system_router", "performance_router"]
