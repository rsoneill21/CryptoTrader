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

const formatHybridChatText = (summaryParagraph, bullets, fallbackText = null) => {
  const segments = [];
  if (summaryParagraph) {
    segments.push(summaryParagraph);
  }
  if (Array.isArray(bullets) && bullets.length > 0) {
    segments.push(
      bullets
        .map((bullet) => {
          if (bullet.label && bullet.text) {
            return `- ${bullet.label}: ${bullet.text}`;
          }
          return `- ${bullet.text || bullet.label}`;
        })
        .join('\n')
    );
  }
  if (segments.length > 0) {
    return segments.join('\n\n');
  }
  return fallbackText;
};

const normalizeBullet = (value) => {
  if (typeof value === 'string') {
    const text = normalizeText(value);
    return text ? { label: null, text } : null;
  }
  if (!value || typeof value !== 'object') {
    return null;
  }
  const label = normalizeText(value.label) || normalizeText(value.title);
  const text =
    normalizeText(value.text) ||
    normalizeText(value.content) ||
    normalizeText(value.value) ||
    normalizeText(value.message);
  if (!label && !text) {
    return null;
  }
  return { label, text: text || label };
};

export const normalizeAIChatPayload = (rawPayload) => {
  const parseJsonString = (value) => {
    if (typeof value !== 'string') {
      return value;
    }
    const trimmed = value.trim();
    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) {
      return value;
    }
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  };

  const payload = parseJsonString(rawPayload);
  if (typeof payload === 'string') {
    const text = normalizeText(payload) || '';
    return {
      text,
      chunk: text,
      summaryParagraph: null,
      bullets: [],
      recommendations: null,
      guardrail: null,
      meta: null,
      hasStructuredContent: false,
      errorMessage: null,
    };
  }

  if (!payload || typeof payload !== 'object') {
    return {
      text: '',
      chunk: null,
      summaryParagraph: null,
      bullets: [],
      recommendations: null,
      guardrail: null,
      meta: null,
      hasStructuredContent: false,
      errorMessage: null,
    };
  }

  const summaryParagraph =
    normalizeText(payload.summary_paragraph) || normalizeText(payload.summaryParagraph);
  const bullets = (Array.isArray(payload.bullets) ? payload.bullets : [])
    .map((entry) => normalizeBullet(entry))
    .filter(Boolean);
  const chunk =
    normalizeText(payload.chunk) ||
    normalizeText(payload.delta) ||
    normalizeText(payload.token) ||
    normalizeText(payload.partial);
  const plainText =
    normalizeText(payload.response) ||
    normalizeText(payload.message) ||
    normalizeText(payload.text) ||
    null;
  const structuredText = formatHybridChatText(summaryParagraph, bullets, null);
  const text = structuredText || chunk || plainText || '';
  const errorMessage =
    normalizeText(payload.error) ||
    normalizeText(payload.detail) ||
    normalizeText(payload.details) ||
    null;

  return {
    text,
    chunk,
    summaryParagraph,
    bullets,
    recommendations:
      payload.recommendations && typeof payload.recommendations === 'object'
        ? payload.recommendations
        : null,
    guardrail:
      payload.guardrail && typeof payload.guardrail === 'object'
        ? payload.guardrail
        : null,
    meta: payload.meta && typeof payload.meta === 'object' ? payload.meta : null,
    hasStructuredContent: Boolean(summaryParagraph || bullets.length),
    errorMessage,
  };
};

export const extractAIErrorMessage = (value, fallback = 'AI chat request failed.') => {
  const parsed = normalizeAPIError(value);
  if (parsed?.message) {
    return parsed.message;
  }
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  if (value && typeof value === 'object') {
    const detail = normalizeText(value.detail);
    if (detail) {
      return detail;
    }
    const error = normalizeText(value.error);
    if (error) {
      return error;
    }
  }
  return fallback;
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

const normalizeText = (value) => {
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const normalizeSymbol = (value, fallbackValue) => {
  const symbol = normalizeText(value) || normalizeText(fallbackValue);
  return symbol || 'Unknown Symbol';
};

const normalizeSide = (value, fallbackValue) => {
  const candidate = normalizeText(value) || normalizeText(fallbackValue);
  if (!candidate) {
    return 'unknown';
  }

  const normalized = candidate.toLowerCase();
  if (normalized === 'long') {
    return 'buy';
  }
  if (normalized === 'short') {
    return 'sell';
  }
  if (normalized === 'buy' || normalized === 'sell') {
    return normalized;
  }

  return 'unknown';
};

const normalizeTimestamp = (payload = {}, fallback = {}) => {
  const candidates = [payload.updated_at, payload.created_at, payload.timestamp, fallback.timestamp, new Date().toISOString()];
  for (const value of candidates) {
    if (!value) {
      continue;
    }
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) {
      return date.toISOString();
    }
  }
  return new Date().toISOString();
};

export const normalizeTradeOutcome = (payload = {}, fallback = {}) => {
  const parsedReason = parseReasonFromErrorMessage(payload.error_message);
  const reasonCode = normalizeText(payload.reason_code) || normalizeText(fallback.reasonCode) || parsedReason.reasonCode;
  const reasonMessage = normalizeText(payload.reason_message) || normalizeText(fallback.reasonMessage) || parsedReason.reasonMessage;

  return {
    id: payload.order_id || payload.id || payload.trade_id || `outcome-${Date.now()}`,
    timestamp: normalizeTimestamp(payload, fallback),
    orderId: payload.order_id || payload.id || null,
    tradeId: payload.trade_id || null,
    symbol: normalizeSymbol(payload.symbol || payload.trade_symbol, fallback.symbol),
    side: normalizeSide(payload.side || payload.trade_side, fallback.side),
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

export const isKrakenThrottleError = (error) => {
  const messageParts = [
    error?.message,
    error?.response?.data?.detail?.message,
    typeof error?.response?.data?.detail === 'string' ? error.response.data.detail : null,
    error?.apiDetails?.error,
    error?.apiDetails?.reason,
  ].filter((part) => typeof part === 'string' && part.trim().length > 0);

  const message = messageParts.join(' ').toLowerCase();
  const details = error?.apiDetails || error?.response?.data?.detail?.details || {};
  const dependency = String(details?.dependency || details?.service || '').toLowerCase();
  const code = String(error?.apiCode || error?.response?.data?.detail?.code || '').toLowerCase();

  if (message.includes('unable to acquire kraken rate-limit budget')) {
    return true;
  }

  return code === 'service_unavailable' && dependency === 'kraken';
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

  submitManualOrderOutcome: async (data) => {
    const response = await api.post('/api/trades/orders', data);
    return {
      response,
      outcome: normalizeTradeOutcome(response?.data, {
        source: 'ticket_submit',
      }),
    };
  },

  listPendingOrders: () =>
    api.get('/api/trades/orders/pending'),

  closePosition: (tradeId, data) =>
    api.post(`/api/trades/${tradeId}/close`, data),

  closePositionOutcome: async (tradeId, data) => {
    const response = await api.post(`/api/trades/${tradeId}/close`, data);
    return {
      response,
      outcome: normalizeTradeOutcome(response?.data, {
        source: 'position_close',
      }),
    };
  },

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
  streamChat: async (payload = {}) => {
    const token = getToken();
    const response = await fetch(`${API_BASE_URL}/api/ai/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let responsePayload = null;
      try {
        responsePayload = await response.json();
      } catch {
        responsePayload = await response.text();
      }
      throw new Error(extractAIErrorMessage(responsePayload));
    }

    return response;
  },
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

// Strategies API
export const strategiesAPI = {
  list: (params = {}) =>
    api.get('/api/strategies', { params }),
  get: (id) =>
    api.get(`/api/strategies/${id}`),
  create: (data) =>
    api.post('/api/strategies', data),
  saveStrategy: (data) =>
    api.post('/api/strategies', data),
  generateStrategy: (data) =>
    api.post('/api/strategies/suggestions', data),
  update: (id, data) =>
    api.put(`/api/strategies/${id}`, data),
  delete: (id) =>
    api.delete(`/api/strategies/${id}`),
  promote: (id, confirm = true) =>
    api.post(`/api/strategies/${id}/promote`, { confirm }),
  simulate: (id, data) =>
    api.post(`/api/strategies/${id}/simulate`, data),
  getPaperPortfolio: () =>
    api.get('/api/strategies/paper-portfolio'),
  resetPaperTrading: (data) =>
    api.post('/api/strategies/paper-trading/reset', data),
  importGithub: (url) =>
    api.post('/api/strategies/import/github', { github_url: url }),
  applyAdjustment: (id) =>
    api.post(`/api/strategies/${id}/adjustments/apply`),
  discardAdjustment: (id) =>
    api.delete(`/api/strategies/${id}/adjustments`),
};

// Export default instance for custom requests
export default api;
