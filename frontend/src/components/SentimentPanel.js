import React, { useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const DEFAULT_SCORE = 48;
const DEFAULT_TREND = 'Monitoring news, social, and chain chatter for the strongest signals.';

const DEFAULT_RECENT = [
  {
    id: 'recent-news-1',
    source: 'News',
    summary: 'Macro regulation chatter softens after calming statements from the EU.',
    score: 61,
    timestamp: '2026-01-30T00:44:00Z',
  },
  {
    id: 'recent-twitter-1',
    source: 'Twitter/X',
    summary: 'Crypto influencers highlight BTC resilience while altcoins lag on volume.',
    score: 54,
    timestamp: '2026-01-30T00:55:00Z',
  },
  {
    id: 'recent-reddit-1',
    source: 'Reddit',
    summary: 'r/CryptoMarkets sees bullish threads around on-chain demand spikes.',
    score: 67,
    timestamp: '2026-01-30T01:02:00Z',
  },
];

const DEFAULT_SOURCES = [
  { id: 'source-news', label: 'News', score: 59, coverage: '8 sources', status: 'healthy' },
  { id: 'source-twitter', label: 'Twitter / X', score: 51, coverage: '120 mentions', status: 'stale' },
  { id: 'source-reddit', label: 'Reddit', score: 64, coverage: '42 mentions', status: 'healthy' },
  { id: 'source-onchain', label: 'On-chain', score: 48, coverage: 'Whale flows', status: 'pending' },
];

const clampSentiment = (value) => {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return 0;
  }
  return Math.max(-100, Math.min(100, numeric));
};

const formatTimestamp = (value) => {
  if (!value) {
    return 'Unknown';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

const buildSentimentLabel = (score) => {
  if (score >= 20) return 'Bullish';
  if (score <= -20) return 'Bearish';
  return 'Neutral';
};

const sourceGradient = (score) => {
  if (score >= 20) {
    return 'from-emerald-400 to-sky-500';
  }
  if (score <= -20) {
    return 'from-rose-500 to-amber-500';
  }
  return 'from-slate-500 to-gray-500';
};

const normalizeRecent = (items = []) => {
  if (!Array.isArray(items) || !items.length) {
    return DEFAULT_RECENT.map((entry) => ({ ...entry }));
  }
  return items.map((entry, index) => ({
    id: entry.id ?? `${entry.source ?? 'recent'}-${index}`,
    source: entry.source ?? entry.platform ?? 'Mixed Data',
    summary: entry.summary ?? entry.description ?? entry.detail ?? 'No additional summary provided.',
    score: clampSentiment(entry.sentiment_score ?? entry.score ?? entry.value ?? DEFAULT_SCORE),
    timestamp: entry.timestamp ?? entry.time ?? new Date().toISOString(),
  }));
};

const normalizeSources = (items = []) => {
  if (!Array.isArray(items) || !items.length) {
    return DEFAULT_SOURCES.map((entry) => ({ ...entry }));
  }
  return items.map((entry, index) => ({
    id: entry.id ?? `${entry.source ?? entry.label ?? 'source'}-${index}`,
    label: entry.label ?? entry.source ?? entry.name ?? 'Source',
    score: clampSentiment(entry.average_score ?? entry.score ?? entry.sentiment_score ?? 0),
    coverage: entry.coverage ?? entry.mentions ?? entry.detail ?? 'Coverage data unavailable',
    status: entry.status ?? entry.health ?? 'unknown',
  }));
};

const SentimentPanel = () => {
  const [score, setScore] = useState(DEFAULT_SCORE);
  const [trend, setTrend] = useState(DEFAULT_TREND);
  const [recent, setRecent] = useState(DEFAULT_RECENT);
  const [sources, setSources] = useState(DEFAULT_SOURCES);
  const [lastUpdated, setLastUpdated] = useState(new Date().toISOString());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const sentimentPercent = useMemo(() => Math.round((clampSentiment(score) + 100) / 2), [score]);
  const sentimentTone = useMemo(() => buildSentimentLabel(score), [score]);

  useEffect(() => {
    let active = true;

    const loadSentiment = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await api.get('/api/sentiment/overview');
        const data = response.data ?? {};
        if (!active) {
          return;
        }
        setScore(clampSentiment(data.current_score ?? data.sentiment_score ?? data.score ?? DEFAULT_SCORE));
        setTrend(data.summary ?? data.trend ?? DEFAULT_TREND);
        setLastUpdated(data.last_updated ?? data.timestamp ?? new Date().toISOString());
        setRecent(normalizeRecent(data.recent ?? data.entries ?? data.data ?? []));
        setSources(normalizeSources(data.sources ?? data.source_breakdown ?? []));
      } catch (err) {
        if (!active) {
          return;
        }
        console.error('Unable to fetch sentiment data', err);
        setError(err.message || 'Unable to refresh sentiment at the moment.');
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadSentiment();
    const refresh = setInterval(loadSentiment, 60_000);
    return () => {
      active = false;
      clearInterval(refresh);
    };
  }, []);

  const sourceSummaryText = useMemo(() => {
    if (loading) {
      return 'Refreshing sources…';
    }
    if (error) {
      return 'Showing cached source health';
    }
    return 'Updated from active listeners';
  }, [loading, error]);

  return (
    <section className="space-y-6 rounded-[32px] border border-gray-800 bg-gradient-to-br from-gray-950/80 to-black/70 p-6 shadow-2xl shadow-black/60">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-sky-400">Sentiment signal</p>
          <h2 className="text-2xl font-semibold text-white">Live sentiment</h2>
        </div>
        <p className="text-xs text-gray-500">Updated {formatTimestamp(lastUpdated)}</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-4 rounded-[28px] border border-slate-800 bg-gray-950/60 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-gray-500">Current score</p>
              <p className="text-5xl font-semibold text-white">{clampSentiment(score)}%</p>
            </div>
            <span className="rounded-full border border-gray-700 px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-gray-300">
              {sentimentTone}
            </span>
          </div>
          <p className="text-sm text-gray-300">{trend}</p>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.3em] text-gray-400">
              <span>Signal strength</span>
              <span>{sentimentPercent}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-gray-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-sky-500 to-indigo-500"
                style={{ width: `${sentimentPercent}%` }}
              />
            </div>
          </div>
          {loading && (
            <p className="text-xs text-sky-300">Refreshing sentiment data…</p>
          )}
          {error && (
            <p className="text-xs text-rose-300">
              {error} Displaying cached values.
            </p>
          )}
        </div>

        <div className="space-y-4 rounded-[28px] border border-slate-800 bg-gradient-to-b from-slate-900/80 to-black/60 p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Source breakdown</p>
              <p className="text-[11px] text-gray-500">{sourceSummaryText}</p>
            </div>
            <span className="text-xs text-white/80">{sources.length} sources</span>
          </div>
          <div className="space-y-3">
            {sources.map((entry) => {
              const width = Math.max(0, Math.min(100, Math.abs(entry.score ?? 0)));
              return (
                <div key={entry.id} className="space-y-1">
                  <div className="flex items-center justify-between text-xs text-gray-300">
                    <span>{entry.label}</span>
                    <span className="font-semibold text-white">
                      {entry.score >= 0 ? '+' : ''}
                      {entry.score ?? 0}%
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-gray-800">
                    <div
                      className={`h-full rounded-full bg-gradient-to-r ${sourceGradient(entry.score)}`}
                      style={{ width: `${width}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-gray-500">{entry.coverage}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="space-y-3 rounded-[28px] border border-slate-800 bg-gray-950/50 p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Recent sentiment data</p>
            <p className="text-[11px] text-gray-500">Last captured mentions & summaries</p>
          </div>
          <span className="text-xs text-gray-500">{recent.length} records</span>
        </div>
        <div className="space-y-3">
          {recent.map((item) => (
            <div
              key={item.id}
              className="space-y-1 rounded-2xl border border-gray-800 bg-black/40 px-4 py-3"
            >
              <div className="flex items-center justify-between text-[11px] text-gray-400">
                <span>{item.source}</span>
                <span>{formatTimestamp(item.timestamp)}</span>
              </div>
              <p className="text-sm text-gray-200">{item.summary}</p>
              <div className="flex items-center justify-between text-[11px] text-gray-400">
                <span className="font-semibold text-white">{item.score >= 0 ? '+' : ''}{item.score ?? 0}%</span>
                <span className="text-gray-500">Sentiment strength</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default SentimentPanel;
