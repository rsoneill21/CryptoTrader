import React, { useState } from 'react';
import { strategiesAPI } from '../services/api';

const STATUS_STYLES = {
  paper: 'bg-blue-600/80 text-blue-50 border-blue-500',
  live: 'bg-green-600/80 text-green-50 border-green-500',
  paused: 'bg-yellow-500/80 text-yellow-950 border-yellow-400',
  archived: 'bg-gray-700/80 text-gray-100 border-gray-600',
};

const HEALTH_STYLES = {
  healthy: 'bg-green-500 text-white',
  degraded: 'bg-yellow-500 text-yellow-900',
  critical: 'bg-red-500 text-white',
};

const StrategyCard = ({ strategy, onUpdate, onSelect, isActive }) => {
  const [showPromoteModal, setShowPromoteModal] = useState(false);
  const [showAdjustmentModal, setShowAdjustmentModal] = useState(false);
  const [isPromoting, setIsPromoting] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  if (!strategy) return null;

  const handlePromote = async () => {
    setIsPromoting(true);
    try {
      await strategiesAPI.promote(strategy.id);
      setShowPromoteModal(false);
      onUpdate();
    } catch (err) {
      alert('Promotion failed: ' + (err.message || 'Unknown error'));
    } finally {
      setIsPromoting(false);
    }
  };

  const handleApplyAdjustment = async () => {
    setIsApplying(true);
    try {
      await strategiesAPI.applyAdjustment(strategy.id);
      setShowAdjustmentModal(false);
      onUpdate();
    } catch (err) {
      alert('Application failed: ' + (err.message || 'Unknown error'));
    } finally {
      setIsApplying(false);
    }
  };

  const handleDiscardAdjustment = async () => {
    try {
      await strategiesAPI.discardAdjustment(strategy.id);
      setShowAdjustmentModal(false);
      onUpdate();
    } catch (err) {
      alert('Discard failed: ' + (err.message || 'Unknown error'));
    }
  };

  const healthStatus = strategy.health_status || 'healthy';
  const hasAdjustment = !!strategy.pending_adjustment;

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => onSelect(strategy.id)}
        className={`w-full text-left rounded-xl border px-4 py-3 transition-all duration-200 focus:outline-none ${
          isActive ? 'border-blue-400 bg-gray-800/80 shadow-lg shadow-blue-500/20' : 'border-gray-700 bg-gray-900/80'
        }`}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white">{strategy.name}</h3>
            <span className={`h-2 w-2 rounded-full ${HEALTH_STYLES[healthStatus]}`} title={`Health: ${healthStatus}`} />
          </div>
          <span className={`inline-flex items-center rounded-full px-3 py-0.5 text-xs font-semibold ${STATUS_STYLES[strategy.status] || STATUS_STYLES.paper}`}>
            {strategy.status?.toUpperCase() || 'PAPER'}
          </span>
        </div>
        <p className="mt-1 text-xs text-gray-400 line-clamp-2">{strategy.description || 'Optimizing...'}</p>
        
        {hasAdjustment && (
          <div className="mt-2 inline-flex items-center gap-1.5 rounded-md bg-blue-500/20 px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-blue-400">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
            Optimization Available
          </div>
        )}
      </button>

      {isActive && (
        <div className="flex flex-wrap gap-2 px-1">
          {strategy.status === 'paper' && (
            <button
              onClick={() => setShowPromoteModal(true)}
              className="flex-1 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 transition"
            >
              Promote to Live
            </button>
          )}
          {hasAdjustment && (
            <button
              onClick={() => setShowAdjustmentModal(true)}
              className="flex-1 rounded-lg border border-blue-500/50 bg-blue-500/10 px-3 py-2 text-xs font-semibold text-blue-400 hover:bg-blue-500/20 transition"
            >
              Review Optimization
            </button>
          )}
        </div>
      )}

      {/* Promotion Modal */}
      {showPromoteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
            <h2 className="text-xl font-bold text-white">Promote Strategy</h2>
            <p className="mt-2 text-sm text-gray-400">
              You are about to promote <span className="text-white font-semibold">{strategy.name}</span> to live trading.
              This will use real capital based on your risk settings.
            </p>

            <div className="mt-6 grid grid-cols-2 gap-4">
              <div className="rounded-xl border border-gray-800 bg-gray-800/50 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-gray-500">Paper Win Rate</p>
                <p className="text-lg font-bold text-green-400">68.4%</p> {/* Mocked for now as we don't have real perf here */}
              </div>
              <div className="rounded-xl border border-gray-800 bg-gray-800/50 p-3 text-center">
                <p className="text-[10px] uppercase tracking-wider text-gray-500">Max Drawdown</p>
                <p className="text-lg font-bold text-red-400">12.2%</p> {/* Mocked for now */}
              </div>
            </div>

            <div className="mt-8 flex gap-3">
              <button
                onClick={() => setShowPromoteModal(false)}
                className="flex-1 rounded-xl border border-gray-700 py-3 text-sm font-semibold text-gray-400 hover:bg-gray-800 transition"
              >
                Cancel
              </button>
              <button
                onClick={handlePromote}
                disabled={isPromoting}
                className="flex-1 rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white hover:bg-blue-500 transition disabled:opacity-50"
              >
                {isPromoting ? 'Promoting...' : 'Confirm Promotion'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Adjustment Modal */}
      {showAdjustmentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-2xl rounded-2xl border border-gray-700 bg-gray-900 p-6 shadow-2xl">
            <h2 className="text-xl font-bold text-white">Strategy Optimization</h2>
            <p className="mt-2 text-sm text-gray-400">
              The AI has proposed improvements based on recent performance degradation.
            </p>

            <div className="mt-6 grid grid-cols-2 gap-6">
              <div>
                <h3 className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3">Current Parameters</h3>
                <div className="space-y-2 rounded-xl border border-gray-800 bg-gray-900/40 p-3 text-xs font-mono text-gray-400">
                  {Object.entries(strategy.rules || {}).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span>{k}:</span>
                      <span className="text-gray-300">{JSON.stringify(v)}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-xs font-bold uppercase tracking-widest text-blue-500 mb-3">Proposed Changes</h3>
                <div className="space-y-2 rounded-xl border border-blue-900/30 bg-blue-500/5 p-3 text-xs font-mono text-blue-300">
                  {Object.entries(strategy.pending_adjustment?.proposed_rules || strategy.pending_adjustment || {}).map(([k, v]) => {
                    const isChanged = JSON.stringify(v) !== JSON.stringify(strategy.rules?.[k]);
                    return (
                      <div key={k} className={`flex justify-between ${isChanged ? 'bg-blue-500/20 px-1 rounded' : ''}`}>
                        <span>{k}:</span>
                        <span className={isChanged ? 'font-bold' : ''}>{JSON.stringify(v)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            <div className="mt-8 flex gap-3">
              <button
                onClick={handleDiscardAdjustment}
                className="rounded-xl border border-gray-700 px-6 py-3 text-sm font-semibold text-rose-400 hover:bg-rose-500/10 transition"
              >
                Discard
              </button>
              <div className="flex-1" />
              <button
                onClick={() => setShowAdjustmentModal(false)}
                className="rounded-xl border border-gray-700 px-6 py-3 text-sm font-semibold text-gray-400 hover:bg-gray-800 transition"
              >
                Close
              </button>
              <button
                onClick={handleApplyAdjustment}
                disabled={isApplying}
                className="rounded-xl bg-blue-600 px-8 py-3 text-sm font-semibold text-white hover:bg-blue-500 transition disabled:opacity-50"
              >
                {isApplying ? 'Applying...' : 'Apply Optimization'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StrategyCard;
