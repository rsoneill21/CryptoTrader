#!/usr/bin/env python3
"""View details for a specific task.

Usage: python task_status.py <task_id>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection


def main():
    if len(sys.argv) < 2:
        print("Usage: python task_status.py <task_id>")
        sys.exit(1)

    task_id = sys.argv[1]
    conn = get_connection(readonly=True)

    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not task:
        print(f"Task {task_id} not found")
        conn.close()
        sys.exit(1)

    files = json.loads(task["files_json"]) if task["files_json"] else []
    deps = json.loads(task["depends_on"]) if task["depends_on"] else []

    print(f"=== Task {task['id']} ===")
    print(f"  Phase:       {task['phase']}")
    print(f"  Title:       {task['title']}")
    print(f"  Status:      {task['status']}")
    print(f"  Assigned to: {task['assigned_to'] or '(none)'}")
    print(f"  Reviewer:    {task['reviewer'] or '(none)'}")
    print(f"  Priority:    {task['priority']}")

    if files:
        print(f"  Files:")
        for f in files:
            # Check if file is currently locked
            lock = conn.execute(
                "SELECT locked_by, expires_at FROM file_locks WHERE file_path=?", (f,)
            ).fetchone()
            lock_info = f" [LOCKED by {lock['locked_by']} until {lock['expires_at']}]" if lock else ""
            print(f"    {f}{lock_info}")

    if deps:
        print(f"  Depends on:")
        for dep_id in deps:
            dep = conn.execute("SELECT id, status, title FROM tasks WHERE id=?", (dep_id,)).fetchone()
            if dep:
                print(f"    {dep['id']} [{dep['status']}] {dep['title']}")

    if task["description"]:
        print(f"  Criteria:    {task['description']}")
    if task["commit_hash"]:
        print(f"  Commit:      {task['commit_hash']}")
    if task["claimed_at"]:
        print(f"  Claimed at:  {task['claimed_at']}")
    if task["completed_at"]:
        print(f"  Completed:   {task['completed_at']}")

    # Show recent events for this task
    events = conn.execute(
        "SELECT * FROM event_log WHERE task_id=? ORDER BY timestamp DESC LIMIT 10",
        (task_id,),
    ).fetchall()

    if events:
        print(f"\n  Recent events:")
        for e in events:
            details = f" - {e['details']}" if e["details"] else ""
            model = f" ({e['model_name']})" if e["model_name"] else ""
            print(f"    [{e['timestamp']}] {e['event_type']}{model}{details}")

    conn.close()


if __name__ == "__main__":
    main()
