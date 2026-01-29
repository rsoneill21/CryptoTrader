#!/usr/bin/env python3
"""Submit completed task for review.

Releases file locks and moves task to review_pending status.

Usage: python submit_work.py <model_name> <task_id> [--commit-hash <sha>]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, log_event, now_sqlite


def main():
    if len(sys.argv) < 3:
        print("Usage: python submit_work.py <model_name> <task_id> [--commit-hash <sha>]")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    task_id = sys.argv[2]
    commit_hash = None

    # Parse optional commit hash
    if "--commit-hash" in sys.argv:
        idx = sys.argv.index("--commit-hash")
        if idx + 1 < len(sys.argv):
            commit_hash = sys.argv[idx + 1]

    conn = get_connection()
    now = now_sqlite()

    try:
        conn.execute("BEGIN IMMEDIATE")

        # Verify task is claimed by this model
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            print(f"ERROR: Task {task_id} not found")
            conn.rollback()
            sys.exit(1)

        if task["status"] != "claimed" or task["assigned_to"] != model:
            print(f"ERROR: Task {task_id} is not claimed by {model} (status={task['status']}, assigned={task['assigned_to']})")
            conn.rollback()
            sys.exit(1)

        # Update task status
        conn.execute(
            "UPDATE tasks SET status='review_pending', commit_hash=?, review_submitted_at=? WHERE id=?",
            (commit_hash, now, task_id),
        )

        # Release file locks
        released = conn.execute(
            "DELETE FROM file_locks WHERE task_id=? AND locked_by=?",
            (task_id, model),
        ).rowcount

        # Update worker state
        conn.execute(
            "UPDATE workers SET status='idle', current_task=NULL WHERE model_name=?",
            (model,),
        )

        log_event(conn, "work_submitted", model_name=model, task_id=task_id,
                  details=f"commit={commit_hash}, locks_released={released}")

        conn.commit()

        print(f"SUBMITTED: Task {task_id} moved to review_pending")
        print(f"  {released} file lock(s) released")
        if commit_hash:
            print(f"  Commit: {commit_hash}")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
