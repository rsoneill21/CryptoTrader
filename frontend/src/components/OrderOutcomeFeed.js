import React from 'react';

const statusClass = {
  pending: 'text-amber-300 border-amber-500/40 bg-amber-500/10',
  partially_filled: 'text-sky-300 border-sky-500/40 bg-sky-500/10',
  filled: 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10',
  rejected: 'text-rose-300 border-rose-500/40 bg-rose-500/10',
  canceled: 'text-gray-300 border-gray-600 bg-gray-800/40',
};

const formatTime = (value) => {
  if (!value) {
    return 'Time unavailable';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Time unavailable';
  }
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

const formatSide = (value) => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return 'UNKNOWN';
  }
  return value.toUpperCase();
};

const formatSymbol = (value) => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return 'Unknown Symbol';
  }
  return value;
};

const OrderOutcomeFeed = ({ entries }) => {
  return (
    <section className="rounded-[32px] border border-gray-800 bg-gray-900/40 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Order Outcomes</h2>
        <p className="text-[10px] uppercase tracking-widest text-gray-500">Global Feed</p>
      </div>
      {!entries.length ? (
        <p className="mt-4 text-sm text-gray-500">No order outcomes yet.</p>
      ) : (
        <div className="mt-4 space-y-3 max-h-[320px] overflow-auto pr-1">
          {entries.map((entry) => (
            <article
              key={entry.id}
              className={`rounded-2xl border px-4 py-3 ${statusClass[entry.status] || statusClass.rejected}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-white">
                    {formatSymbol(entry.symbol)} · {formatSide(entry.side)}
                  </p>
                  <p className="text-[11px] uppercase tracking-widest mt-1">{entry.status}</p>
                </div>
                <p className="text-[11px] text-gray-300">{formatTime(entry.timestamp)}</p>
              </div>
              {(entry.reasonCode || entry.reasonMessage) && (
                <div className="mt-2 text-xs text-gray-200">
                  {entry.reasonCode && <span className="font-semibold">[{entry.reasonCode}] </span>}
                  {entry.reasonMessage || 'No additional details'}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

export default OrderOutcomeFeed;
