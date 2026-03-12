import React, { useState, useEffect } from 'react';
import { performanceAPI } from '../../services/api';

const TradeHistoryTable = () => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchTrades = async () => {
      try {
        const response = await performanceAPI.trades(50);
        setTrades(response.data.trades || []);
      } catch (err) {
        console.error('Failed to fetch trade history:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchTrades();

    // SSE for new closed trades
    const eventSource = new EventSource(performanceAPI.streamURL, { withCredentials: true });
    eventSource.onmessage = (event) => {
      // When a new performance snapshot occurs (often triggered by a trade), 
      // refresh the trade history to show the latest closure.
      fetchTrades();
    };

    return () => eventSource.close();
  }, []);

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleString();
  };

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return 'N/A';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  const formatPercent = (val) => {
    if (val === null || val === undefined) return 'N/A';
    return `${(val * 100).toFixed(2)}%`;
  };

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 shadow-lg shadow-black/40 overflow-hidden">
      <div className="p-6 border-b border-gray-800 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Closed Trade History</h3>
        <span className="text-xs text-gray-400">{trades.length} recent trades</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-gray-950/50 text-xs uppercase tracking-wider text-gray-500">
            <tr>
              <th className="px-6 py-4 font-medium">Asset Pair</th>
              <th className="px-6 py-4 font-medium">Type</th>
              <th className="px-6 py-4 font-medium text-right">Entry Price</th>
              <th className="px-6 py-4 font-medium text-right">Exit Price</th>
              <th className="px-6 py-4 font-medium text-right">P&L (%)</th>
              <th className="px-6 py-4 font-medium text-right">P&L (Amount)</th>
              <th className="px-6 py-4 font-medium text-right">Closed At</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {loading ? (
              <tr>
                <td colSpan="7" className="px-6 py-10 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
                    <p className="text-gray-500 italic">Loading trades...</p>
                  </div>
                </td>
              </tr>
            ) : trades.length === 0 ? (
              <tr>
                <td colSpan="7" className="px-6 py-10 text-center text-gray-500 italic">
                  No closed trades found.
                </td>
              </tr>
            ) : (
              trades.map((trade) => {
                const isProfit = (trade.pnl || 0) >= 0;
                return (
                  <tr key={trade.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="px-6 py-4 font-medium text-white">{trade.symbol}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        trade.side === 'buy' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'
                      }`}>
                        {trade.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right text-gray-300 font-mono">{formatCurrency(trade.entry_price)}</td>
                    <td className="px-6 py-4 text-right text-gray-300 font-mono">{formatCurrency(trade.exit_price)}</td>
                    <td className={`px-6 py-4 text-right font-semibold font-mono ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {trade.pnl ? `${trade.pnl > 0 ? '+' : ''}${((trade.pnl / (trade.entry_price * trade.quantity)) * 100).toFixed(2)}%` : '0.00%'}
                    </td>
                    <td className={`px-6 py-4 text-right font-semibold font-mono ${isProfit ? 'text-emerald-400' : 'text-rose-400'}`}>
                      {trade.pnl ? `${trade.pnl > 0 ? '+' : ''}${formatCurrency(trade.pnl)}` : '$0.00'}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-500">{formatDate(trade.exit_time)}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default TradeHistoryTable;
