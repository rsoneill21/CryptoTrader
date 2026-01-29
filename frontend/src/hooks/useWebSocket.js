import { useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_FEED = 'ohlc';
const DEFAULT_RECONNECT_MS = 5000;

const buildWebSocketUrl = (feed = DEFAULT_FEED) => {
  const fallback = `ws://localhost:8000/api/market/stream/${feed}`;
  const configUrl = process.env.REACT_APP_API_URL;

  if (configUrl) {
    try {
      const parsed = new URL(configUrl);
      const scheme = parsed.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${scheme}//${parsed.host}/api/market/stream/${feed}`;
    } catch (err) {
      // fallback to window origin or localhost if parsing fails
    }
  }

  if (typeof window !== 'undefined') {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${scheme}//${window.location.host}/api/market/stream/${feed}`;
  }

  return fallback;
};

/**
 * Hook that manages a WebSocket connection to the market streaming endpoint.
 *
 * @param {Object} options WebSocket configuration
 * @param {string} options.feed WebSocket feed (ticker, trade, ohlc)
 * @param {string} options.symbol Optional symbol filter for incoming messages
 * @param {boolean} options.autoReconnect Automatically attempt to reconnect
 * @param {number} options.reconnectInterval Delay between reconnect attempts in ms
 * @param {Function} options.onMessage Callback invoked with parsed payloads
 * @param {Function} options.onOpen Callback invoked when socket opens
 * @param {Function} options.onError Callback invoked when an error occurs
 * @param {Function} options.onClose Callback invoked when socket closes
 *
 * @returns {Object} Connection helpers and state
 */
export const useWebSocket = ({
  feed = DEFAULT_FEED,
  symbol,
  autoReconnect = true,
  reconnectInterval = DEFAULT_RECONNECT_MS,
  onMessage,
  onOpen,
  onError,
  onClose,
} = {}) => {
  const socketRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const mountedRef = useRef(false);
  const shouldReconnectRef = useRef(autoReconnect);

  const [connectionStatus, setConnectionStatus] = useState('connecting');
  const [connectionError, setConnectionError] = useState('');
  const [lastPayload, setLastPayload] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const safeSet = useCallback((setter, value) => {
    if (mountedRef.current) {
      setter(value);
    }
  }, []);

  const processPayload = useCallback(
    (payload) => {
      if (!payload) {
        return;
      }

      if (feed && payload.type && payload.type !== feed) {
        return;
      }

      if (symbol && payload.data?.symbol && payload.data.symbol !== symbol) {
        return;
      }

      safeSet(setLastPayload, payload);

      const timestamp = payload?.data?.timestamp ? Date.parse(payload.data.timestamp) : NaN;
      if (!Number.isNaN(timestamp)) {
        safeSet(setLastUpdate, new Date(timestamp));
      }

      if (typeof onMessage === 'function') {
        onMessage(payload);
      }
    },
    [feed, symbol, onMessage, safeSet]
  );

  const connect = useCallback(() => {
    if (!mountedRef.current) {
      return;
    }

    if (reconnectTimerRef.current && typeof window !== 'undefined') {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    safeSet(setConnectionStatus, 'connecting');
    safeSet(setConnectionError, '');

    const wsUrl = buildWebSocketUrl(feed);

    const scheduleReconnect = () => {
      if (!shouldReconnectRef.current || typeof window === 'undefined') {
        return;
      }

      reconnectTimerRef.current = window.setTimeout(() => {
        if (shouldReconnectRef.current) {
          connect();
        }
      }, Math.max(1000, reconnectInterval));
    };

    let socket;
    try {
      socket = new WebSocket(wsUrl);
    } catch (err) {
      safeSet(setConnectionStatus, 'disconnected');
      safeSet(setConnectionError, 'Live stream unavailable');

      if (typeof onError === 'function') {
        onError(err);
      }

      scheduleReconnect();
      return;
    }

    socketRef.current = socket;

    socket.onopen = () => {
      if (!mountedRef.current) {
        return;
      }
      safeSet(setConnectionStatus, 'connected');
      safeSet(setConnectionError, '');
      if (typeof onOpen === 'function') {
        onOpen();
      }
    };

    socket.onmessage = (event) => {
      if (!mountedRef.current) {
        return;
      }

      try {
        const parsed = JSON.parse(event.data);
        processPayload(parsed);
      } catch (err) {
        // Ignore malformed payloads
      }
    };

    socket.onerror = (event) => {
      if (!mountedRef.current) {
        return;
      }
      safeSet(setConnectionError, 'Live stream disconnected');
      if (typeof onError === 'function') {
        onError(event);
      }
    };

    socket.onclose = (event) => {
      if (!mountedRef.current) {
        return;
      }
      safeSet(setConnectionStatus, 'disconnected');
      if (typeof onClose === 'function') {
        onClose(event);
      }
      scheduleReconnect();
    };
  }, [feed, reconnectInterval, onClose, onError, onOpen, processPayload, safeSet]);

  useEffect(() => {
    mountedRef.current = true;
    shouldReconnectRef.current = autoReconnect;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current && typeof window !== 'undefined') {
        window.clearTimeout(reconnectTimerRef.current);
      }
      socketRef.current?.close();
      mountedRef.current = false;
    };
  }, [autoReconnect, connect]);

  const sendMessage = useCallback(
    (message) => {
      const socket = socketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) {
        return false;
      }

      try {
        const payload = typeof message === 'string' ? message : JSON.stringify(message);
        socket.send(payload);
        return true;
      } catch (err) {
        safeSet(setConnectionError, 'Unable to send message');
        if (typeof onError === 'function') {
          onError(err);
        }
        return false;
      }
    },
    [onError, safeSet]
  );

  const closeConnection = useCallback(() => {
    shouldReconnectRef.current = false;
    if (reconnectTimerRef.current && typeof window !== 'undefined') {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    socketRef.current?.close();
    safeSet(setConnectionStatus, 'disconnected');
  }, [safeSet]);

  return {
    buildWebSocketUrl,
    connectionError,
    connectionStatus,
    lastPayload,
    lastUpdate,
    reconnectDelay: reconnectInterval,
    sendMessage,
    closeConnection,
  };
};

export default useWebSocket;
