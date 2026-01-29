/**
 * Login page component.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import LoginForm from '../components/LoginForm';

const Login = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated, error, clearError } = useAuth();
  const [loading, setLoading] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      const from = location.state?.from?.pathname || '/dashboard';
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, navigate, location]);

  // Clear errors on unmount
  useEffect(() => {
    return () => clearError();
  }, [clearError]);

  const handleLogin = async (email, password) => {
    setLoading(true);
    const result = await login(email, password);
    setLoading(false);

    if (result.success) {
      const from = location.state?.from?.pathname || '/dashboard';
      navigate(from, { replace: true });
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">CryptoTrader</h1>
          <p className="mt-2 text-gray-400">AI-Powered Trading Platform</p>
        </div>

        <div className="bg-gray-800 rounded-lg shadow-xl p-8">
          <h2 className="text-xl font-semibold text-white mb-6">Sign in to your account</h2>
          <LoginForm
            onSubmit={handleLogin}
            error={error}
            loading={loading}
          />
        </div>
      </div>
    </div>
  );
};

export default Login;
