import React, { useEffect, useMemo, useRef, useState } from 'react';
import api, { aiAPI, normalizeAIChatPayload } from '../services/api';

const createId = (prefix) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

const formatTimestamp = (value) => {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return '';
  }
  return parsed.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

const truncateText = (value, limit = 110) => {
  if (!value) return '—';
  if (value.length <= limit) {
    return value;
  }
  return `${value.slice(0, limit - 1)}…`;
};

const parseSSEFrame = (frame) => {
  if (!frame) {
    return null;
  }

  const lines = frame.split('\n');
  let eventType = null;
  const dataLines = [];

  for (const line of lines) {
    const normalizedLine = line.trimEnd();
    if (!normalizedLine || normalizedLine.startsWith(':')) {
      continue;
    }
    if (normalizedLine.startsWith('event:')) {
      eventType = normalizedLine.slice(6).trim();
      continue;
    }
    if (normalizedLine.startsWith('data:')) {
      dataLines.push(normalizedLine.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const rawData = dataLines.join('\n');
  let payload = rawData;
  try {
    payload = JSON.parse(rawData);
  } catch {
    payload = rawData;
  }

  return {
    eventType,
    payload,
  };
};

const normalizeHistoryMessages = (history) => {
  const rows = [];
  const safeHistory = Array.isArray(history) ? history : [];

  safeHistory.forEach((entry, index) => {
    const baseId = entry.id ?? `history-${index}`;
    const timestamp = entry.timestamp ?? entry.created_at ?? new Date().toISOString();
    const userText = typeof entry.user_message === 'string' ? entry.user_message.trim() : '';
    const assistantPayload = normalizeAIChatPayload(entry.ai_response);
    const assistantText = assistantPayload.text || '';

    if (userText) {
      rows.push({
        id: `${baseId}-user`,
        role: 'user',
        content: userText,
        timestamp,
        sortRank: 0,
      });
    }

    if (assistantText) {
      rows.push({
        id: `${baseId}-assistant`,
        role: 'assistant',
        content: assistantText,
        timestamp,
        sortRank: 1,
        structuredResponse: assistantPayload.hasStructuredContent ? assistantPayload : null,
      });
    }
  });

  const result = [...rows].sort((a, b) => {
    const timeDiff = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    if (timeDiff !== 0) {
      return timeDiff;
    }
    if (a.sortRank !== b.sortRank) {
      return a.sortRank - b.sortRank;
    }
    return String(a.id).localeCompare(String(b.id));
  });

  return result;
};

const RecommendationDisplay = ({ recommendations }) => {
  if (!recommendations) return null;

  const renderBadge = (rec, label) => {
    if (!rec || !rec.action) return null;

    const action = rec.action.toLowerCase();
    let bgColor = 'bg-gray-800/50';
    let textColor = 'text-gray-300';
    let borderColor = 'border-gray-700';

    if (action === 'buy') {
      bgColor = 'bg-emerald-500/10';
      textColor = 'text-emerald-400';
      borderColor = 'border-emerald-500/30';
    } else if (action === 'sell' || action === 'reduce' || action === 'hold') {
      bgColor = 'bg-amber-500/10';
      textColor = 'text-amber-400';
      borderColor = 'border-amber-500/30';
    }

    return (
      <div className={`rounded-xl border ${borderColor} ${bgColor} p-3`}>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] uppercase tracking-[0.2em] font-bold text-gray-400">
            {label} Recommendation
          </span>
          <span className={`text-xs font-bold uppercase tracking-widest ${textColor}`}>
            {rec.action}
          </span>
        </div>
        {rec.rationale && (
          <p className="text-xs text-gray-300 leading-relaxed italic">
            "{rec.rationale}"
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-2 mt-3">
      {renderBadge(recommendations.primary, 'Primary')}
      {renderBadge(recommendations.backup, 'Backup')}
    </div>
  );
};

const ImpactDisplay = ({ impact }) => {
  if (!impact) return null;

  return (
    <div className="mt-3 flex items-center gap-2 rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2">
      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-500/20">
        <svg className="h-3 w-3 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      </div>
      <span className="text-xs font-medium text-blue-200">Portfolio Impact:</span>
      <span className="text-xs font-bold text-white">{impact}</span>
    </div>
  );
};

const RationaleDisplay = ({ explanation }) => {
  if (!explanation) return null;

  const { thesis, market_signals, risk_checks, counterfactual } = explanation;

  return (
    <div className="mt-4 space-y-4 rounded-2xl border border-gray-800 bg-black/20 p-4">
      {thesis && (
        <div>
          <h4 className="text-[10px] uppercase tracking-[0.2em] font-bold text-gray-500 mb-1">Thesis</h4>
          <p className="text-sm font-medium text-gray-100 leading-relaxed italic">{thesis}</p>
        </div>
      )}

      {market_signals && market_signals.length > 0 && (
        <div>
          <h4 className="text-[10px] uppercase tracking-[0.2em] font-bold text-gray-500 mb-1">Signals</h4>
          <ul className="list-none space-y-1">
            {market_signals.map((signal, idx) => (
              <li key={idx} className="flex items-start gap-2 text-xs text-gray-300">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-sky-400" />
                <span>{signal}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {risk_checks && risk_checks.length > 0 && (
        <div>
          <h4 className="text-[10px] uppercase tracking-[0.2em] font-bold text-gray-500 mb-1">Risk Analysis</h4>
          <ul className="list-none space-y-1">
            {risk_checks.map((check, idx) => (
              <li key={idx} className="flex items-start gap-2 text-xs text-gray-300">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-rose-400" />
                <span>{check}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {counterfactual && (
        <div className="pt-2 border-t border-gray-800">
          <h4 className="text-[10px] uppercase tracking-[0.2em] font-bold text-gray-500 mb-1">What to watch for</h4>
          <p className="text-xs text-gray-400 leading-relaxed">{counterfactual}</p>
        </div>
      )}
    </div>
  );
};

const ChatWindow = () => {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    let isMounted = true;

    const loadHistory = async () => {
      setLoadingHistory(true);
      setHistoryError('');

      try {
        const response = await api.get('/api/ai/chat/history');
        if (!isMounted) {
          return;
        }

        const history = Array.isArray(response.data?.history)
          ? response.data.history
          : [];

        const normalized = normalizeHistoryMessages(history);

        setMessages(normalized);
      } catch (error) {
        if (isMounted) {
          setHistoryError(error?.message || 'Unable to load conversation history.');
        }
      } finally {
        if (isMounted) {
          setLoadingHistory(false);
        }
      }
    };

    loadHistory();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loadingHistory]);

  const contextItems = useMemo(() => {
    const lastUser = [...messages].reverse().find((message) => message.role === 'user');
    const lastAssistant = [...messages].reverse().find((message) => message.role === 'assistant');
    const messageCount = messages.length;

    return [
      {
        label: 'Last user prompt',
        value: lastUser ? truncateText(lastUser.content) : 'No prompts yet',
      },
      {
        label: 'Last AI reply',
        value: lastAssistant ? truncateText(lastAssistant.content) : 'Awaiting engagement',
      },
      {
        label: 'Messages exchanged',
        value: `${messageCount} message${messageCount === 1 ? '' : 's'}`,
      },
      {
        label: 'Streaming state',
        value: isStreaming ? 'Receiving streaming response' : 'Ready for new prompt',
      },
    ];
  }, [messages, isStreaming]);

  const memoryAnchors = useMemo(() => {
    const anchors = [];
    for (const message of [...messages].reverse()) {
      if (message.role !== 'user' || !message.content) {
        continue;
      }
      const snippet = message.content.trim().split(/\s+/).slice(0, 5).join(' ');
      if (snippet && !anchors.includes(snippet)) {
        anchors.push(snippet);
      }
      if (anchors.length >= 4) {
        break;
      }
    }
    return anchors.length ? anchors : ['No anchors captured yet'];
  }, [messages]);

  const riskMeter = useMemo(() => {
    const depth = Math.min(messages.length / 12, 1);
    return Math.round(35 + depth * 55);
  }, [messages.length]);

  const sendMessage = async () => {
    const trimmed = inputValue.trim();
    if (!trimmed || isStreaming) {
      return;
    }

    setInputValue('');
    const timestamp = new Date().toISOString();
    const userMessage = {
      id: createId('user'),
      role: 'user',
      content: trimmed,
      timestamp,
    };
    const assistantId = createId('assistant');
    const assistantPlaceholder = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp,
      streaming: true,
    };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
    setIsStreaming(true);

    const updateAssistant = (patch) => {
      setMessages((prev) =>
        prev.map((msg) => (msg.id === assistantId ? { ...msg, ...patch } : msg))
      );
    };

    let streamedText = '';
    let hadError = false;

    try {
      const response = await aiAPI.streamChat({ prompt: trimmed });

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('Streaming responses are not supported by the server.');
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let streamCompleted = false;
      let finalContent = '';
      let structuredResponse = null;
      let guardrailPayload = null;
      let metaPayload = null;

      const applyNormalizedPayload = (normalized, eventType) => {
        if (normalized.errorMessage) {
          throw new Error(normalized.errorMessage);
        }

        if (normalized.meta) {
          metaPayload = normalized.meta;
        }
        if (normalized.guardrail) {
          guardrailPayload = normalized.guardrail;
        }
        if (normalized.hasStructuredContent) {
          structuredResponse = normalized;
          finalContent = normalized.text || finalContent;
        }

        const lowerEvent = String(eventType || '').toLowerCase();
        const isDoneEvent = lowerEvent === 'done';
        const isChunkEvent = lowerEvent === 'chunk' || !lowerEvent;

        if (isChunkEvent && normalized.chunk) {
          streamedText += normalized.chunk;
        } else if ((isDoneEvent || !isChunkEvent) && normalized.text && !normalized.hasStructuredContent) {
          finalContent = normalized.text;
        }

        const nextContent = finalContent || streamedText;
        updateAssistant({
          content: nextContent,
          ...(structuredResponse ? { structuredResponse } : {}),
          ...(guardrailPayload ? { guardrail: guardrailPayload } : {}),
          ...(metaPayload ? { meta: metaPayload } : {}),
        });

        if (isDoneEvent) {
          streamCompleted = true;
        }
      };

      const processFrame = (frame) => {
        const parsedFrame = parseSSEFrame(frame);
        if (!parsedFrame) {
          return;
        }

        const normalizedPayload = normalizeAIChatPayload(parsedFrame.payload);
        const payloadEventType =
          parsedFrame.eventType ||
          (typeof parsedFrame.payload === 'object' && parsedFrame.payload
            ? parsedFrame.payload.type || parsedFrame.payload.event
            : null);
        applyNormalizedPayload(normalizedPayload, payloadEventType);
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() || '';
        for (const frame of frames) {
          processFrame(frame);
        }
      }

      buffer += decoder.decode();
      if (buffer.trim()) {
        processFrame(buffer.trim());
      }

      const resolvedContent = finalContent || streamedText;
      updateAssistant({
        content: resolvedContent,
        streaming: false,
        ...(structuredResponse ? { structuredResponse } : {}),
        ...(guardrailPayload ? { guardrail: guardrailPayload } : {}),
        ...(metaPayload ? { meta: metaPayload } : {}),
      });

      if (!streamCompleted && !resolvedContent) {
        throw new Error('AI response stream completed without content.');
      }
    } catch (error) {
      hadError = true;
      const message = error?.message || 'Unable to receive a response right now.';
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantId
            ? {
                ...msg,
                streaming: false,
                error: message,
                content: msg.content || 'The AI could not respond to that request.',
              }
            : msg
        )
      );
    } finally {
      setIsStreaming(false);
      if (!hadError) {
        updateAssistant({ streaming: false });
      }
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const renderMessage = (message) => {
    const isUser = message.role === 'user';

    return (
      <div
        key={message.id}
        className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}
      >
        <div
          className={`max-w-[88%] rounded-[28px] border px-4 py-3 text-sm shadow-sm shadow-black/40 ${
            isUser
              ? 'border-blue-500/30 bg-blue-500/10 text-slate-100'
              : 'border-gray-800/80 bg-[#0f172a]/80 text-gray-200'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase tracking-[0.3em] text-gray-400">
              {isUser ? 'You' : 'Orchestrator'}
            </span>
            {message.streaming && (
              <span className="ml-2 text-[10px] font-semibold uppercase tracking-[0.3em] text-sky-300">
                Streaming
              </span>
            )}
          </div>
          {message.structuredResponse?.hasStructuredContent ? (
            <div className="mt-2 space-y-2 text-white">
              {message.structuredResponse.summaryParagraph && (
                <p className="whitespace-pre-line text-sm leading-relaxed">
                  {message.structuredResponse.summaryParagraph}
                </p>
              )}
              <RecommendationDisplay recommendations={message.structuredResponse.recommendations} />
              <ImpactDisplay impact={message.structuredResponse.portfolioImpact} />
              {message.structuredResponse.bullets.length > 0 && (
                <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-gray-100">
                  {message.structuredResponse.bullets.map((bullet, index) => (
                    <li key={`${message.id}-bullet-${index}`}>
                      {bullet.label ? `${bullet.label}: ${bullet.text}` : bullet.text}
                    </li>
                  ))}
                </ul>
              )}
              <RationaleDisplay explanation={message.structuredResponse.tradeExplanation} />
            </div>
          ) : (
            <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-white">
              {message.content || 'Waiting for response...'}
            </p>
          )}
          {message.guardrail?.refusal_reason && (
            <p className="mt-2 text-xs text-amber-300">Guardrail: {message.guardrail.refusal_reason}</p>
          )}
          {message.error && (
            <p className="mt-2 text-xs text-rose-300">Error: {message.error}</p>
          )}
        </div>
        <div className="text-[10px] text-gray-500">
          <span>{isUser ? 'You' : 'Orchestrator'}</span>
          <span className="mx-1">•</span>
          <span>{formatTimestamp(message.timestamp)}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="grid w-full gap-6 lg:grid-cols-[1.8fr_1fr]">
      <section className="flex min-h-[520px] flex-col rounded-[36px] border border-gray-800 bg-gradient-to-br from-slate-900/70 to-black/70 p-6 shadow-[0_20px_60px_rgba(3,7,18,0.8)]">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.4em] text-sky-400">AI Orchestrator</p>
            <h2 className="text-2xl font-semibold text-white">Conversation</h2>
          </div>
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] ${
              isStreaming
                ? 'bg-emerald-500/20 text-emerald-300'
                : 'bg-gray-800/70 text-gray-300'
            }`}
          >
            {isStreaming ? 'Streaming' : 'Idle'}
          </span>
        </div>

        {historyError ? (
          <div className="mt-4 rounded-[24px] border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-200">
            {historyError}
          </div>
        ) : null}

        <div className="mt-4 flex flex-1 min-h-0 flex-col">
          {loadingHistory ? (
            <div className="flex flex-1 items-center justify-center text-sm text-gray-400">
              Loading conversation…
            </div>
          ) : (
            <div className="flex flex-1 flex-col gap-4 overflow-y-auto pr-2" aria-live="polite">
              {messages.length === 0 && (
                <p className="text-sm text-gray-400">Frame your first question to begin.</p>
              )}
              {messages.map(renderMessage)}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <div className="mt-4">
          <div className="flex flex-col gap-3 rounded-[28px] border border-gray-800 bg-black/40 p-4 shadow-inner shadow-black/30">
            <label className="text-[11px] uppercase tracking-[0.3em] text-gray-500" htmlFor="chat-input">
              Ask the AI
            </label>
            <textarea
              id="chat-input"
              rows={2}
              className="min-h-[72px] w-full resize-none rounded-2xl border border-gray-800 bg-gray-950/40 px-4 py-3 text-sm text-white placeholder-gray-500 focus:border-sky-400 focus:outline-none"
              placeholder="Ask about risk, trades, or general market context…"
              value={inputValue}
              onChange={(event) => setInputValue(event.target.value)}
              onKeyDown={handleKeyDown}
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">
                {isStreaming ? 'Waiting for AI to finish streaming' : 'Shift+Enter for line break'}
              </span>
              <button
                type="button"
                onClick={sendMessage}
                disabled={isStreaming || !inputValue.trim()}
                className={`inline-flex items-center gap-2 rounded-2xl border px-5 py-2 text-sm font-semibold uppercase tracking-[0.3em] transition ${
                  isStreaming || !inputValue.trim()
                    ? 'cursor-not-allowed border-sky-700/40 bg-sky-500/20 text-sky-200'
                    : 'border-sky-400/60 bg-gradient-to-r from-sky-500 to-indigo-500 text-white shadow-lg shadow-sky-500/40 hover:translate-y-[-1px]'
                }`}
              >
                Send
              </button>
            </div>
          </div>
        </div>
      </section>

      <aside className="space-y-5 rounded-[36px] border border-gray-800 bg-[#05070f]/80 p-6 shadow-[0_20px_48px_rgba(0,0,0,0.7)]">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-gray-400">Context panel</p>
          <h3 className="text-lg font-semibold text-white">Live context</h3>
        </div>
        <div className="space-y-3">
          {contextItems.map((item) => (
            <div
              key={item.label}
              className="rounded-2xl border border-gray-800 bg-black/40 px-4 py-3 text-sm text-gray-200 shadow-sm shadow-black/40"
            >
              <p className="text-[10px] uppercase tracking-[0.3em] text-gray-500">{item.label}</p>
              <p className="mt-1 text-sm font-semibold text-white">{item.value}</p>
            </div>
          ))}
        </div>
        <div className="space-y-2 rounded-2xl border border-blue-500/30 bg-gradient-to-b from-slate-900/80 to-black/60 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-white">Risk posture</p>
            <span className="text-[10px] uppercase tracking-[0.4em] text-blue-300">Auto</span>
          </div>
          <p className="text-xs text-gray-400">Aggressiveness vs. drawdown buffer</p>
          <div className="h-2 w-full rounded-full bg-gray-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-sky-500 to-indigo-500"
              style={{ width: `${riskMeter}%` }}
            />
          </div>
          <p className="text-sm font-semibold text-white">{riskMeter}% tolerance used</p>
        </div>
        <div className="space-y-2 rounded-2xl border border-gray-800/70 bg-black/40 p-4 text-sm text-gray-300">
          <p className="text-[10px] uppercase tracking-[0.3em] text-gray-500">Memory anchors</p>
          <ul className="space-y-1">
            {memoryAnchors.map((anchor, index) => (
              <li key={anchor + index} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
                <span className="truncate text-[13px] text-gray-100">{anchor}</span>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
};

export default ChatWindow;
