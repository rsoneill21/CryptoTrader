import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { isKrakenThrottleError, normalizeTradeErrorOutcome, normalizeTradeOutcome, tradesAPI } from '../services/api';

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const percentFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const formatCurrency = (value) => {
  if (!Number.isFinite(Number(value))) {
    return '—';
  }
  return currencyFormatter.format(Number(value));
};

const formatPercent = (value) => {
  if (!Number.isFinite(Number(value))) {
    return '—';
  }
  return `${percentFormatter.format(Number(value))}%`;
};

const formatQuantity = (value) => {
  if (!Number.isFinite(Number(value))) {
    return '—';
  }
  return Number(value).toFixed(4);
};

const parseNumber = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const formatOrderSide = (value) => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return 'UNKNOWN';
  }
  return value.toUpperCase();
};

const formatOrderSymbol = (value) => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    return 'Unknown Symbol';
  }
  return value;
};

const PositionManager = ({ onOutcome }) => {
  const [positions, setPositions] = useState([]);
  const [pendingOrders, setPendingOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedRows, setExpandedRows] = useState({});
  const [highlightRows, setHighlightRows] = useState({});
  const [toast, setToast] = useState(null);
  const [closeDraft, setCloseDraft] = useState({ tradeId: null, quantity: '', closeReason: '' });
  const [confirmCloseOpen, setConfirmCloseOpen] = useState(false);
  const [closeSubmitting, setCloseSubmitting] = useState(false);
  const [retryPayload, setRetryPayload] = useState(null);
  const [pendingSyncNotice, setPendingSyncNotice] = useState('');
  const previousPendingSnapshotRef = useRef([]);

  const emitPendingLifecycleOutcomes = useCallback((nextPending) => {
    if (typeof onOutcome !== 'function') {
      previousPendingSnapshotRef.current = nextPending;
      return;
    }

    const previous = previousPendingSnapshotRef.current;
    if (!previous.length) {
      previousPendingSnapshotRef.current = nextPending;
      return;
    }

    const previousById = new Map(previous.map((item) => [item.id, item]));
    nextPending.forEach((order) => {
      const prior = previousById.get(order.id);
      if (!prior) {
        return;
      }

      const statusChanged = String(prior.status || '').toLowerCase() !== String(order.status || '').toLowerCase();
      const fillChanged = parseNumber(prior.filled_quantity) !== parseNumber(order.filled_quantity);
      if (!statusChanged && !fillChanged) {
        return;
      }

      onOutcome(
        normalizeTradeOutcome(
          {
            id: order.id,
            order_id: order.id,
            trade_id: order.trade_id,
            symbol: order.trade_symbol,
            side: order.side,
            status: order.status,
            reason_code: order.reason_code,
            reason_message: order.reason_message,
            updated_at: order.updated_at,
          },
          {
            source: 'pending_refresh',
            symbol: order.trade_symbol,
            side: order.side,
          }
        )
      );
    });

    previousPendingSnapshotRef.current = nextPending;
  }, [onOutcome]);

  const fetchData = useCallback(async () => {
    try {
      const activeResponse = await tradesAPI.getActiveTrades();
      const nextPositions = activeResponse?.data || [];

      setPositions((previous) => {
        const previousIds = new Set(previous.map((item) => item.id));
        const nextIds = new Set(nextPositions.map((item) => item.id));
        const merged = {};

        nextPositions.forEach((item) => {
          if (!previousIds.has(item.id)) {
            merged[item.id] = 'new';
          }
        });

        previous.forEach((item) => {
          if (!nextIds.has(item.id)) {
            merged[item.id] = 'closed';
          }
        });

        if (Object.keys(merged).length > 0) {
          setHighlightRows(merged);
          setTimeout(() => {
            setHighlightRows({});
          }, 2800);
        }

        return nextPositions;
      });

      setError('');
    } catch (requestError) {
      setError(requestError.message || 'Unable to load positions.');
    }

    try {
      const pendingResponse = await tradesAPI.listPendingOrders();
      const nextPending = pendingResponse?.data || [];
      emitPendingLifecycleOutcomes(nextPending);

      setPendingOrders(nextPending);
      setPendingSyncNotice('');
    } catch (requestError) {
      if (isKrakenThrottleError(requestError)) {
        setPendingSyncNotice('Kraken is rate-limited. Showing last synced pending orders until exchange budget recovers.');
      } else {
        setError(requestError.message || 'Unable to load positions.');
      }
    } finally {
      setLoading(false);
    }
  }, [emitPendingLifecycleOutcomes]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 12000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }
    const timer = setTimeout(() => {
      setToast(null);
    }, 5000);
    return () => clearTimeout(timer);
  }, [toast]);

  const totalPnl = useMemo(() => {
    return positions.reduce((sum, position) => {
      const pnl = parseNumber(position.pnl);
      return sum + pnl;
    }, 0);
  }, [positions]);

  const openCloseDialog = (position) => {
    setRetryPayload(null);
    setCloseDraft({
      tradeId: position.id,
      quantity: String(position.quantity),
      closeReason: '',
    });
    setConfirmCloseOpen(true);
  };

  const submitClose = async (payload) => {
    setCloseSubmitting(true);
    try {
      const response = await tradesAPI.closePosition(payload.tradeId, {
        quantity: parseNumber(payload.quantity),
        close_reason: payload.closeReason?.trim() || undefined,
      });

      const outcome = normalizeTradeOutcome(response?.data, {
        source: 'position_close',
        status: 'filled',
      });

      if (typeof onOutcome === 'function') {
        onOutcome(outcome);
      }

      setConfirmCloseOpen(false);
      setCloseDraft({ tradeId: null, quantity: '', closeReason: '' });
      setHighlightRows((previous) => ({ ...previous, [payload.tradeId]: 'new' }));
      setToast({ type: 'success', message: 'Position closed successfully.' });
      await fetchData();
    } catch (requestError) {
      const outcome = normalizeTradeErrorOutcome(requestError, {
        source: 'position_close',
        tradeId: payload.tradeId,
      });
      if (typeof onOutcome === 'function') {
        onOutcome(outcome);
      }

      setRetryPayload(payload);
      setToast({
        type: 'error',
        message: outcome.reasonMessage || 'Close failed. Try again.',
      });
      setConfirmCloseOpen(false);
    } finally {
      setCloseSubmitting(false);
    }
  };

  const confirmClose = async () => {
    if (!closeDraft.tradeId) {
      return;
    }
    if (parseNumber(closeDraft.quantity) <= 0) {
      setToast({ type: 'error', message: 'Quantity must be greater than zero.' });
      return;
    }

    await submitClose(closeDraft);
  };

  const retryClose = async () => {
    if (!retryPayload) {
      return;
    }
    await submitClose(retryPayload);
  };

  return (
    <section className="space-y-6">
      <header className="rounded-2xl border border-gray-800 bg-gray-900/80 p-5 shadow-sm shadow-black/30">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wide text-emerald-400">Active Positions</p>
            <p className="text-2xl font-bold text-white">{positions.length} open</p>
          </div>
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-gray-400">Total P&L</p>
            <p className={`text-3xl font-semibold ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {formatCurrency(totalPnl)}
            </p>
          </div>
        </div>
      </header>

      {error && (
        <div className="rounded-lg border border-rose-500/60 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <div className="rounded-3xl border border-gray-800 bg-gray-900/60 p-5">
        <h3 className="text-lg font-semibold text-white">Open Positions</h3>
        {loading ? (
          <div className="py-8 text-sm text-gray-400">Loading positions…</div>
        ) : positions.length === 0 ? (
          <div className="py-8 text-sm text-gray-400">No active positions.</div>
        ) : (
          <>
            <div className="hidden md:block mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-500 text-xs uppercase tracking-widest border-b border-gray-800">
                    <th className="text-left py-2">Symbol</th>
                    <th className="text-left py-2">Side</th>
                    <th className="text-right py-2">Quantity</th>
                    <th className="text-right py-2">Entry</th>
                    <th className="text-right py-2">P&L</th>
                    <th className="text-right py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position) => {
                    const pnl = parseNumber(position.pnl);
                    const pnlPercent = position.entry_price
                      ? (pnl / (parseNumber(position.entry_price) * parseNumber(position.quantity))) * 100
                      : 0;
                    const isExpanded = Boolean(expandedRows[position.id]);
                    const highlightClass = highlightRows[position.id]
                      ? 'ring-2 ring-blue-400/50'
                      : '';

                    return (
                      <React.Fragment key={position.id}>
                        <tr className={`border-b border-gray-900 ${highlightClass}`}>
                          <td className="py-3 text-white font-semibold">
                            <button
                              type="button"
                              onClick={() => setExpandedRows((prev) => ({ ...prev, [position.id]: !isExpanded }))}
                              className="hover:text-blue-300 transition"
                            >
                              {position.symbol}
                            </button>
                          </td>
                          <td className="py-3 uppercase text-gray-300">{position.side}</td>
                          <td className="py-3 text-right text-gray-200">{formatQuantity(position.quantity)}</td>
                          <td className="py-3 text-right text-gray-200">{formatCurrency(position.entry_price)}</td>
                          <td className={`py-3 text-right font-semibold ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {formatCurrency(pnl)}
                            <span className="ml-2 text-xs text-gray-500">{formatPercent(pnlPercent)}</span>
                          </td>
                          <td className="py-3 text-right">
                            <button
                              type="button"
                              onClick={() => openCloseDialog(position)}
                              className="rounded-full border border-rose-500/60 bg-rose-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-rose-200 hover:border-rose-400/80"
                            >
                              Close
                            </button>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="bg-black/20">
                            <td colSpan={6} className="px-3 py-3 text-xs text-gray-400">
                              Trade ID #{position.id} · Entered {new Date(position.entry_time).toLocaleString()} · Source {position.trade_source}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="md:hidden mt-4 space-y-3">
              {positions.map((position) => {
                const pnl = parseNumber(position.pnl);
                const highlightClass = highlightRows[position.id] ? 'ring-2 ring-blue-400/50' : '';
                return (
                  <article
                    key={position.id}
                    className={`rounded-2xl border border-gray-800 bg-black/20 p-4 ${highlightClass}`}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="text-sm font-semibold text-white">{position.symbol}</p>
                        <p className="text-xs uppercase text-gray-500">{position.side}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-sm font-semibold ${pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {formatCurrency(pnl)}
                        </p>
                        <p className="text-xs text-gray-500">Qty {formatQuantity(position.quantity)}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => openCloseDialog(position)}
                      className="mt-3 w-full rounded-xl border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-rose-200"
                    >
                      Close Position
                    </button>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </div>

      <div className="rounded-3xl border border-gray-800 bg-gray-900/60 p-5">
        <h3 className="text-lg font-semibold text-white">Pending Orders</h3>
        {pendingSyncNotice && (
          <p className="mt-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
            {pendingSyncNotice}
          </p>
        )}
        {loading && pendingOrders.length === 0 ? (
          <p className="mt-4 text-sm text-gray-400">Loading pending orders…</p>
        ) : pendingOrders.length === 0 ? (
          <p className="mt-4 text-sm text-gray-400">No pending orders.</p>
        ) : (
          <div className="mt-4 space-y-3">
            {pendingOrders.map((order) => (
              <div key={order.id} className="rounded-2xl border border-gray-800 bg-black/20 px-4 py-3 text-sm">
                <div className="flex items-center justify-between">
                  <p className="text-white font-semibold">{formatOrderSymbol(order.trade_symbol)} · {formatOrderSide(order.side)}</p>
                  <p className="text-amber-300 uppercase text-xs tracking-widest">{order.status}</p>
                </div>
                <p className="mt-1 text-gray-400">
                  Qty {formatQuantity(order.quantity)} · Filled {formatQuantity(order.filled_quantity)} · Limit {formatCurrency(order.price)}
                </p>
                {(order.reason_code || order.reason_message) && (
                  <p className="mt-2 text-xs text-rose-300">
                    [{order.reason_code || 'update'}] {order.reason_message || 'Awaiting exchange update'}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {confirmCloseOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-md rounded-3xl border border-gray-700 bg-gray-950 p-6 shadow-2xl">
            <p className="text-xs uppercase tracking-[0.35em] text-rose-300">Confirm Close</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Close full or partial position</h3>
            <div className="mt-4 space-y-3">
              <label className="text-sm text-gray-300">
                Quantity to close
                <input
                  type="number"
                  min="0"
                  step="any"
                  value={closeDraft.quantity}
                  onChange={(event) => setCloseDraft((prev) => ({ ...prev, quantity: event.target.value }))}
                  className="mt-1 w-full rounded-xl border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white outline-none transition focus:border-rose-500"
                />
              </label>
              <label className="text-sm text-gray-300">
                Reason (optional)
                <input
                  type="text"
                  maxLength={256}
                  value={closeDraft.closeReason}
                  onChange={(event) => setCloseDraft((prev) => ({ ...prev, closeReason: event.target.value }))}
                  className="mt-1 w-full rounded-xl border border-gray-700 bg-gray-900/70 px-3 py-2 text-sm text-white outline-none transition focus:border-rose-500"
                />
              </label>
            </div>
            <div className="mt-6 flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setConfirmCloseOpen(false)}
                className="rounded-xl border border-gray-700 px-4 py-2 text-sm font-semibold text-gray-200 hover:border-gray-500"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmClose}
                disabled={closeSubmitting}
                className="rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-400 disabled:opacity-50"
              >
                {closeSubmitting ? 'Closing...' : 'Confirm Close'}
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 rounded-2xl border px-4 py-3 text-sm shadow-2xl ${toast.type === 'error' ? 'border-rose-500/60 bg-rose-500/10 text-rose-200' : 'border-emerald-500/60 bg-emerald-500/10 text-emerald-200'}`}>
          <p>{toast.message}</p>
          {toast.type === 'error' && retryPayload && (
            <button
              type="button"
              className="mt-2 text-xs underline underline-offset-2"
              onClick={retryClose}
            >
              Retry close
            </button>
          )}
        </div>
      )}
    </section>
  );
};

export default PositionManager;
