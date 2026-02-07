"""Strategy rule evaluator for backtesting and autonomous trading."""

import logging
from typing import Any, Dict, List, Optional
import pandas as pd
from pydantic import BaseModel

from core.indicators import (
    simple_moving_average,
    exponential_moving_average,
    relative_strength_index,
    moving_average_convergence_divergence,
    bollinger_bands,
)

logger = logging.getLogger(__name__)

class StrategyEvaluator:
    """Evaluates strategy rules against market data."""

    def __init__(self, rules: Dict[str, Any]) -> None:
        self.rules = rules

    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Evaluate rules against a DataFrame of OHLCV data.
        Returns a DataFrame with 'entry_signal' and 'exit_signal' columns.
        """
        if df.empty:
            return df

        # Calculate all needed indicators once
        indicators = self._calculate_indicators(df)
        
        # Merge indicators into main dataframe
        eval_df = pd.concat([df, indicators], axis=1)
        
        # Evaluate entry conditions
        eval_df['entry_signal'] = self._evaluate_conditions(eval_df, self.rules.get('entry', {}))
        
        # Evaluate exit conditions
        eval_df['exit_signal'] = self._evaluate_conditions(eval_df, self.rules.get('exit', {}))
        
        return eval_df

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators mentioned in the rules."""
        indicator_data = {}
        closes = df['close'].tolist()
        
        # This is a bit naive, ideally we'd scan the rules to see which windows are needed.
        # For now, we'll calculate standard ones or look at specific rule params.
        
        # Example of dynamic calculation based on rules
        all_conditions = []
        if 'entry' in self.rules:
            all_conditions.extend(self.rules['entry'].get('conditions', []))
        if 'exit' in self.rules:
            all_conditions.extend(self.rules['exit'].get('conditions', []))
            
        for cond in all_conditions:
            ind_type = cond.get('indicator', '').lower()
            if ind_type == 'sma':
                window = cond.get('window', 20)
                indicator_data[f"sma_{window}"] = simple_moving_average(closes, window=window)
            elif ind_type == 'ema':
                window = cond.get('window', 20)
                indicator_data[f"ema_{window}"] = exponential_moving_average(closes, window=window)
            elif ind_type == 'rsi':
                window = cond.get('window', 14)
                indicator_data[f"rsi_{window}"] = relative_strength_index(closes, window=window)
            elif ind_type == 'macd':
                macd_df = moving_average_convergence_divergence(closes)
                indicator_data['macd'] = macd_df['macd']
                indicator_data['macd_signal'] = macd_df['signal']
                indicator_data['macd_histogram'] = macd_df['histogram']
            elif ind_type == 'bollinger':
                bb_df = bollinger_bands(closes)
                indicator_data['bollinger_upper'] = bb_df['upper']
                indicator_data['bollinger_lower'] = bb_df['lower']
                
        return pd.DataFrame(indicator_data, index=df.index)

    def _evaluate_conditions(self, df: pd.DataFrame, rule_group: Dict[str, Any]) -> pd.Series:
        """Evaluate a group of conditions (AND/OR)."""
        conditions = rule_group.get('conditions', [])
        if not conditions:
            return pd.Series(False, index=df.index)
            
        logic = rule_group.get('logic', 'and').lower()
        
        results = []
        for cond in conditions:
            results.append(self._evaluate_single_condition(df, cond))
            
        if not results:
            return pd.Series(False, index=df.index)
            
        final_result = results[0]
        for res in results[1:]:
            if logic == 'or':
                final_result = final_result | res
            else:
                final_result = final_result & res
                
        return final_result

    def _evaluate_single_condition(self, df: pd.DataFrame, cond: Dict[str, Any]) -> pd.Series:
        """Evaluate a single condition like 'rsi_14 < 30'."""
        ind_type = cond.get('indicator', '').lower()
        if not ind_type:
            return pd.Series(False, index=df.index)
            
        window = cond.get('window', 20 if ind_type != 'rsi' else 14)
        col_name = f"{ind_type}_{window}" if ind_type in ['sma', 'ema', 'rsi'] else ind_type
        
        if col_name not in df.columns:
            return pd.Series(False, index=df.index)
            
        operator = cond.get('operator', '==')
        value = cond.get('value')
        
        # If value is another indicator/column
        if isinstance(value, str) and value in df.columns:
            compare_to = df[value]
        else:
            compare_to = value
            
        if operator == '>':
            return df[col_name] > compare_to
        elif operator == '<':
            return df[col_name] < compare_to
        elif operator == '>=':
            return df[col_name] >= compare_to
        elif operator == '<=':
            return df[col_name] <= compare_to
        elif operator == '==':
            return df[col_name] == compare_to
        elif operator == 'crosses_above':
            # Needs previous value
            prev_val = df[col_name].shift(1)
            if isinstance(compare_to, pd.Series):
                prev_compare = compare_to.shift(1)
            else:
                prev_compare = compare_to
            return (prev_val <= prev_compare) & (df[col_name] > compare_to)
        elif operator == 'crosses_below':
            prev_val = df[col_name].shift(1)
            if isinstance(compare_to, pd.Series):
                prev_compare = compare_to.shift(1)
            else:
                prev_compare = compare_to
            return (prev_val >= prev_compare) & (df[col_name] < compare_to)
            
        return pd.Series(False, index=df.index)
