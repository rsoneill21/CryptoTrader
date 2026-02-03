#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Triad Autonomous Worker Driver
# ============================================================
#
# Drives an AI model through the triad work loop automatically.
# The model doesn't need to know how to loop — this script
# handles startup, task selection, and re-invocation.
#
# Usage:
#   ./triad/run_worker.sh claude          # Run Claude worker
#   ./triad/run_worker.sh codex           # Run Codex worker
#   ./triad/run_worker.sh gemini          # Run Gemini worker
#   ./triad/run_worker.sh claude --once   # Run one task only
#
# The script will loop until:
#   - No available tasks or reviews
#   - Usage reaches ROTATE threshold
#   - Ctrl+C is pressed
#   - --once flag: exits after one task
# ============================================================

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

MODEL="${1:?Usage: ./triad/run_worker.sh <claude|codex|gemini> [--once]}"
MODEL=$(echo "$MODEL" | tr '[:upper:]' '[:lower:]')
ONCE=false
[[ "${2:-}" == "--once" ]] && ONCE=true

if [[ ! "$MODEL" =~ ^(claude|codex|gemini)$ ]]; then
    echo "ERROR: Model must be claude, codex, or gemini"
    exit 1
fi

# ---- Startup ----
echo "========================================"
echo "  Triad Worker: $MODEL"
echo "  Project: $PROJECT_ROOT"
echo "  Mode: $(if $ONCE; then echo 'single task'; else echo 'continuous loop'; fi)"
echo "========================================"
echo ""

python3 triad/bin/cleanup_stale.py
python3 triad/bin/worker_register.py "$MODEL"
echo ""

# ---- Build the prompt for the AI model ----
build_task_prompt() {
    local TASK_ID="$1"
    local TASK_INFO
    TASK_INFO=$(python3 triad/bin/task_status.py "$TASK_ID" 2>&1)
    local FEATURE_PROMPT=""
    if [[ "$TASK_ID" == "feature-137" ]]; then
        FEATURE_PROMPT=$'8. Extra Guidance for feature-137:\n   - Resize the relevant chart page to a typical phone width (≈360–480px) and keep the candlestick area visible without overflow.\n   - Check that axis labels, tooltips, and timeframe picker remain legible and touch friendly; adjust padding or layout as needed.\n   - Confirm chart interactions (pan/zoom/timeframe) still work on narrow screens and that supporting indicators/annotations wrap or hide gracefully.\n   - Mention in your response how the mobile layout was validated per the checklist in triad/WORKER_PROMPT.md.\n'
    fi
    if [[ "$TASK_ID" == "feature-138" ]]; then
        FEATURE_PROMPT+=$'9. Extra Guidance for feature-138:\n   - Validate the mobile experience for key input forms (login, register, forgot password, settings, etc.) by resizing to ≈360–480px and ensuring fields stack, labels remain visible, and containers do not overflow.\n   - Make sure buttons, dropdowns, toggles, and error/helper text stay legible, wide enough for touch, and do not clip when the viewport narrows.\n   - Test form interactions (focus, validation states, submissions, and any dropdown or selector controls) with touch-like gestures to confirm nothing breaks or becomes hidden.\n   - Mention in your response how these forms were validated using the mobile form checklist in triad/WORKER_PROMPT.md.\n'
    fi
    if [[ "$TASK_ID" == "feature-138" ]]; then
        FEATURE_PROMPT+=$'9. Extra Guidance for feature-138:\n   - Validate the mobile experience for key input forms (login, register, forgot password, settings, etc.) by resizing to ≈360–480px and ensuring fields stack, labels remain visible, and containers do not overflow.\n   - Make sure buttons, dropdowns, toggles, and error/helper text stay legible, wide enough for touch, and do not clip when the viewport narrows.\n   - Test form interactions (focus, validation states, submissions, and any dropdown or selector controls) with touch-like gestures to confirm nothing breaks or becomes hidden.\n   - Mention in your response how these forms were validated using the mobile form checklist in triad/WORKER_PROMPT.md.\n'
    fi

    cat <<PROMPT
You are the "$MODEL" worker in the Triad parallel coding system.

You have been assigned task $TASK_ID. Here are the details:

$TASK_INFO

INSTRUCTIONS:
1. Read the task criteria carefully.
2. ONLY modify the files listed in the task's Files section. Do not touch any other files.
3. Implement the task to meet ALL acceptance criteria.
4. Follow project coding standards:
   - Python: type hints, async/await for IO, Pydantic for validation
   - React: functional components with hooks
   - Styling: TailwindCSS, dark theme default
   - Error handling: try/catch on all API calls
${FEATURE_PROMPT:+$FEATURE_PROMPT}
5. When done, stage ONLY the task files and commit:
   git add <task files only>
   git commit -m "Task $TASK_ID: <description>"
6. Then run: python3 triad/bin/submit_work.py $MODEL $TASK_ID --commit-hash \$(git rev-parse HEAD)
7. If you cannot complete the task, run:
   python3 triad/bin/fail_task.py $MODEL $TASK_ID --reason "explanation"

Do NOT modify files outside the task's file list.
Do NOT ask questions — implement or fail the task.
Begin now.
PROMPT
}

build_review_prompt() {
    local TASK_ID="$1"
    local TASK_INFO
    TASK_INFO=$(python3 triad/bin/task_status.py "$TASK_ID" 2>&1)

    # Get the commit hash
    local COMMIT
    COMMIT=$(python3 -c "
import sqlite3
conn = sqlite3.connect('triad/triad.db')
conn.row_factory = sqlite3.Row
t = conn.execute('SELECT commit_hash FROM tasks WHERE id=?', ('$TASK_ID',)).fetchone()
print(t['commit_hash'] or 'HEAD')
")

    cat <<PROMPT
You are the "$MODEL" worker in the Triad parallel coding system.

You are REVIEWING task $TASK_ID (implemented by another model).

$TASK_INFO

REVIEW INSTRUCTIONS:
1. Check the changes: git show $COMMIT
2. Verify ALL acceptance criteria are met.
3. Verify ONLY the listed files were modified.
4. Check for bugs, security issues, missing error handling.
5. Submit your verdict:

   If correct:
   python3 triad/bin/submit_review.py $MODEL $TASK_ID approve --notes "reason"

   If needs fixes:
   python3 triad/bin/submit_review.py $MODEL $TASK_ID request_changes --notes "what to fix"

Be strict but fair. Approve if criteria are met.
Begin now.
PROMPT
}

# ---- Model-specific invocation ----
invoke_model() {
    local PROMPT="$1"

    case "$MODEL" in
        claude)
            claude -p --print "$PROMPT"
            ;;
        codex)
            codex exec "$PROMPT"
            ;;
        gemini)
            gemini --approval-mode yolo "$PROMPT"
            ;;
    esac
}

# ---- Main loop ----
TASKS_DONE=0
IDLE_COUNT=0
MAX_IDLE=3  # Exit after 3 consecutive idle rounds

while true; do
    echo ""
    echo "---- Loop iteration $(date '+%H:%M:%S') ----"

    # Check usage
    USAGE=$(python3 triad/bin/check_usage.py "$MODEL" 2>&1 | grep "^Status:" | awk '{print $2}')
    if [[ "$USAGE" == "ROTATE" ]]; then
        echo "[ROTATE] Usage limit reached. Stopping."
        break
    fi

    # Check for stale reviews to auto-approve
    python3 -c "
import sys
sys.path.insert(0, 'triad/bin')
from auto_loop import auto_approve_stale_reviews
approved = auto_approve_stale_reviews()
if approved:
    print(f'[AUTO-APPROVE] Stale reviews approved: {\", \".join(approved)}')
" 2>/dev/null || true

    # Priority 1: Reviews
    REVIEW_TASK=$(python3 -c "
import sqlite3
conn = sqlite3.connect('triad/triad.db')
conn.row_factory = sqlite3.Row
t = conn.execute(
    \"SELECT id FROM tasks WHERE status='review_pending' AND assigned_to != ? AND reviewer IS NULL LIMIT 1\",
    ('$MODEL',)
).fetchone()
print(t['id'] if t else '')
" 2>/dev/null)

    if [[ -n "$REVIEW_TASK" ]]; then
        echo "[REVIEW] Claiming review for task $REVIEW_TASK"
        if python3 triad/bin/claim_review.py "$MODEL" "$REVIEW_TASK" 2>&1; then
            PROMPT=$(build_review_prompt "$REVIEW_TASK")
            invoke_model "$PROMPT"
        fi
        IDLE_COUNT=0
        continue
    fi

    # Priority 2: Ensure every task has files_json before claiming
    if python3 triad/bin/populate_task_files.py --limit 3 --quiet 2>/dev/null; then
        :
    else
        echo "[DISCOVER] Unable to populate files_json for pending tasks"
    fi

    # Priority 3: Block repeatedly stalled tasks
    if python3 triad/bin/block_stuck_tasks.py --limit 2 --quiet 2>/dev/null; then
        :
    else
        echo "[BLOCK] Unable to auto-block hung tasks"
    fi

    # Priority 4: Available tasks
    NEXT_TASK=$(python3 -c "
import sqlite3, json
conn = sqlite3.connect('triad/triad.db')
conn.row_factory = sqlite3.Row
from datetime import datetime, timezone
now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

# Get files locked by others
locked = {r['file_path'] for r in conn.execute(
    'SELECT file_path FROM file_locks WHERE locked_by != ? AND expires_at > ?',
    ('$MODEL', now)
).fetchall()}

# Find available task without file conflicts
for t in conn.execute(
    \"SELECT id, files_json FROM tasks WHERE status IN ('available','changes_requested') ORDER BY priority DESC, id\"
).fetchall():
    files = set(json.loads(t['files_json']) if t['files_json'] else [])
    if not files & locked:
        print(t['id'])
        break
" 2>/dev/null)

    if [[ -z "$NEXT_TASK" ]]; then
        IDLE_COUNT=$((IDLE_COUNT + 1))
        echo "[IDLE] No tasks or reviews available. ($IDLE_COUNT/$MAX_IDLE)"
        if [[ $IDLE_COUNT -ge $MAX_IDLE ]]; then
            echo "[EXIT] Idle too long, no work available. Stopping."
            break
        fi
        sleep 30
        continue
    fi

    IDLE_COUNT=0
    echo "[TASK] Claiming task $NEXT_TASK"

    if ! python3 triad/bin/claim_task.py "$MODEL" "$NEXT_TASK" 2>&1; then
        echo "[CONFLICT] Claim failed, retrying next iteration..."
        sleep 5
        continue
    fi

    # Build prompt and invoke model
    PROMPT=$(build_task_prompt "$NEXT_TASK")
    invoke_model "$PROMPT"

    # Check if the model submitted or failed the task
    TASK_STATUS=$(python3 -c "
import sqlite3
conn = sqlite3.connect('triad/triad.db')
conn.row_factory = sqlite3.Row
t = conn.execute('SELECT status FROM tasks WHERE id=?', ('$NEXT_TASK',)).fetchone()
print(t['status'] if t else 'unknown')
" 2>/dev/null)

    case "$TASK_STATUS" in
        done|review_pending)
            TASKS_DONE=$((TASKS_DONE + 1))
            echo "[DONE] Task $NEXT_TASK -> $TASK_STATUS (total: $TASKS_DONE)"
            ;;
        claimed)
            echo "[STALE] Model didn't submit task $NEXT_TASK. Failing it."
            python3 triad/bin/fail_task.py "$MODEL" "$NEXT_TASK" --reason "Worker did not submit or fail the task" 2>&1
            ;;
        *)
            echo "[INFO] Task $NEXT_TASK status: $TASK_STATUS"
            ;;
    esac

    if $ONCE; then
        echo "[ONCE] Single-task mode, stopping."
        break
    fi

    if [[ "$USAGE" == "WARNING" ]]; then
        echo "[WARNING] Usage warning active. Stopping after task."
        break
    fi

    sleep 2
done

# ---- Summary ----
echo ""
echo "========================================"
echo "  Worker $MODEL finished"
echo "  Tasks completed: $TASKS_DONE"
echo "========================================"
python3 triad/bin/dashboard.py
