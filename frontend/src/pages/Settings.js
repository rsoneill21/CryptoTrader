import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const DEFAULT_SOURCES = [
  {
    id: 'news',
    name: 'News feeds',
    description: 'Worldwide crypto, macro, and regulation headlines.',
    enabled: true,
    api_key: '',
    last_fetch: '2026-01-30T01:00:00Z',
    fetch_status: 'healthy',
    fetch_message: 'Fetched 4 sources without error.',
    fetch_interval_seconds: 60,
  },
  {
    id: 'twitter',
    name: 'Twitter / X streams',
    description: 'Live social chatter and sentiment threads.',
    enabled: true,
    api_key: '',
    last_fetch: '2026-01-30T00:53:00Z',
    fetch_status: 'stale',
    fetch_message: 'Delayed updates (rate limit).',
    fetch_interval_seconds: 45,
  },
  {
    id: 'onchain',
    name: 'On-chain signals',
    description: 'Whale flow, exchange net flows, and staking moves.',
    enabled: false,
    api_key: '',
    last_fetch: '2026-01-29T23:40:00Z',
    fetch_status: 'error',
    fetch_message: 'Provider unreachable.',
    fetch_interval_seconds: 90,
  },
];

const STATUS_LABELS = {
  healthy: 'Healthy',
  stale: 'Stale',
  error: 'Error',
  pending: 'Pending',
  unknown: 'Unknown',
};

const STATUS_STYLES = {
  healthy: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-200',
  stale: 'border-amber-400/60 bg-amber-500/10 text-amber-100',
  error: 'border-rose-500/60 bg-rose-500/10 text-rose-200',
  pending: 'border-sky-500/60 bg-sky-500/10 text-sky-200',
  unknown: 'border-gray-600 bg-gray-700/60 text-gray-300',
};

const formatTimestamp = (value) => {
  if (!value) {
    return 'Not yet fetched';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
};

const SettingsPage = () => {
  const [sources, setSources] = useState(
    DEFAULT_SOURCES.map((item) => ({ ...item, dirty: false }))
  );
  const [loading, setLoading] = useState(true);
  const [savingSourceId, setSavingSourceId] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [visibleKeyId, setVisibleKeyId] = useState(null);

  const loadSources = useCallback(async () => {
    setLoading(true);
    setErrorMessage('');
    setSuccessMessage('');
    try {
      const response = await api.get('/api/settings/data-sources');
      const data = response.data?.data_sources ?? response.data?.sources ?? [];
      if (!Array.isArray(data) || !data.length) {
        setSources(DEFAULT_SOURCES.map((item) => ({ ...item, dirty: false })));
        return;
      }
      const normalized = data.map((item) => ({
        id: item.id ?? item.source_name ?? `${item.name ?? 'source'}-${Math.random()}`,
        name: item.display_name ?? item.name ?? item.source_name ?? 'Data source',
        description: item.description ?? 'Configured data source',
        enabled: Boolean(item.enabled),
        api_key: item.api_key ?? '',
        last_fetch: item.last_fetch ?? item.last_run ?? null,
        fetch_status: item.fetch_status ?? item.status ?? 'unknown',
        fetch_message: item.fetch_message ?? item.last_error ?? '',
        fetch_interval_seconds: item.fetch_interval_seconds ?? 60,
        dirty: false,
      }));
      setSources(normalized);
    } catch (err) {
      console.error('Data source load failed:', err);
      setErrorMessage(err.message || 'Unable to load data sources.');
      setSources(DEFAULT_SOURCES.map((item) => ({ ...item, dirty: false })));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const updateSource = useCallback((id, changes) => {
    setSources((prev) =>
      prev.map((source) =>
        source.id === id
          ? {
              ...source,
              ...changes,
              dirty: true,
            }
          : source
      )
    );
  }, []);

  const handleToggle = useCallback(
    (id) => {
      setSources((prev) =>
        prev.map((source) =>
          source.id === id
            ? {
                ...source,
                enabled: !source.enabled,
                dirty: true,
              }
            : source
        )
      );
    },
    []
  );

  const handleApiKeyChange = useCallback((id, value) => {
    updateSource(id, { api_key: value });
  }, [updateSource]);

  const handleVisibilityToggle = useCallback((id) => {
    setVisibleKeyId((prev) => (prev === id ? null : id));
  }, []);

  const handleSave = useCallback(
    async (id) => {
      const target = sources.find((source) => source.id === id);
      if (!target) {
        return;
      }
      setSavingSourceId(id);
      setErrorMessage('');
      setSuccessMessage('');
      try {
        await api.put(`/api/settings/data-sources/${id}`, {
          enabled: target.enabled,
          api_key: target.api_key || null,
        });
        setSuccessMessage(`${target.name} updated successfully.`);
        setSources((prev) =>
          prev.map((item) =>
            item.id === id
              ? {
                  ...item,
                  dirty: false,
                  last_fetch: item.last_fetch,
                }
              : item
          )
        );
      } catch (err) {
        console.error('Unable to update source:', err);
        setErrorMessage(err.message || `Failed to save ${target.name}.`);
      } finally {
        setSavingSourceId(null);
      }
    },
    [sources]
  );

  const statusSummary = useMemo(() => {
    const counts = {
      healthy: 0,
      stale: 0,
      error: 0,
      pending: 0,
      unknown: 0,
    };
    let latestFetch = null;
    sources.forEach((source) => {
      const key = counts[source.fetch_status] !== undefined ? source.fetch_status : 'unknown';
      counts[key] += 1;
      if (source.last_fetch) {
        const parsed = Date.parse(source.last_fetch);
        if (!Number.isNaN(parsed) && (!latestFetch || parsed > latestFetch)) {
          latestFetch = parsed;
        }
      }
    });
    return {
      counts,
      refreshedAt: latestFetch
        ? new Date(latestFetch).toLocaleString('en-US', {
            hour12: true,
            month: 'short',
            day: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
          })
        : 'No recent pulls',
    };
  }, [sources]);

  const hasUnsavedChanges = useMemo(
    () => sources.some((source) => source.dirty),
    [sources]
  );

  const summaryChips = useMemo(() => {
    return Object.entries(statusSummary.counts).map(([status, count]) => {
      const label = STATUS_LABELS[status] || 'Unknown';
      const style = STATUS_STYLES[status] || STATUS_STYLES.unknown;
      return (
        <div
          key={status}
          className={`rounded-2xl border px-4 py-2 text-sm font-semibold ${style}`}
        >
          {label}: {count}
        </div>
      );
    });
  }, [statusSummary.counts]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <section className="rounded-2xl border border-gray-700/60 bg-gradient-to-br from-gray-900/80 to-gray-900/40 p-6 shadow-xl shadow-black/60">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-widest text-blue-300">System controls</p>
            <h1 className="text-3xl font-semibold text-white">Data source configuration</h1>
            <p className="mt-1 text-sm text-gray-400">
              Enable or disable connectors, update API credentials, and monitor ingest status in one place.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={loadSources}
              disabled={loading}
              className="inline-flex items-center gap-2 rounded-lg border border-blue-500/80 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-200 transition hover:bg-blue-500/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? 'Refreshing...' : 'Refresh statuses'}
            </button>
            <div className="text-right text-xs text-gray-400">
              <p>Latest fetch: {statusSummary.refreshedAt}</p>
              <p>{hasUnsavedChanges ? 'You have unsaved changes.' : 'All sources synced.'}</p>
            </div>
          </div>
        </div>
        <div className="mt-6 grid auto-rows-min gap-3 text-xs sm:grid-cols-2 lg:grid-cols-5">
          {summaryChips}
        </div>
      </section>

      {errorMessage && (
        <div className="rounded-2xl border border-rose-400/70 bg-rose-400/10 p-4 text-sm text-rose-200">
          {errorMessage}
        </div>
      )}

      {successMessage && (
        <div className="rounded-2xl border border-emerald-400/70 bg-emerald-400/10 p-4 text-sm text-emerald-100">
          {successMessage}
        </div>
      )}

      <section className="space-y-4">
        {loading && sources.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-gray-700/60 bg-gray-800/60 p-8 text-center text-sm text-gray-300">
            Loading data sources...
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {sources.map((source) => {
              const status = source.fetch_status || 'unknown';
              const badgeStyle = STATUS_STYLES[status] || STATUS_STYLES.unknown;
              const statusLabel = STATUS_LABELS[status] || STATUS_LABELS.unknown;
              return (
                <div
                  key={source.id}
                  className="flex flex-col rounded-2xl border border-gray-700/60 bg-gray-900/60 p-5 shadow-sm shadow-black/40"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h2 className="text-lg font-semibold text-white">{source.name}</h2>
                      <p className="mt-1 text-sm text-gray-400">{source.description}</p>
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${badgeStyle}`}>
                      {statusLabel}
                    </span>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <label className="flex items-center gap-2 text-sm font-semibold text-gray-300">
                      <span>Enabled</span>
                      <button
                        type="button"
                        onClick={() => handleToggle(source.id)}
                        className={`relative inline-flex h-7 w-12 items-center rounded-full border border-gray-600 transition ${
                          source.enabled ? 'bg-emerald-500/80' : 'bg-gray-700'
                        }`}
                        aria-pressed={source.enabled}
                      >
                        <span
                          className={`h-5 w-5 rounded-full bg-white transition ${
                            source.enabled ? 'translate-x-5' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </label>
                    <div className="text-xs text-gray-400">
                      Last fetch: {formatTimestamp(source.last_fetch)}
                    </div>
                  </div>

                  <div className="mt-4 border-t border-gray-700/40 pt-4">
                    <div className="flex items-center justify-between">
                      <p className="text-xs uppercase tracking-widest text-gray-500">API key</p>
                      <button
                        type="button"
                        onClick={() => handleVisibilityToggle(source.id)}
                        className="text-xs font-semibold text-blue-300 hover:text-blue-200"
                      >
                        {visibleKeyId === source.id ? 'Hide' : 'Show'}
                      </button>
                    </div>
                    <input
                      type={visibleKeyId === source.id ? 'text' : 'password'}
                      value={source.api_key}
                      onChange={(event) => handleApiKeyChange(source.id, event.target.value)}
                      autoComplete="off"
                      placeholder="Enter API key"
                      className="mt-2 w-full rounded-xl border border-gray-700 bg-gray-900/80 px-3 py-2 text-sm text-gray-100 focus:border-blue-500 focus:outline-none"
                    />
                    <p className="mt-2 text-xs text-gray-500">
                      Credentials are stored encrypted. Leave blank to keep the existing key.
                    </p>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-gray-400">
                    <span>Fetch every {source.fetch_interval_seconds ?? 60}s</span>
                    {source.fetch_message && <span>Note: {source.fetch_message}</span>}
                  </div>

                  <div className="mt-5 flex items-center justify-end gap-3">
                    {source.dirty && (
                      <span className="text-xs uppercase tracking-wide text-amber-300">
                        Unsaved
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => handleSave(source.id)}
                      disabled={savingSourceId === source.id}
                      className="inline-flex items-center justify-center rounded-xl border border-blue-500/80 bg-blue-500/10 px-4 py-2 text-sm font-semibold text-blue-200 transition hover:bg-blue-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {savingSourceId === source.id ? 'Saving...' : 'Save changes'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};

export default SettingsPage;
