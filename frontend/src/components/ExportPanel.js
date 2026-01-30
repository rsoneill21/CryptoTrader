import React, { useMemo, useState } from 'react';
import api from '../services/api';

const FORMAT_OPTIONS = [
  {
    value: 'csv',
    label: 'Trade history (CSV)',
    description: 'Download executed trades within the selected window.',
    endpoint: '/api/export/trades',
    responseType: 'blob',
    filename: 'trades_export.csv',
    startParam: 'start_time',
    endParam: 'end_time',
  },
  {
    value: 'json',
    label: 'Strategy catalog (JSON)',
    description: 'Download created strategies metadata.',
    endpoint: '/api/export/strategies',
    responseType: 'json',
    filename: 'strategies_export.json',
    startParam: 'start_date',
    endParam: 'end_date',
  },
];

const toIsoString = (value) => {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed.toISOString();
};

const ExportPanel = () => {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [format, setFormat] = useState(FORMAT_OPTIONS[0].value);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const selectedFormat = useMemo(
    () => FORMAT_OPTIONS.find((option) => option.value === format) ?? FORMAT_OPTIONS[0],
    [format],
  );

  const buildFilters = () => {
    const filters = {};
    const isoStart = toIsoString(startDate);
    const isoEnd = toIsoString(endDate);

    if (isoStart) {
      filters[selectedFormat.startParam] = isoStart;
    }
    if (isoEnd) {
      filters[selectedFormat.endParam] = isoEnd;
    }

    return filters;
  };

  const triggerDownload = (blob, filename) => {
    const downloadUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = downloadUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.URL.revokeObjectURL(downloadUrl);
  };

  const handleDownload = async () => {
    setLoading(true);
    setError('');
    setMessage('');
    const filters = buildFilters();

    try {
      if (selectedFormat.responseType === 'blob') {
        const response = await api.get(selectedFormat.endpoint, {
          params: filters,
          responseType: 'blob',
        });
        triggerDownload(response.data, selectedFormat.filename);
        setMessage('Trade export is downloading.');
        return;
      }

      const response = await api.get(selectedFormat.endpoint, {
        params: filters,
      });
      const payload = response.data ?? [];
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: 'application/json',
      });
      triggerDownload(blob, selectedFormat.filename);
      setMessage('Strategy export is downloading.');
    } catch (err) {
      console.error('Export failed', err);
      setError(err?.message || 'Unable to generate export.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-gray-800 bg-slate-950/70 p-6 shadow-xl shadow-black/40">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.3em] text-sky-300">
            Data export
          </p>
          <h2 className="text-2xl font-semibold text-white">Generate export</h2>
          <p className="mt-1 text-sm text-gray-400">
            Select a range and format to download a snapshot of your recent activity.
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          <span>Start date</span>
          <input
            className="rounded-xl border border-gray-800 bg-slate-900/60 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-sky-400 focus:outline-none"
            type="datetime-local"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            aria-label="Export start datetime"
          />
        </label>
        <label className="flex flex-col gap-2 text-sm text-gray-300">
          <span>End date</span>
          <input
            className="rounded-xl border border-gray-800 bg-slate-900/60 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-sky-400 focus:outline-none"
            type="datetime-local"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            aria-label="Export end datetime"
          />
        </label>
      </div>

      <div className="mt-6 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-gray-500">Format</p>
        <div className="flex flex-wrap gap-2">
          {FORMAT_OPTIONS.map((option) => {
            const isActive = option.value === selectedFormat.value;
            return (
              <button
                key={option.value}
                type="button"
                className={`rounded-2xl border px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 ${
                  isActive
                    ? 'border-sky-400 bg-sky-500/10 text-sky-200'
                    : 'border-gray-800 bg-slate-900/60 text-gray-200 hover:border-slate-500'
                }`}
                onClick={() => setFormat(option.value)}
              >
                <div className="text-sm font-semibold">{option.label}</div>
                <p className="text-xs text-gray-400">{option.description}</p>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-6 flex flex-col gap-3">
        {error && <p className="text-sm text-rose-400">{error}</p>}
        {message && <p className="text-sm text-emerald-300">{message}</p>}
        <button
          type="button"
          className="flex items-center justify-center rounded-2xl border border-transparent bg-sky-500 px-5 py-3 text-sm font-semibold uppercase tracking-[0.3em] text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:bg-slate-700"
          onClick={handleDownload}
          disabled={loading}
        >
          {loading ? 'Preparing export…' : 'Download export'}
        </button>
      </div>
    </div>
  );
};

export default ExportPanel;
