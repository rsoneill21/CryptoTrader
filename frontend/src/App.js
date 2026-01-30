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

// Placeholder pages (to be implemented)
const StrategyLab = () => (
  <div className="text-white">
    <h1 className="text-2xl font-bold mb-4">AI Strategy Lab</h1>
    <p className="text-gray-400">Coming in Phase 4...</p>
  </div>
);

const LiveTrading = () => (
  <div className="text-white">
    <h1 className="text-2xl font-bold mb-4">Live Trading</h1>
    <p className="text-gray-400">Coming in Phase 5...</p>
  </div>
);

const AIChat = () => (
  <div className="text-white">
    <h1 className="text-2xl font-bold mb-4">AI Chat</h1>
    <p className="text-gray-400">Coming in Phase 7...</p>
  </div>
);

const Alerts = () => (
  <div className="text-white">
    <h1 className="text-2xl font-bold mb-4">Alerts & Activity</h1>
    <p className="text-gray-400">Coming in Phase 8...</p>
  </div>
);

const Settings = () => (
  <div className="text-white">
    <h1 className="text-2xl font-bold mb-4">Settings</h1>
    <p className="text-gray-400">Coming soon...</p>
  </div>
);

function App() {
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
