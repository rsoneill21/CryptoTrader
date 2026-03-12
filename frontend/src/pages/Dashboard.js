/**
 * Main dashboard page.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { systemAPI, agentsAPI } from '../services/api';
import ModelComparison from '../components/ModelComparison';
import AgentStatusGrid from '../components/AgentStatusGrid';
import QueueMetrics from '../components/QueueMetrics';
import PipelineTimeline from '../components/PipelineTimeline';

const STAT_COLOR_MAP = {
  blue: 'bg-blue-500/20 text-blue-300 border-blue-700',
  green: 'bg-emerald-500/20 text-emerald-200 border-emerald-700',
  yellow: 'bg-amber-400/20 text-amber-200 border-amber-600',
  red: 'bg-rose-500/20 text-rose-200 border-rose-600',
};

const StatCard = ({ title, value, icon, color = 'blue', loading = false }) => {
  const colorClasses = STAT_COLOR_MAP[color] || STAT_COLOR_MAP.blue;
  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-lg shadow-black/40 transition duration-300 hover:-translate-y-1 hover:border-white">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{title}</p>
          <div className="mt-2 h-10 flex items-center">
            {loading ? (
              <span className="h-8 w-24 rounded-full bg-white/10 animate-pulse" />
            ) : (
              <p className="text-2xl font-semibold text-white">{value}</p>
            )}
          </div>
        </div>
        <div
          className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${colorClasses}`}
        >
          {icon}
        </div>
      </div>
    </div>
  );
};

const FeatureCard = ({ to, title, description, icon }) => (
  <Link
    to={to}
    className="group flex h-full flex-col rounded-2xl border border-gray-700 bg-gradient-to-br from-gray-900/80 via-gray-900/60 to-gray-900/40 p-5 shadow-xl shadow-black/40 transition duration-300 hover:-translate-y-1 hover:border-white/40"
  >
    <div className="flex items-start justify-between">
      <div
        className="flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/20 text-blue-300 transition duration-300 group-hover:bg-blue-500 group-hover:text-white"
      >
        {icon}
      </div>
      <span className="text-xs uppercase tracking-[0.4em] text-gray-500">{title}</span>
    </div>
    <p className="mt-5 text-sm leading-relaxed text-gray-300">{description}</p>
  </Link>
);

const featureSections = [
  {
    to: '/strategy-lab',
    title: 'AI Strategy Lab',
    description: 'Create, test, and optimize trading strategies with AI assistance.',
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h4l3-3h4l3 3h4v8H3z" />
      </svg>
    ),
  },
  {
    to: '/live-trading',
    title: 'Live Trading',
    description: 'Monitor real-time market data and manage active positions.',
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7v6h6l2-2M5 19h14" />
      </svg>
    ),
  },
  {
    to: '/ai-chat',
    title: 'AI Chat',
    description: 'Discuss strategies and get insights from your trading AI.',
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9 9 0 010-18c5 0 9 3.582 9 8z" />
      </svg>
    ),
  },
  {
    to: '/alerts',
    title: 'Alerts & Activity',
    description: 'View trade alerts, AI decisions, and activity history.',
    icon: (
      <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l2 2M16 17h4m-9 3h2m-6-2h3" />
      </svg>
    ),
  },
];

const Dashboard = () => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Agent dashboard state
  const [agentData, setAgentData] = useState(null);
  const [agentLoading, setAgentLoading] = useState(true);
  const [agentError, setAgentError] = useState('');
  const [controlLoading, setControlLoading] = useState(null);
  const [flushLoading, setFlushLoading] = useState(false);
  const [retrySignalId, setRetrySignalId] = useState('');

  useEffect(() => {
    const controller = new AbortController();

    const fetchHealth = async () => {
      try {
        const response = await systemAPI.health();
        setHealth(response.data);
      } catch (err) {
        if (!controller.signal.aborted) {
          console.error('Failed to fetch health:', err);
          setError(err?.message || 'Unable to load system status.');
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchHealth();

    return () => controller.abort();
  }, []);

  // Fetch agent dashboard data with polling
  useEffect(() => {
    const controller = new AbortController();
    let intervalId;

    const fetchAgentDashboard = async () => {
      try {
        const response = await agentsAPI.dashboard(20);
        if (!controller.signal.aborted) {
          setAgentData(response.data);
          setAgentError('');
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          console.error('Failed to fetch agent dashboard:', err);
          setAgentError(err?.message || 'Unable to load agent status.');
        }
      } finally {
        if (!controller.signal.aborted) {
          setAgentLoading(false);
        }
      }
    };

    fetchAgentDashboard();

    // Poll every 5 seconds
    intervalId = setInterval(fetchAgentDashboard, 5000);

    return () => {
      controller.abort();
      clearInterval(intervalId);
    };
  }, []);

  // Agent control handler
  const handleAgentControl = async (agentName, action) => {
    setControlLoading(agentName);
    try {
      await agentsAPI.controlAgent(agentName, action);
      // Refresh dashboard immediately
      const response = await agentsAPI.dashboard(20);
      setAgentData(response.data);
    } catch (err) {
      console.error('Failed to control agent:', err);
      setAgentError(err?.message || 'Failed to control agent.');
    } finally {
      setControlLoading(null);
    }
  };

  // Flush queue handler
  const handleFlushQueue = async (channel) => {
    if (!window.confirm(`Flush all messages from "${channel}"? This cannot be undone.`)) {
      return;
    }

    setFlushLoading(true);
    try {
      await agentsAPI.flushQueue(channel);
      // Refresh dashboard immediately
      const response = await agentsAPI.dashboard(20);
      setAgentData(response.data);
    } catch (err) {
      console.error('Failed to flush queue:', err);
      setAgentError(err?.message || 'Failed to flush queue.');
    } finally {
      setFlushLoading(false);
    }
  };

  // Retry signal handler
  const handleRetrySignal = async (signalId) => {
    if (!signalId) {
      return;
    }

    try {
      await agentsAPI.retrySignal(signalId);
      // Refresh dashboard immediately
      const response = await agentsAPI.dashboard(20);
      setAgentData(response.data);
      setRetrySignalId('');
    } catch (err) {
      console.error('Failed to retry signal:', err);
      setAgentError(err?.message || 'Failed to retry signal.');
    }
  };

  const healthStatus = useMemo(() => {
    if (loading) {
      return 'Checking system status…';
    }
    if (error) {
      return error;
    }
    return health?.status === 'healthy' ? 'All systems go' : 'Degraded service';
  }, [error, health, loading]);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-[0.4em] text-sky-400">Phase 11 · UI polish</p>
        <h1 className="text-3xl font-bold text-white">Dashboard</h1>
        <p className="max-w-3xl text-sm text-gray-300">
          Welcome to CryptoTrader — everything you need to monitor AI strategies, live trading, and alerts.
        </p>
      </header>

      <section className="rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/80 to-black/60 p-5 shadow-2xl shadow-black/60">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`h-3 w-3 rounded-full ${
                health?.status === 'healthy' ? 'bg-emerald-500' : 'bg-amber-500'
              } transition duration-500 ${loading ? 'animate-pulse' : ''}`}
            />
            <p className="text-sm text-gray-300">{healthStatus}</p>
          </div>
          <span className="text-xs text-gray-500">
            v{health?.version || '0.1.0'}
          </span>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Active Strategies"
          value="12"
          icon={
            <svg className="h-6 w-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v9m4-4-4-4-4 4m4-4v7" />
            </svg>
          }
          loading={loading}
        />
        <StatCard
          title="Open Positions"
          value="8"
          color="green"
          icon={
            <svg className="h-6 w-6 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4" />
            </svg>
          }
          loading={loading}
        />
        <StatCard
          title="Today's P&L"
          value="+$4,377"
          color="yellow"
          icon={
            <svg className="h-6 w-6 text-amber-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9l-5 5-5-5" />
            </svg>
          }
          loading={loading}
        />
        <StatCard
          title="Risk Score"
          value="18%"
          color="red"
          icon={
            <svg className="h-6 w-6 text-rose-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3m0 4h.01m6.938 4H5.062c-1.54 0-2.502-1.667-1.732-3L10.268 4.0c.77-1.333 2.694-1.333 3.464 0L19.67 17c.77 1.333-.192 3-1.732 3z" />
            </svg>
          }
          loading={loading}
        />
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white">Agent Operations</h2>
          <div className="flex items-center gap-2">
            {agentLoading ? (
              <span className="text-xs text-gray-500">Loading...</span>
            ) : agentError ? (
              <span className="text-xs text-rose-400">Error</span>
            ) : (
              <div className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs text-gray-500">Live</span>
              </div>
            )}
          </div>
        </div>

        {agentError && (
          <div className="rounded-2xl border border-rose-800 bg-rose-500/10 p-4">
            <p className="text-sm text-rose-400">{agentError}</p>
          </div>
        )}

        <AgentStatusGrid
          agents={agentData?.agents || []}
          onControl={handleAgentControl}
          controlLoading={controlLoading}
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <QueueMetrics metrics={agentData?.queue_metrics || { channels: {}, total_depth: 0, throughput_per_minute: {} }} />
          <PipelineTimeline events={agentData?.pipeline_events || []} />
        </div>

        <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-5 shadow-lg shadow-black/40">
          <h3 className="text-sm font-semibold text-white mb-4">Operator Actions</h3>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => handleFlushQueue('trade_signals')}
              disabled={flushLoading}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-amber-500/20 text-amber-300 border border-amber-700 hover:bg-amber-500/30 transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {flushLoading ? 'Flushing...' : 'Flush Trade Signals Queue'}
            </button>
            <button
              onClick={() => handleFlushQueue('risk_alerts')}
              disabled={flushLoading}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-amber-500/20 text-amber-300 border border-amber-700 hover:bg-amber-500/30 transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {flushLoading ? 'Flushing...' : 'Flush Risk Alerts Queue'}
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={retrySignalId}
              onChange={(event) => setRetrySignalId(event.target.value)}
              placeholder="Failed signal id"
              className="rounded-lg border border-gray-700 bg-gray-950/70 px-3 py-2 text-xs text-white placeholder:text-gray-500 focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={() => handleRetrySignal(retrySignalId.trim())}
              disabled={!retrySignalId.trim()}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-700 hover:bg-emerald-500/30 transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Retry Failed Signal
            </button>
          </div>
          <p className="mt-2 text-xs text-gray-500">
            Flush clears all pending messages from a queue. Retry republishes a failed signal with high priority.
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white">Quick access</h2>
          <span className="text-xs uppercase tracking-[0.4em] text-gray-500">Tap into AI</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {featureSections.map((feature) => (
            <FeatureCard key={feature.to} {...feature} />
          ))}
        </div>
      </section>

      <ModelComparison />
    </div>
  );
};

export default Dashboard;
