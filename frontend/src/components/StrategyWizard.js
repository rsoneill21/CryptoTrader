import React, { useState } from 'react';
import { strategiesAPI } from '../services/api';

/**
 * StrategyWizard component provides a multi-step flow for generating
 * new trading strategies using AI.
 * 
 * Steps:
 * 1. Intent: User describes the strategy and selects risk/symbols.
 * 2. Generation: AI processes the request.
 * 3. Review: User reviews the generated proposal and can edit rules.
 */
const StrategyWizard = ({ isOpen, onClose, onSave }) => {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Step 1 state
  const [description, setDescription] = useState('');
  const [riskProfile, setRiskProfile] = useState('balanced');
  const [symbols, setSymbols] = useState('BTC/USD');

  // Step 3 state (Review)
  const [proposal, setProposal] = useState(null);
  const [editedRules, setEditedRules] = useState({});
  const [strategyName, setStrategyName] = useState('');

  if (!isOpen) return null;

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await strategiesAPI.generateStrategy({
        symbols: symbols.split(',').map(s => s.trim()),
        notes: description,
        risk_tolerance: riskProfile,
      });
      
      // The suggestions endpoint returns a list of suggestions per symbol
      // We take the first one that has a successful AI proposal
      const suggestion = response.data.suggestions.find(s => s.ai_proposal && !s.ai_error) || response.data.suggestions[0];
      
      if (suggestion && suggestion.ai_proposal) {
        setProposal(suggestion.ai_proposal);
        setEditedRules(suggestion.ai_proposal.rules || {});
        setStrategyName(suggestion.ai_proposal.name || `AI ${suggestion.symbol} Strategy`);
        setStep(3);
      } else if (suggestion && suggestion.ai_error) {
        setError(suggestion.ai_error);
        setStep(1);
      } else {
        setError('AI failed to generate a strategy proposal. Please try a different description.');
        setStep(1);
      }
    } catch (err) {
      setError(err.message || 'Failed to generate strategy. Please check your connection.');
      setStep(1);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setError(null);
    try {
      await strategiesAPI.saveStrategy({
        name: strategyName,
        description: proposal.description || proposal.thesis,
        rules: editedRules,
        status: 'paper',
        source: 'ai_wizard'
      });
      onSave();
      onClose();
      // Reset state for next time
      setStep(1);
      setDescription('');
      setProposal(null);
    } catch (err) {
      setError(err.message || 'Failed to save strategy');
    } finally {
      setLoading(false);
    }
  };

  const updateRule = (key, value) => {
    setEditedRules(prev => ({
      ...prev,
      [key]: value
    }));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-2xl border border-gray-700 bg-gray-900 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-800 flex justify-between items-center bg-gray-900/50">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <span className="text-blue-500">✨</span> Strategy Wizard
          </h2>
          <button onClick={onClose} className="text-gray-500 hover:text-white transition p-2 hover:bg-white/5 rounded-full">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {step === 1 && (
            <div className="space-y-6">
              <div className="space-y-1">
                <label className="block text-sm font-medium text-gray-400">What&apos;s your strategy idea?</label>
                <p className="text-xs text-gray-500 mb-2">Describe the logic you want the AI to implement.</p>
                <textarea
                  className="w-full h-32 px-4 py-3 rounded-xl border border-gray-700 bg-gray-800 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition resize-none placeholder:text-gray-600"
                  placeholder="e.g. A mean reversion strategy that buys when RSI is below 30 and sells when it touches the upper Bollinger Band..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="block text-sm font-medium text-gray-400">Symbols (comma separated)</label>
                  <input
                    type="text"
                    className="w-full px-4 py-3 rounded-xl border border-gray-700 bg-gray-800 text-white focus:ring-2 focus:ring-blue-500 transition"
                    value={symbols}
                    onChange={(e) => setSymbols(e.target.value)}
                    placeholder="BTC/USD, ETH/USD"
                  />
                </div>
                <div className="space-y-1">
                  <label className="block text-sm font-medium text-gray-400">Risk Profile</label>
                  <select
                    className="w-full px-4 py-3 rounded-xl border border-gray-700 bg-gray-800 text-white focus:ring-2 focus:ring-blue-500 transition"
                    value={riskProfile}
                    onChange={(e) => setRiskProfile(e.target.value)}
                  >
                    <option value="conservative">Conservative</option>
                    <option value="balanced">Balanced</option>
                    <option value="aggressive">Aggressive</option>
                  </select>
                </div>
              </div>

              {error && (
                <div className="text-sm text-red-400 bg-red-400/10 p-3 rounded-lg border border-red-400/20 flex gap-2 items-center">
                  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {error}
                </div>
              )}

              <button
                onClick={() => { setStep(2); handleGenerate(); }}
                disabled={!description || !symbols || loading}
                className="w-full py-4 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-bold hover:from-blue-500 hover:to-indigo-500 transition shadow-lg shadow-blue-500/20 disabled:opacity-50 disabled:shadow-none"
              >
                {loading ? 'Consulting AI...' : 'Generate Strategy Proposal'}
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="py-20 flex flex-col items-center justify-center space-y-6">
              <div className="relative">
                <div className="w-20 h-20 border-4 border-blue-500/10 border-t-blue-500 rounded-full animate-spin"></div>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-2xl animate-pulse">🤖</span>
                </div>
              </div>
              <div className="text-center space-y-2">
                <p className="text-xl font-bold text-white">AI is formulating your strategy</p>
                <p className="text-sm text-gray-400 max-w-xs mx-auto">Analyzing historical patterns and building specific execution rules based on your intent.</p>
              </div>
            </div>
          )}

          {step === 3 && proposal && (
            <div className="space-y-6">
              <div className="space-y-3">
                <div className="flex justify-between items-start">
                  <h3 className="text-lg font-bold text-white">{strategyName}</h3>
                  <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 text-[10px] font-bold uppercase tracking-wider">
                    {proposal.provider} proposed
                  </span>
                </div>
                <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-4">
                  <p className="text-sm text-blue-100 italic leading-relaxed">&quot;{proposal.description}&quot;</p>
                </div>
              </div>

              <div className="space-y-3">
                <label className="block text-sm font-medium text-gray-400 uppercase tracking-widest text-[10px]">Rule Parameters</label>
                <div className="grid grid-cols-2 gap-x-4 gap-y-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar p-1">
                  {Object.entries(editedRules).length > 0 ? (
                    Object.entries(editedRules).map(([key, value]) => (
                      <div key={key} className="space-y-1">
                        <label className="text-[10px] font-bold text-gray-500 uppercase">{key.replace(/_/g, ' ')}</label>
                        {typeof value === 'number' ? (
                          <input
                            type="number"
                            step="any"
                            className="w-full px-3 py-2 rounded-lg border border-gray-700 bg-gray-800 text-white text-sm focus:ring-2 focus:ring-blue-500 transition"
                            value={value}
                            onChange={(e) => updateRule(key, parseFloat(e.target.value))}
                          />
                        ) : (
                          <input
                            type="text"
                            className="w-full px-3 py-2 rounded-lg border border-gray-700 bg-gray-800 text-white text-sm focus:ring-2 focus:ring-blue-500 transition"
                            value={typeof value === 'object' ? JSON.stringify(value) : value}
                            onChange={(e) => updateRule(key, e.target.value)}
                          />
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="col-span-2 text-xs text-gray-500 italic">No adjustable numeric parameters found.</p>
                  )}
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-sm font-medium text-gray-400">Final Strategy Name</label>
                <input
                  type="text"
                  className="w-full px-4 py-3 rounded-xl border border-gray-700 bg-gray-800 text-white focus:ring-2 focus:ring-blue-500 transition"
                  value={strategyName}
                  onChange={(e) => setStrategyName(e.target.value)}
                />
              </div>

              {error && (
                <div className="text-sm text-red-400 bg-red-400/10 p-3 rounded-lg border border-red-400/20 flex gap-2 items-center">
                  <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {error}
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 py-3 rounded-xl border border-gray-700 text-gray-400 font-semibold hover:bg-gray-800 transition"
                >
                  Edit Intent
                </button>
                <button
                  onClick={handleSave}
                  disabled={loading}
                  className="flex-[2] py-3 rounded-xl bg-blue-600 text-white font-bold hover:bg-blue-500 transition shadow-lg shadow-blue-500/20 disabled:opacity-50"
                >
                  {loading ? 'Saving...' : 'Deploy to Paper Trading'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StrategyWizard;
