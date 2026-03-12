"""
AI Agents for CryptoTrader.

Multi-agent architecture with specialized agents for:
- Market Analyst: Monitors price data, detects patterns
- Strategy Optimizer: Tests and tunes strategies
- Sentiment/News: Monitors social media and news
- Risk Monitor: Calculates and monitors risk
- Trade Executor: Places orders with exchange
- Orchestrator: Coordinates all agents and user interaction
"""

from agents.base import BaseAgent, AgentRegistry

__all__ = ["BaseAgent", "AgentRegistry"]
