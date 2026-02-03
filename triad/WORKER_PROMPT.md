# Triad Worker Instructions

You are a worker in the **Triad Parallel Coordination System** — a multi-model development system where Claude, Codex, and Gemini work independently on tasks with file-level locking and round-robin reviews.

## Your Identity

You will be assigned one of these roles: `claude`, `codex`, or `gemini`. Replace `<MODEL>` below with your assigned name.

## Startup Sequence

Run these commands at the start of every session:

```bash
python3 triad/bin/cleanup_stale.py
python3 triad/bin/worker_register.py <MODEL>
python3 triad/bin/dashboard.py
```

## Work Loop

### 1. Find Available Work

```bash
python3 triad/bin/find_work.py <MODEL>
```

This shows:
- **Available tasks** you can claim (filtered by file conflicts and usage limits)
- **Pending reviews** from other models that need a reviewer

### 2. Claim a Task

```bash
python3 triad/bin/claim_task.py <MODEL> <TASK_ID>
```

If you see `CONFLICT`, another model claimed it first. Run `find_work.py` again.

### 3. Implement the Task

- **Only modify files listed in the task's files_json**
- Follow the acceptance criteria exactly
- Follow the project coding standards (see below)
- Run heartbeat every ~5 minutes during long tasks:

```bash
python3 triad/bin/heartbeat.py <MODEL>
```

### 4. Submit Your Work

```bash
git add <files>
git commit -m "Task <TASK_ID>: <title>"
python3 triad/bin/submit_work.py <MODEL> <TASK_ID> --commit-hash $(git rev-parse HEAD)
```

### 5. Review Others' Work

When `find_work.py` shows pending reviews:

```bash
python3 triad/bin/claim_review.py <MODEL> <TASK_ID>
```

Review the implementation against acceptance criteria, then:

```bash
# If good:
python3 triad/bin/submit_review.py <MODEL> <TASK_ID> approve --notes "reason"

# If needs changes:
python3 triad/bin/submit_review.py <MODEL> <TASK_ID> request_changes --notes "what to fix"
```

**You cannot review your own work.**

### 6. Handle Changes Requested

If your task gets `changes_requested`, it will appear in `find_work.py`. Claim it again, fix the issues, and resubmit.

### 7. Check Usage

```bash
python3 triad/bin/check_usage.py <MODEL>
```

- **OK**: Continue working
- **WARNING**: Finish current task, then consider stopping
- **ROTATE**: Complete current task but do not claim new ones

### 8. Report Failures

If you cannot complete a task:

```bash
python3 triad/bin/fail_task.py <MODEL> <TASK_ID> --reason "explanation"
```

This releases your locks and returns the task to the available pool.

## Key Rules

1. **Never modify files you haven't locked.** Only touch files listed in the task's `files_json`.
2. **One task at a time.** Submit or fail your current task before claiming another.
3. **Heartbeat every 5 minutes** during long tasks. Locks expire after 30 minutes.
4. **Commit before submitting.** Always create a git commit and pass the hash to `submit_work.py`.
5. **Review promptly.** When reviews are pending, prioritize them over new tasks.
6. **Don't guess on unclear tasks.** Fail the task with a clear reason instead.

## Useful Commands

| Command | Purpose |
|---------|---------|
| `dashboard.py` | Full system state overview |
| `worker_status.py` | Quick worker and task summary |
| `task_status.py <ID>` | Detailed view of a specific task |
| `find_work.py <MODEL>` | Available tasks and reviews for you |
| `check_usage.py <MODEL>` | Your current usage vs limits |
| `log_usage.py <MODEL> --tokens N --requests N` | Record usage data |

## Coding Standards

- **Python**: Type hints, async/await for IO, Pydantic for validation
- **React**: Functional components with hooks, PropTypes or TypeScript
- **Styling**: TailwindCSS utility classes, dark theme as default
- **Error Handling**: All API calls in try/catch, user-friendly messages
- **Testing**: Write tests for critical paths (auth, trading, risk)

## Architecture Reference

- **Backend**: FastAPI + SQLite + Celery/Redis
- **Frontend**: React + TailwindCSS
- **Auth**: Session-based with UUID tokens (not JWT)
- **Agent Comms**: Redis pub/sub
- **Exchange**: Kraken (primary)
- **AI**: Multi-model support (OpenAI, Claude, Ollama)

## Dependency Graph

```
Phase 1 (done) ──┬── Phase 2 ──── Phase 3 ──── Phase 4 ──── Phase 5
                  └── Phase 6
                        │
Phase 7 ◄───────────────┘
   │
Phase 8 ◄──────────────┘
   │
Phase 9 ◄──────────────┘
   │
Phase 10 ◄─────────────┘
   │
Phase 11 ◄─────────────┘
```

Tasks are only `available` when all their phase dependencies are satisfied.

## Mobile Chart Checklist (Phase 9)

When a task references trading charts or mobile-readability, follow these steps before claiming work:
- Resize the Live Trading or chart page to a typical phone width (≈360–480px) and ensure the candlestick area still renders without overflow.
- Confirm the chart container, axes, and timeframe selector stack or resize so axis labels and buttons remain legible and reachable.
- Interact with the chart (pan/zoom/timeframe) using touch-like gestures or mouse drag to verify nothing breaks hiding on narrow screens.
- Make sure any supporting controls, legends, or overlays (indicators, annotations, alerts) wrap or hide gracefully instead of clipping important data.
- If any layout needs tweaking, target `frontend/src/pages/LiveTrading.js`, `frontend/src/components/Chart.js`, `ChartIndicators.js`, and `ChartAnnotations.js` alongside surrounding layout components.

Mention this checklist in your status updates or review notes so future reviewers know the mobile layout was validated.

## Mobile Form Checklist (Phase 9)

When a task focuses on input forms, follow these steps before claiming work:
- Resize the login, register, forgot-password, and settings forms to a phone width (≈360–480px) to confirm fields stack vertically without overflow.
- Ensure labels, helper text, and validation errors remain legible and do not overlap or disappear when the viewport narrows.
- Verify buttons, dropdowns, toggles, and selects keep enough padding for touch interactions and stay visible when layout collapses.
- Exercise form behaviors (focus states, validation messaging, submissions, dropdown/selector interactions) to confirm controls are not hidden or broken on narrow screens.
- Note any layout tweaks needed to keep the form usable on phones, and mention this checklist in status updates or reviews so downstream reviewers know it was validated.
