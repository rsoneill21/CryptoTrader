import { useCallback, useEffect, useMemo, useState } from 'react';
import api from '../services/api';

const ALERT_POLL_INTERVAL_MS = 20_000;
const ALERT_PAGE_SIZE = 12;
const hasWindow = typeof window !== 'undefined';

const alertStore = {
  alerts: [],
  unreadCount: 0,
  loading: false,
  error: '',
  currentPopup: null,
  popupVisible: false,
  pendingPopups: [],
  lastSyncedAt: null,
};

const subscribers = new Set();
let pollTimer = null;
let isFetching = false;
let initialSyncComplete = false;

const cloneAlert = (alert) => (alert ? { ...alert } : null);

const snapshotState = () => ({
  alerts: alertStore.alerts.map((alert) => cloneAlert(alert)),
  unreadCount: alertStore.unreadCount,
  loading: alertStore.loading,
  error: alertStore.error,
  popupVisible: alertStore.popupVisible,
  currentPopup: cloneAlert(alertStore.currentPopup),
  lastSyncedAt: alertStore.lastSyncedAt,
});

const notifySubscribers = () => {
  const snapshot = snapshotState();
  subscribers.forEach((subscriber) => {
    try {
      subscriber(snapshot);
    } catch (err) {
      console.warn('useAlerts subscriber error', err);
    }
  });
};

const advancePopupQueue = () => {
  if (!alertStore.pendingPopups.length) {
    alertStore.currentPopup = null;
    alertStore.popupVisible = false;
    return;
  }

  const [nextAlert, ...rest] = alertStore.pendingPopups;
  alertStore.pendingPopups = rest;
  alertStore.currentPopup = cloneAlert(nextAlert);
  alertStore.popupVisible = true;
};

const queueNewPopups = (incoming) => {
  if (!incoming.length) {
    return;
  }

  const unique = incoming.filter((alert) => {
    if (!alert?.id) {
      return false;
    }
    if (alertStore.currentPopup?.id === alert.id) {
      return false;
    }
    return !alertStore.pendingPopups.some((queued) => queued.id === alert.id);
  });

  if (!unique.length) {
    return;
  }

  alertStore.pendingPopups = [...alertStore.pendingPopups, ...unique.map((alert) => ({ ...alert }))];

  if (!alertStore.currentPopup) {
    advancePopupQueue();
  }

  notifySubscribers();
};

const dismissActivePopup = () => {
  if (!alertStore.currentPopup) {
    return;
  }

  alertStore.currentPopup = null;
  alertStore.popupVisible = false;

  if (alertStore.pendingPopups.length) {
    advancePopupQueue();
  }

  notifySubscribers();
};

const startPolling = () => {
  if (pollTimer !== null) {
    return;
  }

  // Trigger an immediate fetch so the UI can render data as soon as a subscriber exists.
  fetchAlerts();

  if (!hasWindow) {
    return;
  }

  pollTimer = window.setInterval(() => {
    fetchAlerts();
  }, ALERT_POLL_INTERVAL_MS);
};

const stopPolling = () => {
  if (pollTimer !== null && hasWindow) {
    window.clearInterval(pollTimer);
  }
  pollTimer = null;
};

const fetchAlerts = async () => {
  if (isFetching) {
    return;
  }

  isFetching = true;
  alertStore.loading = true;
  alertStore.error = '';
  notifySubscribers();

  try {
    const response = await api.get('/api/alerts', {
      params: {
        page: 1,
        page_size: ALERT_PAGE_SIZE,
      },
    });

    const fetchedAlerts = Array.isArray(response.data?.alerts) ? response.data.alerts : [];
    const existingIds = new Set(alertStore.alerts.map((item) => item.id));
    const newAlerts = fetchedAlerts.filter((alert) => alert?.id && !existingIds.has(alert.id));

    alertStore.alerts = fetchedAlerts.map((alert) => ({ ...alert }));
    alertStore.unreadCount = fetchedAlerts.filter((alert) => alert.status === 'new').length;
    alertStore.lastSyncedAt = new Date().toISOString();
    alertStore.loading = false;
    alertStore.error = '';

    if (initialSyncComplete) {
      queueNewPopups(newAlerts);
    } else {
      initialSyncComplete = true;
      notifySubscribers();
    }
  } catch (error) {
    alertStore.error = error?.message || 'Unable to load alerts.';
    alertStore.loading = false;
    notifySubscribers();
  } finally {
    isFetching = false;
  }
};

const registerSubscriber = (callback) => {
  subscribers.add(callback);
  callback(snapshotState());
  if (subscribers.size === 1) {
    startPolling();
  }
};

const unregisterSubscriber = (callback) => {
  subscribers.delete(callback);
  if (!subscribers.size) {
    stopPolling();
  }
};

export const useAlerts = () => {
  const [state, setState] = useState(() => snapshotState());

  useEffect(() => {
    const listener = (nextState) => {
      setState(nextState);
    };

    registerSubscriber(listener);
    return () => {
      unregisterSubscriber(listener);
    };
  }, []);

  const dismissPopup = useCallback(() => {
    dismissActivePopup();
  }, []);

  const refresh = useCallback(() => {
    fetchAlerts();
  }, []);

  return useMemo(() => ({
    ...state,
    dismissPopup,
    refresh,
  }), [state, dismissPopup, refresh]);
};

export default useAlerts;
