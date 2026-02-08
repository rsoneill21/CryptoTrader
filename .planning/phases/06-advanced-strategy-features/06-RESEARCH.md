# Research: Phase 06 - Advanced Strategy Features

**Objective:** Enable multi-timeframe strategies, AI generation/customization, and automated lifecycle management (promotion/adjustment).

## 1. Multi-Timeframe Strategy Logic

**Current State:**
- `MarketData` supports `timeframe` column.
- `StrategyEvaluator` (Phase 5) likely processes a single DataFrame of candles.
- `KrakenService` supports standard intervals.

**Gap:**
- Strategy rules need to specify context: `{"indicator": "rsi", "window": 14, "timeframe": "1h"}`.
- Evaluator needs to fetch/align data from multiple timeframes.
    - *Challenge:* Aligning "1h" RSI with "1m" price action.
    - *Solution:* Use "forward-fill" logic. The 1h RSI value applies to all 1m candles until the next hour closes.

**Implementation Plan:**
- Update `StrategyEvaluator.evaluate()` to accept a map of DataFrames: `Dict[str, pd.DataFrame]`.
- Update rule schema to include optional `timeframe` field (default to base timeframe).
- Implementation detail: `resample()` lower timeframe data if higher timeframe data is missing, or fetch explicitly.

## 2. AI Strategy Generation & Wizard UI

**Current State:**
- `backend/services/strategy_ai.py` exists with `propose_strategy`.
- Returns structured `StrategyProposal`.

**Gap:**
- No UI for this interaction.
- "Customization" means editing the JSON or a form view of the parameters.

**Implementation Plan:**
- **Backend:** Ensure `propose_strategy` returns adjustable parameters separate from logic where possible (e.g., `params` dict vs `rules` logic).
- **Frontend (Wizard):**
    1.  **Intent:** User types idea / constraints.
    2.  **Generation:** Loading state -> AI response.
    3.  **Refinement:** "Make it more aggressive" -> Re-roll.
    4.  **Tuning:** Sliders/Inputs for thresholds (RSI 30 vs 40).
    5.  **Backtest (Optional):** Quick verify (Phase 5 integration).
    6.  **Save:** Commit to DB.

## 3. Promotion Lifecycle

**Current State:**
- `Strategy.status` field exists.
- `BacktestRun` exists (Phase 5).

**Gap:**
- Formal process for "Paper -> Live".
- Safety checks (min trades, min win rate).

**Implementation Plan:**
- **Backend:** `POST /api/strategies/{id}/promote`
    - Checks prerequisites (e.g., >10 paper trades, profitable).
    - Updates status to 'live'.
    - Logs event.
- **Frontend:** "Promote" button on Strategy Lab card.
    - Shows summary modal: "This strategy has 55% win rate. Promote to live?"

## 4. Auto-Adjustment (Self-Healing)

**Current State:**
- Concept only.

**Gap:**
- How to detect degradation?
- How to adjust safe?

**Implementation Plan:**
- **Monitor:** Background task `monitor_strategy_health` (hourly/daily).
- **Trigger:**
    - Drawdown > 1.5x expected.
    - Win rate drops < 40% (rolling 20 trades).
- **Action:**
    - **Step 1:** Pause strategy? Or flag for review.
    - **Step 2 (AI):** Generate `StrategyUpdate` suggestion.
    - **Step 3:** Notify user (Alerts).
    - **Step 4:** User approves update.

## 5. Conflict Resolution (Multi-Timeframe)

**Context:**
- What if 1m says BUY but 1h says SELL?

**Decision:**
- Rules defines logic. e.g. `1h_trend == UP AND 1m_rsi < 30`.
- System assumes explicit AND logic unless specified.
- "Conflict" is just "Conditions not met".

## Actionable Tasks

1.  **Backend:** Upgrade `StrategyEvaluator` for multi-timeframe support.
2.  **Backend:** Implement `StrategyPromotion` logic and checks.
3.  **Backend:** Implement `StrategyHealthMonitor` task.
4.  **Frontend:** Build `StrategyWizard` component (AI chat -> Config -> Save).
5.  **Frontend:** Build `PromotionModal` with stats review.
