/**
 * Registration page component.
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import RegisterForm from '../components/RegisterForm';

const Register = () => {
  const navigate = useNavigate();
  const { register, isAuthenticated, error, clearError } = useAuth();
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Clear errors on unmount
  useEffect(() => {
    return () => clearError();
  }, [clearError]);

  const handleRegister = async (email, password) => {
    setLoading(true);
    const result = await register(email, password);
    setLoading(false);

    if (result.success) {
      setSuccess(true);
      // Redirect to login after short delay
      setTimeout(() => {
        navigate('/login', {
          state: { message: 'Registration successful! Please sign in.' }
        });
      }, 2000);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900 px-4">
        <div className="max-w-md w-full text-center">
          <div className="bg-green-900/50 border border-green-500 rounded-lg p-8">
            <svg className="mx-auto h-12 w-12 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <h2 className="mt-4 text-xl font-semibold text-white">Registration Successful!</h2>
            <p className="mt-2 text-gray-300">Redirecting to login...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 px-4">
      <div className="max-w-md w-full space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-white">CryptoTrader</h1>
          <p className="mt-2 text-gray-400">AI-Powered Trading Platform</p>
        </div>

        <div className="bg-gray-800 rounded-lg shadow-xl p-8">
          <h2 className="text-xl font-semibold text-white mb-6">Create your account</h2>
          <RegisterForm
            onSubmit={handleRegister}
            error={error}
            loading={loading}
          />
        </div>
      </div>
    </div>
  );
};

export default Register;
