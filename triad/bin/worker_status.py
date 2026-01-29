#!/usr/bin/env python3
"""Show current system state summary.

Usage: python worker_status.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection


def main():
    conn = get_connection(readonly=True)

    # Workers
    workers = conn.execute("SELECT * FROM workers ORDER BY model_name").fetchall()
    print("=== Workers ===")
    if not workers:
        print("  (none registered)")
    for w in workers:
        task_info = f" -> task {w['current_task']}" if w["current_task"] else ""
        print(f"  {w['model_name']:8s} [{w['status']:9s}]{task_info}  (heartbeat: {w['last_heartbeat']})")

    # Task summary
    print("\n=== Tasks ===")
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status ORDER BY status"
    ).fetchall()
    total = 0
    for r in rows:
        print(f"  {r['status']:20s} {r['cnt']}")
        total += r["cnt"]
    print(f"  {'TOTAL':20s} {total}")

    # Active file locks
    locks = conn.execute("SELECT * FROM file_locks ORDER BY locked_by").fetchall()
    print(f"\n=== File Locks ({len(locks)}) ===")
    for lock in locks:
        print(f"  {lock['locked_by']:8s} {lock['file_path']}  (task {lock['task_id']}, expires {lock['expires_at']})")

    # Pending reviews
    reviews = conn.execute(
        "SELECT id, title, assigned_to FROM tasks WHERE status='review_pending'"
    ).fetchall()
    print(f"\n=== Pending Reviews ({len(reviews)}) ===")
    for r in reviews:
        print(f"  Task {r['id']}: {r['title']} (by {r['assigned_to']})")

    conn.close()


if __name__ == "__main__":
    main()
