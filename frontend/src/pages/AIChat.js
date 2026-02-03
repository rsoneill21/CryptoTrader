import React, { useEffect, useMemo, useState } from 'react';
import ChatWindow from '../components/ChatWindow';
import api from '../services/api';

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
    const merged = { ...parsedBody, tone };
    const clonedInit = { ...(init || {}), body: JSON.stringify(merged) };
    return baseFetch(input, clonedInit);
  };
};

if (typeof window !== 'undefined') {
  window.__cryptotraderChatTone = window.__cryptotraderChatTone ?? loadStoredChatTone();
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

const AIChat = () => {
  const [tonePreference, setTonePreference] = useState(loadStoredChatTone);
  const [styleProfile, setStyleProfile] = useState(null);
  const [styleLoading, setStyleLoading] = useState(true);
  const [styleError, setStyleError] = useState('');

  useEffect(() => {
    setGlobalChatTone(tonePreference);
  }, [tonePreference]);

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
          <p className="text-xs text-gray-400 max-w-3xl">{currentToneDetails.description}</p>
        </div>
      </header>
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
