import React, { useState, useEffect } from 'react';
import { performanceAPI } from '../../services/api';

const STAT_COLOR_MAP = {
  blue: 'bg-blue-500/20 text-blue-300 border-blue-700',
  green: 'bg-emerald-500/20 text-emerald-200 border-emerald-700',
  yellow: 'bg-amber-400/20 text-amber-200 border-amber-600',
  red: 'bg-rose-500/20 text-rose-200 border-rose-600',
  purple: 'bg-purple-500/20 text-purple-300 border-purple-700',
};

const StatCard = ({ title, value, icon, color = 'blue', loading = false }) => {
  const colorClasses = STAT_COLOR_MAP[color] || STAT_COLOR_MAP.blue;
  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-lg shadow-black/40 transition duration-300 hover:-translate-y-1 hover:border-white">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{title}</p>
          <div className="mt-2 h-10 flex items-center">
            {loading ? (
              <span className="h-8 w-24 rounded-full bg-white/10 animate-pulse" />
            ) : (
              <p className="text-2xl font-semibold text-white">{value}</p>
            )}
          </div>
        </div>
        <div
          className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${colorClasses}`}
        >
          {icon}
        </div>
      </div>
    </div>
  );
};

const PerformanceSummary = ({ initialData }) => {
  const [metrics, setMetrics] = useState(initialData || {
    sharpe_ratio: 0,
    win_rate: 0,
    max_drawdown: 0,
    volatility: 0,
    sortino_ratio: 0,
    total_equity: 0,
    cash_balance: 0,
    asset_value: 0
  });
  const [loading, setLoading] = useState(!initialData);

  useEffect(() => {
    let eventSource;

    const fetchSummary = async () => {
      try {
        const response = await performanceAPI.summary();
        setMetrics(response.data);
      } catch (err) {
        console.error('Failed to fetch performance summary:', err);
      } finally {
        setLoading(false);
      }
    };

    if (!initialData) {
      fetchSummary();
    }

    // Set up SSE listener
    eventSource = new EventSource(performanceAPI.streamURL, { withCredentials: true });
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setMetrics(prev => ({ ...prev, ...data }));
      } catch (err) {
        console.error('Failed to parse performance SSE data:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('Performance SSE error:', err);
      eventSource.close();
    };

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [initialData]);

  const formatPercent = (val) => `${(val * 100).toFixed(2)}%`;
  const formatValue = (val) => val.toFixed(2);

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatCard
        title="Sharpe Ratio"
        value={formatValue(metrics.sharpe_ratio || 0)}
        color="blue"
        loading={loading}
        icon={
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
          </svg>
        }
      />
      <StatCard
        title="Win Rate"
        value={formatPercent(metrics.win_rate || 0)}
        color="green"
        loading={loading}
        icon={
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
      />
      <StatCard
        title="Max Drawdown"
        value={formatPercent(metrics.max_drawdown || 0)}
        color="red"
        loading={loading}
        icon={
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 17h8m0 0V9m0 8l-8-8-4 4-6-6" />
          </svg>
        }
      />
      <StatCard
        title="Volatility"
        value={formatPercent(metrics.volatility || 0)}
        color="yellow"
        loading={loading}
        icon={
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
      />
    </div>
  );
};

export default PerformanceSummary;
