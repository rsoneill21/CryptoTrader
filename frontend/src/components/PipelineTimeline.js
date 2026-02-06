/**
 * Pipeline timeline component.
 * Displays recent events flowing through the agent pipeline.
 */

import React from 'react';

const PRIORITY_COLORS = {
  critical: 'text-rose-400',
  high: 'text-amber-400',
  normal: 'text-emerald-400',
  low: 'text-gray-400',
};

const EVENT_TYPE_COLORS = {
  trade_signal: 'bg-blue-500/20 text-blue-300 border-blue-700',
  market_update: 'bg-emerald-500/20 text-emerald-300 border-emerald-700',
  agent_control: 'bg-amber-500/20 text-amber-300 border-amber-700',
  heartbeat: 'bg-gray-500/20 text-gray-300 border-gray-700',
  error: 'bg-rose-500/20 text-rose-300 border-rose-700',
};

const formatTimestamp = (timestamp) => {
  if (!timestamp) return '';

  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffSeconds = Math.floor(diffMs / 1000);

  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return date.toLocaleTimeString();
};

const PipelineTimeline = ({ events = [] }) => {
  if (events.length === 0) {
    return (
      <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-8 text-center">
        <p className="text-gray-400">No recent pipeline events</p>
        <p className="text-xs text-gray-500 mt-1">Events will appear as agents process messages</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-lg shadow-black/40">
      <h3 className="text-sm font-semibold text-white mb-4">Pipeline Timeline</h3>

      <div className="space-y-3 max-h-96 overflow-y-auto">
        {events.map((event, index) => {
          const priorityColor = PRIORITY_COLORS[event.priority] || PRIORITY_COLORS.normal;
          const typeColors = EVENT_TYPE_COLORS[event.event_type] || EVENT_TYPE_COLORS.heartbeat;

          return (
            <div key={event.id || index} className="relative pl-6">
              {/* Timeline line */}
              {index < events.length - 1 && (
                <div className="absolute left-2 top-6 bottom-0 w-px bg-gray-800" />
              )}

              {/* Timeline dot */}
              <div className={`absolute left-0 top-2 h-4 w-4 rounded-full border-2 border-gray-900 ${priorityColor.replace('text-', 'bg-')}`} />

              <div className="pb-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 text-xs rounded border ${typeColors}`}>
                      {event.event_type}
                    </span>
                    {event.priority && event.priority !== 'normal' && (
                      <span className={`text-xs ${priorityColor}`}>
                        {event.priority}
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-gray-500">{formatTimestamp(event.timestamp)}</span>
                </div>

                <div className="flex items-center gap-2 text-xs text-gray-400 mb-1">
                  <span className="font-medium">{event.source}</span>
                  <span>→</span>
                  <span className="font-medium">{event.target}</span>
                </div>

                {event.summary && (
                  <p className="text-xs text-gray-500 leading-relaxed">{event.summary}</p>
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
