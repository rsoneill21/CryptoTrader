/**
 * Agent status grid component.
 * Displays agent status cards with pause/resume controls.
 */

import React from 'react';

const STATUS_COLORS = {
  running: 'bg-emerald-500',
  paused: 'bg-amber-500',
  stopped: 'bg-rose-500',
  unknown: 'bg-gray-500',
};

const formatHeartbeatAge = (timestamp) => {
  if (!timestamp) return 'No heartbeat';

  const age = Date.now() - new Date(timestamp).getTime();
  const seconds = Math.floor(age / 1000);

  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
};

const AgentStatusGrid = ({ agents = [], onControl, controlLoading = false }) => {
  if (agents.length === 0) {
    return (
      <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-8 text-center">
        <p className="text-gray-400">No agents available</p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
      {agents.map((agent) => {
        const statusColor = STATUS_COLORS[agent.status] || STATUS_COLORS.unknown;
        const heartbeatAge = formatHeartbeatAge(agent.last_heartbeat);
        const isStale = agent.last_heartbeat &&
          (Date.now() - new Date(agent.last_heartbeat).getTime() > 60000);

        return (
          <div
            key={agent.name}
            className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-lg shadow-black/40 transition duration-300 hover:border-gray-700"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className={`h-3 w-3 rounded-full ${statusColor} ${agent.status === 'running' ? 'animate-pulse' : ''}`} />
                <h3 className="text-sm font-semibold text-white">{agent.name}</h3>
              </div>
              <span className="text-xs uppercase tracking-wider text-gray-500">{agent.status}</span>
            </div>

            <p className="text-xs text-gray-400 mb-4">{agent.description || 'No description'}</p>

            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">Heartbeat:</span>
                <span className={isStale ? 'text-amber-400' : 'text-gray-300'}>
                  {heartbeatAge}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">Queue:</span>
                <span className="text-gray-300">{agent.queue_size || 0} messages</span>
              </div>
            </div>

            <button
              onClick={() => onControl(agent.name, agent.status === 'running' ? 'pause' : 'resume')}
              disabled={controlLoading || agent.status === 'stopped'}
              className={`w-full rounded-lg py-2 text-xs font-medium transition duration-200 ${
                agent.status === 'stopped'
                  ? 'bg-gray-800 text-gray-600 cursor-not-allowed'
                  : agent.status === 'running'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-700 hover:bg-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-700 hover:bg-emerald-500/30'
              } ${controlLoading ? 'opacity-50 cursor-wait' : ''}`}
            >
              {controlLoading ? 'Processing...' : agent.status === 'running' ? 'Pause' : 'Resume'}
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default AgentStatusGrid;
