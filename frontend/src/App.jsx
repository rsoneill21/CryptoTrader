/**
 * CryptoTrader - Main Application Component
 */

import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';

// Pages
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import ForgotPassword from './pages/ForgotPassword';
import SystemLogs from './pages/SystemLogs';
import StrategyLab from './pages/StrategyLab';
import Backtesting from './pages/Backtesting';
import LiveTrading from './pages/LiveTrading';
import AIChat from './pages/AIChat';
import Alerts from './pages/Alerts';
import Settings from './pages/Settings';

function App() {
  console.log('Rendering App component');
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />

            {/* Protected routes with layout */}
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Dashboard />
                  </Layout>
                </ProtectedRoute>
              }
            />
            {/* ... rest of the routes ... */}
            <Route
              path="/strategy-lab"
              element={
                <ProtectedRoute>
                  <Layout>
                    <StrategyLab />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/backtesting"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Backtesting />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/live-trading"
              element={
                <ProtectedRoute>
                  <Layout>
                    <LiveTrading />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/ai-chat"
              element={
                <ProtectedRoute>
                  <Layout>
                    <AIChat />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/alerts"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Alerts />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Settings />
                  </Layout>
                </ProtectedRoute>
              }
            />
            <Route
              path="/system-logs"
              element={
                <ProtectedRoute>
                  <Layout>
                    <SystemLogs />
                  </Layout>
                </ProtectedRoute>
              }
            />

            {/* Default redirect */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
