# Triad Agents State

> **Coordination system: Parallel Triad (triad/triad.db)**
>
> This file is a human-readable summary. The source of truth is `triad/triad.db`.
> Run `python3 triad/bin/dashboard.py` for live system state.

## Current System

The Triad Parallel Coordination System replaces the old sequential handoff (Claude→Codex→Gemini) with parallel independent work. All three models can work simultaneously on non-conflicting tasks.

### How It Works

1. **Database coordination**: `triad/triad.db` (SQLite WAL) manages tasks, file locks, and worker state
2. **File-level locking**: Models declare files before starting; conflicts are prevented atomically
3. **Round-robin reviews**: Every completed task is reviewed by a different model before approval
4. **Usage-aware rotation**: Models rotate when approaching API usage limits
5. **Dependency cascade**: Completing a task automatically unblocks dependent tasks

### Worker Instructions

All models follow the unified instructions in `triad/WORKER_PROMPT.md`.

### Quick Reference

```bash
# Startup
python3 triad/bin/cleanup_stale.py
python3 triad/bin/worker_register.py <MODEL>
python3 triad/bin/dashboard.py

# Work loop
python3 triad/bin/find_work.py <MODEL>
python3 triad/bin/claim_task.py <MODEL> <TASK_ID>
# ... implement ...
python3 triad/bin/submit_work.py <MODEL> <TASK_ID> --commit-hash <SHA>

# Review
python3 triad/bin/claim_review.py <MODEL> <TASK_ID>
python3 triad/bin/submit_review.py <MODEL> <TASK_ID> approve|request_changes
```

## Project Status

- **Phase 1**: Foundation & Infrastructure — 20/20 tasks DONE
- **Phase 2**: Exchange Integration — available for work
- **Phase 6**: Risk Monitor — available for work (parallel with Phase 2)
- **Phases 3-5, 7-11**: Blocked (waiting on dependencies)

## Known Issues

- Phase 1 review found: missing auth tests (HIGH priority)
- Password reset uses in-memory storage
- Hardcoded CORS origins

## Architecture Decisions

See `triad/DECISIONS.md` for the full decision log.
