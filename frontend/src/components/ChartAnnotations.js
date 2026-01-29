import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';

const DEFAULT_SYMBOL = 'BTC/USD';
const DEFAULT_TIMEFRAME = '1m';
const DEFAULT_LIMIT = 400;

const INITIAL_LAYER_STATE = {
  supportResistance: true,
  patterns: true,
  entry: true,
  exit: true,
};

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

const computeSupportResistanceLevels = (candles) => {
  if (candles.length < 6) {
    return {
      support: [],
      resistance: [],
    };
  }

  const supportCandidates = [];
  const resistanceCandidates = [];

  for (let i = 2; i < candles.length - 2; i += 1) {
    const window = candles.slice(i - 2, i + 3);
    const highs = window.map((entry) => entry.high);
    const lows = window.map((entry) => entry.low);
    const current = candles[i];

    if (current.low <= Math.min(...lows)) {
      supportCandidates.push(current.low);
    }

    if (current.high >= Math.max(...highs)) {
      resistanceCandidates.push(current.high);
    }
  }

  const dedupeLevels = (values, ascending = true) => {
    const seen = new Set();
    const sorted = [...values].sort((a, b) => (ascending ? a - b : b - a));
    return sorted.filter((level) => {
      const chroma = level.toFixed(2);
      if (seen.has(chroma)) {
        return false;
      }
      seen.add(chroma);
      return true;
    });
  };

  const supports = dedupeLevels(supportCandidates, true).slice(-3);
  const resistances = dedupeLevels(resistanceCandidates, false).slice(-3);

  const lastClose = candles[candles.length - 1].close;
  const lastHigh = candles[candles.length - 1].high;
  const lastLow = candles[candles.length - 1].low;

  if (!supports.length) {
    supports.push(Math.max(lastLow, lastClose * 0.98));
  }

  if (!resistances.length) {
    resistances.push(Math.min(lastHigh, lastClose * 1.02));
  }

  return {
    support: supports,
    resistance: resistances,
  };
};

const findLocalExtrema = (candles, type = 'peak') => {
  const points = [];
  if (candles.length < 6) {
    return points;
  }

  for (let i = 2; i < candles.length - 2; i += 1) {
    const sample = candles.slice(i - 2, i + 3);
    const current = candles[i];
    if (type === 'peak') {
      if (sample.every((entry) => current.high >= entry.high)) {
        points.push({ time: current.time, value: current.high });
      }
    } else if (type === 'trough') {
      if (sample.every((entry) => current.low <= entry.low)) {
        points.push({ time: current.time, value: current.low });
      }
    }
  }

  return points;
};

const detectPatterns = (candles, symbol = '') => {
  const patterns = [];
  const clamp = (value, minimum) => Math.max(value, minimum || 0);
  if (candles.length < 8) {
    return patterns;
  }

  const peaks = findLocalExtrema(candles, 'peak');
  const troughs = findLocalExtrema(candles, 'trough');
  const threshold = 0.015;

  const capturePairedPoints = (points) => {
    for (let i = points.length - 2; i >= 0; i -= 1) {
      const first = points[i];
      const second = points[i + 1];
      const avg = (first.value + second.value) / 2;
      const diff = Math.abs(first.value - second.value) / avg;
      if (diff < threshold) {
        return { first, second, avg };
      }
    }
    return null;
  };

  const lastClose = candles[candles.length - 1].close;
  const candleRange = candles[candles.length - 1].high - candles[candles.length - 1].low;
  const minimumRange = clamp(candleRange * 0.25, 0.25);

  const doubleTop = capturePairedPoints(peaks);
  if (doubleTop) {
    const zoneLow = clamp(lastClose * 0.98, 0);
    const zoneHigh = doubleTop.avg;
    patterns.push({
      id: `double-top-${doubleTop.first.time}`,
      label: 'Double top resistance',
      type: 'double-top',
      high: zoneHigh,
      low: Math.max(zoneLow, zoneHigh - minimumRange),
      start: Math.max(doubleTop.first.time - 120, candles[0].time),
      end: Math.min(doubleTop.second.time + 120, candles[candles.length - 1].time),
      detail: `${symbol || 'Market'} tested ${zoneHigh.toFixed(2)} twice, watching for rejection.`,
    });
  }

  const doubleBottom = capturePairedPoints(troughs);
  if (doubleBottom) {
    const zoneLow = doubleBottom.avg;
    const zoneHigh = zoneLow + minimumRange;
    patterns.push({
      id: `double-bottom-${doubleBottom.first.time}`,
      label: 'Double bottom support',
      type: 'double-bottom',
      high: Math.min(zoneHigh, lastClose * 1.02),
      low: zoneLow,
      start: Math.max(doubleBottom.first.time - 120, candles[0].time),
      end: Math.min(doubleBottom.second.time + 120, candles[candles.length - 1].time),
      detail: `${symbol || 'Market'} found support near ${zoneLow.toFixed(2)} twice.`,
    });
  }

  return patterns;
};

const computeEntryExitZones = (candles) => {
  if (!candles.length) {
    return null;
  }

  const last = candles[candles.length - 1];
  const previous = candles[candles.length - 2] || last;
  const volatility = Math.max(Math.abs(last.close - previous.close), last.close * 0.005);
  const trendUp = last.close >= previous.close;
  const entryCenter = last.close - (trendUp ? volatility * 0.35 : -volatility * 0.35);
  const entryLow = entryCenter - volatility * 0.4;
  const entryHigh = entryCenter + volatility * 0.4;
  const exitLow = last.close + (trendUp ? volatility * 0.6 : -volatility * 0.6);
  const exitHigh = last.close + (trendUp ? volatility * 1.2 : -volatility * 1.2);
  const timeStep = Math.max(60, last.time - (previous.time || last.time));
  const start = Math.max(last.time - timeStep * 4, candles[0].time);
  const end = last.time + timeStep * 2;

  return {
    entryZone: {
      low: Number(entryLow.toFixed(4)),
      high: Number(entryHigh.toFixed(4)),
      start,
      end,
    },
    exitZone: {
      low: Number(exitLow.toFixed(4)),
      high: Number(exitHigh.toFixed(4)),
      start,
      end,
    },
  };
};

const buildLineSeries = (chart, options, data) => {
  const series = chart.addLineSeries({
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crossHairMarkerVisible: false,
    ...options,
  });
  if (data?.length) {
    series.setData(data);
  }
  return series;
};

const ChartAnnotations = ({
  chartRef,
  symbol = DEFAULT_SYMBOL,
  timeframe = DEFAULT_TIMEFRAME,
  limit = DEFAULT_LIMIT,
}) => {
  const [selectedLayers, setSelectedLayers] = useState(INITIAL_LAYER_STATE);
  const [candles, setCandles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const layersRef = useRef({
    support: [],
    resistance: [],
    patterns: [],
    entry: [],
    exit: [],
  });
  const abortControllerRef = useRef(null);

  const patternZones = useMemo(() => detectPatterns(candles, symbol), [candles, symbol]);
  const entryExitZones = useMemo(() => computeEntryExitZones(candles), [candles]);

  const toggleLayer = useCallback((key) => {
    setSelectedLayers((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  }, []);

  const clearLayerSeries = useCallback(
    (layerKey) => {
      const chart = chartRef?.current;
      const existing = layersRef.current[layerKey];
      if (!existing?.length) {
        layersRef.current[layerKey] = [];
        return;
      }
      if (!chart) {
        layersRef.current[layerKey] = [];
        return;
      }
      existing.forEach((series) => {
        try {
          chart.removeSeries(series);
        } catch (err) {
          // ignore removal errors
        }
      });
      layersRef.current[layerKey] = [];
    },
    [chartRef]
  );

  useEffect(() => {
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setLoading(true);
    setError('');

    const loadCandles = async () => {
      try {
        const response = await api.get(`/api/market/ohlc/${encodeURIComponent(symbol)}`, {
          params: {
            interval: timeframe,
            limit,
          },
          signal: controller.signal,
        });

        const normalized = normalizeCandles(response.data?.candles || []);
        if (!normalized.length) {
          throw new Error('No candle data returned for annotations');
        }

        const sorted = [...normalized].sort((a, b) => a.time - b.time);
        setCandles(sorted);
      } catch (err) {
        if (err.name === 'CanceledError') {
          return;
        }
        const message = err?.response?.data?.detail || err?.message || 'Unable to load annotation data';
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    loadCandles();

    return () => {
      controller.abort();
      abortControllerRef.current = null;
    };
  }, [symbol, timeframe, limit]);

  useEffect(() => {
    const chart = chartRef?.current;
    if (!chart || !candles.length) {
      return undefined;
    }

    const startTime = candles[0].time;
    const endTime = Math.max(candles[candles.length - 1].time, startTime + 1);

    const { support, resistance } = computeSupportResistanceLevels(candles);

    const drawLines = (values, layerKey, color, lineStyle = 2) => {
      clearLayerSeries(layerKey);
      const layerFlag = layerKey === 'support' || layerKey === 'resistance' ? 'supportResistance' : layerKey;
      if (!values.length || !selectedLayers[layerFlag]) {
        return;
      }
      const seriesList = [];
      values.forEach((level) => {
        if (!Number.isFinite(level)) {
          return;
        }
        const series = buildLineSeries(chart, {
          color,
          lineStyle,
        }, [
          { time: startTime, value: level },
          { time: endTime, value: level },
        ]);
        seriesList.push(series);
      });
      layersRef.current[layerKey] = seriesList;
    };

    drawLines(support, 'support', '#0ea5e9', 2);
    drawLines(resistance, 'resistance', '#f97316', 3);

    if (selectedLayers.patterns && patternZones.length) {
      clearLayerSeries('patterns');
      const patternSeries = [];
      patternZones.forEach((pattern) => {
        const zoneStart = Math.max(pattern.start, startTime);
        const zoneEnd = Math.min(pattern.end, endTime);
        [pattern.high, pattern.low].forEach((value) => {
          if (!Number.isFinite(value)) {
            return;
          }
          const series = buildLineSeries(chart, {
            color: pattern.type === 'double-top' ? '#f59e0b' : '#10b981',
            lineStyle: 1,
          }, [
            { time: zoneStart, value },
            { time: zoneEnd, value },
          ]);
          patternSeries.push(series);
        });
      });
      layersRef.current.patterns = patternSeries;
    } else {
      clearLayerSeries('patterns');
    }

    const drawZone = (zone, layerKey, color) => {
      clearLayerSeries(layerKey);
      if (!zone || !selectedLayers[layerKey]) {
        return;
      }
      const zoneStart = Math.max(zone.start, startTime);
      const zoneEnd = Math.min(zone.end, endTime);
      const seriesList = [];
      [zone.high, zone.low].forEach((value, index) => {
        const series = buildLineSeries(chart, {
          color,
          lineStyle: index === 0 ? 0 : 1,
        }, [
          { time: zoneStart, value },
          { time: zoneEnd, value },
        ]);
        seriesList.push(series);
      });
      layersRef.current[layerKey] = seriesList;
    };

    drawZone(entryExitZones?.entryZone, 'entry', '#8b5cf6');
    drawZone(entryExitZones?.exitZone, 'exit', '#ec4899');

    return undefined;
  }, [chartRef, candles, selectedLayers, patternZones, entryExitZones, clearLayerSeries]);

  useEffect(() => {
    return () => {
      const chart = chartRef?.current;
      if (!chart) {
        layersRef.current = {
          support: [],
          resistance: [],
          patterns: [],
          entry: [],
          exit: [],
        };
        return;
      }
      Object.keys(layersRef.current).forEach((key) => {
        layersRef.current[key].forEach((series) => {
          try {
            chart.removeSeries(series);
          } catch (err) {
            // swallow cleanup errors
          }
        });
        layersRef.current[key] = [];
      });
    };
  }, [chartRef]);

  const layerOptions = [
    {
      key: 'supportResistance',
      label: 'Support / Resistance',
      description: 'Swing levels the AI watches for rejections or breakouts.',
    },
    {
      key: 'patterns',
      label: 'AI patterns',
      description: 'Double tops / bottoms detected from recent candles.',
    },
    {
      key: 'entry',
      label: 'Entry zone',
      description: 'Suggested pullback corridor before next buy signal.',
    },
    {
      key: 'exit',
      label: 'Exit zone',
      description: 'AI exit targets and trim areas.',
    },
  ];

  return (
    <div className="max-w-sm rounded-2xl border border-gray-800 bg-gray-900/80 p-4 text-xs text-gray-200 shadow-lg backdrop-blur">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-white">AI annotations</p>
          <p className="text-[11px] text-gray-400">
            {symbol} · {timeframe} · {Math.max(candles.length, 0)} candles
          </p>
        </div>
        {loading && <span className="text-[11px] text-gray-400">Updating…</span>}
      </div>

      {error && (
        <div className="mt-3 rounded-xl border border-rose-500/30 bg-rose-900/40 p-2 text-[11px] text-rose-200">
          {error}
        </div>
      )}

      <div className="mt-3 grid gap-2">
        {layerOptions.map((option) => (
          <label
            key={option.key}
            className="flex cursor-pointer items-start justify-between rounded-xl border border-gray-800 bg-gradient-to-br from-gray-900/60 to-black/40 px-3 py-2 transition hover:border-gray-600"
          >
            <div>
              <p className="text-sm font-medium text-white">{option.label}</p>
              <p className="text-[11px] text-gray-400">{option.description}</p>
            </div>
            <input
              type="checkbox"
              checked={!!selectedLayers[option.key]}
              onChange={() => toggleLayer(option.key)}
              className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-indigo-400 focus:ring-indigo-400"
            />
          </label>
        ))}
      </div>

      <div className="mt-4 space-y-2 rounded-2xl border border-dashed border-gray-700/60 bg-gray-900/50 p-3 text-[11px] text-gray-400">
        {patternZones.length ? (
          patternZones.map((pattern) => (
            <div key={pattern.id} className="space-y-0.5">
              <p className="text-[10px] uppercase tracking-[0.3em] text-blue-300">{pattern.label}</p>
              <p className="text-sm text-white">{pattern.detail}</p>
              <p className="text-[10px] text-gray-400">
                {pattern.low.toFixed(2)} – {pattern.high.toFixed(2)}
              </p>
            </div>
          ))
        ) : (
          <p>No stable patterns detected yet.</p>
        )}
      </div>
    </div>
  );
};

export default ChartAnnotations;
