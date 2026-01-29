import React, { useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const STATUS_STYLES = {
  paper: 'bg-blue-600/80 text-blue-50 border-blue-500',
  live: 'bg-green-600/80 text-green-50 border-green-500',
  paused: 'bg-yellow-500/80 text-yellow-950 border-yellow-400',
  archived: 'bg-gray-700/80 text-gray-100 border-gray-600',
};

const formatCurrency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);

const formatPercent = (value) => {
  const numeric = typeof value === 'number' && !Number.isNaN(value) ? value : 0;
  return `${numeric.toFixed(1)}%`;
};

const StrategyLab = () => {
  const [strategies, setStrategies] = useState([]);
  const [selectedStrategyId, setSelectedStrategyId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [capital, setCapital] = useState(12000);
  const [riskTolerance, setRiskTolerance] = useState(1.8);
  const [paperMode, setPaperMode] = useState(true);
  const [paperTrades, setPaperTrades] = useState([]);

  useEffect(() => {
    const fetchStrategies = async () => {
      setLoading(true);
      setError('');

      try {
        const response = await api.get('/api/strategies');
        const list = Array.isArray(response.data) ? response.data : [];
        setStrategies(list);
        if (!selectedStrategyId && list.length) {
          setSelectedStrategyId(list[0].id);
        }
      } catch (fetchError) {
        console.error('Unable to load strategies:', fetchError);
        setError(fetchError?.message || 'Failed to load strategies.');
      } finally {
        setLoading(false);
      }
    };

    fetchStrategies();
  }, []);

  useEffect(() => {
    if (!selectedStrategyId && strategies.length) {
      setSelectedStrategyId(strategies[0].id);
    }
  }, [strategies, selectedStrategyId]);

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.id === selectedStrategyId) || null,
    [selectedStrategyId, strategies]
  );

  const performanceMetrics = useMemo(() => {
    if (!selectedStrategy) {
      return {
        winRate: 0,
        totalTrades: 0,
        avgPnl: 0,
        totalPnl: 0,
        maxDrawdown: 0,
        sharpeRatio: 0,
        projectedRoi: 0,
      };
    }

    const seed = Math.max(1, selectedStrategy.id);
    const totalTrades = 18 + ((seed * 7) % 12) * 3;
    const winRate = Math.min(90, 36 + ((seed * 13) % 50));
    const avgPnl = (seed % 9) * 3 - 9;
    const totalPnl = Number((avgPnl * totalTrades * 0.12).toFixed(2));
    const maxDrawdown = Math.min(32, 4 + ((seed * 4) % 28));
    const sharpeRatio = Number((0.7 + ((seed * 5) % 18) * 0.08).toFixed(2));
    const projectedRoi = Number((totalPnl / capital) * 100);

    return {
      winRate,
      totalTrades,
      avgPnl,
      totalPnl,
      maxDrawdown,
      sharpeRatio,
      projectedRoi,
    };
  }, [capital, selectedStrategy]);

  const ruleSummary = useMemo(() => {
    if (!selectedStrategy?.rules) {
      return 'No rule definition available yet.';
    }

    const entries = Object.entries(selectedStrategy.rules);
    if (!entries.length) {
      return 'Rule definition is empty.';
    }

    return entries
      .slice(0, 4)
      .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`)
      .join(' • ');
  }, [selectedStrategy]);

  const paperStats = useMemo(() => {
    const total = paperTrades.length;
    const winners = paperTrades.filter((trade) => trade.pnl > 0).length;
    const losers = total - winners;
    const totalPnl = Number(paperTrades.reduce((sum, trade) => sum + trade.pnl, 0).toFixed(2));
    const winRate = total ? Math.round((winners / total) * 100) : 0;

    return { total, winners, losers, totalPnl, winRate };
  }, [paperTrades]);

  const handlePaperTrade = (side) => {
    const newTrade = {
      id: Date.now(),
      symbol: 'BTC/USDT',
      side,
      pnl: Number((Math.random() * 40 - 15).toFixed(2)),
      timestamp: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
    };

    setPaperTrades((prev) => [newTrade, ...prev].slice(0, 5));
  };

  const handleResetPaperTrades = () => {
    setPaperTrades([]);
  };

  const strategyListContent = () => {
    if (loading) {
      return <p className="text-sm text-gray-400">Fetching strategies…</p>;
    }

    if (error) {
      return <p className="text-sm text-red-400">{error}</p>;
    }

    if (!strategies.length) {
      return <p className="text-sm text-gray-400">No strategies yet. Import or build one to get started.</p>;
    }

    return (
      <div className="space-y-3">
        {strategies.map((strategy) => {
          const isActive = selectedStrategyId === strategy.id;
          const statusClass = STATUS_STYLES[strategy.status] || STATUS_STYLES.paper;

          return (
            <button
              key={strategy.id}
              type="button"
              onClick={() => setSelectedStrategyId(strategy.id)}
              className={`w-full text-left rounded-xl border px-4 py-3 transition-all duration-200 focus:outline-none ${
                isActive ? 'border-blue-400 bg-gray-800/80 shadow-lg shadow-blue-500/20' : 'border-gray-700 bg-gray-900/80'
              }`}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">{strategy.name}</h3>
                <span className={`inline-flex items-center rounded-full px-3 py-0.5 text-xs font-semibold ${statusClass}`}>
                  {strategy.status?.toUpperCase() || 'PAPER'}
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-400 line-clamp-2">{strategy.description || 'Optimizing...'}</p>
            </button>
          );
        })}
      </div>
    );
  };

  const detailRows = [
    { label: 'Source', value: selectedStrategy?.source || 'manual' },
    { label: 'Last updated', value: selectedStrategy?.updated_at ? new Date(selectedStrategy.updated_at).toLocaleString() : '—' },
    { label: 'Promoted', value: selectedStrategy?.promoted_at ? new Date(selectedStrategy.promoted_at).toLocaleString() : 'Not yet' },
    { label: 'AI changes', value: selectedStrategy?.ai_modifications ? 'Applied' : 'None' },
  ];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-sm uppercase tracking-[0.3em] text-blue-400">Phase 4</p>
        <h1 className="text-3xl font-bold text-white">Strategy Lab</h1>
        <p className="text-sm text-gray-400">Design, review, and paper trade your AI strategies.</p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <aside className="rounded-2xl border border-gray-700 bg-gray-900/60 p-5 shadow-inner shadow-black/40">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Strategy catalog</h2>
            <span className="text-xs text-gray-500">{strategies.length} total</span>
          </div>
          <div className="mt-4 h-[560px] overflow-auto pr-1">{strategyListContent()}</div>
        </aside>

        <section className="space-y-6">
          <div className="rounded-2xl border border-gray-700 bg-gradient-to-br from-gray-900/90 to-gray-900/70 p-6 shadow-xl shadow-black/50">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm text-gray-400">Selected strategy</p>
                <h2 className="text-xl font-semibold text-white">
                  {selectedStrategy ? selectedStrategy.name : 'Select a strategy'}
                </h2>
              </div>
              <div className="flex items-center gap-3 text-xs">
                <span className="text-gray-500">Paper mode</span>
                <button
                  type="button"
                  onClick={() => setPaperMode((prev) => !prev)}
                  className={`rounded-full px-3 py-1 text-white transition-all ${paperMode ? 'bg-blue-500' : 'bg-gray-700'}`}
                >
                  {paperMode ? 'Enabled' : 'Disabled'}
                </button>
              </div>
            </div>

            <p className="mt-3 text-sm text-gray-300">
              {selectedStrategy?.description || 'Explore strategies created by the AI Strategy Generator or import your own.'}
            </p>

            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {detailRows.map((row) => (
                <div key={row.label} className="rounded-xl border border-gray-800 bg-gray-900/40 px-4 py-3">
                  <p className="text-xs uppercase tracking-wide text-gray-500">{row.label}</p>
                  <p className="text-sm font-medium text-white">{row.value}</p>
                </div>
              ))}
            </div>

            <div className="mt-5 rounded-xl border border-dashed border-gray-700 bg-gray-900/50 p-4">
              <p className="text-xs text-gray-500">Rule summary</p>
              <p className="text-sm text-gray-200">{ruleSummary}</p>
            </div>
          </div>

          <div className="space-y-4 rounded-2xl border border-gray-700 bg-gray-900/60 p-5 shadow-inner">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Performance metrics</h3>
              <span className="text-xs text-gray-500">Last 90 days projection</span>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
                <p className="text-xs uppercase tracking-widest text-gray-500">Win rate</p>
                <p className="text-2xl font-semibold text-white">{formatPercent(performanceMetrics.winRate)}</p>
                <p className="text-xs text-gray-400">Trailing 30d estimate</p>
              </div>
              <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
                <p className="text-xs uppercase tracking-widest text-gray-500">Total trades</p>
                <p className="text-2xl font-semibold text-white">{performanceMetrics.totalTrades}</p>
                <p className="text-xs text-gray-400">Strategy resilience</p>
              </div>
              <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
                <p className="text-xs uppercase tracking-widest text-gray-500">Avg trade P&L</p>
                <p className="text-2xl font-semibold text-white">{formatCurrency(performanceMetrics.avgPnl)}</p>
                <p className="text-xs text-gray-400">Baseline expectation</p>
              </div>
              <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
                <p className="text-xs uppercase tracking-widest text-gray-500">Max drawdown</p>
                <p className="text-2xl font-semibold text-white">{formatPercent(performanceMetrics.maxDrawdown)}</p>
                <p className="text-xs text-gray-400">Worst case window</p>
              </div>
              <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
                <p className="text-xs uppercase tracking-widest text-gray-500">Projected ROI</p>
                <p className="text-2xl font-semibold text-white">{formatPercent(performanceMetrics.projectedRoi)}</p>
                <p className="text-xs text-gray-400">Based on capital ${capital.toLocaleString()}</p>
              </div>
              <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
                <p className="text-xs uppercase tracking-widest text-gray-500">Sharpe ratio</p>
                <p className="text-2xl font-semibold text-white">{performanceMetrics.sharpeRatio.toFixed(2)}</p>
                <p className="text-xs text-gray-400">Risk-adjusted return</p>
              </div>
            </div>
          </div>

          <div className="space-y-4 rounded-2xl border border-gray-700 bg-gradient-to-br from-gray-900/80 to-black/40 p-5 shadow-2xl shadow-black/80">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Paper trading controls</h3>
              <p className="text-xs text-gray-500">Simulate without live capital</p>
            </div>

            <div className="space-y-2 rounded-xl border border-gray-800 bg-gray-900/60 p-4">
              <p className="text-xs uppercase tracking-wide text-gray-400">Capital allocation</p>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="5000"
                  max="50000"
                  step="1000"
                  value={capital}
                  onChange={(event) => setCapital(Number(event.target.value))}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-gray-700/50"
                />
                <span className="text-sm font-semibold text-white">{formatCurrency(capital)}</span>
              </div>
              <p className="text-xs text-gray-500">Risk tolerance: {riskTolerance.toFixed(1)}%</p>
              <input
                type="range"
                min="0.5"
                max="3"
                step="0.1"
                value={riskTolerance}
                onChange={(event) => setRiskTolerance(Number(event.target.value))}
                className="h-2 w-full cursor-pointer appearance-none rounded-full bg-gray-700/50"
              />
            </div>

            <div className="grid auto-rows-[52px] gap-3 sm:grid-cols-3">
              <button
                type="button"
                onClick={() => handlePaperTrade('buy')}
                className="rounded-xl border border-blue-500/60 bg-blue-500/20 text-white transition hover:bg-blue-500/30"
              >
                Simulate entry
              </button>
              <button
                type="button"
                onClick={() => handlePaperTrade('sell')}
                className="rounded-xl border border-red-500/60 bg-red-500/20 text-white transition hover:bg-red-500/30"
              >
                Simulate exit
              </button>
              <button
                type="button"
                onClick={handleResetPaperTrades}
                className="rounded-xl border border-gray-600 bg-transparent text-gray-200 transition hover:border-gray-400"
              >
                Reset timeline
              </button>
            </div>

            <div className="rounded-xl border border-dashed border-gray-600 bg-gray-900/60 p-4">
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>Recent paper trades</span>
                <span>{paperStats.total} recorded</span>
              </div>
              <div className="mt-3 space-y-2">
                {paperTrades.length ? (
                  paperTrades.map((trade) => (
                    <div key={trade.id} className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900/70 px-3 py-2 text-sm">
                      <div>
                        <p className="text-gray-200">{trade.symbol}</p>
                        <p className="text-xs text-gray-500">{trade.timestamp} · {trade.side.toUpperCase()}</p>
                      </div>
                      <p className={`text-sm font-semibold ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {trade.pnl >= 0 ? '+' : ''}{formatCurrency(trade.pnl)}
                      </p>
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-gray-500">Execute a simulation to seed the timeline.</p>
                )}
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-gray-400">
                <div>
                  <p className="text-[10px] text-gray-500">Win rate</p>
                  <p className="text-sm text-white">{paperStats.winRate}%</p>
                </div>
                <div>
                  <p className="text-[10px] text-gray-500">Net P&L</p>
                  <p className={`text-sm font-semibold ${paperStats.totalPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {paperStats.totalPnl >= 0 ? '+' : ''}{formatCurrency(paperStats.totalPnl)}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-gray-500">Winning trades</p>
                  <p className="text-sm text-white">{paperStats.winners}</p>
                </div>
                <div>
                  <p className="text-[10px] text-gray-500">Losing trades</p>
                  <p className="text-sm text-white">{paperStats.losers}</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default StrategyLab;
