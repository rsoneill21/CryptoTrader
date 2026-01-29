import React, { useEffect, useMemo, useState } from 'react';
import Chart from '../components/Chart';
import api from '../services/api';

const TARGET_SYMBOL = 'BTC/USD';
const PRICE_SYMBOLS = ['BTC/USD', 'ETH/USD', 'SOL/USD', 'LTC/USD'];
const OVERLAY_POSITIONS = ['top-4 left-4', 'top-4 right-4', 'bottom-4 right-4'];

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
    maximumFractionDigits: 0,
  }).format(normalized);
};

const formatPercent = (value, digits = 1) => {
  if (typeof value !== 'number' && typeof value !== 'string') {
    return '0%';
  }

  const normalized = Number(value);
  if (!Number.isFinite(normalized)) {
    return '0%';
  }

  const sign = normalized > 0 ? '+' : normalized < 0 ? '' : '';
  return `${sign}${normalized.toFixed(digits)}%`;
};

const LiveTrading = () => {
  const [portfolio, setPortfolio] = useState(null);
  const [portfolioLoading, setPortfolioLoading] = useState(true);
  const [portfolioError, setPortfolioError] = useState('');
  const [priceTickers, setPriceTickers] = useState([]);
  const [pricesLoading, setPricesLoading] = useState(true);
  const [pricesError, setPricesError] = useState('');
  const [currentSymbol, setCurrentSymbol] = useState(TARGET_SYMBOL);

  useEffect(() => {
    let active = true;

    const loadPortfolio = async () => {
      setPortfolioLoading(true);
      setPortfolioError('');

      try {
        const response = await api.get('/api/market/portfolio');
        if (!active) {
          return;
        }

        setPortfolio(response.data);
      } catch (error) {
        if (!active) {
          return;
        }

        console.error('Live trading portfolio fetch failed', error);
        setPortfolioError(error?.message || 'Unable to load portfolio snapshot.');
      } finally {
        if (active) {
          setPortfolioLoading(false);
        }
      }
    };

    loadPortfolio();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    let intervalId;

    const loadPrices = async () => {
      setPricesError('');
      if (!priceTickers.length) {
        setPricesLoading(true);
      }

      try {
        const response = await api.get('/api/market/prices', {
          params: {
            symbol: PRICE_SYMBOLS,
          },
        });

        if (!active) {
          return;
        }

        const payload = Array.isArray(response.data?.prices) ? response.data.prices : [];
        setPriceTickers(payload);
      } catch (error) {
        if (!active) {
          return;
        }

        console.error('Live trading prices fetch failed', error);
        setPricesError(error?.message || 'Unable to load ticker data.');
      } finally {
        if (active) {
          setPricesLoading(false);
        }
      }
    };

    loadPrices();
    intervalId = window.setInterval(loadPrices, 45000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const livePositions = useMemo(() => {
    if (!portfolio?.holdings?.length) {
      return [];
    }

    return portfolio.holdings
      .map((holding) => {
        const quantity = parseNumber(holding.total);
        const symbol = `${holding.asset}/USD`;
        const ticker = priceMap.get(symbol);
        const lastPrice = ticker ? parseNumber(ticker.last) : null;
        const openPrice = ticker ? parseNumber(ticker.open_24h ?? ticker.open) : null;
        const valueUsd = lastPrice ? lastPrice * quantity : null;
        const changePercent = lastPrice && openPrice ? ((lastPrice - openPrice) / openPrice) * 100 : 0;
        const pnlUsd = valueUsd ? (valueUsd * changePercent) / 100 : 0;

        return {
          asset: holding.asset,
          symbol,
          quantity,
          valueUsd: valueUsd ?? 0,
          changePercent,
          pnlUsd,
          available: parseNumber(holding.available),
          reserved: parseNumber(holding.reserved),
          bias: changePercent >= 0 ? 'Long bias' : 'Hedged',
        };
      })
      .filter((entry) => entry.quantity > 0)
      .sort((a, b) => b.valueUsd - a.valueUsd)
      .slice(0, 5);
  }, [portfolio, priceMap]);

  const annotations = useMemo(() => {
    const fallback = [
      {
        id: 'awaiting',
        label: 'AI oversight',
        value: 'Live data pending',
        detail: 'Waiting for Kraken stream',
        confidence: 'Moderate',
      },
      {
        id: 'vault',
        label: 'Risk control',
        value: 'Stable',
        detail: 'Positions held steady',
        confidence: 'Medium',
      },
    ];

    if (!priceMap.size) {
      return fallback;
    }

    const cards = [];
    const primary = priceMap.get(currentSymbol);

    if (primary) {
      const last = parseNumber(primary.last);
      const open = parseNumber(primary.open_24h ?? primary.open);
      const momentum = open ? ((last - open) / open) * 100 : 0;

      cards.push({
        id: 'momentum',
        label: 'Momentum',
        value: formatPercent(momentum),
        detail: momentum >= 0 ? 'Bullish lift' : 'Pullback forming',
        confidence: momentum >= 0 ? 'High' : 'Medium',
      });
    }

    const sortedByChange = Array.from(priceMap.values())
      .map((ticker) => {
        const last = parseNumber(ticker.last);
        const open = parseNumber(ticker.open_24h ?? ticker.open);
        const change = open ? ((last - open) / open) * 100 : 0;
        return { symbol: ticker.symbol, change };
      })
      .sort((a, b) => b.change - a.change);

    if (sortedByChange.length >= 2) {
      const topGainer = sortedByChange[0];
      const topLoser = sortedByChange[sortedByChange.length - 1];

      cards.push({
        id: 'gainer',
        label: `${topGainer.symbol} trend`,
        value: `${formatPercent(topGainer.change)}`,
        detail: 'Strong relative strength',
        confidence: 'High',
      });

      cards.push({
        id: 'loser',
        label: `${topLoser.symbol} caution`,
        value: `${formatPercent(topLoser.change)}`,
        detail: 'Watch for reversal',
        confidence: 'Medium',
      });
    }

    return cards.slice(0, 3);
  }, [currentSymbol, priceMap]);

  const reasoningPoints = useMemo(() => {
    const points = [];

    if (annotations.length) {
      annotations.forEach((annotation) => {
        points.push(`${annotation.label}: ${annotation.detail} (${annotation.value}).`);
      });
    }

    if (livePositions.length) {
      const top = livePositions[0];
      points.push(`Largest position ${top.asset} (${top.bias}) pairs with ${formatCurrency(top.valueUsd)} exposure.`);
    }

    if (pricesError) {
      points.push('Price stream paused — relying on cached ticks until Kraken reconnects.');
    }

    if (!points.length) {
      points.push('Awaiting live feeds before AI can express trading rationale.');
    }

    return points.slice(0, 5);
  }, [annotations, livePositions, pricesError]);

  const stats = useMemo(() => {
    if (!currentTicker) {
      return [];
    }

    const last = parseNumber(currentTicker.last);
    const open = parseNumber(currentTicker.open_24h ?? currentTicker.open);
    const change = open ? last - open : 0;

    return [
      { label: 'Last price', value: formatCurrency(last) },
      { label: '24h change', value: formatPercent(((change / open) * 100) || 0), positive: change >= 0 },
      { label: 'Bid / Ask', value: `${formatCurrency(currentTicker.bid)} / ${formatCurrency(currentTicker.ask)}` },
      { label: '24h volume', value: `${Number(currentTicker.volume_24h || 0).toFixed(2)} ${currentSymbol.split('/')[0]}` },
    ];
  }, [currentSymbol, currentTicker]);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-xs uppercase tracking-[0.4em] text-blue-300">Phase 5</p>
        <h1 className="text-3xl font-bold text-white">Live Trading</h1>
        <p className="text-sm text-gray-400">
          Monitor the AI assistant, visualize the live chart, and keep tabs on your most active positions.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[3fr_1.2fr]">
        <section className="space-y-6">
          <div className="relative rounded-[28px] border border-gray-800 bg-gradient-to-b from-gray-900/80 to-black/70 p-6 shadow-2xl shadow-black/60">
            <div className="relative">
              <div className="pointer-events-none absolute inset-0 z-10">
                {annotations.map((annotation, index) => (
                  <div
                    key={`${annotation.id}-${index}`}
                    className={`absolute w-48 rounded-2xl border border-white/5 bg-black/70 px-4 py-3 text-sm text-gray-100 shadow-2xl backdrop-blur ${OVERLAY_POSITIONS[index % OVERLAY_POSITIONS.length]}`}
                  >
                    <p className="text-[10px] uppercase tracking-[0.3em] text-blue-300">{annotation.label}</p>
                    <p className="mt-1 text-lg font-semibold text-white">{annotation.value}</p>
                    <p className="text-xs text-gray-300">{annotation.detail}</p>
                    <p className="mt-1 text-[11px] uppercase tracking-[0.2em] text-green-300">Confidence {annotation.confidence}</p>
                  </div>
                ))}
              </div>

              <Chart symbol={currentSymbol} />
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-4">
              {stats.length ? (
                stats.map((stat) => (
                  <div key={stat.label} className="rounded-2xl border border-gray-800 bg-gray-900/60 p-3 text-sm">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-500">{stat.label}</p>
                    <p className={`mt-1 text-lg font-semibold ${stat.positive === false ? 'text-rose-400' : 'text-emerald-400'}`}>{stat.value}</p>
                  </div>
                ))
              ) : (
                <div className="rounded-2xl border border-dashed border-gray-600 bg-gray-900/40 p-4 text-xs text-gray-400">
                  {pricesLoading ? 'Connecting to price feed…' : 'Select a market to view live stats.'}
                </div>
              )}
            </div>

            <div className="mt-6 flex flex-wrap gap-2">
              {PRICE_SYMBOLS.map((symbolOption) => (
                <button
                  key={symbolOption}
                  type="button"
                  onClick={() => setCurrentSymbol(symbolOption)}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                    currentSymbol === symbolOption
                      ? 'border-blue-400 bg-blue-500/20 text-blue-200'
                      : 'border-gray-700 bg-white/5 text-gray-300 hover:border-blue-300 hover:text-white'
                  }`}
                >
                  {symbolOption}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[28px] border border-gray-800 bg-gray-900/60 px-4 py-5 shadow-inner shadow-black/40">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-gray-500">Positions</p>
                <h2 className="text-xl font-semibold text-white">Live holdings</h2>
              </div>
              <p className="text-xs text-gray-400">
                {portfolio?.fetched_at
                  ? `Updated ${new Date(portfolio.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                  : 'Syncing…'}
              </p>
            </div>

            <div className="mt-4 space-y-3">
              {portfolioLoading ? (
                <p className="text-sm text-gray-400">Loading portfolio snapshot…</p>
              ) : portfolioError ? (
                <p className="text-sm text-rose-300">{portfolioError}</p>
              ) : livePositions.length ? (
                livePositions.map((position) => (
                  <div
                    key={position.asset}
                    className="flex items-center justify-between rounded-2xl border border-gray-800 bg-gray-950/70 p-3"
                  >
                    <div>
                      <p className="text-sm font-semibold text-white">{position.asset}</p>
                      <p className="text-xs text-gray-400">{position.symbol}</p>
                      <p className="text-xs text-gray-500">{position.bias}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm text-gray-300">{position.quantity.toFixed(4)} · {formatCurrency(position.valueUsd)}</p>
                      <p className={`${position.changePercent >= 0 ? 'text-emerald-400' : 'text-rose-400'} text-xs`}>Δ {formatPercent(position.changePercent)}</p>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-gray-400">No active positions detected yet.</p>
              )}
            </div>
          </div>
        </section>

        <section className="space-y-5 rounded-[28px] border border-gray-800 bg-gray-900/60 p-6 shadow-xl shadow-black/50">
          <div>
            <p className="text-xs uppercase tracking-[0.4em] text-blue-300">AI reasoning</p>
            <h2 className="text-2xl font-semibold text-white">Why trade now?</h2>
            <p className="text-sm text-gray-400">Insights guided by the market analyst agent.</p>
          </div>

          <ul className="space-y-4 text-sm text-gray-200">
            {reasoningPoints.map((point, index) => (
              <li key={`reason-${index}`} className="rounded-2xl border border-gray-800 bg-gray-950/80 p-4 text-gray-200">
                {point}
              </li>
            ))}
          </ul>

          <div className="rounded-2xl border border-dashed border-blue-500/50 bg-gradient-to-b from-blue-900/40 to-black/40 p-4 text-sm text-gray-200">
            <p className="font-semibold text-white">AI confidence</p>
            <p className="text-xs text-gray-400">
              {annotations[0]?.confidence ? `${annotations[0].confidence} across highlighted signals` : 'Awaiting signal quality score.'}
            </p>
          </div>
        </section>
      </div>
    </div>
  );
};

export default LiveTrading;
