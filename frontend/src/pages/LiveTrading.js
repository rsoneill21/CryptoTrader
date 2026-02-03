import React, { useEffect, useMemo, useState, useCallback } from 'react';
import Chart from '../components/Chart';
import PositionManager from '../components/PositionManager';
import { marketAPI, tradesAPI, systemAPI } from '../services/api';

const TARGET_SYMBOL = 'BTC/USD';
const PRICE_SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'LTC/USD', 'XRP/USD', 'ADA/USD'];

const parseNumber = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const formatCurrency = (value) => {
  if (typeof value !== 'number' && typeof value !== 'string') {
    return '—';
  }

  const normalized = parseNumber(value);
  if (!Number.isFinite(normalized)) {
    return '—';
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(normalized);
};

const LiveTrading = () => {
  const [portfolio, setPortfolio] = useState(null);
  const [portfolioLoading, setPortfolioLoading] = useState(true);
  const [priceTickers, setPriceTickers] = useState([]);
  const [currentSymbol, setCurrentSymbol] = useState(TARGET_SYMBOL);
  const [connectionStatus, setConnectionStatus] = useState(null);

  // Manual trade form state
  const [tradeSide, setTradeSide] = useState('buy');
  const [tradeQuantity, setTradeQuantity] = useState('');
  const [tradeLoading, setTradeLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [portfolioRes, pricesRes, connRes] = await Promise.all([
        marketAPI.getPortfolio(),
        marketAPI.getPrices(PRICE_SYMBOLS),
        systemAPI.connectionStatus().catch(() => null),
      ]);

      setPortfolio(portfolioRes.data);
      setPriceTickers(pricesRes.data?.prices || []);
      if (connRes?.data) setConnectionStatus(connRes.data);
    } catch (error) {
      console.error('Failed to fetch live trading data', error);
    } finally {
      setPortfolioLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [fetchData]);

  const priceMap = useMemo(() => {
    const map = new Map();
    priceTickers.forEach((ticker) => {
      if (ticker?.symbol) {
        map.set(ticker.symbol, ticker);
      }
    });
    return map;
  }, [priceTickers]);

  const currentTicker = priceMap.get(currentSymbol);

  const handleCreateTrade = async (e) => {
    e.preventDefault();
    if (!tradeQuantity || parseNumber(tradeQuantity) <= 0) return;

    setTradeLoading(true);
    try {
      await tradesAPI.createTrade({
        symbol: currentSymbol,
        side: tradeSide,
        quantity: parseNumber(tradeQuantity),
        is_paper: true,
      });
      setTradeQuantity('');
      fetchData();
    } catch (error) {
      console.error('Failed to execute trade', error);
      alert('Trade execution failed: ' + (error.message || 'Unknown error'));
    } finally {
      setTradeLoading(false);
    }
  };

  const livePositions = useMemo(() => {
    if (!portfolio?.holdings?.length) return [];

    return portfolio.holdings
      .map((holding) => {
        const quantity = parseNumber(holding.total);
        const symbol = `${holding.asset}/USD`;
        const ticker = priceMap.get(symbol);
        const lastPrice = ticker ? parseNumber(ticker.last) : null;
        const valueUsd = lastPrice ? lastPrice * quantity : 0;

        return {
          asset: holding.asset,
          symbol,
          quantity,
          valueUsd,
          available: parseNumber(holding.available),
        };
      })
      .filter((entry) => entry.quantity > 0.0001)
      .sort((a, b) => b.valueUsd - a.valueUsd);
  }, [portfolio, priceMap]);

  return (
    <div className="space-y-6">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.4em] text-blue-400">Live Trading</p>
          <h1 className="text-3xl font-bold text-white">Execution Terminal</h1>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-gray-800 bg-black/20">
            <div className={`h-2 w-2 rounded-full ${connectionStatus?.reachable ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]' : connectionStatus?.authenticated ? 'bg-amber-400' : 'bg-gray-600'}`} />
            <span className="text-[10px] uppercase tracking-widest text-gray-400">
              {connectionStatus?.reachable ? 'Connected' : connectionStatus?.authenticated ? 'Disconnected' : 'No API Key'}
            </span>
            {connectionStatus?.latency_ms && (
              <span className="text-[10px] text-gray-600">{connectionStatus.latency_ms}ms</span>
            )}
          </div>
          <div className="h-8 w-px bg-gray-800" />
          <div className="text-right">
            <p className="text-gray-500 uppercase text-[10px] tracking-widest">Portfolio Value</p>
            <p className="text-white font-semibold">{portfolio ? formatCurrency(portfolio.total_value_usd) : '—'}</p>
          </div>
          <div className="h-8 w-px bg-gray-800" />
          <div className="text-right">
            <p className="text-gray-500 uppercase text-[10px] tracking-widest">Available Cash</p>
            <p className="text-emerald-400 font-semibold">{portfolio ? formatCurrency(portfolio.holdings.find(h => h.asset === 'USD')?.available || 0) : '—'}</p>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_350px]">
        {/* Main Content Area */}
        <div className="space-y-6">
          {/* Chart & Market Stats */}
          <div className="rounded-[32px] border border-gray-800 bg-gray-900/40 p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 rounded-xl bg-blue-500/20 flex items-center justify-center text-blue-400 font-bold">
                  {currentSymbol.split('/')[0]}
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">{currentSymbol}</h2>
                  <p className="text-xs text-gray-400 uppercase tracking-tighter">Kraken Spot</p>
                </div>
              </div>
              <div className="flex gap-2">
                {PRICE_SYMBOLS.slice(0, 4).map(s => (
                  <button
                    key={s}
                    onClick={() => setCurrentSymbol(s)}
                    className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider transition ${currentSymbol === s ? 'bg-blue-500 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
                  >
                    {s.split('/')[0]}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-[400px] w-full rounded-2xl overflow-hidden border border-gray-800 bg-black/40">
              <Chart symbol={currentSymbol} />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
              {[
                { label: 'Last Price', value: formatCurrency(currentTicker?.last), color: 'text-white' },
                { label: '24h High', value: formatCurrency(currentTicker?.high_24h), color: 'text-gray-300' },
                { label: '24h Low', value: formatCurrency(currentTicker?.low_24h), color: 'text-gray-300' },
                { label: '24h Volume', value: `${parseNumber(currentTicker?.volume_24h).toFixed(2)} ${currentSymbol.split('/')[0]}`, color: 'text-gray-300' },
              ].map(stat => (
                <div key={stat.label} className="p-3 rounded-2xl bg-black/20 border border-gray-800">
                  <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">{stat.label}</p>
                  <p className={`text-sm font-bold ${stat.color}`}>{stat.value || '—'}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Active Trades — managed by PositionManager */}
          <PositionManager />
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Manual Trade Form */}
          <div className="rounded-[32px] border border-gray-800 bg-gray-900/40 p-6">
            <h2 className="text-xl font-bold text-white mb-6">Trade</h2>
            <form onSubmit={handleCreateTrade} className="space-y-4">
              <div className="grid grid-cols-2 gap-2 p-1 bg-black/40 rounded-2xl border border-gray-800">
                <button
                  type="button"
                  onClick={() => setTradeSide('buy')}
                  className={`py-2 rounded-xl text-xs font-bold uppercase transition ${tradeSide === 'buy' ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-900/40' : 'text-gray-500 hover:text-gray-300'}`}
                >
                  Buy
                </button>
                <button
                  type="button"
                  onClick={() => setTradeSide('sell')}
                  className={`py-2 rounded-xl text-xs font-bold uppercase transition ${tradeSide === 'sell' ? 'bg-rose-500 text-white shadow-lg shadow-rose-900/40' : 'text-gray-500 hover:text-gray-300'}`}
                >
                  Sell
                </button>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-widest text-gray-500 ml-1">Asset</label>
                <div className="relative">
                  <select
                    value={currentSymbol}
                    onChange={(e) => setCurrentSymbol(e.target.value)}
                    className="w-full bg-black/40 border border-gray-800 rounded-2xl py-3 px-4 text-white text-sm focus:outline-none focus:border-blue-500 appearance-none"
                  >
                    {PRICE_SYMBOLS.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-gray-500">
                    ↓
                  </div>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] uppercase tracking-widest text-gray-500 ml-1">Quantity</label>
                <div className="relative">
                  <input
                    type="number"
                    step="any"
                    value={tradeQuantity}
                    onChange={(e) => setTradeQuantity(e.target.value)}
                    placeholder="0.00"
                    className="w-full bg-black/40 border border-gray-800 rounded-2xl py-3 px-4 text-white text-sm focus:outline-none focus:border-blue-500"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-bold text-gray-500 uppercase">
                    {currentSymbol.split('/')[0]}
                  </span>
                </div>
              </div>

              <div className="pt-2">
                <div className="flex justify-between text-[10px] text-gray-500 uppercase tracking-widest mb-2 px-1">
                  <span>Est. Cost</span>
                  <span>{formatCurrency(parseNumber(tradeQuantity) * (currentTicker?.last || 0))}</span>
                </div>
                <button
                  type="submit"
                  disabled={tradeLoading || !tradeQuantity}
                  className={`w-full py-4 rounded-[20px] font-bold uppercase tracking-widest text-sm transition ${tradeSide === 'buy' ? 'bg-emerald-500 hover:bg-emerald-400 text-white' : 'bg-rose-500 hover:bg-rose-400 text-white'} disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  {tradeLoading ? 'Processing...' : `${tradeSide === 'buy' ? 'Execute Buy' : 'Execute Sell'}`}
                </button>
              </div>
            </form>
          </div>

          {/* Portfolio Breakdown */}
          <div className="rounded-[32px] border border-gray-800 bg-gray-900/40 p-6">
            <h2 className="text-xl font-bold text-white mb-6">Holdings</h2>
            <div className="space-y-3">
              {portfolioLoading ? (
                <p className="text-center text-xs text-gray-500 py-4">Loading holdings...</p>
              ) : livePositions.length === 0 ? (
                <p className="text-center text-xs text-gray-500 py-4">No assets held.</p>
              ) : (
                livePositions.map(pos => (
                  <div key={pos.asset} className="flex items-center justify-between p-3 rounded-2xl bg-black/20 border border-gray-800">
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-lg bg-gray-800 flex items-center justify-center text-[10px] font-bold text-gray-300">
                        {pos.asset}
                      </div>
                      <div>
                        <p className="text-xs font-bold text-white">{pos.asset}</p>
                        <p className="text-[10px] text-gray-500">{pos.quantity.toFixed(4)}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xs font-bold text-white">{formatCurrency(pos.valueUsd)}</p>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LiveTrading;