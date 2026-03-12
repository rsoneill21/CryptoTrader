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

    def evaluate(self, data: Any, base_timeframe: str = "1m") -> pd.DataFrame:
        """
        Evaluate rules against market data.
        data can be a single DataFrame (legacy) or a Dict[str, pd.DataFrame].
        Returns a DataFrame with 'entry_signal' and 'exit_signal' columns.
        """
        # Handle legacy single-dataframe input
        if isinstance(data, pd.DataFrame):
            data = {base_timeframe: data}
        
        if not data or base_timeframe not in data:
            return pd.DataFrame()

        base_df = data[base_timeframe]
        if base_df.empty:
            return base_df

        # Identify all timeframes involved
        all_rules = []
        if 'entry' in self.rules:
            all_rules.extend(self.rules['entry'].get('conditions', []))
        if 'exit' in self.rules:
            all_rules.extend(self.rules['exit'].get('conditions', []))
            
        # Group conditions by timeframe
        tf_conditions = {}
        for cond in all_rules:
            tf = cond.get('timeframe', base_timeframe)
            if tf not in tf_conditions:
                tf_conditions[tf] = []
            tf_conditions[tf].append(cond)
            
        eval_df = base_df.copy()
        
        # Calculate and align indicators for each timeframe
        for tf, conditions in tf_conditions.items():
            if tf not in data:
                logger.warning(f"Data for timeframe {tf} not provided for evaluation")
                continue
                
            ind_df = self._calculate_indicators_for_df(data[tf], conditions)
            
            if tf == base_timeframe:
                # Merge indicators directly for base timeframe
                eval_df = pd.concat([eval_df, ind_df], axis=1)
            else:
                # Align higher timeframe indicators to base index (forward fill)
                aligned_ind_df = ind_df.reindex(base_df.index, method='ffill')
                # Prefix columns to avoid collision (e.g., '1h_sma_20')
                aligned_ind_df.columns = [f"{tf}_{col}" for col in aligned_ind_df.columns]
                eval_df = pd.concat([eval_df, aligned_ind_df], axis=1)

        # Evaluate entry conditions
        eval_df['entry_signal'] = self._evaluate_conditions(eval_df, self.rules.get('entry', {}), default_tf=base_timeframe)
        
        # Evaluate exit conditions
        eval_df['exit_signal'] = self._evaluate_conditions(eval_df, self.rules.get('exit', {}), default_tf=base_timeframe)
        
        return eval_df

    def _calculate_indicators_for_df(self, df: pd.DataFrame, conditions: List[Dict[str, Any]]) -> pd.DataFrame:
        """Calculate all indicators mentioned in the provided conditions."""
        indicator_data = {}
        closes = df['close'].tolist()
        
        for cond in conditions:
            ind_type = cond.get('indicator', '').lower()
            if not ind_type:
                continue
                
            if ind_type == 'sma':
                window = cond.get('window', 20)
                series = simple_moving_average(closes, window=window)
                series.index = df.index
                indicator_data[f"sma_{window}"] = series
            elif ind_type == 'ema':
                window = cond.get('window', 20)
                series = exponential_moving_average(closes, window=window)
                series.index = df.index
                indicator_data[f"ema_{window}"] = series
            elif ind_type == 'rsi':
                window = cond.get('window', 14)
                series = relative_strength_index(closes, window=window)
                series.index = df.index
                indicator_data[f"rsi_{window}"] = series
            elif ind_type == 'macd':
                macd_df = moving_average_convergence_divergence(closes)
                macd_df.index = df.index
                indicator_data['macd'] = macd_df['macd']
                indicator_data['macd_signal'] = macd_df['signal']
                indicator_data['macd_histogram'] = macd_df['histogram']
            elif ind_type == 'bollinger':
                bb_df = bollinger_bands(closes)
                bb_df.index = df.index
                indicator_data['bollinger_upper'] = bb_df['upper']
                indicator_data['bollinger_lower'] = bb_df['lower']
                
        return pd.DataFrame(indicator_data, index=df.index)

    def _evaluate_conditions(self, df: pd.DataFrame, rule_group: Dict[str, Any], default_tf: str = "1m") -> pd.Series:
        """Evaluate a group of conditions (AND/OR)."""
        conditions = rule_group.get('conditions', [])
        if not conditions:
            return pd.Series(False, index=df.index)
            
        logic = rule_group.get('logic', 'and').lower()
        
        results = []
        for cond in conditions:
            results.append(self._evaluate_single_condition(df, cond, default_tf))
            
        if not results:
            return pd.Series(False, index=df.index)
            
        final_result = results[0]
        for res in results[1:]:
            if logic == 'or':
                final_result = final_result | res
            else:
                final_result = final_result & res
                
        return final_result

    def _evaluate_single_condition(self, df: pd.DataFrame, cond: Dict[str, Any], default_tf: str = "1m") -> pd.Series:
        """Evaluate a single condition like 'rsi_14 < 30'."""
        tf = cond.get('timeframe', default_tf)
        ind_type = cond.get('indicator', '').lower()
        if not ind_type:
            return pd.Series(False, index=df.index)
            
        window = cond.get('window', 20 if ind_type != 'rsi' else 14)
        col_name = f"{ind_type}_{window}" if ind_type in ['sma', 'ema', 'rsi'] else ind_type
        
        # Use prefixed column name if not base timeframe
        if tf != default_tf:
            col_name = f"{tf}_{col_name}"
            
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