"""
Database initialization script.
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db.database import init_db

if __name__ == "__main__":
    print("Initializing CryptoTrader database...")
    init_db()
    print("Database initialization complete!")
