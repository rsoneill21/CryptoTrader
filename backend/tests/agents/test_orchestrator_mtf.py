import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal
import pandas as pd
from agents.orchestrator import OrchestratorAgent
from services.kraken import OHLC, Ticker, OrderSide
from db.models import Strategy

@pytest.mark.asyncio
async def test_orchestrator_multi_timeframe_decision():
    """Test that orchestrator correctly evaluates multi-timeframe strategies."""
    
    # 1. Setup Orchestrator
    orchestrator = OrchestratorAgent()
    orchestrator._decision_lock = AsyncMock() # Skip lock for testing
    
    symbol = "BTC/USD"
    strategy_id = 1
    
    # Mock strategy rules
    rules = {
        "base_timeframe": "1m",
        "entry": {
            "logic": "and",
            "conditions": [
                {
                    "indicator": "sma",
                    "window": 1,
                    "operator": ">",
                    "value": 100,
                    "timeframe": "1h"
                },
                {
                    "indicator": "rsi",
                    "window": 14,
                    "operator": "<",
                    "value": 70,
                    "timeframe": "1m"
                }
            ]
        },
        "exit": {"conditions": []}
    }
    
    # Mock data
    # 1h data: SMA(1) will be 105 (> 100)
    h1_candles = [
        OHLC(timestamp=datetime.now(timezone.utc), open=Decimal("100"), high=Decimal("110"), low=Decimal("90"), close=Decimal("105"), volume=Decimal("1000"), vwap=Decimal("100"), trades=100)
    ]
    
    # 1m data: RSI will be low
    m1_candles = [
        OHLC(timestamp=datetime.now(timezone.utc), open=Decimal("100"), high=Decimal("105"), low=Decimal("95"), close=Decimal("102"), volume=Decimal("10"), vwap=Decimal("100"), trades=10)
        for _ in range(20)
    ]

    # 2. Patch dependencies
    with (
        patch("agents.orchestrator.AsyncSessionLocal") as mock_session_factory,
        patch("agents.orchestrator.kraken_service") as mock_kraken,
        patch("agents.orchestrator.message_queue") as mock_mq,
        patch("agents.orchestrator.trading_control") as mock_tc
    ):
        # Mock DB session
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        # Correctly mock the result of session.execute()
        mock_result = MagicMock()
        mock_session.execute.return_value = mock_result
        
        mock_strategy = MagicMock(spec=Strategy)
        mock_strategy.rules_json = rules
        mock_result.scalar_one_or_none.return_value = mock_strategy
        
        # Mock Kraken service
        async def mock_get_ohlc(sym, interval):
            return (h1_candles, 123456) if interval == "1h" else (m1_candles, 123456)
        
        mock_kraken.get_ohlc.side_effect = mock_get_ohlc
        
        async def mock_get_ticker(sym):
            return Ticker(
                symbol=symbol, ask=Decimal("102"), bid=Decimal("101"), last=Decimal("102"),
                volume_24h=Decimal("1000"), vwap_24h=Decimal("100"), high_24h=Decimal("110"),
                low_24h=Decimal("90"), open_24h=Decimal("100"), trades_24h=1000,
                timestamp=datetime.now(timezone.utc)
            )
        
        mock_kraken.get_ticker.side_effect = mock_get_ticker
        
        # Mock trading control
        mock_tc.is_paused.return_value = False
        
        # Mock message queue
        mock_mq.publish_reliable.return_value = True
        mock_mq.publish.return_value = True
        
        # 3. Setup orchestrator state
        from agents.orchestrator import MarketInsightPayload, StrategyOptimizationPayload
        
        orchestrator._insights[symbol] = MarketInsightPayload(
            symbol=symbol, insight_type="test", level="bullish", summary="test"
        )
        orchestrator._strategies[symbol] = StrategyOptimizationPayload(
            strategy_id=strategy_id, strategy_name="test", symbol=symbol, params={"position_size_pct": 1.0}
        )
        
        # 4. Execute evaluation
        await orchestrator._maybe_create_trade_signal(symbol)
        
        # 5. Verify results
        # Should have called get_ohlc twice (1h and 1m)
        assert mock_kraken.get_ohlc.call_count == 2
        
        # Should have published a trade signal
        assert mock_mq.publish_reliable.called or mock_mq.publish.called
        
        # Check signal content if needed
        if mock_mq.publish_reliable.called:
            args, kwargs = mock_mq.publish_reliable.call_args
            payload = args[1]
            assert payload["symbol"] == symbol
            assert payload["side"] == "buy"
