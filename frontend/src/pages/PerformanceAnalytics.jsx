import React, { useState, useEffect } from 'react';
import PerformanceSummary from '../components/analytics/PerformanceSummary';
import EquityCurveChart from '../components/analytics/EquityCurveChart';
import TradeHistoryTable from '../components/analytics/TradeHistoryTable';
import { performanceAPI } from '../services/api';

const PerformanceAnalytics = () => {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const response = await performanceAPI.summary();
        setSummary(response.data);
      } catch (err) {
        console.error('Failed to fetch summary for alpha badge:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();

    // SSE for alpha badge updates
    const eventSource = new EventSource(performanceAPI.streamURL, { withCredentials: true });
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.alpha !== undefined) {
          setSummary(prev => ({ ...prev, alpha: data.alpha }));
        }
      } catch (err) {
        console.error('Failed to parse SSE for alpha badge:', err);
      }
    };

    return () => eventSource.close();
  }, []);

  const alpha = summary?.alpha || 0;
  const alphaColor = alpha >= 0 ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50' : 'bg-rose-500/20 text-rose-400 border-rose-500/50';

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.4em] text-sky-400">Phase 08 · Performance</p>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold text-white">Performance Analytics</h1>
            {!loading && (
              <div className={`px-3 py-1 rounded-full border text-sm font-bold ${alphaColor}`}>
                Alpha: {alpha >= 0 ? '+' : ''}{(alpha * 100).toFixed(2)}%
              </div>
            )}
          </div>
          <p className="max-w-3xl text-sm text-gray-300">
            Comprehensive breakdown of your trading strategy's performance, risk metrics, and historical growth.
          </p>
        </div>
      </header>

      <PerformanceSummary initialData={summary} />

      <div className="grid gap-6 lg:grid-cols-1">
        <EquityCurveChart />
      </div>

      <div className="grid gap-6 lg:grid-cols-1">
        <TradeHistoryTable />
      </div>
    </div>
  );
};

export default PerformanceAnalytics;