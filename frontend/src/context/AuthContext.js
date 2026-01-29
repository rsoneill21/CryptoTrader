/**
 * Authentication context for CryptoTrader.
 *
 * Provides authentication state and methods to all components.
 */

import React, { createContext, useState, useEffect, useCallback } from 'react';
import { authAPI, setToken, removeToken, getToken } from '../services/api';

// Create context
export const AuthContext = createContext(null);

/**
 * Authentication provider component.
 */
export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  /**
   * Check current session on mount.
   */
  useEffect(() => {
    const checkSession = async () => {
      const token = getToken();
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await authAPI.getSession();
        setUser(response.data);
      } catch (err) {
        // Invalid/expired session - clear token
        removeToken();
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    checkSession();
  }, []);

  /**
   * Register a new user.
   */
  const register = useCallback(async (email, password) => {
    setError(null);
    try {
      const response = await authAPI.register(email, password);
      return { success: true, data: response.data };
    } catch (err) {
      const message = err.message || 'Registration failed';
      setError(message);
      return { success: false, error: message };
    }
  }, []);

  /**
   * Log in a user.
   */
  const login = useCallback(async (email, password) => {
    setError(null);
    try {
      const response = await authAPI.login(email, password);
      const { token, user_id } = response.data;

      // Store token
      setToken(token);

      // Fetch full user data
      const sessionResponse = await authAPI.getSession();
      setUser(sessionResponse.data);

      return { success: true, data: response.data };
    } catch (err) {
      const message = err.message || 'Login failed';
      setError(message);
      return { success: false, error: message };
    }
  }, []);

  /**
   * Log out current user.
   */
  const logout = useCallback(async () => {
    try {
      await authAPI.logout();
    } catch (err) {
      // Ignore logout errors - still clear local state
      console.error('Logout error:', err);
    } finally {
      removeToken();
      setUser(null);
      setError(null);
    }
  }, []);

  /**
   * Request password reset.
   */
  const requestPasswordReset = useCallback(async (email) => {
    setError(null);
    try {
      const response = await authAPI.requestPasswordReset(email);
      return { success: true, message: response.data.message };
    } catch (err) {
      const message = err.message || 'Password reset request failed';
      setError(message);
      return { success: false, error: message };
    }
  }, []);

  /**
   * Confirm password reset with token.
   */
  const confirmPasswordReset = useCallback(async (token, newPassword) => {
    setError(null);
    try {
      const response = await authAPI.confirmPasswordReset(token, newPassword);
      return { success: true, message: response.data.message };
    } catch (err) {
      const message = err.message || 'Password reset failed';
      setError(message);
      return { success: false, error: message };
    }
  }, []);

  /**
   * Clear current error.
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const value = {
    user,
    loading,
    error,
    isAuthenticated: !!user,
    register,
    login,
    logout,
    requestPasswordReset,
    confirmPasswordReset,
    clearError,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
