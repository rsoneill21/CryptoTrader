import React from 'react';

const formatAgentName = (name = '') => {
  return name
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
};

const getStatus = (agent) => {
  if (!agent.running) {
    return { label: 'Stopped', dot: 'bg-rose-500', text: 'text-rose-300' };
  }
  if (agent.paused) {
    return { label: 'Paused', dot: 'bg-amber-500', text: 'text-amber-300' };
  }
  return { label: 'Running', dot: 'bg-emerald-500', text: 'text-emerald-300' };
};

const formatHeartbeat = (seconds) => {
  if (typeof seconds !== 'number') {
    return { label: 'No heartbeat', color: 'text-gray-400' };
  }
  const rounded = Number(seconds.toFixed(1));
  if (rounded < 10) {
    return { label: `${rounded}s ago`, color: 'text-emerald-300' };
  }
  if (rounded <= 30) {
    return { label: `${rounded}s ago`, color: 'text-amber-300' };
  }
  return { label: `${rounded}s ago`, color: 'text-rose-300' };
};

const AgentStatusGrid = ({ agents = [], onControl, controlLoading = null }) => {
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
        const status = getStatus(agent);
        const heartbeat = formatHeartbeat(agent.heartbeat_age_seconds);
        const controlAction = agent.paused ? 'resume' : 'pause';
        const isLoading = controlLoading === agent.name;

        return (
          <div
            key={agent.name}
            className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-lg shadow-black/40 transition duration-300 hover:border-gray-700"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className={`h-3 w-3 rounded-full ${status.dot} ${status.label === 'Running' ? 'animate-pulse' : ''}`} />
                <h3 className="text-sm font-semibold text-white">{formatAgentName(agent.name)}</h3>
              </div>
              <span className={`text-xs uppercase tracking-wider ${status.text}`}>{status.label}</span>
            </div>

            <p className="text-xs text-gray-400 mb-4">{agent.description || 'No description'}</p>

            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">Heartbeat:</span>
                <span className={heartbeat.color}>{heartbeat.label}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">Queue:</span>
                <span className="rounded-full border border-gray-700 bg-gray-800/70 px-2 py-0.5 text-gray-300">
                  {agent.queue_size || 0}
                </span>
              </div>
            </div>

            <button
              onClick={() => onControl(agent.name, controlAction)}
              disabled={isLoading || !agent.running}
              className={`w-full rounded-lg py-2 text-xs font-medium transition duration-200 ${
                !agent.running
                  ? 'bg-gray-800 text-gray-600 cursor-not-allowed'
                  : agent.paused
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-700 hover:bg-emerald-500/30'
                  : 'bg-amber-500/20 text-amber-300 border border-amber-700 hover:bg-amber-500/30'
              } ${isLoading ? 'opacity-50 cursor-wait' : ''}`}
            >
              {isLoading ? 'Updating...' : !agent.running ? 'Stopped' : agent.paused ? 'Resume' : 'Pause'}
            </button>
          </div>
        );
      })}
    </div>
  );
};

export default AgentStatusGrid;
