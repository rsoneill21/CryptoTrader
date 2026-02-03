import React, { useEffect, useMemo, useState } from 'react';
import ChatWindow from '../components/ChatWindow';

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

const AIChat = () => {
  const [tonePreference, setTonePreference] = useState(loadStoredChatTone);

  useEffect(() => {
    setGlobalChatTone(tonePreference);
  }, [tonePreference]);

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
      <ChatWindow />
    </section>
  );
};

export default AIChat;
