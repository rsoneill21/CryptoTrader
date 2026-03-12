#!/usr/bin/env python3
"""Report a task as failed and release its locks.

Moves the task back to available so another model can attempt it.

Usage: python fail_task.py <model_name> <task_id> [--reason "explanation"]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, log_event, now_sqlite


def main():
    if len(sys.argv) < 3:
        print("Usage: python fail_task.py <model_name> <task_id> [--reason \"explanation\"]")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    task_id = sys.argv[2]
    reason = None

    if "--reason" in sys.argv:
        idx = sys.argv.index("--reason")
        if idx + 1 < len(sys.argv):
            reason = sys.argv[idx + 1]

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            print(f"ERROR: Task {task_id} not found")
            conn.rollback()
            sys.exit(1)

        if task["assigned_to"] != model:
            print(f"ERROR: Task {task_id} is not assigned to {model}")
            conn.rollback()
            sys.exit(1)

        # Move back to available
        conn.execute(
            "UPDATE tasks SET status='available', assigned_to=NULL, claimed_at=NULL WHERE id=?",
            (task_id,),
        )

        # Release file locks
        released = conn.execute(
            "DELETE FROM file_locks WHERE task_id=? AND locked_by=?",
            (task_id, model),
        ).rowcount

        # Update worker
        conn.execute(
            "UPDATE workers SET status='idle', current_task=NULL WHERE model_name=?",
            (model,),
        )

        log_event(conn, "task_failed", model_name=model, task_id=task_id,
                  details=f"reason={reason}, locks_released={released}")

        conn.commit()

        print(f"FAILED: Task {task_id} returned to available pool")
        print(f"  {released} file lock(s) released")
        if reason:
            print(f"  Reason: {reason}")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
