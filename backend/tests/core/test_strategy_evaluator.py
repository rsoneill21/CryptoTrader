import pytest
import pandas as pd
import numpy as np
from core.strategy_evaluator import StrategyEvaluator

def test_multi_timeframe_evaluation():
    # Create 5m synthetic data
    base_index = pd.date_range("2023-01-01", periods=24, freq="5min")
    base_df = pd.DataFrame({
        "open": np.linspace(100, 110, 24),
        "high": np.linspace(101, 111, 24),
        "low": np.linspace(99, 109, 24),
        "close": [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100, 99, 
                  98, 97, 96, 95, 96, 97, 98, 99, 100, 101, 102, 103],
        "volume": [100] * 24
    }, index=base_index)

    # Create 1h synthetic data
    h1_index = pd.date_range("2023-01-01", periods=2, freq="h")
    h1_df = pd.DataFrame({
        "open": [100, 98],
        "high": [105, 103],
        "low": [99, 95],
        "close": [100, 103],
        "volume": [1200, 1200]
    }, index=h1_index)

    rules = {
        "entry": {
            "logic": "and",
            "conditions": [
                {
                    "indicator": "sma",
                    "window": 1,
                    "operator": ">",
                    "value": 101,
                    "timeframe": "1h"
                },
                {
                    "indicator": "rsi",
                    "window": 14,
                    "operator": "<",
                    "value": 70,
                    "timeframe": "5m"
                }
            ]
        },
        "exit": {
            "logic": "or",
            "conditions": []
        }
    }

    evaluator = StrategyEvaluator(rules)
    data = {
        "5m": base_df,
        "1h": h1_df
    }
    
    # We pass data as a dict now
    result_df = evaluator.evaluate(data, base_timeframe="5m")
    
    assert "entry_signal" in result_df.columns
    
    # First hour (indices 0-11): 1h SMA(1) is 100, which is NOT > 101.
    # Second hour (indices 12-23): 1h SMA(1) is 103, which IS > 101.
    
    # Check alignment: first 12 candles should be False
    for i in range(12):
        assert result_df.iloc[i]["entry_signal"] == False, f"Failed at index {i}"
        
    # Check that SOME candles in second half are True (RSI should be < 70)
    assert result_df.iloc[12:24]["entry_signal"].any()
