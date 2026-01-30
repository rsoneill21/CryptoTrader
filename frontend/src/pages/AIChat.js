import React from 'react';
import ChatWindow from '../components/ChatWindow';

const AIChat = () => (
  <section className="space-y-6 text-white">
    <header className="space-y-2">
      <p className="text-xs uppercase tracking-[0.4em] text-sky-400">Phase 7 · AI Orchestrator</p>
      <h1 className="text-3xl font-semibold text-white">AI Chat</h1>
      <p className="max-w-3xl text-sm text-gray-300">
        Talk directly with the orchestrator to surface risk-aware trade ideas, review AI reasoning, and keep a
        streaming log of every interaction.
      </p>
    </header>
    <ChatWindow />
  </section>
);

export default AIChat;
