# AI Model Instructions — Triad Autonomous Worker

Read this file completely before doing anything else.

You are an autonomous worker in the **Triad Parallel Coordination System**. Multiple AI models (Claude, Codex, Gemini) work in parallel on the CryptoTrader project, coordinated through a SQLite database that manages tasks, file locks, and reviews.

---

## Step 1: Identify Yourself

You are one of: `claude`, `codex`, or `gemini`. Use your model name in all commands below. If you're unsure which you are:
- **Claude** (Anthropic) → use `claude`
- **Codex / ChatGPT / OpenAI** → use `codex`
- **Gemini** (Google) → use `gemini`

Replace `<MODEL>` with your name in all commands.

---

## Step 2: Start Your Session

Run these three commands at the start of every session:

```bash
python3 triad/bin/cleanup_stale.py
python3 triad/bin/worker_register.py <MODEL>
python3 triad/bin/dashboard.py
```

This cleans up any stale locks from crashed sessions, registers you as active, and shows the current system state.

---

## Step 3: Autonomous Work Loop

Repeat this loop until you run out of usage or there's no more work:

### 3a. Find work

```bash
python3 triad/bin/find_work.py <MODEL>
```

This shows two sections:
- **Available Tasks** — tasks you can claim and implement
- **Reviews Available** — tasks other models completed that need your review

**If reviews are available, do them first.** Reviews unblock other models.

### 3b. Claim a task

Pick a task ID from the available list and claim it:

```bash
python3 triad/bin/claim_task.py <MODEL> <TASK_ID>
```

If you see `CONFLICT`, another model claimed it first. Run `find_work.py` again and pick a different task.

### 3c. Read the task details

```bash
python3 triad/bin/task_status.py <TASK_ID>
```

This shows:
- **Title** and **Criteria** — what to implement and how to verify it
- **Files** — the ONLY files you are allowed to modify
- **Dependencies** — what this task builds on

### 3d. Implement the task

Follow these rules strictly:

1. **Only modify files listed in the task's Files section.** Do not touch any other files.
2. **Meet all acceptance criteria** listed in the task description.
3. **Follow project coding standards:**
   - Python: type hints, async/await for IO, Pydantic for validation
   - React: functional components with hooks
   - Styling: TailwindCSS, dark theme default
   - Error handling: try/catch on all API calls
4. **If the task takes longer than 5 minutes**, refresh your heartbeat to prevent lock expiry:
   ```bash
   python3 triad/bin/heartbeat.py <MODEL>
   ```

### 3e. Commit and submit

When implementation is complete:

```bash
git add <only the files listed in the task>
git commit -m "Task <TASK_ID>: <short description>"
python3 triad/bin/submit_work.py <MODEL> <TASK_ID> --commit-hash $(git rev-parse HEAD)
```

**Important:** The system will auto-approve your task if no other models are currently active (solo mode). Otherwise it goes to `review_pending` for another model to review. Either way, you can immediately move on to the next task.

### 3f. If you can't complete a task

Don't stay stuck. Fail it and move on:

```bash
python3 triad/bin/fail_task.py <MODEL> <TASK_ID> --reason "clear explanation of what went wrong"
```

This returns the task to the available pool so another model can attempt it.

### 3g. Review other models' work

When `find_work.py` shows pending reviews:

```bash
python3 triad/bin/claim_review.py <MODEL> <TASK_ID>
```

Then review the implementation:
- Check the commit: `git show <commit_hash>`
- Verify acceptance criteria are met
- Check only the listed files were modified
- Look for bugs, security issues, missing error handling

Then submit your verdict:

```bash
# If the implementation is correct:
python3 triad/bin/submit_review.py <MODEL> <TASK_ID> approve --notes "reason"

# If it needs fixes:
python3 triad/bin/submit_review.py <MODEL> <TASK_ID> request_changes --notes "what to fix"
```

**You cannot review your own work.** The system enforces this.

### 3h. Check your usage

```bash
python3 triad/bin/check_usage.py <MODEL>
```

- **OK** → keep working
- **WARNING** → finish current task, then stop
- **ROTATE** → stop immediately, do not claim new tasks

### 3i. Log your usage (optional but helpful)

After completing work, log your approximate usage:

```bash
python3 triad/bin/log_usage.py <MODEL> --tokens <count> --requests <count>
```

---

## Step 4: End of Session

When stopping (usage limit, no work, end of session):

```bash
python3 triad/bin/dashboard.py
```

This shows the final state. Your locks will auto-expire if you forget to clean up, and `cleanup_stale.py` will handle it when the next model starts.

---

## Key Rules

| Rule | Why |
|------|-----|
| Only modify files listed in the task | Prevents conflicts with other models |
| One task at a time | Submit or fail before claiming another |
| Heartbeat every 5 min on long tasks | Locks expire after 30 min |
| Commit before submitting | Review needs a commit hash |
| Reviews before new tasks | Unblocks other models |
| Don't guess on unclear tasks | Fail with reason instead |

---

## How Reviews Work (Anti-Bottleneck)

The system prevents review bottlenecks in three ways:

1. **Solo auto-approve**: If you're the only active worker, your tasks are auto-approved on submit. No waiting.
2. **Timeout auto-approve**: If a review sits unclaimed for 15 minutes, it's auto-approved.
3. **Any model can review**: Reviews aren't assigned to a specific model — any available model can claim them.

This means: **you should never be stuck waiting for a review.** If no one reviews your work within 15 minutes, the system approves it and unblocks dependents automatically.

---

## Architecture Quick Reference

- **Backend**: FastAPI + SQLite + Celery/Redis — `backend/`
- **Frontend**: React + TailwindCSS — `frontend/`
- **Auth**: Session-based with UUID tokens (not JWT)
- **Agents**: Base class in `backend/agents/base.py`, Redis pub/sub comms
- **Exchange**: Kraken (primary), multi-exchange architecture planned
- **AI**: Multi-model support (OpenAI, Claude, Ollama)
- **Theme**: Dark default, light option, TailwindCSS

---

## Project Structure

```
CryptoTrader/
├── backend/
│   ├── agents/          # AI agent classes
│   ├── api/             # FastAPI route handlers
│   ├── core/            # Auth, celery, indicators, etc.
│   ├── db/              # Database models
│   └── services/        # Business logic services
├── frontend/
│   ├── src/
│   │   ├── components/  # React components
│   │   ├── context/     # React contexts (auth, theme)
│   │   ├── hooks/       # Custom hooks
│   │   ├── pages/       # Page components
│   │   └── services/    # API client
├── triad/
│   ├── bin/             # Coordination CLI tools (you use these)
│   ├── PLAN.md          # Master task plan
│   ├── DECISIONS.md     # Architecture decisions
│   └── config.json      # System configuration
```

---

## Dependency Graph

```
Phase 1 (DONE) ──┬── Phase 2 (Exchange) ──── Phase 3 ──── Phase 4 ──── Phase 5
                  └── Phase 6 (Risk)
                        │
Phase 7 ◄───────────────┘
Phase 8 ◄── Phase 7
Phase 9 ◄── Phase 8
Phase 10 ◄── Phase 9
Phase 11 ◄── Phase 10
```

Phases 2 and 6 can run in parallel. Everything else is sequential through the chain.

---

## If Something Goes Wrong

| Problem | Solution |
|---------|----------|
| `CONFLICT` on claim | Another model got it first. Run `find_work.py` again |
| Can't modify a file (locked) | Someone else has it. Pick a different task |
| Task criteria unclear | Fail it with `--reason "criteria unclear: <detail>"` |
| Tests failing | Fix them or fail the task with the error |
| Stuck / confused | Run `dashboard.py` to see full system state |
| No tasks available | All tasks may be blocked. Check if reviews need doing |

---

## Begin

Start your session now. Run the three startup commands from Step 2 and begin the work loop from Step 3.
