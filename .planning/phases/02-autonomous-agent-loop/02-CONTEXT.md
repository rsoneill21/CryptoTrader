# Phase 2: Autonomous Agent Loop - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Spin up the Market Analyst, Orchestrator, and Trade Executor agents automatically with the FastAPI backend so they exchange signals through the queue, place paper orders, and stay alive even when individual agents fail. This phase is only about the autonomous loop; richer strategy/risk features happen later.

</domain>

<decisions>
## Implementation Decisions

### Agent Scheduling & Start/Stop
- Agents should start in a staggered sequence after backend startup health checks (backend → Market Analyst → Orchestrator → Trade Executor).
- Market Analyst runs an always-on loop, while Orchestrator and Trade Executor wake up based on incoming events.
- Operators need admin UI toggles to pause/resume each agent; changing a toggle gracefully stops the agent after it finishes its current work and restarts when toggled back on.
- Deploy one instance of Orchestrator and one Trade Executor; allow multiple Market Analyst instances (configurable) when more data streams are needed.

### Message Flow & Coordination
- Analyst → Orchestrator → Executor messages should contain the full analysis bundle (raw indicators, sentiment, references) so downstream steps can audit without extra DB lookups.
- Use priority queues so critical/urgent signals bypass routine chatter; priorities should reflect urgency (e.g., halt signals > rebalance > research ideas).

### Failure Handling & Recovery
- If an agent crashes, restart it immediately; no manual confirmation needed.
- Surface failure/restart state on the dashboard rather than pushing Slack/email alerts.
- When the queue backs up, drop the oldest signals so fresh data continues to flow; log what was discarded for audit.
- When the Trade Executor cannot place an order, apply a fallback strategy automatically (e.g., reduced position size or alternate venue) before marking the signal failed.

### Observability & Operator Controls
- Operator dashboard must show: (1) agent status grid with heartbeat timestamps, (2) pipeline timeline illustrating recent messages flowing through the loop, and (3) queue metrics (depth, throughput, latency).
- Log agent telemetry through the existing system log API endpoints so the current monitoring tooling can consume it.
- Provide limited safe actions in the dashboard (e.g., flush queue, retry a failed signal) in addition to the pause/resume toggles.

### Claude's Discretion
- Choose the exact messaging backbone/transport implementation that best fits these behaviors.
- Set the message delivery guarantee (e.g., at-least-once vs exactly-once) consistent with the chosen transport.
- Define the heartbeat freshness threshold (user is fine with Claude picking the window).
- Include any additional dashboard insights beyond the three mandated widgets.

</decisions>

<specifics>
## Specific Ideas

- Limited operator actions should include the ability to flush a backlog or retry a failed signal without exposing powerful arbitrary controls.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 02-autonomous-agent-loop*
*Context gathered: 2026-02-05*
