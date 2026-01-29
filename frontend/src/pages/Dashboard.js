/**
 * Main dashboard page.
 */

import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { systemAPI } from '../services/api';

const StatCard = ({ title, value, icon, color = 'blue' }) => (
  <div className="bg-gray-800 dark:bg-gray-800 light:bg-white rounded-lg p-6 border border-gray-700 dark:border-gray-700 light:border-gray-200">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm text-gray-400 dark:text-gray-400 light:text-gray-500">{title}</p>
        <p className="mt-1 text-2xl font-semibold text-white dark:text-white light:text-gray-900">{value}</p>
      </div>
      <div className={`p-3 rounded-lg bg-${color}-500/20`}>
        {icon}
      </div>
    </div>
  </div>
);

const FeatureCard = ({ to, title, description, icon }) => (
  <Link
    to={to}
    className="block bg-gray-800 dark:bg-gray-800 light:bg-white rounded-lg p-6 border border-gray-700 dark:border-gray-700 light:border-gray-200 hover:border-blue-500 transition-colors group"
  >
    <div className="flex items-start space-x-4">
      <div className="p-3 rounded-lg bg-blue-500/20 text-blue-400 group-hover:bg-blue-500 group-hover:text-white transition-colors">
        {icon}
      </div>
      <div>
        <h3 className="text-lg font-medium text-white dark:text-white light:text-gray-900 group-hover:text-blue-400 transition-colors">
          {title}
        </h3>
        <p className="mt-1 text-sm text-gray-400 dark:text-gray-400 light:text-gray-500">
          {description}
        </p>
      </div>
    </div>
  </Link>
);

const Dashboard = () => {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await systemAPI.health();
        setHealth(response.data);
      } catch (err) {
        console.error('Failed to fetch health:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchHealth();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white dark:text-white light:text-gray-900">Dashboard</h1>
        <p className="text-gray-400 dark:text-gray-400 light:text-gray-500">Welcome to CryptoTrader</p>
      </div>

      {/* System Status */}
      <div className="bg-gray-800 dark:bg-gray-800 light:bg-white rounded-lg p-4 border border-gray-700 dark:border-gray-700 light:border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className={`w-3 h-3 rounded-full ${health?.status === 'healthy' ? 'bg-green-500' : 'bg-yellow-500'}`} />
            <span className="text-sm text-gray-300 dark:text-gray-300 light:text-gray-600">
              System Status: {loading ? 'Checking...' : health?.status || 'Unknown'}
            </span>
          </div>
          <span className="text-xs text-gray-500">v{health?.version || '0.1.0'}</span>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Active Strategies"
          value="0"
          icon={
            <svg className="w-6 h-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          }
        />
        <StatCard
          title="Open Positions"
          value="0"
          icon={
            <svg className="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          }
          color="green"
        />
        <StatCard
          title="Today's P&L"
          value="$0.00"
          icon={
            <svg className="w-6 h-6 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          color="yellow"
        />
        <StatCard
          title="Risk Score"
          value="0%"
          icon={
            <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          }
          color="red"
        />
      </div>

      {/* Feature Cards */}
      <div>
        <h2 className="text-lg font-semibold text-white dark:text-white light:text-gray-900 mb-4">Quick Access</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FeatureCard
            to="/strategy-lab"
            title="AI Strategy Lab"
            description="Create, test, and optimize trading strategies with AI assistance"
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            }
          />
          <FeatureCard
            to="/live-trading"
            title="Live Trading"
            description="Monitor real-time market data and manage active positions"
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
            }
          />
          <FeatureCard
            to="/ai-chat"
            title="AI Chat"
            description="Discuss strategies and get insights from your trading AI"
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            }
          />
          <FeatureCard
            to="/alerts"
            title="Alerts & Activity"
            description="View trade alerts, AI decisions, and activity history"
            icon={
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
            }
          />
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
