import React, { useMemo } from 'react';

const clampScore = (value) => {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return 0;
  }
  return Math.min(100, Math.max(0, numeric));
};

const buildConfidenceTier = (value) => {
  if (value >= 80) {
    return 'High';
  }
  if (value >= 55) {
    return 'Medium';
  }
  return 'Low';
};

const confidenceBadgeClass = (value) => {
  if (value >= 80) {
    return 'border border-emerald-500/40 bg-emerald-500/10 text-emerald-300';
  }
  if (value >= 55) {
    return 'border border-sky-500/40 bg-sky-500/10 text-sky-200';
  }
  return 'border border-amber-500/40 bg-amber-500/10 text-amber-200';
};

const toTimestamp = (offsetMinutes) => new Date(Date.now() - offsetMinutes * 60000).toISOString();

const DEFAULT_THINKING = [
  'Price is consolidating against the 50% retracement while derivatives skew stays neutral, so patience is rewarded.',
  'Momentum has softened but volume is holding above the daily VWAP zone.',
  'Macro liquidity is favoring Bitcoin, while altcoins show relative strength on the short squeeze radar.',
  'The AI is monitoring Kraken order depth for early imbalance clues before firing entry signals.',
];

const DEFAULT_DECISIONS = [
  {
    id: 'decision-1',
    summary: 'Delay new entries until BTC clears resistance at 48.2k with confirmation candle close.',
    type: 'Signal gating',
    timestamp: toTimestamp(2),
    confidence: 71,
  },
  {
    id: 'decision-2',
    summary: 'Increase coverage on ETH/USDT after support re-test and positive on-chain sentiment.',
    type: 'Position sizing',
    timestamp: toTimestamp(8),
    confidence: 64,
  },
  {
    id: 'decision-3',
    summary: 'Close small SOL swing once the 12h RSI rolls over to avoid fade risk.',
    type: 'Risk control',
    timestamp: toTimestamp(15),
    confidence: 59,
  },
];

const DEFAULT_CONFIDENCE = [
  { id: 'conf-1', label: 'Trend clarity', detail: 'Higher timeframe momentum aligns with bias.', score: 84 },
  { id: 'conf-2', label: 'Signal validity', detail: 'Fresh liquidity and order flow support the trigger.', score: 72 },
  { id: 'conf-3', label: 'Risk posture', detail: 'Drawdown buffer is within tolerance levels.', score: 65 },
];

const formatTimestamp = (iso) => {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return 'Unknown';
  }
  return parsed.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

const ReasoningPanel = ({
  thinking = DEFAULT_THINKING,
  decisions = DEFAULT_DECISIONS,
  confidence = DEFAULT_CONFIDENCE,
  lastUpdated,
}) => {
  const sortedDecisions = useMemo(() => {
    return [...decisions].sort((a, b) => {
      const aTime = new Date(a.timestamp).getTime() || 0;
      const bTime = new Date(b.timestamp).getTime() || 0;
      return bTime - aTime;
    });
  }, [decisions]);

  const normalizedConfidence = useMemo(() => {
    if (!confidence.length) {
      return 0;
    }
    const total = confidence.reduce((sum, entry) => sum + clampScore(entry.score), 0);
    return Math.round(total / confidence.length);
  }, [confidence]);

  const lastUpdatedTime = useMemo(() => {
    if (lastUpdated) {
      const parsed = new Date(lastUpdated);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed;
      }
    }
    return new Date();
  }, [lastUpdated]);

  const insightHeadline = thinking[0] || 'AI is calibrating its next move and will update shortly.';
  const supportingPoints = thinking.slice(1, 4);

  return (
    <section className="space-y-6 rounded-[32px] border border-gray-800 bg-gradient-to-br from-gray-900/80 to-black/60 p-6 shadow-2xl shadow-black/60">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-sky-400">AI reasoning</p>
          <h2 className="text-2xl font-semibold text-white">Current thinking</h2>
        </div>
        <p className="text-xs capitalize text-gray-500">Updated {lastUpdatedTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
      </div>

      <div className="space-y-3">
        <p className="text-lg font-semibold text-white">{insightHeadline}</p>
        <ul className="space-y-2 text-sm text-gray-300">
          {supportingPoints.map((point) => (
            <li key={point} className="flex items-start gap-2">
              <span className="mt-1 h-1.5 w-1.5 rounded-full bg-sky-400" />
              <span>{point}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-3 rounded-[24px] border border-gray-800 bg-gray-950/60 p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Recent decisions</p>
            <span className="text-[11px] uppercase tracking-[0.3em] text-gray-500">{sortedDecisions.length} logged</span>
          </div>
          <div className="space-y-3">
            {sortedDecisions.map((decision) => (
              <div key={decision.id} className="space-y-1 rounded-2xl border border-gray-800/70 bg-black/40 p-3">
                <div className="flex items-center justify-between text-xs uppercase tracking-[0.3em] text-gray-500">
                  <span>{decision.type}</span>
                  <span>{formatTimestamp(decision.timestamp)}</span>
                </div>
                <p className="text-sm text-gray-200">{decision.summary}</p>
                <div className="flex items-center justify-between text-[11px]">
                  <span className={`rounded-full px-2 py-1 ${confidenceBadgeClass(clampScore(decision.confidence))}`}>
                    Confidence {clampScore(decision.confidence)}%
                  </span>
                  <span className="text-gray-400">{buildConfidenceTier(decision.confidence)} certainty</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4 rounded-[24px] border border-gray-800 bg-gradient-to-b from-slate-900/80 to-black/60 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-blue-300">Confidence score</p>
              <p className="text-sm text-gray-400">Average across indicators</p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-semibold text-white">{normalizedConfidence}%</p>
              <p className="text-xs text-gray-500">{buildConfidenceTier(normalizedConfidence)}</p>
            </div>
          </div>
          <div className="h-2 w-full rounded-full bg-gray-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-cyan-400 via-blue-500 to-indigo-500"
              style={{ width: `${clampScore(normalizedConfidence)}%` }}
            />
          </div>
          <p className="text-[11px] text-gray-500">Scores update as soon as new analyst decisions are logged.</p>
          <div className="space-y-3">
            {confidence.map((entry) => (
              <div key={entry.id} className="space-y-1">
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span>{entry.label}</span>
                  <span className="font-semibold text-white">{clampScore(entry.score)}%</span>
                </div>
                <div className="h-1.5 w-full rounded-full bg-gray-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-emerald-400 via-sky-400 to-indigo-500"
                    style={{ width: `${clampScore(entry.score)}%` }}
                  />
                </div>
                <p className="text-[11px] text-gray-500">{entry.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default ReasoningPanel;
