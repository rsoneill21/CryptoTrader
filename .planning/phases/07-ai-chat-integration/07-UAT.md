# UAT: Phase 07 - AI Chat Integration

**Status:** In Progress
**Phase Goal:** Users can query trading context and get recommendations via AI assistant.

## Test Results

| ID | Test Case | Expected Behavior | Status | Notes |
|----|-----------|-------------------|--------|-------|
| 7.1 | Broad Prompt Clarification | Prompting "How am I doing?" returns a clarifying follow-up asking for a specific timeframe or asset. | Pending | |
| 7.2 | Stale Context Refusal | If portfolio data is old, AI refuses to give advice and asks the user to refresh the dashboard or wait for updates. | Pending | |
| 7.3 | Incomplete Context Refusal | Asking "Why did you trade BTC?" when rationale is missing returns a refusal explaining the missing data. | Pending | |
| 7.4 | Recommendation Badges | BUY/SELL/HOLD recommendations appear as color-coded badges with primary and backup options. | Pending | |
| 7.5 | Portfolio Impact | Suggestions include a "Portfolio Impact" section showing how the trade affects exposure. | Pending | |
| 7.6 | Structured Trade Rationale | "Why trade" queries show a structured deep-dive: Thesis, Signals, Risk Analysis, and watch-for conditions. | Pending | |
| 7.7 | Streaming Integrity | Chat text streams in smoothly without raw `data:` or `<rationale>` protocol text appearing in the bubble. | Pending | |
| 7.8 | History Normalization | Refreshing the page preserves chat history in the correct User -> Assistant turn order. | Pending | |

## Gaps Identified
*(None yet)*
