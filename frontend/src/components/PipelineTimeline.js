import React from 'react';

const EVENT_TYPE_COLORS = {
  insight: 'border-blue-700 bg-blue-500/20 text-blue-300',
  signal: 'border-amber-700 bg-amber-500/20 text-amber-300',
  order: 'border-emerald-700 bg-emerald-500/20 text-emerald-300',
  default: 'border-gray-700 bg-gray-500/20 text-gray-300',
};

const PRIORITY_STYLES = {
  0: 'text-rose-300',
  1: 'text-amber-300',
  2: 'text-gray-300',
};

const formatRelative = (timestamp) => {
  if (!timestamp) return '';
  const ageMs = Date.now() - Date.parse(timestamp);
  if (ageMs < 60000) return `${Math.max(1, Math.floor(ageMs / 1000))}s ago`;
  if (ageMs < 3600000) return `${Math.floor(ageMs / 60000)}m ago`;
  if (ageMs < 86400000) return `${Math.floor(ageMs / 3600000)}h ago`;
  return `${Math.floor(ageMs / 86400000)}d ago`;
};

const truncateSummary = (value = '') => {
  if (value.length <= 120) return value;
  return `${value.slice(0, 120)}...`;
};

const PipelineTimeline = ({ events = [] }) => {
  const recentEvents = events.slice(0, 20);

  if (events.length === 0) {
    return (
      <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5">
        <h3 className="mb-4 text-sm font-semibold text-white">Pipeline Timeline</h3>
        <p className="text-sm text-gray-400">
          No pipeline activity yet. Agents will appear here when they start exchanging messages.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5">
      <h3 className="mb-4 text-sm font-semibold text-white">Pipeline Timeline</h3>

      <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
        {recentEvents.map((event, index) => {
          const typeKey = String(event.event_type || '').toLowerCase();
          const typeStyle = EVENT_TYPE_COLORS[typeKey] || EVENT_TYPE_COLORS.default;
          const priority = Number.isInteger(event.priority) ? event.priority : 2;
          const priorityStyle = PRIORITY_STYLES[priority] || PRIORITY_STYLES[2];
          const priorityLabel = `P${priority}`;
          const summary = event.summary || '';

          return (
            <div key={`${event.timestamp}-${index}`} className="border-l-2 border-gray-700 pl-4 ml-2">
              <div className="relative">
                <span className="absolute -left-[22px] top-1 h-2.5 w-2.5 rounded-full bg-gray-400" />

                <div className="mb-1 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className={`rounded border px-2 py-0.5 ${typeStyle}`}>{event.event_type}</span>
                    <span className={priorityStyle}>{priorityLabel}</span>
                  </div>
                  <span className="text-xs text-gray-500">{formatRelative(event.timestamp)}</span>
                </div>

                <div className="mb-1 text-xs text-gray-300">
                  {event.source_agent} -&gt; {event.target_agent}
                </div>

                {summary && (
                  <p className="text-xs leading-relaxed text-gray-400" title={summary}>
                    {truncateSummary(summary)}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default PipelineTimeline;
