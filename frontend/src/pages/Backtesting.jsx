import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const STATUS_COLORS = {
  running: 'text-amber-400 border-amber-400/30 bg-amber-400/10',
  completed: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10',
  failed: 'text-rose-400 border-rose-400/30 bg-rose-400/10',
};

const formatCurrency = (value) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);

const formatPercent = (value) => {
  const numeric = typeof value === 'number' && !Number.isNaN(value) ? value : 0;
  return `${(numeric * 100).toFixed(2)}%`;
};

const Backtesting = () => {
  const [strategies, setStrategies] = useState([]);
  const [backtests, setBacktests] = useState([]);
  const [selectedBacktest, setSelectedBacktest] = useState(null);
  const [_loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    strategy_id: '',
    symbol: 'BTC/USD',
    start_date: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    initial_capital: 100000,
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [stratRes] = await Promise.all([
        api.get('/api/strategies'),
      ]);
      const stratList = stratRes.data.strategies || stratRes.data || [];
      setStrategies(stratList);
      
      if (stratList.length > 0) {
        if (!formData.strategy_id) {
          setFormData(prev => ({ ...prev, strategy_id: stratList[0].id }));
        }
        const backtestRes = await api.get(`/api/backtests/strategy/${stratList[0].id}`);
        setBacktests(backtestRes.data);
      }
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError('Failed to load backtesting data.');
    } finally {
      setLoading(false);
    }
  }, [formData.strategy_id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const payload = {
        ...formData,
        strategy_id: parseInt(formData.strategy_id),
        start_date: new Date(formData.start_date).toISOString(),
        end_date: new Date(formData.end_date).toISOString(),
        initial_capital: parseFloat(formData.initial_capital),
      };
      const response = await api.post('/api/backtests/', payload);
      setBacktests(prev => [response.data, ...prev]);
      alert('Backtest started in background.');
    } catch (err) {
      console.error('Failed to trigger backtest:', err);
      setError(err.response?.data?.detail || 'Failed to trigger backtest.');
    } finally {
      setSubmitting(false);
    }
  };

  const viewDetails = async (id) => {
    try {
      const response = await api.get(`/api/backtests/${id}`);
      setSelectedBacktest(response.data);
    } catch (err) {
      console.error('Failed to fetch backtest details:', err);
      alert('Failed to load details.');
    }
  };

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-sm uppercase tracking-[0.3em] text-blue-400">Phase 5</p>
        <h1 className="text-3xl font-bold text-white">Strategy Backtesting</h1>
        <p className="text-sm text-gray-400">Validate your strategies against historical market data.</p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[350px_1fr]">
        {/* Configuration Form */}
        <aside className="rounded-2xl border border-gray-800 bg-gray-900/60 p-6 shadow-xl">
          <h2 className="text-lg font-semibold text-white mb-4">Run Simulation</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs uppercase tracking-widest text-gray-500 mb-1">Strategy</label>
              <select
                name="strategy_id"
                value={formData.strategy_id}
                onChange={handleInputChange}
                className="w-full bg-black/40 border border-gray-800 rounded-xl py-2 px-3 text-sm text-white focus:outline-none focus:border-blue-500"
                required
              >
                <option value="" disabled>Select a strategy</option>
                {strategies.map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs uppercase tracking-widest text-gray-500 mb-1">Symbol</label>
              <input
                type="text"
                name="symbol"
                value={formData.symbol}
                onChange={handleInputChange}
                className="w-full bg-black/40 border border-gray-800 rounded-xl py-2 px-3 text-sm text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs uppercase tracking-widest text-gray-500 mb-1">Start Date</label>
                <input
                  type="date"
                  name="start_date"
                  value={formData.start_date}
                  onChange={handleInputChange}
                  className="w-full bg-black/40 border border-gray-800 rounded-xl py-2 px-3 text-sm text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
              <div>
                <label className="block text-xs uppercase tracking-widest text-gray-500 mb-1">End Date</label>
                <input
                  type="date"
                  name="end_date"
                  value={formData.end_date}
                  onChange={handleInputChange}
                  className="w-full bg-black/40 border border-gray-800 rounded-xl py-2 px-3 text-sm text-white focus:outline-none focus:border-blue-500"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-xs uppercase tracking-widest text-gray-500 mb-1">Initial Capital ($)</label>
              <input
                type="number"
                name="initial_capital"
                value={formData.initial_capital}
                onChange={handleInputChange}
                className="w-full bg-black/40 border border-gray-800 rounded-xl py-2 px-3 text-sm text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>

            <button
              type="submit"
              disabled={submitting || !formData.strategy_id}
              className="w-full py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold uppercase tracking-widest text-xs transition disabled:opacity-50"
            >
              {submitting ? 'Starting...' : 'Run Backtest'}
            </button>
          </form>
          {error && <p className="mt-4 text-xs text-rose-400 bg-rose-400/10 p-2 rounded-lg border border-rose-400/20">{error}</p>}
        </aside>

        {/* Results Area */}
        <section className="space-y-6">
          {/* Backtest History */}
          <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Recent Runs</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs uppercase tracking-widest border-b border-gray-800">
                    <th className="text-left py-2">Symbol</th>
                    <th className="text-left py-2">Date Range</th>
                    <th className="text-right py-2">P&L</th>
                    <th className="text-right py-2">Win Rate</th>
                    <th className="text-center py-2">Status</th>
                    <th className="text-right py-2">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/50">
                  {backtests.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="py-8 text-center text-gray-500 italic">No backtest history found.</td>
                    </tr>
                  ) : (
                    backtests.map(bt => (
                      <tr key={bt.id} className="hover:bg-white/5 transition-colors">
                        <td className="py-3 text-white font-medium">{bt.symbol}</td>
                        <td className="py-3 text-gray-400 text-xs">
                          {new Date(bt.start_date).toLocaleDateString()} - {new Date(bt.end_date).toLocaleDateString()}
                        </td>
                        <td className={`py-3 text-right font-semibold ${bt.total_pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {bt.total_pnl !== null ? formatCurrency(bt.total_pnl) : '—'}
                        </td>
                        <td className="py-3 text-right text-gray-300">
                          {bt.win_rate !== null ? formatPercent(bt.win_rate) : '—'}
                        </td>
                        <td className="py-3 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-bold border ${STATUS_COLORS[bt.status] || ''}`}>
                            {bt.status.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-3 text-right">
                          <button
                            onClick={() => viewDetails(bt.id)}
                            className="text-blue-400 hover:text-blue-300 text-xs font-semibold"
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Details View */}
          {selectedBacktest && (
            <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-6 animate-in fade-in slide-in-from-bottom-4">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-white">Simulation Details: Run #{selectedBacktest.id}</h2>
                <button 
                  onClick={() => setSelectedBacktest(null)}
                  className="text-gray-500 hover:text-white"
                >
                  Close
                </button>
              </div>

              {selectedBacktest.status === 'completed' ? (
                <div className="grid gap-6">
                  {/* Summary Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 rounded-xl bg-black/20 border border-gray-800">
                      <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Final Capital</p>
                      <p className="text-lg font-bold text-white">{formatCurrency(selectedBacktest.final_capital)}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-black/20 border border-gray-800">
                      <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Total Trades</p>
                      <p className="text-lg font-bold text-white">{selectedBacktest.total_trades}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-black/20 border border-gray-800">
                      <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Max Drawdown</p>
                      <p className="text-lg font-bold text-rose-400">{formatPercent(selectedBacktest.max_drawdown)}</p>
                    </div>
                    <div className="p-4 rounded-xl bg-black/20 border border-gray-800">
                      <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Win Rate</p>
                      <p className="text-lg font-bold text-emerald-400">{formatPercent(selectedBacktest.win_rate)}</p>
                    </div>
                  </div>

                  {/* Trade List */}
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Trade Execution Log</h3>
                    <div className="max-h-60 overflow-y-auto space-y-2 pr-2">
                      {selectedBacktest.results_json?.trades?.length > 0 ? (
                        selectedBacktest.results_json.trades.map((trade, idx) => (
                          <div key={idx} className="flex items-center justify-between p-3 rounded-xl bg-black/20 border border-gray-800 text-xs">
                            <div>
                              <p className="text-white font-medium">{trade.side.toUpperCase()} {trade.quantity.toFixed(4)} @ {formatCurrency(trade.entry_price)}</p>
                              <p className="text-gray-500 mt-0.5">{new Date(trade.entry_time).toLocaleString()}</p>
                            </div>
                            <div className="text-right">
                              <p className={`font-bold ${trade.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {trade.pnl >= 0 ? '+' : ''}{formatCurrency(trade.pnl)}
                              </p>
                              <p className="text-gray-500 mt-0.5">Exit @ {formatCurrency(trade.exit_price)}</p>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-center py-4 text-gray-500">No trades executed during this period.</p>
                      )}
                    </div>
                  </div>
                </div>
              ) : selectedBacktest.status === 'failed' ? (
                <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400">
                  <p className="font-semibold">Backtest failed</p>
                  <p className="mt-1 text-sm">{selectedBacktest.error_message}</p>
                </div>
              ) : (
                <div className="py-12 text-center text-gray-500">
                  <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4"></div>
                  <p>Backtest is currently running in the background...</p>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default Backtesting;
