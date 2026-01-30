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

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
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

// Request interceptor - add auth token
api.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
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

  logs: (params = {}) =>
    api.get('/api/system/logs', { params }),
};

// Export default instance for custom requests
export default api;
