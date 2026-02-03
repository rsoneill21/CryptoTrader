#!/bin/bash

# CryptoTrader - Development Environment Setup Script
# This script initializes and starts the development environment

set -e

echo "============================================"
echo "  CryptoTrader Development Environment"
echo "============================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for required tools
check_requirements() {
    echo "Checking requirements..."

    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        echo -e "${GREEN}✓${NC} Python: $PYTHON_VERSION"
    else
        echo -e "${RED}✗${NC} Python 3.11+ is required but not found"
        exit 1
    fi

    # Check Node.js
    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        echo -e "${GREEN}✓${NC} Node.js: $NODE_VERSION"
    else
        echo -e "${RED}✗${NC} Node.js 18+ is required but not found"
        exit 1
    fi

    # Check npm
    if command -v npm &> /dev/null; then
        NPM_VERSION=$(npm --version)
        echo -e "${GREEN}✓${NC} npm: $NPM_VERSION"
    else
        echo -e "${RED}✗${NC} npm is required but not found"
        exit 1
    fi

    echo ""
}

# Setup Python virtual environment
setup_python_env() {
    echo "Setting up Python environment..."

    if [ ! -d "backend/venv" ]; then
        echo "Creating virtual environment..."
        cd backend
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip

        if [ -f "requirements.txt" ]; then
            echo "Installing Python dependencies..."
            pip install -r requirements.txt
        fi
        cd ..
    else
        echo "Virtual environment already exists"
        source backend/venv/bin/activate
    fi

    echo -e "${GREEN}✓${NC} Python environment ready"
    echo ""
}

# Setup Node.js/React frontend
setup_frontend() {
    echo "Setting up Frontend..."

    if [ -d "frontend" ]; then
        cd frontend
        if [ ! -d "node_modules" ]; then
            echo "Installing Node.js dependencies..."
            npm install
        else
            echo "Node modules already installed"
        fi
        cd ..
    fi

    echo -e "${GREEN}✓${NC} Frontend ready"
    echo ""
}

# Initialize database
init_database() {
    echo "Initializing database..."

    if [ -f "backend/init_db.py" ]; then
        cd backend
        source venv/bin/activate
        python init_db.py
        cd ..
    fi

    echo -e "${GREEN}✓${NC} Database initialized"
    echo ""
}

# Check environment variables
load_env_file() {
    if [ -f ".env" ]; then
        echo "Loading environment variables from .env..."
        set -a
        # shellcheck disable=SC1091
        source ".env"
        set +a
    fi
}

check_env_vars() {
    echo "Checking environment variables..."

    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}!${NC} No .env file found. Creating template..."
        cat > .env << 'EOF'
# CryptoTrader Environment Variables

# Kraken API (Required for live trading)
KRAKEN_API_KEY=your_kraken_api_key
KRAKEN_API_SECRET=your_kraken_api_secret

# AI Model API Keys
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# Application Settings
APP_SECRET_KEY=generate_a_secure_random_key_here
DATABASE_URL=sqlite:///./cryptotrader.db

# Server Configuration
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_PORT=3000
VITE_API_URL=http://127.0.0.1:8000
VITE_WS_URL=ws://127.0.0.1:8000

# Session Settings
SESSION_TIMEOUT_MINUTES=60

# Optional: Data Sources
TWITTER_API_KEY=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
EOF
        echo -e "${YELLOW}!${NC} Please edit .env with your API keys before running"
    else
        echo -e "${GREEN}✓${NC} .env file found"
    fi
    echo ""
}

# Start development servers
start_servers() {
    echo "Starting development servers..."
    echo ""

    # Start backend in background
    local backend_host="${BACKEND_HOST:-127.0.0.1}"
    local backend_port="${BACKEND_PORT:-8000}"
    echo "Starting FastAPI backend on ${backend_host}:${backend_port}..."
    cd backend
    source venv/bin/activate
    uvicorn main:app --reload --host "${backend_host}" --port "${backend_port}" &
    BACKEND_PID=$!
    cd ..

    # Wait for backend to start
    sleep 2

    # Start frontend in background
    echo "Starting React frontend on port 3000..."
    cd frontend
    npm run dev &
    FRONTEND_PID=$!
    cd ..

    echo ""
    echo "============================================"
    echo -e "${GREEN}Servers Started Successfully!${NC}"
    echo "============================================"
    echo ""
    echo "  Frontend:  http://localhost:3000"
    echo "  Backend:   http://${backend_host}:${backend_port}"
    echo "  API Docs:  http://${backend_host}:${backend_port}/docs"
    echo ""
    echo "Press Ctrl+C to stop all servers"
    echo ""

    # Wait for interrupt
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
    wait
}

# Main execution
main() {
    # Ensure we're in the project root
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR"

    check_requirements
    check_env_vars

    # Create directories if they don't exist
    mkdir -p backend frontend

    setup_python_env
    setup_frontend
    init_database

    load_env_file

    local backend_host="${BACKEND_HOST:-127.0.0.1}"
    local backend_port="${BACKEND_PORT:-8000}"

    echo ""
    read -p "Start development servers? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        BACKEND_HOST="$backend_host" BACKEND_PORT="$backend_port" start_servers
    else
        echo ""
        echo "Setup complete! Run './init.sh' again to start servers."
        echo ""
    fi
}

# Run main
main "$@"
