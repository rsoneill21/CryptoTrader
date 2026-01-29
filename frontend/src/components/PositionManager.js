import React, { useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const formatCurrency = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—';
  }
  return currencyFormatter.format(value);
};

const formatDateTime = (value) => {
  if (!value) {
    return '—';
  }
  try {
    return new Date(value).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (error) {
    return '—';
  }
};

const formatQuantity = (value) => {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(4);
};

const createInitialCloseState = () => ({
  tradeId: null,
  exitPrice: '',
  reason: '',
  submitting: false,
  error: '',
});

const createInitialAdjustState = () => ({
  tradeId: null,
  stopLoss: '',
  takeProfit: '',
  note: '',
  submitting: false,
  error: '',
});

const PositionManager = () => {
  const [positions, setPositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [closeState, setCloseState] = useState(createInitialCloseState);
  const [adjustState, setAdjustState] = useState(createInitialAdjustState);

  const fetchPositions = async () => {
    setLoading(true);
    setFetchError('');

    try {
      const response = await api.get('/api/trades/active');
      setPositions(response.data ?? []);
    } catch (error) {
      setFetchError(error.message || 'Unable to load active positions.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPositions();
  }, []);

  const totalPnl = useMemo(() => {
    return positions.reduce((sum, trade) => {
      const pnl = Number(trade.pnl);
      if (Number.isFinite(pnl)) {
        return sum + pnl;
      }
      return sum;
    }, 0);
  }, [positions]);

  const openCloseForm = (tradeId) => {
    setCloseState({
      ...createInitialCloseState(),
      tradeId,
    });
    setAdjustState(createInitialAdjustState());
  };

  const openAdjustForm = (tradeId) => {
    setAdjustState({
      ...createInitialAdjustState(),
      tradeId,
    });
    setCloseState(createInitialCloseState());
  };

  const handleCloseSubmit = async (event) => {
    event.preventDefault();
    if (!closeState.tradeId) {
      return;
    }

    const exitPrice = parseFloat(closeState.exitPrice);
    if (!Number.isFinite(exitPrice) || exitPrice <= 0) {
      setCloseState((prev) => ({
        ...prev,
        error: 'Enter a valid exit price above zero.',
      }));
      return;
    }

    setCloseState((prev) => ({ ...prev, submitting: true, error: '' }));

    try {
      const payload = {
        exit_price: exitPrice,
      };
      if (closeState.reason.trim()) {
        payload.reason = closeState.reason.trim();
      }

      const response = await api.post(
        `/api/trades/${closeState.tradeId}/close`,
        payload
      );

      setStatusMessage(response?.data?.message || 'Position closed.');
      setCloseState(createInitialCloseState());
      await fetchPositions();
    } catch (error) {
      setCloseState((prev) => ({
        ...prev,
        error: error.message || 'Unable to close the position.',
      }));
    } finally {
      setCloseState((prev) => ({ ...prev, submitting: false }));
    }
  };

  const handleAdjustSubmit = async (event) => {
    event.preventDefault();
    if (!adjustState.tradeId) {
      return;
    }

    const stopLossValue = adjustState.stopLoss.trim();
    const takeProfitValue = adjustState.takeProfit.trim();

    if (!stopLossValue && !takeProfitValue) {
      setAdjustState((prev) => ({
        ...prev,
        error: 'Provide a stop loss or take profit level.',
      }));
      return;
    }

    const payload = {};
    if (stopLossValue) {
      const parsed = parseFloat(stopLossValue);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        setAdjustState((prev) => ({
          ...prev,
          error: 'Stop loss must be a positive number.',
        }));
        return;
      }
      payload.stop_loss = parsed;
    }

    if (takeProfitValue) {
      const parsed = parseFloat(takeProfitValue);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        setAdjustState((prev) => ({
          ...prev,
          error: 'Take profit must be a positive number.',
        }));
        return;
      }
      payload.take_profit = parsed;
    }

    if (adjustState.note.trim()) {
      payload.note = adjustState.note.trim();
    }

    setAdjustState((prev) => ({ ...prev, submitting: true, error: '' }));

    try {
      const response = await api.put(
        `/api/trades/${adjustState.tradeId}/adjust`,
        payload
      );

      setStatusMessage(response?.data?.message || 'Adjustment saved.');
      setAdjustState(createInitialAdjustState);
      await fetchPositions();
    } catch (error) {
      setAdjustState((prev) => ({
        ...prev,
        error: error.message || 'Unable to save adjustments.',
      }));
    } finally {
      setAdjustState((prev) => ({ ...prev, submitting: false }));
    }
  };

  const renderOrders = (orders) => {
    if (!orders?.length) {
      return null;
    }

    return (
      <div className="flex flex-wrap gap-2">
        {orders.map((order) => (
          <span
            className="rounded-full border border-gray-700 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-gray-300"
            key={order.id}
          >
            {order.side} {order.order_type} · {order.status}
          </span>
        ))}
      </div>
    );
  };

  return (
    <section className="space-y-6">
      <header className="flex flex-col gap-3 rounded-2xl border border-gray-800 bg-gray-900/80 p-5 shadow-sm shadow-black/30">
        <div className="flex flex-col gap-2 md:flex-row md:items-baseline md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-emerald-400">
              Active Positions
            </p>
            <p className="text-2xl font-bold text-white">
              {positions.length} open {positions.length === 1 ? 'position' : 'positions'}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-gray-400">
              Total P&L
            </p>
            <p
              className={`text-3xl font-semibold ${
                totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
              }`}
            >
              {formatCurrency(totalPnl)}
            </p>
            <p className="text-xs text-gray-500">
              Calculated from reported trade delta
            </p>
          </div>
        </div>
        {statusMessage && (
          <p className="rounded-lg border border-emerald-500/60 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300">
            {statusMessage}
          </p>
        )}
      </header>

      {fetchError && (
        <div className="rounded-lg border border-rose-500/60 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {fetchError}
        </div>
      )}

      <div className="rounded-3xl border border-gray-800 bg-gray-900/60 p-5">
        {loading ? (
          <div className="flex items-center justify-center py-10 text-sm text-gray-400">
            Fetching positions…
          </div>
        ) : positions.length === 0 ? (
          <div className="flex flex-col gap-2 text-sm text-gray-400">
            <p>No active positions right now.</p>
            <p>When strategies run, you'll see their live state here.</p>
          </div>
        ) : (
          <div className="space-y-5">
            {positions.map((trade) => (
              <article
                key={trade.id}
                className="rounded-2xl border border-gray-800 bg-gradient-to-br from-gray-950/80 to-gray-900 p-5 shadow-[0_0_30px_rgba(0,0,0,0.4)]"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <div className="space-y-1">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-500">
                      {trade.strategy_id ? `Strategy #${trade.strategy_id}` : 'Manual Entry'}
                    </p>
                    <p className="text-2xl font-semibold text-white">{trade.symbol}</p>
                    <p className="text-sm text-gray-400">
                      {trade.side} · {formatQuantity(trade.quantity)} @{' '}
                      {formatCurrency(trade.entry_price)}
                    </p>
                    <p className="text-xs text-gray-500">Entered {formatDateTime(trade.entry_time)}</p>
                  </div>
                  <div className="text-right">
                    <p
                      className={`text-lg font-bold ${
                        (trade.pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}
                    >
                      {formatCurrency(trade.pnl)}
                    </p>
                    <p className="text-xs uppercase tracking-[0.4em] text-gray-500">Live P&L</p>
                  </div>
                </div>

                <div className="mt-4 space-y-3 text-xs text-gray-400">
                  {renderOrders(trade.orders)}
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded-full border border-indigo-500/60 bg-indigo-500/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-indigo-200 transition hover:border-indigo-400/80"
                      onClick={() => openCloseForm(trade.id)}
                    >
                      Close Trade
                    </button>
                    <button
                      type="button"
                      className="rounded-full border border-sky-500/60 bg-sky-500/10 px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-sky-200 transition hover:border-sky-400/80"
                      onClick={() => openAdjustForm(trade.id)}
                    >
                      Adjust Levels
                    </button>
                  </div>
                </div>

                {closeState.tradeId === trade.id && (
                  <form onSubmit={handleCloseSubmit} className="mt-5 space-y-3 rounded-2xl border border-gray-800 bg-gray-950/80 p-4">
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="text-sm text-gray-300">
                        Exit price
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={closeState.exitPrice}
                          onChange={(event) =>
                            setCloseState((prev) => ({
                              ...prev,
                              exitPrice: event.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-xl border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white outline-none transition focus:border-indigo-500"
                        />
                      </label>
                      <label className="text-sm text-gray-300">
                        Exit reason
                        <input
                          type="text"
                          maxLength={256}
                          placeholder="Optional notes"
                          value={closeState.reason}
                          onChange={(event) =>
                            setCloseState((prev) => ({
                              ...prev,
                              reason: event.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-xl border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white outline-none transition focus:border-indigo-500"
                        />
                      </label>
                    </div>
                    {closeState.error && (
                      <p className="text-xs font-semibold text-rose-300">
                        {closeState.error}
                      </p>
                    )}
                    <div className="flex flex-wrap justify-end gap-3">
                      <button
                        type="button"
                        className="rounded-xl border border-gray-700 px-4 py-2 text-sm font-semibold text-gray-200 hover:border-gray-500"
                        onClick={() => setCloseState(createInitialCloseState)}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={closeState.submitting}
                        className="rounded-xl bg-rose-500/90 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:opacity-70"
                      >
                        {closeState.submitting ? 'Closing…' : 'Close Position'}
                      </button>
                    </div>
                  </form>
                )}

                {adjustState.tradeId === trade.id && (
                  <form onSubmit={handleAdjustSubmit} className="mt-5 space-y-3 rounded-2xl border border-gray-800 bg-gray-950/80 p-4">
                    <div className="grid gap-3 md:grid-cols-3">
                      <label className="text-sm text-gray-300">
                        Stop loss
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={adjustState.stopLoss}
                          onChange={(event) =>
                            setAdjustState((prev) => ({
                              ...prev,
                              stopLoss: event.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-xl border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500"
                        />
                      </label>
                      <label className="text-sm text-gray-300">
                        Take profit
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={adjustState.takeProfit}
                          onChange={(event) =>
                            setAdjustState((prev) => ({
                              ...prev,
                              takeProfit: event.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-xl border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500"
                        />
                      </label>
                      <label className="text-sm text-gray-300">
                        Note
                        <input
                          type="text"
                          maxLength={256}
                          placeholder="Optional note"
                          value={adjustState.note}
                          onChange={(event) =>
                            setAdjustState((prev) => ({
                              ...prev,
                              note: event.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-xl border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white outline-none transition focus:border-sky-500"
                        />
                      </label>
                    </div>
                    {adjustState.error && (
                      <p className="text-xs font-semibold text-rose-300">
                        {adjustState.error}
                      </p>
                    )}
                    <div className="flex flex-wrap justify-end gap-3">
                      <button
                        type="button"
                        className="rounded-xl border border-gray-700 px-4 py-2 text-sm font-semibold text-gray-200 hover:border-gray-500"
                        onClick={() => setAdjustState(createInitialAdjustState)}
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={adjustState.submitting}
                        className="rounded-xl bg-sky-500/90 px-4 py-2 text-sm font-semibold text-white transition hover:bg-sky-400 disabled:cursor-not-allowed disabled:opacity-70"
                      >
                        {adjustState.submitting ? 'Saving…' : 'Save Adjustments'}
                      </button>
                    </div>
                  </form>
                )}
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};

export default PositionManager;
