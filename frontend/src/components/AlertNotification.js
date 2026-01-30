/**
 * AlertNotification renders a floating bell badge and pop-up when a new alert arrives.
 */

import React, { useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useAlerts } from '../hooks/useAlerts';

const MAX_BADGE_LABEL = 99;

const severityDecorators = {
  critical: 'bg-red-800/10 border border-red-700 text-red-100',
  warning: 'bg-yellow-800/10 border border-yellow-600 text-yellow-100',
  info: 'bg-blue-800/10 border border-blue-600 text-blue-100',
};

const formatTimestamp = (value) => {
  if (!value) {
    return 'Just now';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleTimeString('en-US', { timeStyle: 'short' });
};

const BellIcon = ({ className }) => (
  <svg
    aria-hidden="true"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.5}
    className={className}
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
    />
  </svg>
);

const AlertNotification = () => {
  const {
    currentPopup,
    popupVisible,
    unreadCount,
    loading,
    error,
    dismissPopup,
    refresh,
  } = useAlerts();

  const badgeLabel = useMemo(() => {
    if (!unreadCount) {
      return null;
    }
    return unreadCount > MAX_BADGE_LABEL ? `${MAX_BADGE_LABEL}+` : String(unreadCount);
  }, [unreadCount]);

  const severityLabel = useMemo(() => {
    return (currentPopup?.severity || 'info').toLowerCase();
  }, [currentPopup]);

  const severityClass = severityDecorators[severityLabel] ?? severityDecorators.info;

  const handleDismiss = useCallback(() => {
    dismissPopup();
  }, [dismissPopup]);

  return (
    <>
      <div className="fixed top-4 right-4 z-40 flex items-center gap-2">
        <Link
          to="/alerts"
          className="relative flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-gray-800 text-gray-300 shadow-lg shadow-black/50 transition hover:text-white"
          aria-label="Open alerts dashboard"
        >
          <BellIcon className="h-6 w-6" />
          {badgeLabel && (
            <span className="absolute -top-1 -right-1 flex h-5 min-w-[20px] items-center justify-center rounded-full bg-red-500 px-1.5 text-xs font-semibold text-white">
              {badgeLabel}
            </span>
          )}
        </Link>
        <button
          type="button"
          onClick={refresh}
          disabled={loading}
          className="rounded-lg border border-white/20 px-3 py-2 text-xs uppercase tracking-wide text-white transition hover:border-white/40 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? 'Syncing...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="fixed top-20 right-4 z-40 rounded-xl border border-red-500/60 bg-red-900/90 px-4 py-2 text-xs text-red-100">
          {error}
        </div>
      )}

      {popupVisible && currentPopup && (
        <div
          className="fixed bottom-6 right-6 z-50 max-w-sm rounded-2xl border border-white/10 bg-gray-900/95 p-5 text-sm text-white shadow-2xl shadow-black/60"
          role="status"
          aria-live="assertive"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-gray-400">
                {formatTimestamp(currentPopup.created_at)}
              </p>
              <p className="text-lg font-semibold leading-tight">
                {currentPopup.title || 'New alert received'}
              </p>
            </div>
            <button
              type="button"
              onClick={handleDismiss}
              className="rounded-full bg-white/5 p-1 text-gray-300 transition hover:bg-white/10"
              aria-label="Dismiss alert"
            >
              <span className="text-xl leading-none">×</span>
            </button>
          </div>
          <p className="mt-3 text-sm text-gray-200">
            {currentPopup.message || 'No additional details were provided for this alert.'}
          </p>
          <div className="mt-4 flex items-center justify-between">
            <span className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-wider ${severityClass}`}>
              {currentPopup.severity ? currentPopup.severity.toUpperCase() : 'INFO'}
            </span>
            <Link
              to="/alerts"
              onClick={handleDismiss}
              className="text-xs text-blue-300 transition hover:text-blue-100"
            >
              View alerts
            </Link>
          </div>
        </div>
      )}
    </>
  );
};

export default AlertNotification;
