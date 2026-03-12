#!/bin/bash

set -e

echo "Stopping CryptoTrader frontend and backend..."

pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true

# Also stop any lingering npm dev servers
pkill -f "node.*vite" 2>/dev/null || true

echo "Done."
