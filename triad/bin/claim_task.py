#!/usr/bin/env python3
"""Atomically claim a task and lock its files.

Uses BEGIN IMMEDIATE to acquire the SQLite write lock, preventing race conditions
when multiple models try to claim the same task simultaneously.

Usage: python claim_task.py <model_name> <task_id>
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, load_config, log_event, now_sqlite


def main():
    if len(sys.argv) < 3:
        print("Usage: python claim_task.py <model_name> <task_id>")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    task_id = sys.argv[2]
    config = load_config()
    lock_minutes = config.get("lock_timeout_minutes", 30)

    conn = get_connection()

    try:
        # BEGIN IMMEDIATE acquires the write lock immediately
        # If another process holds the lock, it will wait up to busy_timeout
        conn.execute("BEGIN IMMEDIATE")

        # 1. Verify task is claimable
        task = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()

        if not task:
            print(f"ERROR: Task {task_id} not found")
            conn.rollback()
            sys.exit(1)

        if task["status"] not in ("available", "changes_requested"):
            if task["status"] == "claimed" and task["assigned_to"] != model:
                print(f"CONFLICT: Task {task_id} already claimed by {task['assigned_to']}")
            else:
                print(f"ERROR: Task {task_id} has status '{task['status']}', cannot claim")
            conn.rollback()
            sys.exit(1)

        # 2. Check worker isn't already working on something
        worker = conn.execute(
            "SELECT * FROM workers WHERE model_name = ?", (model,)
        ).fetchone()
        if worker and worker["current_task"]:
            print(f"ERROR: {model} is already working on task {worker['current_task']}")
            print("Submit or fail that task first.")
            conn.rollback()
            sys.exit(1)

        # 3. Check file conflicts
        now = now_sqlite()
        task_files = json.loads(task["files_json"]) if task["files_json"] else []

        if task_files:
            placeholders = ",".join("?" for _ in task_files)
            conflicts = conn.execute(
                f"SELECT file_path, locked_by, task_id FROM file_locks "
                f"WHERE file_path IN ({placeholders}) AND locked_by != ? AND expires_at > ?",
                (*task_files, model, now),
            ).fetchall()

            if conflicts:
                print(f"CONFLICT: Files locked by other models:")
                for c in conflicts:
                    print(f"  {c['file_path']} locked by {c['locked_by']} (task {c['task_id']})")
                conn.rollback()
                sys.exit(1)

        # 4. Claim the task
        conn.execute(
            "UPDATE tasks SET status='claimed', assigned_to=?, claimed_at=? WHERE id=?",
            (model, now, task_id),
        )

        # 5. Lock files
        expires = (datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        for fpath in task_files:
            conn.execute(
                """INSERT INTO file_locks (file_path, task_id, locked_by, locked_at, expires_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(file_path) DO UPDATE SET
                     task_id=?, locked_by=?, locked_at=?, expires_at=?""",
                (fpath, task_id, model, now, expires,
                 task_id, model, now, expires),
            )

        # 6. Update worker state
        conn.execute(
            """INSERT INTO workers (model_name, status, current_task, last_heartbeat)
               VALUES (?, 'working', ?, ?)
               ON CONFLICT(model_name) DO UPDATE SET
                 status='working', current_task=?, last_heartbeat=?""",
            (model, task_id, now, task_id, now),
        )

        log_event(conn, "task_claimed", model_name=model, task_id=task_id,
                  details=f"Files: {json.dumps(task_files)}")

        conn.commit()

        print(f"CLAIMED: Task {task_id} assigned to {model}")
        print(f"  Title: {task['title']}")
        if task_files:
            print(f"  Files locked ({lock_minutes}min):")
            for f in task_files:
                print(f"    {f}")
        if task["description"]:
            print(f"  Criteria: {task['description']}")

    except Exception as e:
        conn.rollback()
        if "database is locked" in str(e):
            print(f"CONFLICT: Another model is claiming a task right now. Try again.")
        else:
            print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
