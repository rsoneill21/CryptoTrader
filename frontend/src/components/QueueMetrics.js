/**
 * Queue metrics component.
 * Displays message queue depth, throughput, and channel breakdown.
 */

import React from 'react';

const QueueMetrics = ({ metrics = {} }) => {
  const totalDepth = metrics.total_depth || 0;
  const channels = metrics.channels || {};
  const throughput = metrics.throughput || {};

  const getDepthColor = (depth) => {
    if (depth === 0) return 'text-gray-400';
    if (depth < 10) return 'text-emerald-300';
    if (depth < 50) return 'text-amber-300';
    return 'text-rose-300';
  };

  const depthColor = getDepthColor(totalDepth);

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-lg shadow-black/40">
      <h3 className="text-sm font-semibold text-white mb-4">Queue Metrics</h3>

      <div className="mb-6">
        <p className="text-xs text-gray-500 mb-1">Total Depth</p>
        <p className={`text-4xl font-bold ${depthColor}`}>{totalDepth}</p>
      </div>

      <div className="space-y-3 mb-4">
        <p className="text-xs uppercase tracking-wider text-gray-500">Channel Breakdown</p>
        {Object.keys(channels).length > 0 ? (
          Object.entries(channels).map(([channel, count]) => (
            <div key={channel} className="flex justify-between items-center">
              <span className="text-xs text-gray-400">{channel}</span>
              <span className="text-sm font-medium text-white">{count}</span>
            </div>
          ))
        ) : (
          <p className="text-xs text-gray-500">No messages in queue</p>
        )}
      </div>

      {throughput && Object.keys(throughput).length > 0 && (
        <div className="pt-4 border-t border-gray-800">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-2">Throughput (last 1m)</p>
          {Object.entries(throughput).map(([channel, count]) => (
            <div key={channel} className="flex justify-between items-center">
              <span className="text-xs text-gray-400">{channel}</span>
              <span className="text-xs text-gray-300">{count} msg/min</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default QueueMetrics;
