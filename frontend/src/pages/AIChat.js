import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import ChatWindow from '../components/ChatWindow';
import api, { aiAPI } from '../services/api';

const CHAT_TONE_EVENT = 'cryptotrader:chatTonePreferenceChanged';
const CHAT_TONE_STORAGE_KEY = 'cryptotrader.ai_chat_tone';
const DEFAULT_CHAT_TONE = 'balanced';

const CHAT_TONES = [
  {
    value: 'balanced',
    label: 'Balanced',
    description: 'Measured explanations that juxtapose upside, downside, and context.',
  },
  {
    value: 'concise',
    label: 'Concise',
    description: 'Ultra-short summaries ideal for quick status checks.',
  },
  {
    value: 'detailed',
    label: 'Detailed',
    description: 'Step-by-step reasoning highlighting assumptions and next steps.',
  },
  {
    value: 'data_driven',
    label: 'Data-driven',
    description: 'Numbers-first answers that emphasize metrics, signals, and evidence.',
  },
  {
    value: 'conversational',
    label: 'Conversational',
    description: 'Casual tone that mirrors a teammate walking through the idea.',
  },
];

const loadStoredChatTone = () => {
  if (typeof window === 'undefined') {
    return DEFAULT_CHAT_TONE;
  }
  try {
    return window.localStorage.getItem(CHAT_TONE_STORAGE_KEY) ?? DEFAULT_CHAT_TONE;
  } catch (error) {
    console.debug('Unable to read preferred chat tone:', error);
    return DEFAULT_CHAT_TONE;
  }
};

const setGlobalChatTone = (value) => {
  if (typeof window === 'undefined') {
    return;
  }
  window.__cryptotraderChatTone = value;
};

const ensureChatToneFetchInterceptor = () => {
  if (typeof window === 'undefined' || window.__cryptotraderChatToneFetchPatched) {
    return;
  }
  const baseFetch = window.fetch.bind(window);
  window.__cryptotraderChatToneFetchOriginal = baseFetch;
  window.__cryptotraderChatToneFetchPatched = true;

  window.fetch = async (input, init) => {
    const url = typeof input === 'string' ? input : input?.url;
    const shouldIntercept =
      typeof url === 'string' &&
      url.includes('/api/ai/chat') &&
      (!init?.method || init.method.toUpperCase() === 'POST');
    if (!shouldIntercept) {
      return baseFetch(input, init);
    }

    const body = init?.body;
    if (typeof body !== 'string') {
      return baseFetch(input, init);
    }

    let parsedBody;
    try {
      parsedBody = JSON.parse(body);
    } catch {
      return baseFetch(input, init);
    }

    if (!parsedBody || typeof parsedBody !== 'object') {
      return baseFetch(input, init);
    }

    const tone = window.__cryptotraderChatTone ?? DEFAULT_CHAT_TONE;
    const alertContext = window.__cryptotraderAlertChatContext;
    const alertIdValue = alertContext?.alert_id ?? alertContext?.alertId;
    const merged = { ...parsedBody, tone };
    if (alertIdValue) {
      merged.related_alert_id = alertIdValue;
      const baseContext =
        parsedBody.context_json && typeof parsedBody.context_json === 'object'
          ? { ...parsedBody.context_json }
          : {};
      merged.context_json = {
        ...baseContext,
        alert_context: {
          alert_id: alertIdValue,
          title: alertContext?.title ?? null,
          message: alertContext?.message ?? null,
          severity: alertContext?.severity ?? null,
          status: alertContext?.status ?? null,
          type: alertContext?.type ?? null,
          related_strategy_id: alertContext?.related_strategy_id ?? null,
          related_trade_id: alertContext?.related_trade_id ?? null,
          created_at: alertContext?.created_at ?? null,
          prompt: alertContext?.prompt ?? null,
        },
      };
    }
    const clonedInit = { ...(init || {}), body: JSON.stringify(merged) };
    return baseFetch(input, clonedInit);
  };
};

const ALERT_CHAT_STORAGE_KEY = 'cryptotrader_alert_chat_context';

const loadStoredAlertChatContext = () => {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const stored = window.sessionStorage?.getItem(ALERT_CHAT_STORAGE_KEY);
    if (!stored) {
      return null;
    }
    return JSON.parse(stored);
  } catch (error) {
    console.debug('Unable to read alert chat context:', error);
    return null;
  }
};

const clearStoredAlertChatContext = () => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage?.removeItem(ALERT_CHAT_STORAGE_KEY);
  } catch (error) {
    console.debug('Unable to clear alert chat context:', error);
  }
};

const setGlobalAlertChatContext = (value) => {
  if (typeof window === 'undefined') {
    return;
  }
  window.__cryptotraderAlertChatContext = value ?? null;
};

if (typeof window !== 'undefined') {
  window.__cryptotraderChatTone = window.__cryptotraderChatTone ?? loadStoredChatTone();
  window.__cryptotraderAlertChatContext = window.__cryptotraderAlertChatContext ?? null;
  ensureChatToneFetchInterceptor();
}

const formatDurationMinutes = (value) => {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }
  return `${Math.round(Number(value))} min`;
};

const formatAggressivenessScore = (value) => {
  if (value == null || Number.isNaN(Number(value))) {
    return '—';
  }
  return `${Math.round(Number(value) * 100)}%`;
};

const formatFavoriteSymbols = (symbols) =>
  symbols && symbols.length ? symbols.join(', ') : 'Gathering symbols';

const formatAlertPromptPreview = (value, limit = 140) => {
  if (!value) {
    return null;
  }
  const trimmed = String(value).trim();
  if (!trimmed) {
    return null;
  }
  if (trimmed.length <= limit) {
    return trimmed;
  }
  return `${trimmed.slice(0, limit - 1)}…`;
};

const AIChat = () => {
  const [tonePreference, setTonePreference] = useState(loadStoredChatTone);
  const [styleProfile, setStyleProfile] = useState(null);
  const [styleLoading, setStyleLoading] = useState(true);
  const [styleError, setStyleError] = useState('');
  const location = useLocation();
  const [pendingAlertContext, setPendingAlertContext] = useState(null);
  const [resolvedAlertContext, setResolvedAlertContext] = useState(null);
  const [alertContextLoading, setAlertContextLoading] = useState(false);
  const [alertContextError, setAlertContextError] = useState('');
  const [modelInventory, setModelInventory] = useState([]);
  const [modelLoading, setModelLoading] = useState(true);
  const [modelError, setModelError] = useState('');
  const [desiredProvider, setDesiredProvider] = useState('');

  useEffect(() => {
    setGlobalChatTone(tonePreference);
  }, [tonePreference]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const searchParams = new URLSearchParams(location.search);
    const queryAlertId = searchParams.get('alert_id');
    const navContext = location.state?.alertContext;
    const storedContext = loadStoredAlertChatContext();
    let candidate = null;
    if (navContext?.alertId || navContext?.alert_id) {
      candidate = navContext;
    } else if (storedContext?.alertId || storedContext?.alert_id) {
      candidate = storedContext;
    } else if (queryAlertId) {
      const parsedId = Number(queryAlertId);
      if (!Number.isNaN(parsedId)) {
        candidate = { alert_id: parsedId };
      }
    }

    if (!candidate) {
      setPendingAlertContext(null);
      setResolvedAlertContext(null);
      setAlertContextError('');
      return;
    }

    setPendingAlertContext(candidate);
    setAlertContextError('');
    if (storedContext) {
      clearStoredAlertChatContext();
    }
  }, [location.search, location.state]);

  useEffect(() => {
    const alertIdValue = pendingAlertContext?.alert_id ?? pendingAlertContext?.alertId;
    if (!alertIdValue) {
      setResolvedAlertContext(null);
      setAlertContextLoading(false);
      setAlertContextError('');
      return;
    }

    let isMounted = true;
    setAlertContextLoading(true);
    setAlertContextError('');

    const loadAlertContext = async () => {
      try {
        const response = await api.get(`/api/alerts/${alertIdValue}/chat-context`);
        if (!isMounted) {
          return;
        }
        setResolvedAlertContext(response.data);
      } catch (error) {
        if (!isMounted) {
          return;
        }
        setAlertContextError(error?.message || 'Unable to load alert context.');
        setResolvedAlertContext({
          ...pendingAlertContext,
          alert_id: alertIdValue,
        });
      } finally {
        if (isMounted) {
          setAlertContextLoading(false);
        }
      }
    };

    loadAlertContext();
    return () => {
      isMounted = false;
    };
  }, [pendingAlertContext]);

  useEffect(() => {
    const candidate = resolvedAlertContext || pendingAlertContext;
    if (!candidate) {
      setGlobalAlertChatContext(null);
      return;
    }
    const normalized = {
      alert_id: candidate.alert_id ?? candidate.alertId ?? null,
      title: candidate.title ?? null,
      message: candidate.message ?? null,
      severity: candidate.severity ?? null,
      status: candidate.status ?? null,
      type: candidate.type ?? null,
      related_strategy_id: candidate.related_strategy_id ?? candidate.relatedStrategyId ?? null,
      related_trade_id: candidate.related_trade_id ?? candidate.relatedTradeId ?? null,
      created_at:
        candidate.created_at ?? candidate.createdAt ?? candidate.timestamp ?? null,
      prompt: candidate.prompt ?? null,
    };
    setGlobalAlertChatContext(normalized);
  }, [pendingAlertContext, resolvedAlertContext]);

  useEffect(() => {
    return () => {
      setGlobalAlertChatContext(null);
    };
  }, []);

  const loadModelInventory = useCallback(async () => {
    setModelLoading(true);
    setModelError('');
    try {
      const response = await aiAPI.listModels();
      const models = response.data?.models ?? [];
      setModelInventory(models);
      const active = models.find((entry) => entry.active)?.provider ?? '';
      setDesiredProvider(active);
    } catch (error) {
      setModelError(error?.message || 'Unable to load AI models');
    } finally {
      setModelLoading(false);
    }
  }, []);

  useEffect(() => {
    loadModelInventory();
  }, [loadModelInventory]);

  useEffect(() => {
    let isMounted = true;

    const loadStyleProfile = async () => {
      setStyleLoading(true);
      setStyleError('');
      try {
        const response = await api.get('/api/risk/settings/ai/context');
        if (!isMounted) {
          return;
        }
        const profile = response.data?.context?.style_profile ?? null;
        setStyleProfile(profile);
      } catch (error) {
        if (!isMounted) {
          return;
        }
        setStyleError(error?.message || 'Unable to load AI preferences.');
      } finally {
        if (isMounted) {
          setStyleLoading(false);
        }
      }
    };

    loadStyleProfile();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }
    const listener = (event) => {
      const updated = event?.detail ?? DEFAULT_CHAT_TONE;
      setTonePreference(updated);
    };
    window.addEventListener(CHAT_TONE_EVENT, listener);
    return () => {
      window.removeEventListener(CHAT_TONE_EVENT, listener);
    };
  }, []);

  const currentToneDetails = useMemo(
    () => CHAT_TONES.find((option) => option.value === tonePreference) ?? CHAT_TONES[0],
    [tonePreference]
  );

  const activeAlertContext = resolvedAlertContext || pendingAlertContext;
  const alertContextStatusLabel = alertContextLoading
    ? 'Syncing alert context…'
    : alertContextError
    ? 'Context fallback: using the available alert summary'
    : activeAlertContext
    ? 'Alert context ready'
    : '';
  const alertPromptPreview = formatAlertPromptPreview(activeAlertContext?.prompt);
  const alertContextMeta = [];
  if (activeAlertContext?.type) {
    alertContextMeta.push(activeAlertContext.type);
  }
  if (activeAlertContext?.related_strategy_id) {
    alertContextMeta.push(`Strategy #${activeAlertContext.related_strategy_id}`);
  }
  if (activeAlertContext?.related_trade_id) {
    alertContextMeta.push(`Trade #${activeAlertContext.related_trade_id}`);
  }
  const alertContextMetaLabel = alertContextMeta.length ? alertContextMeta.join(' · ') : 'Alert';

  const activeModel = modelInventory.find((entry) => entry.active);
  const activeLabel = activeModel ? activeModel.provider.toUpperCase() : '—';

  return (
    <section className="space-y-6 text-white">
      <header className="space-y-2">
        <p className="text-xs uppercase tracking-[0.4em] text-sky-400">Phase 7 · AI Orchestrator</p>
        <h1 className="text-3xl font-semibold text-white">AI Chat</h1>
        <p className="max-w-3xl text-sm text-gray-300">
          Talk directly with the orchestrator to surface risk-aware trade ideas, review AI reasoning, and keep a
          streaming log of every interaction.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-[10px] uppercase tracking-[0.3em] text-gray-400">Tone</span>
          <span className="rounded-full border border-sky-500/60 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.3em] text-sky-100">
            {currentToneDetails.label}
          </span>
          <div className="flex flex-col gap-2 rounded-2xl border border-slate-800 bg-slate-950/70 px-4 py-3 text-xs uppercase tracking-[0.3em] text-gray-400">
            <div className="flex items-center justify-between gap-2">
              <p className="text-[9px] uppercase tracking-[0.5em] text-slate-500">Model</p>
              {modelLoading ? (
                <span className="text-[10px] text-gray-400">Loading…</span>
              ) : (
                <span className="text-[10px] font-semibold uppercase tracking-[0.3em] text-emerald-400">
                  {activeLabel}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <select
                className="flex-1 bg-transparent text-[11px] font-semibold uppercase tracking-[0.3em] text-white outline-none"
                value={desiredProvider}
                onChange={(event) => setDesiredProvider(event.target.value)}
              >
                {modelInventory.map((entry) => (
                  <option
                    key={entry.provider}
                    value={entry.provider}
                    disabled={!entry.available}
                  >
                    {entry.provider.toUpperCase()}
                    {!entry.available ? ' (offline)' : ''}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={async () => {
                  if (!desiredProvider) {
                    return;
                  }
                  setModelLoading(true);
                  setModelError('');
                  try {
                    await aiAPI.activateModel(desiredProvider);
                    await loadModelInventory();
                  } catch (error) {
                    setModelError(error?.message || 'Unable to activate provider');
                  } finally {
                    setModelLoading(false);
                  }
                }}
                disabled={modelLoading || !desiredProvider}
                className="rounded-full border border-emerald-500/70 px-3 py-0.5 text-[9px] font-semibold uppercase tracking-[0.3em] text-emerald-300 disabled:opacity-40"
              >
                Activate
              </button>
            </div>
            {modelError && <p className="text-[10px] text-rose-300">{modelError}</p>}
          </div>
          <p className="text-xs text-gray-400 max-w-3xl">{currentToneDetails.description}</p>
        </div>
      </header>
      {activeAlertContext && (
        <div className="space-y-3 rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-950/70 to-slate-900/60 p-5 text-sm text-white shadow-[0_20px_60px_rgba(2,4,20,0.85)]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] uppercase tracking-[0.3em] text-sky-300">Alert context</p>
              <h2 className="text-xl font-semibold text-white">
                {activeAlertContext.title || `Alert #${activeAlertContext.alert_id || '—'}`}
              </h2>
              <p className="text-xs text-gray-400">{alertContextMetaLabel}</p>
            </div>
            {alertContextStatusLabel && (
              <span className="text-[10px] uppercase tracking-[0.3em] text-gray-400">
                {alertContextStatusLabel}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-slate-700 bg-black/40 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] text-white">
              {activeAlertContext.severity?.toUpperCase() || 'Severity unknown'}
            </span>
            <span className="rounded-full border border-slate-700 bg-black/40 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] text-white">
              {activeAlertContext.status?.toUpperCase() || 'Status unknown'}
            </span>
            <span className="rounded-full border border-slate-700 bg-black/40 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] text-white">
              #{activeAlertContext.alert_id ?? '—'}
            </span>
          </div>
          <p className="text-sm leading-relaxed text-gray-300">
            {activeAlertContext.message || 'No additional alert details were provided.'}
          </p>
          {alertPromptPreview && (
            <p className="text-xs text-gray-400">
              {alertPromptPreview}
            </p>
          )}
          {alertContextError && (
            <p className="text-xs text-rose-300">{alertContextError}</p>
          )}
        </div>
      )}
      <div className="rounded-[34px] border border-slate-800 bg-gradient-to-br from-slate-950/80 to-slate-900/60 p-6 shadow-[0_28px_60px_rgba(2,6,23,0.9)]">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-sky-300">Learned preferences</p>
            <h2 className="text-2xl font-semibold text-white">Trading style snapshot</h2>
          </div>
          <span className="text-[10px] uppercase tracking-[0.3em] text-gray-400">
            {styleLoading ? 'Updating now' : 'Recent profile'}
          </span>
        </div>
        {styleLoading ? (
          <p className="mt-3 text-sm text-gray-400">Aligning recommendations with your habits…</p>
        ) : styleError ? (
          <p className="mt-3 text-sm text-rose-300">{styleError}</p>
        ) : styleProfile ? (
          <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {[
              { label: 'Dominant bias', value: styleProfile.dominant_side ?? 'Neutral' },
              { label: 'Risk tolerance', value: styleProfile.risk_tolerance ?? 'Balanced' },
              {
                label: 'Avg trade duration',
                value: formatDurationMinutes(styleProfile.avg_trade_duration_minutes),
              },
              {
                label: 'Favorite symbols',
                value: formatFavoriteSymbols(styleProfile.favorite_symbols),
              },
              {
                label: 'Aggressiveness',
                value: formatAggressivenessScore(styleProfile.aggressiveness_score),
              },
              {
                label: 'Recent trades',
                value: styleProfile.recent_trade_count ?? 0,
              },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-2xl border border-slate-800/60 bg-black/40 p-3 shadow-[0_10px_30px_rgba(0,0,0,0.45)]"
              >
                <dt className="text-[10px] uppercase tracking-[0.3em] text-gray-500">{item.label}</dt>
                <dd className="mt-1 text-sm font-semibold text-white">{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="mt-3 text-sm text-gray-400">
            The AI is still building your profile from recent trades and conversations.
          </p>
        )}
      </div>
      <ChatWindow />
    </section>
  );
};

export default AIChat;
