
import asyncio
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.kraken import kraken_service

async def verify_kraken():
    print("Testing Kraken API connection (public endpoint)...")
    try:
        ticker = await kraken_service.get_ticker("BTC/USD")
        print(f"Success! BTC/USD Last Price: {ticker.last}")
        return True
    except Exception as e:
        print(f"Kraken API connection failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(verify_kraken())
    sys.exit(0 if success else 1)
