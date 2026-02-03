import React, { useEffect, useRef, useState } from 'react';
import { createChart } from 'lightweight-charts';
import api from '../services/api';

const TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];
const DEFAULT_SYMBOL = 'BTC/USD';

const normalizeCandles = (entries) =>
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
    .filter(Boolean); // remove invalid entries

const buildWebSocketUrl = (symbol) => {
  const baseUrl = import.meta.env.VITE_API_URL || window.location.origin;
  const url = new URL(baseUrl);
  const scheme = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${url.host}/api/market/stream/ohlc?symbol=${encodeURIComponent(symbol)}`;
};

const formatLastUpdate = (date) =>
  date ? date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : 'n/a';

const Chart = ({ symbol = DEFAULT_SYMBOL }) => {
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const timeframeRef = useRef('1m');

  const [timeframe, setTimeframe] = useState('1m');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [lastUpdate, setLastUpdate] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState('connecting');

  useEffect(() => {
    timeframeRef.current = timeframe;
  }, [timeframe]);

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) {
      return undefined;
    }

    const chart = createChart(container, {
      layout: {
        background: { color: '#0f172a' },
        textColor: '#f8fafc',
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      crosshair: {
        mode: 1,
      },
      rightPriceScale: {
        borderColor: '#1f2937',
      },
      timeScale: {
        borderColor: '#1f2937',
        timeVisible: true,
      },
      localization: {
        locale: 'en-US',
      },
    });

    chartRef.current = chart;
    seriesRef.current = chart.addCandlestickSeries({
      upColor: '#22c55e',
      downColor: '#e11d48',
      wickVisible: true,
      borderVisible: false,
      priceLineVisible: false,
    });

    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    }) : null;

    if (resizeObserver) {
      resizeObserver.observe(container);
    }

    return () => {
      resizeObserver?.disconnect();
      chart.remove();
    };
  }, []);

  useEffect(() => {
    let active = true;

    const loadCandles = async () => {
      setLoading(true);
      setError('');

      try {
        const response = await api.get(`/api/market/ohlc/${encodeURIComponent(symbol)}`, {
          params: {
            interval: timeframe,
            limit: 400,
          },
        });

        if (!active) {
          return;
        }

        const normalized = normalizeCandles(response.data.candles);
        if (!normalized.length) {
          throw new Error('No candle data returned');
        }

        const sorted = [...normalized].sort((a, b) => a.time - b.time);
        seriesRef.current?.setData(sorted);
        chartRef.current?.timeScale().setVisibleRange({
          from: sorted[0].time,
          to: sorted[sorted.length - 1].time,
        });

        setLastUpdate(new Date(sorted[sorted.length - 1].time * 1000));
      } catch (err) {
        const message = err?.response?.data?.detail || err?.message || 'Unable to load candles';
        if (active) {
          setError(message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadCandles();

    return () => {
      active = false;
    };
  }, [symbol, timeframe]);

  useEffect(() => {
    let socket;
    let reconnectTimer;
    let cancelled = false;

    const connect = () => {
      if (cancelled) {
        return;
      }

      setConnectionStatus('connecting');

      const wsUrl = buildWebSocketUrl(symbol);
      try {
        socket = new WebSocket(wsUrl);
      } catch (_err) {
        setConnectionStatus('disconnected');
        setError('Live stream unavailable');
        return;
      }

      socket.onopen = () => {
        if (cancelled) {
          return;
        }
        setConnectionStatus('connected');
      };

      socket.onmessage = (event) => {
        if (cancelled) {
          return;
        }

        try {
          const payload = JSON.parse(event.data);
          if (payload?.type !== 'ohlc' || payload?.data?.symbol !== symbol) {
            return;
          }

          const updatedTime = Date.parse(payload.data.timestamp);
          if (Number.isNaN(updatedTime)) {
            return;
          }

          const candle = {
            time: Math.floor(updatedTime / 1000),
            open: Number(payload.data.open),
            high: Number(payload.data.high),
            low: Number(payload.data.low),
            close: Number(payload.data.close),
          };

          // Only update if it matches current timeframe (Kraken WS OHLC is usually 1m)
          // For now we assume backend sends 1m updates
          if (timeframeRef.current === '1m') {
            seriesRef.current?.update(candle);
          }
          setLastUpdate(new Date(candle.time * 1000));
        } catch (_err) {
          // ignore malformed websocket payloads
        }
      };

      socket.onerror = () => {
        if (cancelled) {
          return;
        }
        setError('Live stream disconnected');
      };

      socket.onclose = () => {
        if (cancelled) {
          return;
        }
        setConnectionStatus('disconnected');
        reconnectTimer = window.setTimeout(connect, 5000);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [symbol]);

  const statusLabel = {
    connected: 'Live',
    connecting: 'Connecting',
    disconnected: 'Offline',
  }[connectionStatus];

  const statusColor = {
    connected: 'text-emerald-400',
    connecting: 'text-amber-400',
    disconnected: 'text-gray-400',
  }[connectionStatus];

  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-900/80 shadow-lg">
      <div className="flex items-center justify-between space-x-4 border-b border-gray-800 px-5 py-4">
        <div>
          <p className="text-xs uppercase tracking-widest text-gray-500">Live candlestick chart</p>
          <p className="text-lg font-semibold text-white">{symbol}</p>
        </div>
        <div className="text-right">
          <p className={`text-sm font-semibold ${statusColor}`}>{statusLabel}</p>
          <p className="text-xs text-gray-400">Updated {formatLastUpdate(lastUpdate)}</p>
        </div>
      </div>

      <div className="px-5 py-4">
        <div className="flex flex-wrap gap-2">
          {TIMEFRAME_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setTimeframe(option)}
              className={`rounded-full px-3 py-1.5 text-sm font-medium transition ${
                timeframe === option
                  ? 'bg-blue-600 text-white'
                  : 'bg-white/5 text-gray-200 hover:bg-white/10'
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      <div className="relative h-[420px] px-5 pb-5">
        <div ref={chartContainerRef} className="h-full w-full rounded-xl bg-slate-900" />

        {loading && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-gray-900/70 text-sm font-medium text-gray-300">
            Loading candles…
          </div>
        )}

        {error && (
          <div className="absolute left-4 bottom-4 right-4 rounded-lg bg-red-900/80 p-3 text-xs text-red-200">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};

export default Chart;
