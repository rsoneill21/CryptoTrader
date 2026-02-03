# DECISIONS

## 2026-01-28 — Codex and Gemini CLI Selection

**Decision:**
Use Codex CLI (`codex`) for implementation and Gemini CLI (`gemini`) for code review within the Triad workflow.

**Context:**
Triad requires three distinct agent roles. Claude (planning) is handled via Claude Code CLI. For implementation (Codex) and review (Gemini), CLI tools provide:
- Scriptable automation
- CI/CD integration capability
- Consistent interface for wrapper scripts

**Options Considered:**
1. Web interfaces only (ChatGPT, AI Studio) — manual, not automatable
2. Direct API calls — more control but more code to maintain
3. Official CLI tools — balance of simplicity and automation

**Outcome:**
CLI tools selected. Wrapper scripts (`feed-codex.sh`, `review-diff.sh`) will abstract CLI usage. If CLIs prove limited, can fall back to direct API calls in Phase 3.

---

## 2026-01-28 — CI/CD Platform Selection

**Decision:**
Use GitHub Actions for Triad automation.

**Context:**
Repo hosted on GitHub (`rsoneill21/triad`). Need automated triggers for:
- Gemini review on PR open/update
- Optional Codex task execution (manual trigger)

**Options Considered:**
1. GitHub Actions — native integration, free for public repos
2. GitLab CI — would require migration
3. CircleCI/Jenkins — additional setup overhead

**Outcome:**
GitHub Actions selected. Native `gh` CLI available in runners. PR comments straightforward via `gh pr comment`.

---

## 2026-01-28 — OpenCode CLI as Implementation Agent

**Decision:**
Use OpenCode CLI (`opencode`) as an implementation agent alongside Codex CLI.

**Context:**
Testing revealed OpenCode is installed and functional. Provides an alternative implementation path with different model options.

**Verified Setup:**
- Path: `~/.opencode/bin/opencode`
- Version: `1.1.36`
- Working model: `opencode/big-pickle`

**Usage:**
```bash
# Basic message
opencode run -m opencode/big-pickle "your prompt here"

# With file attachment
opencode run -m opencode/big-pickle -f PLAN.md "implement task 1"

# Continue previous session
opencode run -c "follow up message"

# JSON output for parsing
opencode run -m opencode/big-pickle --format json "prompt"
```

**Available Models:**
- `opencode/big-pickle` (verified working)
- `opencode/gpt-5-nano`
- `openai/gpt-5.1-codex`
- `openai/gpt-5.1-codex-max`
- `openai/gpt-5.1-codex-mini`
- `openai/gpt-5.2`
- `openai/gpt-5.2-codex`

**Outcome:**
OpenCode available as implementation option. Use `opencode run -m opencode/big-pickle` for tasks. Codex CLI remains primary; OpenCode provides backup/alternative.

---

## 2026-01-28 — AGENTS_STATE.md Ownership Model

**Decision:**
Hybrid ownership of AGENTS_STATE.md across agents.

**Context:**
Single-owner model causes state to lag behind reality. Multi-owner model distributes updates to those with direct knowledge.

**Options Considered:**
1. Claude owns all — simpler but stale
2. Codex owns all — misses planning context
3. Hybrid — each agent owns relevant sections

**Outcome:**
Hybrid model adopted:
- Claude owns: Goal, Constraints, Next
- Codex owns: Completed, In Progress, How to Run
- Gemini owns: Known Issues

---

## 2026-01-28 — Git Branching Strategy

**Decision:**
Use agent-prefixed feature branches with protected main.

**Context:**
Working directly on main risks:
- Untested changes reaching production
- No review opportunity before merge
- Unclear attribution of who changed what
- Merge conflicts between agents

**Options Considered:**
1. **Trunk-based (main only)** — simple but risky, no review gate
2. **Feature branches** — `feature/<name>` — good isolation but unclear ownership
3. **Agent-prefixed branches** — `claude/<task>`, `codex/<task>` — clear ownership + isolation

**Outcome:**
Agent-prefixed branching adopted:

```
main (protected)
├── claude/<task>    ← Planning/documentation changes
├── codex/<task>     ← Implementation work
└── gemini/<task>    ← Review-driven fixes (rare)
```

**Branch Naming Convention:**
- `claude/` — Documentation, PLAN.md, DECISIONS.md, architecture
- `codex/` — Code implementation, scripts, configs
- `gemini/` — Review-initiated fixes (when Gemini identifies issues)

**Workflow:**
1. Create branch: `git checkout -b <agent>/<short-description>`
2. Make changes and commit
3. Push and create PR against main
4. Gemini reviews (for codex branches)
5. Human approves and merges

**Rules:**
- Never commit directly to main
- All changes via PR
- Human approval required for merge
- Delete branch after merge

---

## 2026-02-03 — Paper trading decision telemetry

**Decision:**
Enrich the paper trading engine with market, indicator, and near-miss context, persist that metadata with simulated trades, and expose the AI decision log via a new `/api/market/decisions` endpoint so analysts can query every logged choice.

**Context:**
Feature 47 demands that paper trading capture “entry/exit points and timing,” “market conditions at time of trade,” “indicators that triggered decisions,” and “near-misses.” The existing strategy endpoint only writes the raw signal dictionary to `ai_decisions` with minimal metadata, so downstream analysis lacks structured context when reviewing simulated decisions.

**Options Considered:**
1. Leave the existing `AIDecision` logging untouched and rely on offline queries to reconstruct context from trade data. (Rejected because analysts still lacked consistent indicator snapshots and near-miss reasoning.)
2. Expand the strategy API to comb through indicator services before each request. (Rejected because it duplicated logic already centralized in the paper trading engine and risked mismatched reasoning.)
3. Extend the paper trading engine to build the context as trades execute, store it on the signal + trade metadata, and provide a dedicated endpoint to fetch recent `ai_decisions`. (Chosen.)

**Outcome:**
Paper trading now keeps a normalized price history, computes volatility/momentum/indicator snapshots, marks near-miss conditions, and records that metadata alongside each signal. The richer metadata flows through trade persistence and the AI decision log that the new `/api/market/decisions` endpoint surfaces, giving analysts the structured context they need for review.
