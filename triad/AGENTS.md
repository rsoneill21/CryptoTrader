# AGENTS.md — Multi-AI Workflow Contract

## Roles
- Claude: architecture, reasoning, PLAN.md author, edge cases, acceptance criteria
- Codex: implementation, refactors, tests, fixes
- Gemini: review, security review, alternative approaches, doc polish

## Golden Rule
Only ONE agent edits source code at a time.

## Source of Truth
- CLAUDE.md: Claude's operating contract
- PLAN.md: current implementation plan
- AGENTS_STATE.md: shared project state
- DECISIONS.md: architectural decisions

## Branching
- feat/<topic>-codex
- review/<topic>-gemini

## Definition of Done
- Tests pass or are documented
- No secrets committed
- Scope matches PLAN.md
