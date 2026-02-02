import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';

const DEFAULT_SYMBOL = 'BTC/USD';
const DEFAULT_TIMEFRAME = '1m';
const DEFAULT_LIMIT = 400;

const normalizeCandles = (entries = []) =>
  entries
    .map((candle) => {
      const time = new Date(candle.timestamp).getTime();
      if (Number.isNaN(time)) {
        return null;
      }
      return {
        time: Math.floor(time / 1000),
        open: Number(candle.open),
        high: Number(candle.high),
        low: Number(candle.low),
        close: Number(candle.close),
      };
    })
    .filter(Boolean);

const calculateSMA = (candles, period) => {
  if (!candles || candles.length < period) {
    return [];
  }

  const result = [];
  let sum = 0;
  const queue = [];

  candles.forEach((point) => {
    const close = point.close;
    queue.push(close);
    sum += close;

    if (queue.length > period) {
      sum -= queue.shift();
    }

    if (queue.length === period) {
      result.push({
        time: point.time,
        value: sum / period,
      });
    }
  });

  return result;
};

const calculateEMA = (candles, period) => {
  if (!candles || candles.length < period) {
    return [];
  }

  const multiplier = 2 / (period + 1);
  const initialSlice = candles.slice(0, period);
  let ema = initialSlice.reduce((acc, point) => acc + point.close, 0) / period;
  const result = [];

  result.push({
    time: candles[period - 1].time,
    value: ema,
  });

  for (let i = period; i < candles.length; i += 1) {
    const close = candles[i].close;
    ema = close * multiplier + ema * (1 - multiplier);
    result.push({
      time: candles[i].time,
      value: ema,
    });
  }

  return result;
};

const calculateRSI = (candles, period = 14) => {
  if (!candles || candles.length < period + 1) {
    return [];
  }

  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i += 1) {
    const delta = candles[i].close - candles[i - 1].close;
    if (delta >= 0) {
      gains += delta;
    } else {
      losses += Math.abs(delta);
    }
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  const computeValue = (gain, loss) => {
    if (loss === 0) {
      return 100;
    }
    const rs = gain / loss;
    return 100 - 100 / (1 + rs);
  };

  const result = [];
  result.push({
    time: candles[period].time,
    value: computeValue(avgGain, avgLoss),
  });

  for (let i = period + 1; i < candles.length; i += 1) {
    const delta = candles[i].close - candles[i - 1].close;
    const gain = delta > 0 ? delta : 0;
    const loss = delta < 0 ? Math.abs(delta) : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
    result.push({
      time: candles[i].time,
      value: computeValue(avgGain, avgLoss),
    });
  }

  return result;
};

const calculateBollingerBands = (candles, period = 20, multiplier = 2) => {
  if (!candles || candles.length < period) {
    return null;
  }

  const result = {
    upper: [],
    middle: [],
    lower: [],
  };

  for (let i = period - 1; i < candles.length; i += 1) {
    const window = candles.slice(i - period + 1, i + 1);
    const mean = window.reduce((sum, point) => sum + point.close, 0) / period;
    const variance = window.reduce((sum, point) => sum + (point.close - mean) ** 2, 0) / period;
    const stdDev = Math.sqrt(variance);
    const time = candles[i].time;

    result.upper.push({ time, value: mean + stdDev * multiplier });
    result.middle.push({ time, value: mean });
    result.lower.push({ time, value: mean - stdDev * multiplier });
  }

  return result;
};

const INDICATOR_DEFINITIONS = [
  {
    key: 'sma20',
    label: 'SMA (20)',
    description: '20-period simple moving average',
    compute: (candles) => calculateSMA(candles, 20),
    seriesOptions: {
      color: '#22d3ee',
      lineWidth: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    },
  },
  {
    key: 'ema50',
    label: 'EMA (50)',
    description: '50-period exponential moving average',
    compute: (candles) => calculateEMA(candles, 50),
    seriesOptions: {
      color: '#f97316',
      lineWidth: 2,
      lineStyle: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    },
  },
  {
    key: 'bollinger',
    label: 'Bollinger Bands (20, 2)',
    description: 'Upper / middle / lower volatility bands',
    compute: (candles) => calculateBollingerBands(candles, 20, 2),
    seriesOptions: {
      upper: {
        color: '#a855f7',
        lineWidth: 1,
        lineStyle: 2,
        lastValueVisible: false,
        priceLineVisible: false,
      },
      middle: {
        color: '#facc15',
        lineWidth: 1,
        lineStyle: 0,
        lastValueVisible: false,
        priceLineVisible: false,
      },
      lower: {
        color: '#a855f7',
        lineWidth: 1,
        lineStyle: 2,
        lastValueVisible: false,
        priceLineVisible: false,
      },
    },
    isBand: true,
  },
  {
    key: 'rsi14',
    label: 'RSI (14)',
    description: 'Relative strength index (0-100)',
    compute: (candles) => calculateRSI(candles, 14),
    seriesOptions: {
      color: '#0ea5e9',
      lineWidth: 1,
      lineStyle: 1,
      lastValueVisible: false,
      priceLineVisible: false,
    },
  },
];

const ChartIndicators = ({
  chartRef,
  symbol = DEFAULT_SYMBOL,
  timeframe = DEFAULT_TIMEFRAME,
  limit = DEFAULT_LIMIT,
}) => {
  const [selectedIndicators, setSelectedIndicators] = useState(() =>
    INDICATOR_DEFINITIONS.reduce((acc, indicator) => {
      acc[indicator.key] = false;
      return acc;
    }, {})
  );
  const [candles, setCandles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const seriesMapRef = useRef({});
  const abortControllerRef = useRef(null);

  const toggleIndicator = useCallback((key) => {
    setSelectedIndicators((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }, []);

  const removeIndicatorSeries = useCallback((key) => {
    const chart = chartRef?.current;
    const existing = seriesMapRef.current[key];

    if (!existing) {
      return;
    }

    if (!chart) {
      delete seriesMapRef.current[key];
      return;
    }

    if (existing.series) {
      chart.removeSeries(existing.series);
    } else {
      Object.values(existing).forEach((series) => {
        chart.removeSeries(series);
      });
    }

    delete seriesMapRef.current[key];
  }, [chartRef]);

  const updateIndicatorSeries = useCallback(
    (indicator, data) => {
      const chart = chartRef?.current;
      if (!chart) {
        return;
      }

      if (indicator.isBand) {
        const bandData = data || {};
        const { upper, middle, lower } = bandData;
        if (!upper?.length || !middle?.length || !lower?.length) {
          removeIndicatorSeries(indicator.key);
          return;
        }

        const existing = seriesMapRef.current[indicator.key];
        if (existing) {
          existing.upper.setData(upper);
          existing.middle.setData(middle);
          existing.lower.setData(lower);
          return;
        }

        const upperSeries = chart.addLineSeries(indicator.seriesOptions.upper);
        const middleSeries = chart.addLineSeries(indicator.seriesOptions.middle);
        const lowerSeries = chart.addLineSeries(indicator.seriesOptions.lower);

        upperSeries.setData(upper);
        middleSeries.setData(middle);
        lowerSeries.setData(lower);

        seriesMapRef.current[indicator.key] = {
          upper: upperSeries,
          middle: middleSeries,
          lower: lowerSeries,
        };
        return;
      }

      if (!Array.isArray(data) || !data.length) {
        removeIndicatorSeries(indicator.key);
        return;
      }

      const existing = seriesMapRef.current[indicator.key];
      if (existing?.series) {
        existing.series.setData(data);
        return;
      }

      const lineSeries = chart.addLineSeries(indicator.seriesOptions);
      lineSeries.setData(data);
      seriesMapRef.current[indicator.key] = { series: lineSeries };
    },
    [chartRef, removeIndicatorSeries]
  );

  useEffect(() => {
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const loadCandles = async () => {
      setLoading(true);
      setError('');

      try {
        const response = await api.get(
          `/api/market/ohlc/${encodeURIComponent(symbol)}`,
          {
            params: {
              interval: timeframe,
              limit,
            },
            signal: controller.signal,
          }
        );

        const normalized = normalizeCandles(response.data?.candles || []);
        if (!normalized.length) {
          throw new Error('No candle data available for indicators');
        }

        const sorted = [...normalized].sort((a, b) => a.time - b.time);
        setCandles(sorted);
      } catch (err) {
        if (err.name === 'CanceledError') {
          return;
        }
        const message = err?.response?.data?.detail || err?.message || 'Unable to load indicator data';
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    loadCandles();

    return () => {
      controller.abort();
    };
  }, [symbol, timeframe, limit]);

  useEffect(() => {
    if (!candles.length || !chartRef?.current) {
      return;
    }

    INDICATOR_DEFINITIONS.forEach((indicator) => {
      if (!selectedIndicators[indicator.key]) {
        removeIndicatorSeries(indicator.key);
        return;
      }

      let data;
      try {
        data = indicator.compute(candles);
      } catch (err) {
        console.error('Indicator calculation failed', err);
        removeIndicatorSeries(indicator.key);
        return;
      }

      updateIndicatorSeries(indicator, data);
    });
  }, [candles, selectedIndicators, chartRef, removeIndicatorSeries, updateIndicatorSeries]);

  useEffect(() => {
    const chart = chartRef?.current;
    return () => {
      if (!chart) {
        seriesMapRef.current = {};
        return;
      }

      Object.values(seriesMapRef.current).forEach((entry) => {
        if (entry.series) {
          chart.removeSeries(entry.series);
        } else {
          Object.values(entry).forEach((series) => chart.removeSeries(series));
        }
      });

      seriesMapRef.current = {};
    };
  }, [chartRef]);

  const renderedIndicators = useMemo(() => INDICATOR_DEFINITIONS, []);

  return (
    <div className="hidden max-w-md flex-col gap-3 rounded-2xl border border-gray-800 bg-gray-900/70 p-4 text-xs text-gray-200 shadow-sm lg:flex">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-white">Chart indicators</p>
          <p className="text-[11px] text-gray-400">
            {symbol} · {timeframe} · {limit} candles
          </p>
        </div>
        {loading && <span className="text-[11px] text-gray-400">Loading data…</span>}
      </div>

      {error && (
        <div className="rounded-lg border border-rose-200/40 bg-rose-900/40 p-2 text-[11px] text-rose-200">
          {error}
        </div>
      )}

      <div className="grid gap-2">
        {renderedIndicators.map((indicator) => (
          <label
            key={indicator.key}
            className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-gray-800 bg-gray-900/50 px-3 py-2 transition hover:border-gray-600"
          >
            <div>
              <p className="text-sm font-medium text-white">{indicator.label}</p>
              <p className="text-[11px] text-gray-400">{indicator.description}</p>
            </div>
            <input
              type="checkbox"
              checked={selectedIndicators[indicator.key]}
              onChange={() => toggleIndicator(indicator.key)}
              className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-sky-500 focus:ring-sky-500"
            />
          </label>
        ))}
      </div>
    </div>
  );
};

export default ChartIndicators;
