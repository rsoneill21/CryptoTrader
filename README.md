# CryptoTrader

AI-powered cryptocurrency trading platform with multi-agent architecture.

## Overview

CryptoTrader is a web-based AI trading platform that acts like a real human trader - analyzing markets in real-time, proposing and testing strategies via paper trading, and executing live trades with user approval. The system features a multi-agent architecture where specialized AI agents handle market analysis, strategy optimization, sentiment monitoring, risk management, and trade execution.

## Features

- **AI Strategy Lab Dashboard** - Create, test, and optimize trading strategies with AI assistance
- **Live Trading Dashboard** - Real-time charts, AI annotations, and position management
- **Paper Trading** - Simulate strategies before going live
- **Multi-Agent Architecture** - Specialized AI agents for different trading functions
- **Risk Management** - Dynamic risk scoring and configurable limits
- **AI Chat Interface** - Conversational interface with your trading AI
- **Alerts & Activity Log** - Comprehensive notification and logging system
- **Multi-Model Support** - Use OpenAI GPT-4, Anthropic Claude, or local Ollama models

## Tech Stack

### Frontend
- React
- TailwindCSS
- TradingView Lightweight Charts
- WebSocket for real-time updates

### Backend
- Python 3.11+
- FastAPI (async support)
- SQLite database
- Celery/asyncio for background tasks

### Integrations
- Kraken Exchange API
- OpenAI API (GPT-4)
- Anthropic API (Claude)
- Social sentiment data sources

## Prerequisites

- Python 3.11+
- Node.js 18+
- API Keys:
  - Kraken API key and secret
  - OpenAI API key
  - Anthropic API key (optional)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd CryptoTrader
   ```

2. **Run the setup script**
   ```bash
   ./init.sh
   ```

3. **Configure environment variables**
   Edit `.env` file with your API keys:
   ```
   KRAKEN_API_KEY=your_key
   KRAKEN_API_SECRET=your_secret
   OPENAI_API_KEY=your_key
   ```

4. **Start the development servers**
   ```bash
   ./init.sh
   ```
   - Frontend: http://localhost:3000
   - Backend: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Project Structure

```
CryptoTrader/
├── backend/                 # FastAPI backend
│   ├── agents/             # AI agent implementations
│   ├── api/                # API routes
│   ├── core/               # Core business logic
│   ├── db/                 # Database models and migrations
│   ├── services/           # External service integrations
│   └── main.py             # FastAPI application entry point
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API services
│   │   ├── hooks/          # Custom React hooks
│   │   └── store/          # State management
│   └── public/
├── prompts/                # AI prompts and specifications
├── init.sh                 # Development setup script
└── README.md
```

## AI Agents

The system uses a multi-agent architecture:

1. **Market Analyst Agent** - Monitors real-time price data, detects patterns, identifies support/resistance levels
2. **Strategy Optimizer Agent** - Runs paper trade simulations and tunes strategy parameters
3. **Sentiment/News Agent** - Monitors social media, news, and on-chain data for market sentiment
4. **Risk Monitor Agent** - Calculates risk scores and triggers emergency actions
5. **Trade Executor Agent** - Handles order placement and management with the exchange
6. **Orchestrator (Main AI)** - Coordinates all agents and handles user interaction

## Security

- Email/password authentication with MFA support
- Configurable session timeouts
- Protected routes and API endpoints
- Confirmation required for sensitive operations (promoting to live trading, adjusting risk parameters)

## Development

### Backend Development
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

### Frontend Development
```bash
cd frontend
npm start
```

### Running Tests
```bash
# Backend tests
cd backend && pytest

# Frontend tests
cd frontend && npm test
```

## License

Private - Personal Use Only

## Disclaimer

This software is for educational and personal use only. Cryptocurrency trading involves substantial risk of loss. Use at your own risk.
