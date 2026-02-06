/**
 * API client service for CryptoTrader.
 *
 * Provides axios instance with:
 * - Base URL configuration
 * - Auth token interceptor
 * - 401 handling (redirect to login)
 * - Error formatting
 */

import axios from 'axios';

// Use relative paths by default to leverage the Vite proxy in development
// and stay flexible in production.
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
  withCredentials: true,
});

// Token storage key
const TOKEN_KEY = 'cryptotrader_token';

/**
 * Get stored auth token.
 */
export const getToken = () => {
  return localStorage.getItem(TOKEN_KEY);
};

/**
 * Store auth token.
 */
export const setToken = (token) => {
  localStorage.setItem(TOKEN_KEY, token);
};

/**
 * Remove auth token.
 */
export const removeToken = () => {
  localStorage.removeItem(TOKEN_KEY);
};

const UNEXPECTED_ERROR_MESSAGE =
  'Something went wrong. Please try again or contact support if the problem persists.';

const extractAPIError = (data) => {
  if (!data) {
    return null;
  }
  if (data.error && typeof data.error === 'object') {
    return data.error;
  }
  return null;
};

const normalizeAPIError = (errorResponseData) => {
  const apiError = extractAPIError(errorResponseData);
  if (!apiError) {
    return null;
  }

  return {
    message: apiError.message || apiError.detail || UNEXPECTED_ERROR_MESSAGE,
    code: apiError.code || 'unknown_error',
    details: apiError.details,
  };
};

const normalizeLifecycleStatus = (statusValue) => {
  const normalized = String(statusValue || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_');

  if (normalized === 'open' || normalized === 'new') {
    return 'pending';
  }

  if (normalized === 'closed') {
    return 'filled';
  }

  if (normalized === 'cancelled' || normalized === 'expired') {
    return 'canceled';
  }

  if (['pending', 'partially_filled', 'filled', 'rejected', 'canceled'].includes(normalized)) {
    return normalized;
  }

  return 'rejected';
};

const parseReasonFromErrorMessage = (errorMessage) => {
  if (!errorMessage || typeof errorMessage !== 'string') {
    return { reasonCode: null, reasonMessage: null };
  }

  const text = errorMessage.trim();
  if (!text) {
    return { reasonCode: null, reasonMessage: null };
  }

  if (text.startsWith('[') && text.includes(']')) {
    const closeIndex = text.indexOf(']');
    const reasonCode = text.slice(1, closeIndex).trim().toLowerCase() || null;
    const reasonMessage = text.slice(closeIndex + 1).trim() || null;
    return { reasonCode, reasonMessage };
  }

  return { reasonCode: null, reasonMessage: text };
};

export const normalizeTradeOutcome = (payload = {}, fallback = {}) => {
  const parsedReason = parseReasonFromErrorMessage(payload.error_message);
  const reasonCode = payload.reason_code || fallback.reasonCode || parsedReason.reasonCode;
  const reasonMessage = payload.reason_message || fallback.reasonMessage || parsedReason.reasonMessage;

  return {
    id: payload.order_id || payload.id || payload.trade_id || `outcome-${Date.now()}`,
    timestamp: new Date().toISOString(),
    orderId: payload.order_id || payload.id || null,
    tradeId: payload.trade_id || null,
    symbol: payload.symbol || payload.trade_symbol || fallback.symbol || 'Unknown',
    side: payload.side || payload.trade_side || fallback.side || null,
    status: normalizeLifecycleStatus(payload.status || fallback.status),
    reasonCode,
    reasonMessage,
    orderType: payload.order_type || fallback.orderType || null,
    source: fallback.source || 'trade',
  };
};

export const normalizeTradeErrorOutcome = (error, fallback = {}) => {
  const detail = error?.response?.data?.detail;
  const isObjectDetail = detail && typeof detail === 'object';
  return normalizeTradeOutcome(
    {
      status: 'rejected',
      reason_code: isObjectDetail ? detail.code : error?.apiCode || 'request_failed',
      reason_message: isObjectDetail
        ? detail.message || error.message
        : error?.message || 'Request failed',
      symbol: fallback.symbol,
      side: fallback.side,
      order_type: fallback.orderType,
      trade_id: fallback.tradeId || null,
      order_id: fallback.orderId || null,
    },
    { ...fallback, status: 'rejected' }
  );
};

// Request interceptor - auth token no longer needed in header as we use HttpOnly cookies
api.interceptors.request.use(
  (config) => {
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor - handle 401 and format errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Server responded with error status
      const { status, data } = error.response;

      if (status === 401) {
        // Unauthorized - clear token and redirect to login
        removeToken();
        // Only redirect if not already on login page
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/login';
        }
      }

      // Format error message
      const normalized = normalizeAPIError(data);
      if (normalized) {
        error.message = normalized.message;
        error.apiCode = normalized.code;
        error.apiDetails = normalized.details;
      } else {
        error.message = data?.detail || data?.message || 'An error occurred';
      }
    } else if (error.request) {
      // Request made but no response
      error.message =
        'Unable to connect to CryptoTrader. Ensure the backend is running and retry.';
    }

    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  register: (email, password) =>
    api.post('/api/auth/register', { email, password }),

  login: (email, password) =>
    api.post('/api/auth/login', { email, password }),

  logout: () =>
    api.post('/api/auth/logout'),

  getSession: () =>
    api.get('/api/auth/session'),

  requestPasswordReset: (email) =>
    api.post('/api/auth/password/reset', { email }),

  confirmPasswordReset: (token, newPassword) =>
    api.post('/api/auth/password/reset/confirm', {
      token,
      new_password: newPassword,
    }),
};

// System API
export const systemAPI = {
  health: () =>
    api.get('/api/system/health'),

  connectionStatus: () =>
    api.get('/api/system/connection-status'),

  logs: (params = {}) =>
    api.get('/api/system/logs', { params }),
};

// Market API
export const marketAPI = {
  getTicker: (pair) =>
    api.get(`/api/market/ticker/${pair}`),

  getPrices: (symbols = []) => {
    const params = symbols.length > 0 ? { symbol: symbols.join(',') } : {};
    return api.get('/api/market/prices', { params });
  },

  getOHLC: (pair, params = {}) =>
    api.get(`/api/market/ohlc/${pair}`, { params }),

  getCandles: (symbol, params = {}) =>
    api.get(`/api/market/candles/${symbol}`, { params }),

  getOrderbook: (symbol, count = 25) =>
    api.get(`/api/market/orderbook/${symbol}`, { params: { count } }),

  listPairs: () =>
    api.get('/api/market/pairs'),

  getPortfolio: (forceRefresh = false) =>
    api.get('/api/market/portfolio', { params: { force_refresh: forceRefresh } }),
};

// Trades API
export const tradesAPI = {
  getActiveTrades: () =>
    api.get('/api/trades/active'),

  createTrade: (data) =>
    api.post('/api/trades/', data),

  submitManualOrder: (data) =>
    api.post('/api/trades/orders', data),

  listPendingOrders: () =>
    api.get('/api/trades/orders/pending'),

  closePosition: (tradeId, data) =>
    api.post(`/api/trades/${tradeId}/close`, data),

  closeTrade: (tradeId, exitPrice, reason = '') =>
    api.post(`/api/trades/${tradeId}/close`, { exit_price: exitPrice, reason }),

  adjustTrade: (tradeId, data) =>
    api.put(`/api/trades/${tradeId}/adjust`, data),

  addToPosition: (tradeId, quantity) =>
    api.post(`/api/trades/${tradeId}/add`, { quantity }),

  toggleAI: (tradeId) =>
    api.put(`/api/trades/${tradeId}/ai-toggle`),

  getTradeOrders: (tradeId) =>
    api.get(`/api/trades/${tradeId}/orders`),

  getOrderStatus: (orderId) =>
    api.get(`/api/trades/orders/${orderId}/status`),

  cancelOrder: (orderId) =>
    api.post(`/api/trades/orders/${orderId}/cancel`),
};

export const aiAPI = {
  listModels: () => api.get('/api/ai/models'),
  activateModel: (provider) =>
    api.put('/api/ai/models/active', { provider }),
  chatHistory: (params = {}) =>
    api.get('/api/ai/chat/history', { params }),
};

// Agents API - agent observability and control
export const agentsAPI = {
  dashboard: (pipelineLimit = 20) =>
    api.get('/api/agents/dashboard', { params: { pipeline_limit: pipelineLimit } }),
  allStatus: () =>
    api.get('/api/agents/status'),
  agentStatus: (agentName) =>
    api.get(`/api/agents/${agentName}/status`),
  controlAgent: (agentName, action) =>
    api.post(`/api/agents/${agentName}/control`, { action }),
  flushQueue: (channel) =>
    api.post('/api/agents/queue/flush', { channel }),
  retrySignal: (signalId) =>
    api.post(`/api/agents/signals/${signalId}/retry`),
};

// Export default instance for custom requests
export default api;
