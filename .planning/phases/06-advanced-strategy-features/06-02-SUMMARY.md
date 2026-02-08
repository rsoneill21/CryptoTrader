---
phase: 06-advanced-strategy-features
plan: 02
subsystem: strategy-engine
tags: [self-healing, health-monitoring, ai-intervention]
provides: [strategy-health-monitoring, automated-degradation-analysis]
tech-stack:
  added: []
  patterns: [Periodic Health Checks, Automated AI Re-optimization]
key-files:
  created: [backend/tests/services/test_strategy_health.py, backend/tests/core/test_tasks_health.py]
  modified: [backend/services/strategy_service.py, backend/core/tasks.py, backend/db/models.py, backend/services/strategy_ai.py, backend/api/strategies.py]
metrics:
  duration: 12m
  completed: 2026-02-08
---

# Phase 6 Plan 2: Strategy Health Monitoring Summary

Implemented "Self-Healing" capabilities by establishing a system to monitor strategy health and automatically trigger AI-driven interventions when performance degrades.

## One-liner
Established a periodic monitoring loop that identifies degrading strategies and generates AI-powered adjustment proposals.

## Key Accomplishments

### 1. Strategy Health Evaluation Logic
- Implemented `check_strategy_health` in `strategy_service.py`.
- Evaluates strategies based on recent trade performance (lookback of N trades).
- Categorizes health as `HEALTHY`, `DEGRADED`, or `CRITICAL` based on Win Rate and Max Drawdown thresholds.

### 2. Periodic Monitoring Task
- Added `monitor_active_strategies` Celery task to `backend/core/tasks.py`.
- Automated hourly scanning of all "live" and "paper" strategies.
- Triggers system alerts when degradation is detected.

### 3. AI-Driven Degradation Analysis
- Implemented `analyze_degradation` in `strategy_ai.py`.
- When a strategy is flagged, the AI service analyzes recent failures and proposes concrete rule adjustments.
- Proposals are stored in the new `pending_adjustment_json` field on the `Strategy` model for user review.

### 4. Database & API Support
- Extended the `Strategy` model with `health_status` and `pending_adjustment_json`.
- Updated `StrategyResponse` and serialization logic to expose these fields to the frontend.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed duplicated code in strategies API**
- **Found during:** Verification of the plan.
- **Issue:** `ArchivePaperTradingResponse` and `archive_paper_trading_session` were duplicated at the end of `backend/api/strategies.py`.
- **Fix:** Removed the redundant code blocks.
- **Files modified:** `backend/api/strategies.py`
- **Commit:** [In progress]

## Verification Results

### Automated Tests
- `backend/tests/services/test_strategy_health.py`: **PASSED**
- `backend/tests/core/test_tasks_health.py`: **PASSED**
- Verified that seeding losing trades correctly flags a strategy as DEGRADED or CRITICAL.
- Verified that the periodic task creates Alerts and calls the AI service.

### Success Criteria
- [x] Periodic task correctly identifies strategies with WinRate < 40% or Drawdown > 15%.
- [x] Degraded strategies are flagged and Alerts generated.
- [x] AI service provides adjustment suggestions for flagged strategies.
