import React from 'react';

const getDepthColor = (depth) => {
  if (depth < 20) return 'text-emerald-300';
  if (depth <= 80) return 'text-amber-300';
  return 'text-rose-300';
};

const QueueMetrics = ({ metrics = { channels: {}, total_depth: 0, throughput_per_minute: {} } }) => {
  const channels = metrics.channels || {};
  const totalDepth = metrics.total_depth || 0;
  const throughput = metrics.throughput_per_minute || {};

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5">
      <h3 className="text-sm font-semibold text-white mb-4">Queue Metrics</h3>

      <div className="mb-6">
        <p className="mb-1 text-xs text-gray-500">Total Queue Depth</p>
        <p className={`text-4xl font-bold ${getDepthColor(totalDepth)}`}>{totalDepth}</p>
      </div>

      <div className="space-y-3">
        <p className="text-xs uppercase tracking-wider text-gray-500">Channel Breakdown</p>
        {Object.keys(channels).length > 0 ? (
          <div className="space-y-2">
            {Object.entries(channels).map(([channel, depth]) => (
              <div key={channel} className="rounded-lg border border-gray-800 bg-gray-950/60 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-gray-300">{channel}</span>
                  <span className="text-xs text-white">total: {depth.total ?? 0}</span>
                </div>
                <div className="mt-1 grid grid-cols-3 gap-2 text-[11px] text-gray-400">
                  <span>P0: {depth.p0 ?? 0}</span>
                  <span>P1: {depth.p1 ?? 0}</span>
                  <span>P2: {depth.p2 ?? 0}</span>
                </div>
                <p className="mt-1 text-[11px] text-gray-500">
                  Throughput: {throughput[channel] ?? 0} msg/min
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-500">No messages in queue</p>
        )}
      </div>
    </div>
  );
};

export default QueueMetrics;
