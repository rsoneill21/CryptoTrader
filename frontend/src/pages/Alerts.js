import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';

const SEVERITY_STYLES = {
  info: 'bg-blue-500 text-black dark:text-white',
  warning: 'bg-yellow-400 text-black',
  critical: 'bg-red-500 text-white',
};

const STATUS_LABELS = {
  new: 'New',
  viewed: 'Viewed',
  actioned: 'Actioned',
  dismissed: 'Dismissed',
};

const STATUS_COLORS = {
  new: 'text-blue-400',
  viewed: 'text-gray-300',
  actioned: 'text-green-400',
  dismissed: 'text-red-300',
};

const formatTimestamp = (value) => {
  if (!value) {
    return '—';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('en-US', {
    hour12: true,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const AlertsPage = () => {
  const [alerts, setAlerts] = useState([]);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState('');
  const [filters, setFilters] = useState({
    severity: 'all',
    status: 'all',
    type: 'all',
  });
  const [searchTerm, setSearchTerm] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState('details');
  const [actionBusy, setActionBusy] = useState(false);
  const [actionFeedback, setActionFeedback] = useState(null);
  const selectedAlertId = selectedAlert?.id;

  useEffect(() => {
    const handler = setTimeout(() => {
      setSearchQuery(searchTerm.trim());
    }, 400);
    return () => clearTimeout(handler);
  }, [searchTerm]);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setFetchError('');
    try {
      const params = {};
      if (filters.severity !== 'all') {
        params.severity = filters.severity;
      }
      if (filters.status !== 'all') {
        params.status = filters.status;
      }
      if (filters.type !== 'all') {
        params.type = filters.type;
      }
      if (searchQuery) {
        params.search = searchQuery;
      }

      const response = await api.get('/api/alerts', { params });
      const alertList = response.data?.alerts ?? [];
      setAlerts(alertList);
      setSelectedAlert((prev) => {
        if (!alertList.length) {
          return null;
        }
        if (prev) {
          const match = alertList.find((item) => item.id === prev.id);
          if (match) {
            return match;
          }
        }
        return alertList[0];
      });
    } catch (error) {
      setFetchError(error?.message || 'Unable to load alerts.');
    } finally {
      setLoading(false);
    }
  }, [filters, searchQuery]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const typeOptions = useMemo(() => {
    const unique = Array.from(new Set(alerts.map((alert) => alert.type))).filter(Boolean);
    return ['all', ...unique];
  }, [alerts]);

  const filteredAlerts = useMemo(() => {
    let result = [...alerts];

    if (filters.severity !== 'all') {
      result = result.filter((alert) => alert.severity === filters.severity);
    }
    if (filters.status !== 'all') {
      result = result.filter((alert) => alert.status === filters.status);
    }
    if (filters.type !== 'all') {
      result = result.filter((alert) => alert.type === filters.type);
    }
    if (searchQuery) {
      const lowered = searchQuery.toLowerCase();
      result = result.filter((alert) => {
        return (
          alert.title.toLowerCase().includes(lowered) ||
          (alert.message?.toLowerCase().includes(lowered) ?? false)
        );
      });
    }

    return result;
  }, [alerts, filters, searchQuery]);

  useEffect(() => {
    if (!filteredAlerts.length) {
      setSelectedAlert(null);
      return;
    }
    if (selectedAlertId && filteredAlerts.some((item) => item.id === selectedAlertId)) {
      return;
    }
    setSelectedAlert(filteredAlerts[0]);
  }, [filteredAlerts, selectedAlertId]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const handleStatusUpdate = async (status, actionTaken) => {
    if (!selectedAlert) {
      return;
    }
    setActionBusy(true);
    setActionFeedback(null);
    try {
      const response = await api.patch(`/api/alerts/${selectedAlert.id}/status`, {
        status,
        action_taken: actionTaken,
      });
      const updated = response.data;
      setAlerts((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setSelectedAlert(updated);
      setActionFeedback({
        type: 'success',
        message: `Alert marked ${status}.`,
      });
    } catch (error) {
      setActionFeedback({
        type: 'error',
        message: error?.message || 'Unable to update alert status.',
      });
    } finally {
      setActionBusy(false);
    }
  };

  const activityLog = useMemo(() => {
    if (!selectedAlert) {
      return [];
    }

    const items = [
      {
        id: 'created',
        title: 'Created',
        detail: selectedAlert.message || 'Alert created by automated monitor.',
        timestamp: selectedAlert.created_at,
      },
    ];

    if (selectedAlert.action_taken) {
      items.push({
        id: 'action',
        title: 'Action logged',
        detail: selectedAlert.action_taken,
        timestamp: selectedAlert.actioned_at || selectedAlert.created_at,
      });
    }

    if (selectedAlert.ai_confidence != null) {
      items.push({
        id: 'ai-confidence',
        title: 'AI confidence',
        detail: `${(selectedAlert.ai_confidence * 100).toFixed(1)}% confidence`,
        timestamp: selectedAlert.created_at,
      });
    }

    items.push({
      id: 'status',
      title: 'Current status',
      detail: STATUS_LABELS[selectedAlert.status] || selectedAlert.status,
      timestamp: selectedAlert.actioned_at || selectedAlert.created_at,
    });

    return items.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }, [selectedAlert]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Alerts & Activity</h1>
        <p className="text-sm text-gray-400">Track risk warnings, AI decisions, and trading activity from a single timeline.</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr] xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-4">
          <div className="rounded-2xl border border-gray-700 bg-gray-900/60 p-4 shadow-lg shadow-black/40">
            <h2 className="text-lg font-semibold text-white">Filters</h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="space-y-1 text-xs uppercase tracking-wide text-gray-400">
                Severity
                <select
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white shadow-inner shadow-black/40"
                  value={filters.severity}
                  onChange={(event) => handleFilterChange('severity', event.target.value)}
                >
                  <option value="all">All</option>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
              <label className="space-y-1 text-xs uppercase tracking-wide text-gray-400">
                Status
                <select
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white shadow-inner shadow-black/40"
                  value={filters.status}
                  onChange={(event) => handleFilterChange('status', event.target.value)}
                >
                  <option value="all">All</option>
                  <option value="new">New</option>
                  <option value="viewed">Viewed</option>
                  <option value="actioned">Actioned</option>
                  <option value="dismissed">Dismissed</option>
                </select>
              </label>
              <label className="space-y-1 text-xs uppercase tracking-wide text-gray-400">
                Type
                <select
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white shadow-inner shadow-black/40"
                  value={filters.type}
                  onChange={(event) => handleFilterChange('type', event.target.value)}
                >
                  {typeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option === 'all' ? 'All' : option}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-xs uppercase tracking-wide text-gray-400">
                Search
                <input
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder:text-gray-500 shadow-inner shadow-black/40"
                  placeholder="Title or message"
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                />
              </label>
            </div>
          </div>

          <div className="rounded-2xl border border-gray-700 bg-gray-900/70 shadow-lg shadow-black/40">
            <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
              <h2 className="text-lg font-semibold text-white">Alerts</h2>
              <button
                className="text-xs font-semibold uppercase tracking-wide text-blue-400"
                onClick={fetchAlerts}
                disabled={loading}
              >
                Refresh
              </button>
            </div>
            <div className="max-h-[560px] space-y-1 overflow-y-auto p-4">
              {loading && <p className="text-sm text-gray-400">Loading alerts...</p>}
              {fetchError && <p className="text-sm text-red-400">{fetchError}</p>}
              {!loading && !filteredAlerts.length && (
                <p className="text-sm text-gray-500">No alerts match the current filters.</p>
              )}
              {filteredAlerts.map((alert) => (
                <button
                  key={alert.id}
                  type="button"
                  className={`flex w-full items-start justify-between rounded-2xl border px-4 py-3 text-left transition-all duration-150 ${
                    selectedAlert?.id === alert.id
                      ? 'border-blue-500 bg-blue-500/10 shadow-[0_0_0_1px_rgba(37,99,235,0.6)]'
                      : 'border-transparent hover:border-gray-600 hover:bg-white/5'
                  }`}
                  onClick={() => setSelectedAlert(alert)}
                >
                  <div className="max-w-[70%] space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                        {alert.type}
                      </span>
                      <span className="rounded-full border border-gray-700 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-300">
                        {formatTimestamp(alert.created_at)}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-white">{alert.title}</p>
                    <p className="text-xs text-gray-400 max-h-10 overflow-hidden text-ellipsis">{alert.message || 'No additional details.'}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1 text-right">
                    <span className={`text-xs font-semibold ${STATUS_COLORS[alert.status] || 'text-gray-300'}`}>
                      {STATUS_LABELS[alert.status] || alert.status}
                    </span>
                    <span className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-gray-200">
                      {alert.severity?.toUpperCase()}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-gray-700 bg-gradient-to-b from-slate-900 to-gray-900/60 p-6 shadow-lg shadow-black/40">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-widest text-gray-400">Alert detail</p>
                <h2 className="text-xl font-semibold text-white">{selectedAlert ? selectedAlert.title : 'Select an alert'}</h2>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${selectedAlert ? SEVERITY_STYLES[selectedAlert.severity] || 'bg-gray-700 text-white' : 'bg-gray-700 text-white'}`}
              >
                {selectedAlert ? selectedAlert.severity : '—'}
              </span>
            </div>
            <div className="mt-6 space-y-3">
              <div className="rounded-xl border border-dashed border-gray-700 px-4 py-3 text-sm text-gray-300">
                {selectedAlert?.message || 'No extra message provided for this alert.'}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-gray-800 bg-black/40 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Status</p>
                  <p className="text-sm font-semibold text-white">{selectedAlert ? STATUS_LABELS[selectedAlert.status] || selectedAlert.status : '—'}</p>
                  <p className="text-xs text-gray-500">Last updated {formatTimestamp(selectedAlert?.actioned_at || selectedAlert?.created_at)}</p>
                </div>
                <div className="rounded-xl border border-gray-800 bg-black/40 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">AI Confidence</p>
                  <p className="text-sm font-semibold text-white">
                    {selectedAlert?.ai_confidence != null
                      ? `${(selectedAlert.ai_confidence * 100).toFixed(1)}%`
                      : 'Not recorded'}
                  </p>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-gray-800 bg-black/40 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Type</p>
                  <p className="text-sm font-semibold text-white">{selectedAlert?.type || '—'}</p>
                </div>
                <div className="rounded-xl border border-gray-800 bg-black/40 p-3">
                  <p className="text-xs uppercase tracking-wide text-gray-400">Created</p>
                  <p className="text-sm font-semibold text-white">{formatTimestamp(selectedAlert?.created_at)}</p>
                </div>
              </div>
            </div>
            <div className="mt-6 space-y-3">
              <p className="text-xs uppercase tracking-wide text-gray-400">Quick actions</p>
              <div className="flex flex-wrap gap-2">
                <Link
                  to="/ai-chat"
                  className="inline-flex items-center justify-center rounded-full border border-blue-500/80 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-blue-400 transition hover:border-blue-400/90 hover:text-white"
                >
                  Start chat with AI
                </Link>
                <button
                  type="button"
                  disabled={actionBusy || !selectedAlert}
                  onClick={() => handleStatusUpdate('viewed', 'Alert reviewed from the alerts page.')}
                  className="inline-flex items-center justify-center rounded-full border border-gray-600 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-gray-200 transition hover:border-gray-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Mark as viewed
                </button>
                <button
                  type="button"
                  disabled={actionBusy || !selectedAlert}
                  onClick={() => handleStatusUpdate('actioned', 'Manual review: Paused trading for this alert.')}
                  className="inline-flex items-center justify-center rounded-full border border-emerald-500/80 bg-emerald-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-emerald-300 transition hover:border-emerald-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Mark as actioned
                </button>
                <button
                  type="button"
                  disabled={actionBusy || !selectedAlert}
                  onClick={() => handleStatusUpdate('dismissed', 'Snoozed this alert for 30m.')}
                  className="inline-flex items-center justify-center rounded-full border border-amber-400/80 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-amber-300 transition hover:border-amber-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Snooze alert
                </button>
              </div>
              {actionFeedback && (
                <p
                  className={`text-sm ${actionFeedback.type === 'error' ? 'text-red-400' : 'text-emerald-300'}`}
                >
                  {actionFeedback.message}
                </p>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-700 bg-gray-900/70">
            <div className="flex items-center border-b border-gray-800 px-4 py-3">
              {['details', 'activity'].map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`mr-3 rounded-full px-4 py-1 text-xs font-semibold uppercase tracking-wide transition ${
                    activeTab === tab
                      ? 'border border-blue-500 text-blue-300'
                      : 'text-gray-500'
                  }`}
                >
                  {tab === 'details' ? 'Overview' : 'Activity log'}
                </button>
              ))}
            </div>
            <div className="p-4">
              {activeTab === 'details' ? (
                <div className="space-y-4">
                  <div className="rounded-xl border border-gray-800 bg-black/40 p-4">
                    <p className="text-xs uppercase tracking-wide text-gray-400">Description</p>
                    <p className="text-sm text-gray-200">
                      {selectedAlert?.message || 'No additional description is available.'}
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-gray-800 bg-black/40 p-4">
                      <p className="text-xs uppercase tracking-wide text-gray-400">Related Trade</p>
                      <p className="text-sm font-semibold text-white">
                        {selectedAlert?.related_trade_id ? `Trade #${selectedAlert.related_trade_id}` : '—'}
                      </p>
                    </div>
                    <div className="rounded-xl border border-gray-800 bg-black/40 p-4">
                      <p className="text-xs uppercase tracking-wide text-gray-400">Related Strategy</p>
                      <p className="text-sm font-semibold text-white">
                        {selectedAlert?.related_strategy_id ? `Strategy #${selectedAlert.related_strategy_id}` : '—'}
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {!activityLog.length && <p className="text-sm text-gray-500">No activity recorded yet.</p>}
                  {activityLog.map((entry) => (
                    <div key={entry.id} className="rounded-xl border border-dashed border-gray-700 bg-gray-900/50 p-4">
                      <div className="flex items-center justify-between text-xs text-gray-400">
                        <span>{entry.title}</span>
                        <span>{formatTimestamp(entry.timestamp)}</span>
                      </div>
                      <p className="text-sm text-gray-200">{entry.detail}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AlertsPage;
