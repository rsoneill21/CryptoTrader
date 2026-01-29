#!/usr/bin/env python3
"""Autonomous work loop for a Triad worker model.

Runs the full lifecycle automatically:
  1. Cleanup stale locks/workers
  2. Register worker
  3. Loop: find work → claim → (delegate implementation) → check usage
  4. Stop when usage hits ROTATE, no work available, or max iterations reached

This script handles the coordination layer. The actual implementation
of tasks is delegated to a model-specific command/script.

Usage:
  python3 triad/bin/auto_loop.py <model_name> --impl-cmd "command to run"

  The --impl-cmd receives the task ID as an argument. It should:
    - Read the task details (files, criteria)
    - Implement the changes
    - Git commit
    - Print the commit hash on the last line of stdout

  If --impl-cmd is omitted, the loop runs in "coordination-only" mode:
    it finds and displays available work but doesn't claim or implement.

Examples:
  # Coordination-only mode (dry run)
  python3 triad/bin/auto_loop.py claude

  # With a custom implementation script
  python3 triad/bin/auto_loop.py claude --impl-cmd "./scripts/claude_implement.sh"

  # With max iterations
  python3 triad/bin/auto_loop.py codex --impl-cmd "./run_codex.sh" --max-tasks 5
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

TRIAD_BIN = Path(__file__).resolve().parent
PROJECT_ROOT = TRIAD_BIN.parent.parent


def run_script(script_name, *args):
    """Run a triad/bin script and return (returncode, stdout)."""
    cmd = [sys.executable, str(TRIAD_BIN / script_name)] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def run_impl_cmd(impl_cmd, task_id):
    """Run the implementation command for a task. Returns (success, commit_hash)."""
    cmd = f"{impl_cmd} {task_id}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"    Implementation failed: {result.stderr.strip()}")
        return False, None
    # Last non-empty line of stdout should be the commit hash
    lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
    commit_hash = lines[-1].strip() if lines else None
    return True, commit_hash


def check_usage(model):
    """Check usage level. Returns 'OK', 'WARNING', or 'ROTATE'."""
    rc, stdout, _ = run_script("check_usage.py", model)
    for line in stdout.split("\n"):
        if line.startswith("Status:"):
            return line.split(":")[1].strip()
    return "OK"


def find_available_task(model):
    """Find the first available task for this model. Returns task_id or None."""
    # Query DB directly for efficiency
    sys.path.insert(0, str(TRIAD_BIN))
    from db_helpers import get_connection
    import json as j

    conn = get_connection(readonly=True)

    # Get files locked by others
    from db_helpers import now_sqlite
    now = now_sqlite()
    locked_rows = conn.execute(
        "SELECT file_path FROM file_locks WHERE locked_by != ? AND expires_at > ?",
        (model, now),
    ).fetchall()
    locked_files = {r["file_path"] for r in locked_rows}

    # Find available tasks
    tasks = conn.execute(
        "SELECT id, files_json FROM tasks WHERE status IN ('available', 'changes_requested') ORDER BY priority DESC, id"
    ).fetchall()

    conn.close()

    for task in tasks:
        files = j.loads(task["files_json"]) if task["files_json"] else []
        if not set(files) & locked_files:
            return task["id"]
    return None


def find_pending_review(model):
    """Find a task pending review that this model can review. Returns task_id or None."""
    sys.path.insert(0, str(TRIAD_BIN))
    from db_helpers import get_connection

    conn = get_connection(readonly=True)
    task = conn.execute(
        "SELECT id FROM tasks WHERE status='review_pending' AND assigned_to != ? AND reviewer IS NULL LIMIT 1",
        (model,),
    ).fetchone()
    conn.close()
    return task["id"] if task else None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 auto_loop.py <model_name> [--impl-cmd \"command\"] [--max-tasks N] [--review-cmd \"command\"]")
        sys.exit(1)

    model = sys.argv[1].lower()
    impl_cmd = None
    review_cmd = None
    max_tasks = 0  # 0 = unlimited
    pause_seconds = 30  # pause between loop iterations

    # Parse args
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--impl-cmd" and i + 1 < len(sys.argv):
            impl_cmd = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--review-cmd" and i + 1 < len(sys.argv):
            review_cmd = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--max-tasks" and i + 1 < len(sys.argv):
            max_tasks = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--pause" and i + 1 < len(sys.argv):
            pause_seconds = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

    coordination_only = impl_cmd is None

    # Startup
    print(f"=== Triad Auto-Loop: {model} ===")
    if coordination_only:
        print("Mode: coordination-only (no --impl-cmd, will only show available work)")
    else:
        print(f"Implementation command: {impl_cmd}")
    print()

    run_script("cleanup_stale.py")
    rc, stdout, _ = run_script("worker_register.py", model)
    print(stdout)

    tasks_completed = 0

    while True:
        # Check usage first
        usage = check_usage(model)
        if usage == "ROTATE":
            print(f"\n[ROTATE] Usage limit reached. Stopping auto-loop.")
            break
        if usage == "WARNING":
            print(f"\n[WARNING] Approaching usage limit. Will complete current iteration then stop.")

        # Priority 1: Pending reviews
        review_task = find_pending_review(model)
        if review_task:
            print(f"\n--- Review available: task {review_task} ---")
            if review_cmd:
                rc, stdout, _ = run_script("claim_review.py", model, review_task)
                print(f"  {stdout}")
                if rc == 0:
                    # Run review command
                    result = subprocess.run(
                        f"{review_cmd} {review_task}", shell=True,
                        capture_output=True, text=True, cwd=str(PROJECT_ROOT)
                    )
                    # Last line should be "approve" or "request_changes [notes]"
                    lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
                    if lines:
                        parts = lines[-1].strip().split(" ", 1)
                        decision = parts[0]
                        notes = parts[1] if len(parts) > 1 else ""
                        args = [model, review_task, decision]
                        if notes:
                            args += ["--notes", notes]
                        rc2, stdout2, _ = run_script("submit_review.py", *args)
                        print(f"  {stdout2}")
            elif not coordination_only:
                print(f"  Skipping review (no --review-cmd provided)")
            else:
                print(f"  (coordination-only mode, not claiming)")

        # Priority 2: Available tasks
        task_id = find_available_task(model)

        if not task_id:
            if not review_task:
                print(f"\n[IDLE] No tasks or reviews available. Waiting {pause_seconds}s...")
                time.sleep(pause_seconds)
            continue

        print(f"\n--- Available task: {task_id} ---")

        if coordination_only:
            rc, stdout, _ = run_script("find_work.py", model)
            print(stdout)
            print(f"\n(coordination-only mode, not claiming)")
            break

        # Claim
        rc, stdout, stderr = run_script("claim_task.py", model, task_id)
        print(f"  {stdout}")
        if rc != 0:
            print(f"  Claim failed, retrying...")
            time.sleep(5)
            continue

        # Heartbeat in background would be ideal, but for simplicity
        # the impl_cmd should call heartbeat.py itself for long tasks

        # Implement
        print(f"  Running implementation command...")
        success, commit_hash = run_impl_cmd(impl_cmd, task_id)

        if success and commit_hash:
            # Submit
            args = [model, task_id]
            if commit_hash:
                args += ["--commit-hash", commit_hash]
            rc, stdout, _ = run_script("submit_work.py", *args)
            print(f"  {stdout}")
            tasks_completed += 1
        else:
            # Fail the task
            rc, stdout, _ = run_script("fail_task.py", model, task_id, "--reason", "Implementation command failed")
            print(f"  {stdout}")

        # Check if we hit the max
        if max_tasks > 0 and tasks_completed >= max_tasks:
            print(f"\n[MAX] Completed {max_tasks} tasks. Stopping.")
            break

        # Stop if WARNING
        if usage == "WARNING":
            print(f"\n[WARNING] Usage warning active. Stopping after completing task.")
            break

        # Brief pause before next iteration
        time.sleep(2)

    # Summary
    print(f"\n=== Auto-Loop Complete ===")
    print(f"  Model: {model}")
    print(f"  Tasks completed: {tasks_completed}")
    rc, stdout, _ = run_script("worker_status.py")
    print(stdout)


if __name__ == "__main__":
    main()
