import React, { useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const metricList = [
  { key: 'strategy_count', label: 'Strategies tracked' },
  { key: 'total_trades', label: 'Trades executed' },
  { key: 'winning_trades', label: 'Winning trades' },
  { key: 'losing_trades', label: 'Losing trades' },
  { key: 'average_win_rate', label: 'Avg win rate', formatter: (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return '—';
    }
    const normalized = Number(value) * 100;
    return `${normalized.toFixed(1)}%`;
  } },
  { key: 'total_pnl', label: 'Total PnL', formatter: (value) => {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return '—';
    }
    const formatter = new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    const formatted = formatter.format(value);
    return value >= 0 ? `+${formatted}` : formatted;
  } },
];

const formatTimestamp = (value) => {
  if (!value) {
    return 'unknown';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const normalizeProviderLabel = (provider) => {
  if (!provider) {
    return 'Unknown provider';
  }
  return provider.toUpperCase();
};

const computeMetricValue = (entry, definition) => {
  if (!entry) {
    return '—';
  }
  const raw = entry[definition.key];
  if (definition.formatter) {
    return definition.formatter(raw);
  }
  if (raw === null || raw === undefined || Number.isNaN(Number(raw))) {
    return '—';
  }
  return Number(raw).toLocaleString('en-US');
};

const ModelComparison = () => {
  const [comparisons, setComparisons] = useState([]);
  const [primaryModel, setPrimaryModel] = useState('');
  const [secondaryModel, setSecondaryModel] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState('');

  useEffect(() => {
    let active = true;

    const loadComparisonData = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await api.get('/api/ai/models/comparison');
        const fetched = response.data?.comparisons ?? [];
        if (!active) {
          return;
        }
        setComparisons(fetched);
        setUpdatedAt(new Date().toISOString());
      } catch (err) {
        if (!active) {
          return;
        }
        console.error('Unable to load model comparison data', err);
        setError(err.message || 'Unable to load model comparison data.');
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadComparisonData();
    const refresh = setInterval(loadComparisonData, 60_000);
    return () => {
      active = false;
      clearInterval(refresh);
    };
  }, []);

  useEffect(() => {
    if (!comparisons.length) {
      setPrimaryModel('');
      return;
    }
    setPrimaryModel((previous) => {
      if (previous && comparisons.some((entry) => entry.model === previous)) {
        return previous;
      }
      return comparisons[0].model;
    });
  }, [comparisons]);

  useEffect(() => {
    if (!comparisons.length) {
      setSecondaryModel('');
      return;
    }
    setSecondaryModel((previous) => {
      if (previous && comparisons.some((entry) => entry.model === previous)) {
        return previous;
      }
      const baseline = primaryModel || comparisons[0].model;
      const fallback = comparisons.find((entry) => entry.model !== baseline);
      return fallback?.model ?? baseline ?? '';
    });
  }, [comparisons, primaryModel]);

  const comparisonOptions = useMemo(
    () =>
      comparisons.map((entry) => ({
        value: entry.model,
        label: `${normalizeProviderLabel(entry.provider)} · ${entry.model}`,
        disabled: !entry.available,
      })),
    [comparisons],
  );

  const primaryEntry = useMemo(
    () => comparisons.find((entry) => entry.model === primaryModel),
    [comparisons, primaryModel],
  );
  const secondaryEntry = useMemo(
    () => comparisons.find((entry) => entry.model === secondaryModel),
    [comparisons, secondaryModel],
  );

const deltaPnl = primaryEntry && secondaryEntry
  ? primaryEntry.total_pnl - secondaryEntry.total_pnl
  : null;


const renderComparisonCard = (entry, label, loadingState) => {
  const ready = Boolean(entry);
  return (
    <div
      className="relative flex flex-col gap-4 rounded-[28px] border border-gray-800 bg-slate-950/60 p-5 shadow-2xl shadow-black/60 transition duration-300 motion-safe:hover:-translate-y-1"
      aria-live="polite"
      aria-busy={!ready}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[0.65rem] uppercase tracking-[0.4em] text-gray-500">{label}</p>
          <h3 className="text-lg font-semibold text-white">
            {entry?.model ?? 'Awaiting data'}
          </h3>
          {entry && (
            <p className="text-xs text-gray-400">
              {normalizeProviderLabel(entry.provider)}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 text-[0.65rem] font-semibold uppercase tracking-[0.3em]">
          {entry?.active && (
            <span className="rounded-full border border-sky-500 px-2 py-0.5 text-sky-200">
              Active
            </span>
          )}
          {entry && (
            <span
              className={`rounded-full border px-2 py-0.5 ${
                entry.available
                  ? 'border-emerald-500 text-emerald-300'
                  : 'border-rose-500 text-rose-300'
              }`}
            >
              {entry.available ? 'Available' : 'Unavailable'}
            </span>
          )}
        </div>
      </div>
      <p className="text-sm text-gray-300">
        {entry?.description ?? 'Select a model to view performance metrics.'}
      </p>
      <div className="space-y-3">
        {metricList.map((metric) => (
          <div
            key={`${label}-${metric.key}`}
            className="flex items-center justify-between border-b border-gray-800 pb-2 text-sm last:border-none"
          >
            <span className="text-xs uppercase tracking-[0.3em] text-gray-400">
              {metric.label}
            </span>
            <span className="text-right text-white">
              {ready ? (
                computeMetricValue(entry, metric)
              ) : (
                <span className="inline-flex h-4 w-16 items-center justify-center rounded-full bg-white/10 text-transparent animate-pulse">
                  &nbsp;
                </span>
              )}
            </span>
          </div>
        ))}
      </div>
      {loadingState && (
        <div className="pointer-events-none absolute inset-0 rounded-[28px] bg-black/60 text-xs uppercase tracking-[0.5em] text-sky-300 backdrop-blur">
          <div className="flex h-full w-full items-center justify-center">
            Refreshing…
          </div>
        </div>
      )}
    </div>
  );
};

  return (
    <section
      className="relative space-y-6 rounded-[32px] border border-gray-800 bg-gradient-to-br from-gray-950/90 to-black/70 p-6 shadow-2xl shadow-black/60 animate-fade-up"
      aria-live="polite"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-sky-400">AI intelligence</p>
          <h2 className="text-2xl font-semibold text-white">Model comparison</h2>
        </div>
        <p className="text-xs text-gray-500">
          {loading ? 'Refreshing…' : `Updated ${formatTimestamp(updatedAt)}`}
        </p>
      </div>
      <div className="grid gap-5 md:grid-cols-2">
        <label className="space-y-2 text-xs uppercase tracking-[0.3em] text-gray-400">
          Primary model
          <div className="relative rounded-[20px] border border-gray-800 bg-slate-900/70 px-3 py-2">
            <select
              className="w-full bg-transparent text-sm font-semibold text-white outline-none"
              value={primaryModel}
              onChange={(event) => setPrimaryModel(event.target.value)}
            >
              {comparisonOptions.map((option) => (
                <option
                  key={option.value}
                  value={option.value}
                  disabled={option.disabled}
                >
                  {option.label}
                  {option.disabled ? ' (offline)' : ''}
                </option>
              ))}
            </select>
          </div>
        </label>
        <label className="space-y-2 text-xs uppercase tracking-[0.3em] text-gray-400">
          Comparator
          <div className="relative rounded-[20px] border border-gray-800 bg-slate-900/70 px-3 py-2">
            <select
              className="w-full bg-transparent text-sm font-semibold text-white outline-none"
              value={secondaryModel}
              onChange={(event) => setSecondaryModel(event.target.value)}
            >
              {comparisonOptions.map((option) => (
                <option
                  key={`secondary-${option.value}`}
                  value={option.value}
                  disabled={option.disabled}
                >
                  {option.label}
                  {option.disabled ? ' (offline)' : ''}
                </option>
              ))}
            </select>
          </div>
        </label>
      </div>
      {error && (
        <p className="text-xs text-rose-300">
          {error} Showing the most recent cached values.
        </p>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        {renderComparisonCard(primaryEntry, 'Primary', loading)}
        {renderComparisonCard(secondaryEntry, 'Comparator', loading)}
      </div>
      {primaryEntry && secondaryEntry && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-[24px] border border-gray-800 bg-gray-950/60 px-4 py-3 text-xs uppercase tracking-[0.3em] text-gray-400">
          <span>Delta PnL</span>
          <span className="text-sm font-semibold text-white">
            {deltaPnl === null ? '—' : deltaPnl >= 0
              ? `+${new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 0,
              }).format(deltaPnl)}`
              : new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 0,
              }).format(deltaPnl)}
          </span>
        </div>
      )}
      {loading && (
        <p className="text-xs text-sky-300">Refreshing comparison data…</p>
      )}
    </section>
  );
};

export default ModelComparison;
