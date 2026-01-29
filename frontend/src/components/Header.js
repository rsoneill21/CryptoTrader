/**
 * Top header/navbar component.
 */

import React from 'react';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../context/ThemeContext';

const Header = ({ sidebarOpen, onToggleSidebar }) => {
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();

  return (
    <header className="sticky top-0 z-10 bg-gray-800 dark:bg-gray-800 light:bg-white border-b border-gray-700 dark:border-gray-700 light:border-gray-200">
      <div className="flex items-center justify-between h-16 px-4">
        {/* Left section */}
        <div className="flex items-center">
          {/* Mobile menu button */}
          <button
            onClick={onToggleSidebar}
            className="lg:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          {/* Page title placeholder */}
          <h1 className="ml-4 lg:ml-0 text-lg font-semibold text-white dark:text-white light:text-gray-900">
            Dashboard
          </h1>
        </div>

        {/* Right section */}
        <div className="flex items-center space-x-4">
          {/* AI Status indicator */}
          <div className="flex items-center space-x-2 px-3 py-1 rounded-full bg-gray-700 dark:bg-gray-700 light:bg-gray-100">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
            </span>
            <span className="text-xs text-gray-300 dark:text-gray-300 light:text-gray-600">AI Active</span>
          </div>

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            )}
          </button>

          {/* Alerts button */}
          <button className="relative p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            {/* Alert badge */}
            <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-xs text-white">
              3
            </span>
          </button>

          {/* User menu */}
          <div className="relative group">
            <button className="flex items-center space-x-2 p-2 rounded-lg text-gray-300 hover:text-white hover:bg-gray-700 transition-colors">
              <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center">
                <span className="text-sm font-medium text-white">
                  {user?.email?.charAt(0).toUpperCase() || 'U'}
                </span>
              </div>
              <span className="hidden md:block text-sm">{user?.email}</span>
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Dropdown menu */}
            <div className="absolute right-0 mt-2 w-48 bg-gray-800 dark:bg-gray-800 light:bg-white rounded-lg shadow-lg py-1 hidden group-hover:block">
              <div className="px-4 py-2 border-b border-gray-700 dark:border-gray-700 light:border-gray-200">
                <p className="text-sm text-white dark:text-white light:text-gray-900 truncate">{user?.email}</p>
              </div>
              <button
                onClick={logout}
                className="w-full text-left px-4 py-2 text-sm text-gray-300 dark:text-gray-300 light:text-gray-600 hover:bg-gray-700 dark:hover:bg-gray-700 light:hover:bg-gray-100 hover:text-white dark:hover:text-white light:hover:text-gray-900"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
