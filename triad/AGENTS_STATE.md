# AGENTS_STATE.md

## Goal
Set up Codex CLI and Gemini CLI as operational Triad agents with local validation first, then GitHub Actions automation.

## Constraints
- Must preserve human-in-the-loop control
- No auto-merging without approval
- Credentials must be secured (.env locally, GitHub Secrets in CI)

## Current Status
- Completed: PLAN.md drafted for agent setup, CLAUDE.md updated with full PM responsibilities
- In Progress: Phase 1 — Local Setup & Validation
- Next: Install and authenticate Codex CLI, then Gemini CLI

## How to Run

### Verified Tools
| Tool | Version | Path | Status |
|------|---------|------|--------|
| codex | 0.92.0 | `~/.nvm/versions/node/v24.13.0/bin/codex` | Installed |
| opencode | 1.1.36 | `~/.opencode/bin/opencode` | Verified working |

### OpenCode Usage
```bash
# Send a task
opencode run -m opencode/big-pickle "implement feature X"

# Attach context files
opencode run -m opencode/big-pickle -f PLAN.md "implement task 1"

# Continue session
opencode run -c "follow up"
```

### Codex Usage
```bash
codex "your prompt here"
```

- Dev: N/A (no app code yet)
- Test: Math and trivia tests passed on opencode/big-pickle

## Known Issues
- Gemini CLI availability/naming to be confirmed
- Codex CLI tested for install but not yet verified with a task
