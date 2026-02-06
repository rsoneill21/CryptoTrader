import React, { useEffect, useMemo, useState } from 'react';
import { normalizeTradeErrorOutcome, normalizeTradeOutcome, tradesAPI } from '../services/api';

const SIDE_STORAGE_KEY = 'live_ticket_last_side';

const parseNumber = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const formatCurrency = (value) => {
  if (!Number.isFinite(Number(value))) {
    return '—';
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
};

const statusTone = {
  pending: 'border-amber-500/50 bg-amber-500/10 text-amber-200',
  partially_filled: 'border-sky-500/50 bg-sky-500/10 text-sky-200',
  filled: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-200',
  rejected: 'border-rose-500/50 bg-rose-500/10 text-rose-200',
};

const OrderTicket = ({ symbol, symbols, marketPrice, onSymbolChange, onOutcome }) => {
  const [orderType, setOrderType] = useState('market');
  const [side, setSide] = useState('buy');
  const [sizeMode, setSizeMode] = useState('quantity');
  const [quantity, setQuantity] = useState('');
  const [riskPercent, setRiskPercent] = useState('');
  const [limitPrice, setLimitPrice] = useState('');
  const [limitTouched, setLimitTouched] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [ticketOutcome, setTicketOutcome] = useState(null);

  useEffect(() => {
    const savedSide = localStorage.getItem(SIDE_STORAGE_KEY);
    if (savedSide === 'buy' || savedSide === 'sell') {
      setSide(savedSide);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(SIDE_STORAGE_KEY, side);
  }, [side]);

  useEffect(() => {
    if (orderType !== 'limit' || limitTouched) {
      return;
    }
    if (marketPrice > 0) {
      setLimitPrice(String(marketPrice.toFixed(2)));
    }
  }, [orderType, marketPrice, limitTouched]);

  const estimatedCost = useMemo(() => {
    const basePrice = orderType === 'limit' ? parseNumber(limitPrice) : parseNumber(marketPrice);
    if (sizeMode !== 'quantity') {
      return null;
    }
    return basePrice * parseNumber(quantity);
  }, [limitPrice, marketPrice, orderType, quantity, sizeMode]);

  const reviewPayload = useMemo(() => {
    const payload = {
      symbol,
      side,
      order_type: orderType,
      is_paper: true,
    };

    if (sizeMode === 'quantity') {
      payload.quantity = parseNumber(quantity);
    } else {
      payload.risk_percent = parseNumber(riskPercent);
    }

    if (orderType === 'limit') {
      payload.limit_price = parseNumber(limitPrice);
    }

    return payload;
  }, [symbol, side, orderType, sizeMode, quantity, riskPercent, limitPrice]);

  const validateDraft = () => {
    if (sizeMode === 'quantity' && parseNumber(quantity) <= 0) {
      return 'Quantity must be greater than zero.';
    }
    if (sizeMode === 'risk_percent' && parseNumber(riskPercent) <= 0) {
      return 'Risk % must be greater than zero.';
    }
    if (orderType === 'limit' && parseNumber(limitPrice) <= 0) {
      return 'Limit price must be greater than zero.';
    }
    return '';
  };

  const handleOpenReview = (event) => {
    event.preventDefault();
    const validationError = validateDraft();
    if (validationError) {
      setTicketOutcome({
        status: 'rejected',
        reasonCode: 'validation_error',
        reasonMessage: validationError,
      });
      return;
    }
    setReviewOpen(true);
  };

  const handleConfirm = async () => {
    setSubmitting(true);
    try {
      const response = await tradesAPI.submitManualOrder(reviewPayload);
      const normalized = normalizeTradeOutcome(response?.data, {
        source: 'ticket_submit',
        symbol,
        side,
        orderType,
      });
      setTicketOutcome(normalized);
      if (typeof onOutcome === 'function') {
        onOutcome(normalized);
      }
      if (normalized.status === 'filled' || normalized.status === 'pending') {
        setQuantity('');
        setRiskPercent('');
      }
      setReviewOpen(false);
    } catch (error) {
      const normalized = normalizeTradeErrorOutcome(error, {
        source: 'ticket_submit',
        symbol,
        side,
        orderType,
      });
      setTicketOutcome(normalized);
      if (typeof onOutcome === 'function') {
        onOutcome(normalized);
      }
      setReviewOpen(false);
    } finally {
      setSubmitting(false);
    }
  };

  const ticketTone = statusTone[ticketOutcome?.status] || statusTone.rejected;

  return (
    <div className="rounded-[32px] border border-gray-800 bg-gray-900/40 p-6">
      <h2 className="text-xl font-bold text-white mb-6">Order Ticket</h2>
      <form onSubmit={handleOpenReview} className="space-y-4">
        <div className="grid grid-cols-2 gap-2 p-1 bg-black/40 rounded-2xl border border-gray-800">
          <button
            type="button"
            onClick={() => setSide('buy')}
            className={`py-2 rounded-xl text-xs font-bold uppercase transition ${side === 'buy' ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-900/40' : 'text-gray-500 hover:text-gray-300'}`}
          >
            Buy
          </button>
          <button
            type="button"
            onClick={() => setSide('sell')}
            className={`py-2 rounded-xl text-xs font-bold uppercase transition ${side === 'sell' ? 'bg-rose-500 text-white shadow-lg shadow-rose-900/40' : 'text-gray-500 hover:text-gray-300'}`}
          >
            Sell
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 p-1 bg-black/40 rounded-2xl border border-gray-800">
          <button
            type="button"
            onClick={() => setOrderType('market')}
            className={`py-2 rounded-xl text-xs font-bold uppercase transition ${orderType === 'market' ? 'bg-blue-500 text-white' : 'text-gray-500 hover:text-gray-300'}`}
          >
            Market
          </button>
          <button
            type="button"
            onClick={() => {
              setOrderType('limit');
              setLimitTouched(false);
            }}
            className={`py-2 rounded-xl text-xs font-bold uppercase transition ${orderType === 'limit' ? 'bg-blue-500 text-white' : 'text-gray-500 hover:text-gray-300'}`}
          >
            Limit
          </button>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] uppercase tracking-widest text-gray-500 ml-1">Asset</label>
          <select
            value={symbol}
            onChange={(event) => onSymbolChange(event.target.value)}
            className="w-full bg-black/40 border border-gray-800 rounded-2xl py-3 px-4 text-white text-sm focus:outline-none focus:border-blue-500"
          >
            {symbols.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>

        {orderType === 'limit' && (
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-widest text-gray-500 ml-1">Limit Price</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={limitPrice}
              onChange={(event) => {
                setLimitTouched(true);
                setLimitPrice(event.target.value);
              }}
              className="w-full bg-black/40 border border-gray-800 rounded-2xl py-3 px-4 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 p-1 bg-black/40 rounded-2xl border border-gray-800">
          <button
            type="button"
            onClick={() => setSizeMode('quantity')}
            className={`py-2 rounded-xl text-xs font-bold uppercase transition ${sizeMode === 'quantity' ? 'bg-gray-200 text-black' : 'text-gray-500 hover:text-gray-300'}`}
          >
            Quantity
          </button>
          <button
            type="button"
            onClick={() => setSizeMode('risk_percent')}
            className={`py-2 rounded-xl text-xs font-bold uppercase transition ${sizeMode === 'risk_percent' ? 'bg-gray-200 text-black' : 'text-gray-500 hover:text-gray-300'}`}
          >
            Risk %
          </button>
        </div>

        {sizeMode === 'quantity' ? (
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-widest text-gray-500 ml-1">Quantity</label>
            <input
              type="number"
              step="any"
              min="0"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              placeholder="0.00"
              className="w-full bg-black/40 border border-gray-800 rounded-2xl py-3 px-4 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
        ) : (
          <div className="space-y-1">
            <label className="text-[10px] uppercase tracking-widest text-gray-500 ml-1">Risk %</label>
            <input
              type="number"
              step="0.1"
              min="1"
              max="100"
              value={riskPercent}
              onChange={(event) => setRiskPercent(event.target.value)}
              placeholder="2"
              className="w-full bg-black/40 border border-gray-800 rounded-2xl py-3 px-4 text-white text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
        )}

        <div className="flex justify-between text-[10px] text-gray-500 uppercase tracking-widest px-1">
          <span>Est. Cost</span>
          <span>{estimatedCost === null ? '—' : formatCurrency(estimatedCost)}</span>
        </div>

        <button
          type="submit"
          disabled={submitting}
          className={`w-full py-4 rounded-[20px] font-bold uppercase tracking-widest text-sm transition ${side === 'buy' ? 'bg-emerald-500 hover:bg-emerald-400 text-white' : 'bg-rose-500 hover:bg-rose-400 text-white'} disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          Review Order
        </button>
      </form>

      {ticketOutcome && (
        <div className={`mt-4 rounded-2xl border px-4 py-3 ${ticketTone}`}>
          <p className="text-xs uppercase tracking-widest">Ticket Status · {ticketOutcome.status}</p>
          {ticketOutcome.reasonCode && (
            <p className="text-xs mt-1 font-semibold">Code: {ticketOutcome.reasonCode}</p>
          )}
          {ticketOutcome.reasonMessage && (
            <p className="text-sm mt-1">{ticketOutcome.reasonMessage}</p>
          )}
        </div>
      )}

      {reviewOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-md rounded-3xl border border-gray-700 bg-gray-950 p-6 shadow-2xl">
            <p className="text-xs uppercase tracking-[0.35em] text-blue-400">Review Order</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Confirm before submit</h3>
            <div className="mt-4 space-y-2 text-sm text-gray-300">
              <p>Symbol: <span className="text-white font-semibold">{symbol}</span></p>
              <p>Side: <span className="text-white font-semibold uppercase">{side}</span></p>
              <p>Type: <span className="text-white font-semibold uppercase">{orderType}</span></p>
              {sizeMode === 'quantity' ? (
                <p>Quantity: <span className="text-white font-semibold">{parseNumber(quantity)}</span></p>
              ) : (
                <p>Risk %: <span className="text-white font-semibold">{parseNumber(riskPercent)}%</span></p>
              )}
              {orderType === 'limit' && (
                <p>Limit: <span className="text-white font-semibold">{formatCurrency(parseNumber(limitPrice))}</span></p>
              )}
            </div>
            <div className="mt-6 flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setReviewOpen(false)}
                className="rounded-xl border border-gray-700 px-4 py-2 text-sm font-semibold text-gray-200 hover:border-gray-500"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                disabled={submitting}
                className="rounded-xl bg-blue-500 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-400 disabled:opacity-50"
              >
                {submitting ? 'Submitting...' : 'Confirm Submit'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OrderTicket;
