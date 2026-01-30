import React, { useCallback, useMemo } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';

const ALERT_CHAT_ROUTE = '/ai-chat';
const ALERT_CHAT_STORAGE_KEY = 'cryptotrader_alert_chat_context';

const STATUS_LABELS = {
  new: 'New',
  viewed: 'Viewed',
  actioned: 'Actioned',
  dismissed: 'Dismissed',
};

const STATUS_COLORS = {
  new: 'text-blue-400',
  viewed: 'text-gray-300',
  actioned: 'text-emerald-400',
  dismissed: 'text-rose-300',
};

const SEVERITY_STYLES = {
  info: 'bg-blue-500 text-black dark:text-white',
  warning: 'bg-yellow-400 text-black',
  critical: 'bg-red-500 text-white',
};

const formatTimestamp = (value) => {
  if (!value) {
    return '—';
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('en-US', {
    hour12: true,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const buildChatContext = (alert) => {
  const title = alert.title || 'Untitled alert';
  const message = alert.message?.trim() || 'No additional details provided.';
  const typeSegment = alert.type ? `Type: ${alert.type}.` : '';
  const severitySegment = alert.severity ? `Severity: ${alert.severity}.` : '';
  const statusSegment = alert.status ? `Status: ${alert.status}.` : '';

  const prompt = [
    `Reviewing alert "${title}".`,
    typeSegment,
    severitySegment,
    statusSegment,
    `Summary: ${message}`,
    'Provide next steps, risk considerations, and any follow-up questions.',
  ]
    .filter(Boolean)
    .join(' ');

  return {
    alertId: alert.id,
    title,
    type: alert.type,
    severity: alert.severity,
    status: alert.status,
    message,
    timestamp: alert.created_at,
    prompt,
  };
};

const persistChatContext = (context) => {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.sessionStorage?.setItem(ALERT_CHAT_STORAGE_KEY, JSON.stringify(context));
  } catch (error) {
    console.warn('Unable to persist alert chat context', error);
  }
};

const AlertItem = ({ alert, isSelected, onSelect, onChatNavigate }) => {
  const navigate = useNavigate();

  const statusLabel = STATUS_LABELS[alert.status] || alert.status || 'Status unknown';
  const severityLabel = alert.severity?.toUpperCase() || '—';

  const containerClasses = useMemo(() => {
    const base = 'flex w-full items-start justify-between rounded-2xl border px-4 py-3 text-left transition-all duration-150';
    const selected = 'border-blue-500 bg-blue-500/10 shadow-[0_0_0_1px_rgba(37,99,235,0.6)]';
    const idle = 'border-transparent hover:border-gray-600 hover:bg-white/5';
    return `${base} ${isSelected ? selected : idle}`;
  }, [isSelected]);

  const handleSelect = useCallback(() => {
    if (typeof onSelect === 'function') {
      onSelect(alert);
    }
  }, [alert, onSelect]);

  const handleChat = useCallback(
    (event) => {
      event.preventDefault();
      event.stopPropagation();
      const context = buildChatContext(alert);
      persistChatContext(context);
      if (typeof onChatNavigate === 'function') {
        onChatNavigate(context);
        return;
      }
      navigate(ALERT_CHAT_ROUTE, { state: { alertContext: context } });
    },
    [alert, navigate, onChatNavigate]
  );

  return (
    <div className="space-y-2">
      <button
        type="button"
        className={containerClasses}
        onClick={handleSelect}
        aria-pressed={isSelected}
      >
        <div className="max-w-[70%] space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              {alert.type || 'Alert'}
            </span>
            <span className="rounded-full border border-gray-700 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gray-300">
              {formatTimestamp(alert.created_at)}
            </span>
          </div>
          <p className="text-sm font-semibold text-white">{alert.title}</p>
          <p className="text-xs text-gray-400 max-h-10 overflow-hidden text-ellipsis">
            {alert.message || 'No additional details.'}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 text-right">
          <span className={`text-xs font-semibold ${STATUS_COLORS[alert.status] || 'text-gray-300'}`}>
            {statusLabel}
          </span>
          <span
            className={`rounded-full px-3 py-1 text-[11px] font-semibold ${
              SEVERITY_STYLES[alert.severity] || 'bg-gray-700 text-white'
            }`}
          >
            {severityLabel}
          </span>
        </div>
      </button>
      <div className="flex items-center justify-between text-[10px] text-gray-400">
        <span>
          Updated {formatTimestamp(alert.actioned_at || alert.created_at)}
        </span>
        <button
          type="button"
          onClick={handleChat}
          className="inline-flex items-center gap-2 rounded-full border border-sky-500/80 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.3em] text-sky-300 transition hover:border-sky-400 hover:text-white"
        >
          Chat with AI
        </button>
      </div>
    </div>
  );
};

AlertItem.propTypes = {
  alert: PropTypes.shape({
    id: PropTypes.oneOfType([PropTypes.number, PropTypes.string]).isRequired,
    title: PropTypes.string,
    message: PropTypes.string,
    type: PropTypes.string,
    severity: PropTypes.string,
    status: PropTypes.string,
    created_at: PropTypes.string,
    actioned_at: PropTypes.string,
  }).isRequired,
  isSelected: PropTypes.bool,
  onSelect: PropTypes.func,
  onChatNavigate: PropTypes.func,
};

AlertItem.defaultProps = {
  isSelected: false,
  onSelect: undefined,
  onChatNavigate: undefined,
};

export { ALERT_CHAT_STORAGE_KEY, ALERT_CHAT_ROUTE };
export default AlertItem;
