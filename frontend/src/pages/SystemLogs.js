/**
 * System logs viewer page.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { systemAPI } from '../services/api';

const LOG_LEVEL_COLORS = {
  debug: 'text-gray-400',
  info: 'text-blue-400',
  warning: 'text-amber-400',
  error: 'text-rose-400',
  critical: 'text-rose-600 font-bold',
};

const SystemLogs = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [total, setTotal] = useState(0);
  const [level, setLevel] = useState('');
  const [source, setSource] = useState('');

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        page_size: pageSize,
      };
      if (level) params.level = level;
      if (source) params.source = source;

      const response = await systemAPI.logs(params);
      setLogs(response.data.logs);
      setTotal(response.data.total);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
      setError(err?.message || 'Unable to load system logs.');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, level, source]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleLevelChange = (e) => {
    setLevel(e.target.value);
    setPage(1);
  };

  const handleSourceChange = (e) => {
    setSource(e.target.value);
    setPage(1);
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-[0.4em] text-sky-400">System Administration</p>
        <h1 className="text-3xl font-bold text-white">System Logs</h1>
        <p className="max-w-3xl text-sm text-gray-300">
          Monitor backend events, errors, and agent activities.
        </p>
      </header>

      {/* Filters */}
      <section className="rounded-2xl border border-gray-800 bg-gray-900/60 p-4 shadow-lg">
        <div className="flex flex-wrap gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs uppercase tracking-widest text-gray-500">Level</label>
            <select
              value={level}
              onChange={handleLevelChange}
              className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="">All Levels</option>
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-[200px]">
            <label className="text-xs uppercase tracking-widest text-gray-500">Source</label>
            <input
              type="text"
              value={source}
              onChange={handleSourceChange}
              placeholder="Filter by source (e.g. kraken, strategy)..."
              className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() => fetchLogs()}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              Refresh
            </button>
          </div>
        </div>
      </section>

      {/* Logs Table */}
      <section className="rounded-2xl border border-gray-800 bg-gray-900/60 overflow-hidden shadow-lg">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-800/50">
                <th className="px-4 py-3 text-xs uppercase tracking-widest text-gray-500 font-medium">Timestamp</th>
                <th className="px-4 py-3 text-xs uppercase tracking-widest text-gray-500 font-medium">Level</th>
                <th className="px-4 py-3 text-xs uppercase tracking-widest text-gray-500 font-medium">Source</th>
                <th className="px-4 py-3 text-xs uppercase tracking-widest text-gray-500 font-medium">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {loading && logs.length === 0 ? (
                <tr>
                  <td colSpan="4" className="px-4 py-8 text-center text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent"></div>
                      <span>Loading logs...</span>
                    </div>
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan="4" className="px-4 py-8 text-center text-rose-400">
                    {error}
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan="4" className="px-4 py-8 text-center text-gray-500">
                    No logs found matching your filters.
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-white/5 transition-colors">
                    <td className="px-4 py-2 text-xs font-mono text-gray-400 whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className={`px-4 py-2 text-xs font-bold uppercase ${LOG_LEVEL_COLORS[log.level.toLowerCase()] || 'text-white'}`}>
                      {log.level}
                    </td>
                    <td className="px-4 py-2 text-xs font-mono text-blue-300">
                      {log.source}
                    </td>
                    <td className="px-4 py-2 text-sm text-gray-300">
                      {log.message}
                      {log.details && Object.keys(log.details).length > 0 && (
                        <details className="mt-1">
                          <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-400">View Details</summary>
                          <pre className="mt-2 p-2 rounded bg-black/40 text-[10px] overflow-x-auto text-gray-400 max-h-40">
                            {JSON.stringify(log.details, null, 2)}
                          </pre>
                        </details>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-gray-800 px-4 py-3 bg-gray-800/30">
            <div className="text-xs text-gray-500">
              Showing <span className="text-gray-300">{((page - 1) * pageSize) + 1}</span> to{' '}
              <span className="text-gray-300">{Math.min(page * pageSize, total)}</span> of{' '}
              <span className="text-gray-300">{total}</span> logs
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded border border-gray-700 px-3 py-1 text-xs font-medium text-gray-400 hover:bg-gray-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="rounded border border-gray-700 px-3 py-1 text-xs font-medium text-gray-400 hover:bg-gray-700 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

export default SystemLogs;
