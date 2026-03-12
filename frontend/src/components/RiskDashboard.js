import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api from '../services/api';

const formatNumber = (value, decimals = 1) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '0.0';
  }
  return Number(value).toFixed(decimals);
};

const formatCurrency = (value) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '$0.00';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
};

const getGaugeColor = (ratio, status) => {
  if (status === 'alert' || ratio >= 1) {
    return '#f87171';
  }
  if (ratio >= 0.9) {
    return '#f97316';
  }
  if (ratio >= 0.75) {
    return '#facc15';
  }
  return '#34d399';
};

const RiskGauge = ({ scoreValue, threshold, status }) => {
  const current = Number(scoreValue ?? 0);
  const target = Number(threshold ?? 0);
  const ratio = target > 0 ? Math.min(1, current / target) : 0;
  const fillPercent = Math.round(ratio * 100);
  const color = getGaugeColor(ratio, status);
  const background = '#0f172a';

  return (
    <div className="flex flex-col items-center justify-center space-y-3">
      <div className="relative w-52 h-52">
        <div
          className="w-full h-full rounded-full"
          style={{
            background: `conic-gradient(${color} ${fillPercent}%, ${background} ${fillPercent}% 100%)`,
          }}
        />
        <div className="absolute inset-6 flex flex-col items-center justify-center rounded-full bg-slate-900/90 border border-gray-800">
          <p className="text-sm uppercase tracking-widest text-gray-400">Risk score</p>
          <p className="text-3xl font-semibold text-white">{formatNumber(current)}</p>
          <p className="text-xs text-gray-400">of {target > 0 ? formatNumber(target, 0) : '—'}</p>
        </div>
      </div>
      <div className="text-center">
        <p className="text-sm font-semibold text-white">{status === 'alert' ? 'Alert level' : 'Within guardrails'}</p>
        <p className="text-xs text-gray-400">{fillPercent}% of alert threshold</p>
      </div>
    </div>
  );
};

const FactorCard = ({ factor }) => (
  <div className="rounded-2xl border border-gray-700/80 bg-gray-900/50 p-4 shadow-sm shadow-black/20">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-sm font-semibold uppercase tracking-widest text-gray-400">{factor.title}</p>
        <p className="text-2xl font-semibold text-white">{factor.limitLabel}</p>
      </div>
      <span className="rounded-full bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-300">
        Weight {factor.weight}%
      </span>
    </div>
    <p className="mt-3 text-sm text-gray-400">{factor.description}</p>
    <div className="mt-3 h-1.5 rounded-full bg-gray-800">
      <div
        className="h-full rounded-full"
        style={{
          width: `${factor.progress}%`,
          background: `linear-gradient(90deg, #22d3ee, #6366f1)`,
        }}
      />
    </div>
    <p className="mt-2 text-xs text-gray-400">{factor.hint}</p>
  </div>
);

const RiskDashboard = () => {
  const [settings, setSettings] = useState(null);
  const [score, setScore] = useState(null);
  const [formState, setFormState] = useState({
    max_position_size_pct: '',
    max_concurrent_positions: '',
    daily_loss_limit: '',
    max_drawdown_pct: '',
    max_risk_score: '',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const isMountedRef = useRef(true);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadRiskData = useCallback(async () => {
    setLoading(true);
    setErrorMessage('');
    setSuccessMessage('');

    try {
      const [settingsRes, scoreRes] = await Promise.all([
        api.get('/api/risk/settings'),
        api.get('/api/risk/score'),
      ]);
      if (!isMountedRef.current) {
        return;
      }
      const data = settingsRes.data;
      setSettings(data);
      setFormState({
        max_position_size_pct: String(data.max_position_size_pct ?? ''),
        max_concurrent_positions: String(data.max_concurrent_positions ?? ''),
        daily_loss_limit: String(data.daily_loss_limit ?? ''),
        max_drawdown_pct: String(data.max_drawdown_pct ?? ''),
        max_risk_score: String(data.max_risk_score ?? ''),
      });
      setScore(scoreRes.data);
    } catch (err) {
      if (!isMountedRef.current) {
        return;
      }
      console.error('Risk dashboard load failed:', err);
      setErrorMessage(err.message || 'Failed to load risk data.');
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    loadRiskData();
  }, [loadRiskData]);

  const handleInputChange = (field) => (event) => {
    setFormState((prev) => ({
      ...prev,
      [field]: event.target.value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setErrorMessage('');
    setSuccessMessage('');

    try {
      const payload = {
        max_position_size_pct: Number(formState.max_position_size_pct ?? 0),
        max_concurrent_positions: Number(formState.max_concurrent_positions ?? 0),
        daily_loss_limit: Number(formState.daily_loss_limit ?? 0),
        max_drawdown_pct: Number(formState.max_drawdown_pct ?? 0),
        max_risk_score: Number(formState.max_risk_score ?? 0),
      };
      await api.put('/api/risk/settings', payload);
      setSuccessMessage('Risk limits saved successfully.');
      await loadRiskData();
    } catch (err) {
      console.error('Risk settings save failed:', err);
      setErrorMessage(err.message || 'Unable to save settings.');
    } finally {
      if (isMountedRef.current) {
        setSaving(false);
      }
    }
  };

  const riskRatio = useMemo(() => {
    if (!score) {
      return 0;
    }
    return score.threshold > 0 ? Math.min(1, score.current_score / score.threshold) : 0;
  }, [score]);

  const factorBreakdown = useMemo(() => {
    if (!settings) {
      return [];
    }

    const weightMap = [
      {
        id: 'position',
        title: 'Position exposure',
        description: 'Largest open trade compared against the configured position size cap.',
        limitLabel: `${formatNumber(settings.max_position_size_pct ?? 0, 1)}% of equity`,
        hint: 'Position weight: 30% of the risk score.',
        weight: 30,
      },
      {
        id: 'concurrent',
        title: 'Concurrent positions',
        description: 'Total open trades relative to the concurrency limit.',
        limitLabel: `${settings.max_concurrent_positions ?? 0} positions`,
        hint: 'Concurrent weight: 20%, keeps the book manageable.',
        weight: 20,
      },
      {
        id: 'daily_loss',
        title: 'Daily loss',
        description: 'Cumulative losses during the trading day versus the guardrail.',
        limitLabel: `${formatCurrency(settings.daily_loss_limit ?? 0)} limit`,
        hint: 'Daily loss weight: 30% of the score.',
        weight: 30,
      },
      {
        id: 'drawdown',
        title: 'Drawdown',
        description: 'Rolling drawdown compared to the configured maximum.',
        limitLabel: `${formatNumber(settings.max_drawdown_pct ?? 0, 1)}% drawdown`,
        hint: 'Drawdown weight: 20% and triggers alerts fastest.',
        weight: 20,
      },
    ];

    return weightMap.map((factor) => ({
      ...factor,
      progress: Math.min(100, riskRatio * 100 * (factor.weight / 40)),
    }));
  }, [settings, riskRatio]);

  const lastUpdatedText = useMemo(() => {
    if (!score?.last_updated) {
      return 'Last updated: —';
    }
    const updatedAt = new Date(score.last_updated);
    return `Last updated: ${updatedAt.toLocaleString()}`;
  }, [score]);

  return (
    <div className="space-y-6 p-4">
      <div className="flex flex-col gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-white">Risk Dashboard</h1>
          <p className="text-sm text-gray-400">Monitor risk exposure, factor weights, and guardrail settings.</p>
        </div>
        {settings?.pending_ai_adjustment && (
          <div className="rounded-2xl border border-yellow-500/70 bg-yellow-500/10 px-4 py-2 text-sm font-semibold text-yellow-200">
            Pending AI recommendation awaiting confirmation.
          </div>
        )}
      </div>

      {loading && (
        <div className="rounded-2xl border border-dashed border-gray-700/60 bg-gray-900/60 p-4 text-sm text-gray-300">
          Loading risk data...
        </div>
      )}

      {!loading && (
        <>
          {errorMessage && (
            <div className="rounded-2xl border border-red-500/70 bg-red-500/10 px-4 py-2 text-sm text-red-100">
              {errorMessage}
            </div>
          )}
          {successMessage && (
            <div className="rounded-2xl border border-emerald-500/70 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-100">
              {successMessage}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-2xl border border-gray-700/60 bg-gradient-to-b from-slate-900/80 to-slate-900/40 p-6">
              <RiskGauge
                scoreValue={score?.current_score}
                threshold={score?.threshold}
                status={score?.status}
              />
              <div className="mt-4 rounded-2xl border border-gray-800/60 bg-gray-900/70 px-4 py-3 text-sm text-gray-300">
                <p>{lastUpdatedText}</p>
                <p className="mt-1">Threshold: {score ? formatNumber(score.threshold, 0) : '—'}</p>
                <p className="text-xs text-gray-500">Status: {score?.status ?? 'loading'}</p>
              </div>
            </div>

            <div className="flex flex-col gap-4">
              <div className="rounded-2xl border border-gray-700/60 bg-gray-900/70 p-4">
                <p className="text-sm text-gray-400">Current risk score</p>
                <p className="text-3xl font-semibold text-white">{score ? formatNumber(score.current_score, 1) : '—'}</p>
                <p className="text-xs text-gray-500">{score ? `${formatNumber(score.ratio * 100, 0)}% of threshold` : ''}</p>
              </div>
              <div className="rounded-2xl border border-gray-700/60 bg-gray-900/70 p-4">
                <p className="text-sm text-gray-400">AI suggestion</p>
                <p className="text-xl font-semibold text-white">
                  {settings?.pending_ai_adjustment ? 'Pending' : 'Not active'}
                </p>
                <p className="text-xs text-gray-500">{settings?.last_ai_recommendation_json ? 'See AI log for details.' : 'Manual guardrails only.'}</p>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-white">Factor breakdown</h2>
              <p className="text-xs uppercase tracking-widest text-gray-500">Weighted contributions</p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {factorBreakdown.map((factor) => (
                <FactorCard key={factor.id} factor={factor} />
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-gray-700/60 bg-gray-900/70 p-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-white">Risk guardrail settings</h2>
                <p className="text-sm text-gray-400">Adjust limits that feed the risk monitor.</p>
              </div>
              <span className="rounded-full border border-gray-700 px-3 py-1 text-xs text-gray-300">Editable</span>
            </div>
            <form onSubmit={handleSubmit} className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="space-y-2 text-sm text-gray-200">
                <span>Max position size (%)</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={formState.max_position_size_pct}
                  onChange={handleInputChange('max_position_size_pct')}
                  className="w-full rounded-xl border border-gray-700 bg-gray-950/70 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <label className="space-y-2 text-sm text-gray-200">
                <span>Max concurrent positions</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={formState.max_concurrent_positions}
                  onChange={handleInputChange('max_concurrent_positions')}
                  className="w-full rounded-xl border border-gray-700 bg-gray-950/70 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <label className="space-y-2 text-sm text-gray-200">
                <span>Daily loss limit (USD)</span>
                <input
                  type="number"
                  min="0"
                  step="10"
                  value={formState.daily_loss_limit}
                  onChange={handleInputChange('daily_loss_limit')}
                  className="w-full rounded-xl border border-gray-700 bg-gray-950/70 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <label className="space-y-2 text-sm text-gray-200">
                <span>Max drawdown (%)</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={formState.max_drawdown_pct}
                  onChange={handleInputChange('max_drawdown_pct')}
                  className="w-full rounded-xl border border-gray-700 bg-gray-950/70 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <label className="space-y-2 text-sm text-gray-200">
                <span>Max risk score (%)</span>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.1"
                  value={formState.max_risk_score}
                  onChange={handleInputChange('max_risk_score')}
                  className="w-full rounded-xl border border-gray-700 bg-gray-950/70 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </label>
              <div className="md:col-span-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="w-full rounded-2xl border border-blue-500 bg-blue-500/80 px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:cursor-wait disabled:bg-blue-500/40"
                >
                  {saving ? 'Saving...' : 'Save guardrail settings'}
                </button>
              </div>
            </form>
          </div>
        </>
      )}
    </div>
  );
};

export default RiskDashboard;
