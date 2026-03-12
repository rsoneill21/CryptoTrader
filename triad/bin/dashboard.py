#!/usr/bin/env python3
"""Full system dashboard showing all Triad coordination state.

Usage: python dashboard.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection


def main():
    conn = get_connection(readonly=True)

    # Header
    print("=" * 60)
    print("  TRIAD PARALLEL COORDINATION DASHBOARD")
    print("=" * 60)

    # Workers
    workers = conn.execute("SELECT * FROM workers ORDER BY model_name").fetchall()
    print("\n--- Workers ---")
    if not workers:
        print("  (none registered)")
    for w in workers:
        task_info = f" -> {w['current_task']}" if w["current_task"] else ""
        print(f"  {w['model_name']:8s} {w['status']:10s}{task_info}  (hb: {w['last_heartbeat'] or 'never'})")

    # Task summary by phase
    print("\n--- Tasks by Phase ---")
    phases = conn.execute(
        "SELECT phase, status, COUNT(*) as cnt FROM tasks GROUP BY phase, status ORDER BY phase, status"
    ).fetchall()

    current_phase = None
    for row in phases:
        if row["phase"] != current_phase:
            current_phase = row["phase"]
            # Get phase total
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE phase=?", (current_phase,)
            ).fetchone()["cnt"]
            done = conn.execute(
                "SELECT COUNT(*) as cnt FROM tasks WHERE phase=? AND status='done'", (current_phase,)
            ).fetchone()["cnt"]
            pct = f"({done}/{total})" if total else ""
            print(f"\n  Phase {current_phase} {pct}")
        print(f"    {row['status']:20s} {row['cnt']}")

    # Overall progress
    total = conn.execute("SELECT COUNT(*) as cnt FROM tasks").fetchone()["cnt"]
    done = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='done'").fetchone()["cnt"]
    available = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='available'").fetchone()["cnt"]
    claimed = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='claimed'").fetchone()["cnt"]
    review = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='review_pending'").fetchone()["cnt"]
    changes = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='changes_requested'").fetchone()["cnt"]
    blocked = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE status='blocked'").fetchone()["cnt"]

    pct_done = (done / total * 100) if total else 0
    bar_len = 30
    filled = int(pct_done / 100 * bar_len)
    bar = "#" * filled + "-" * (bar_len - filled)
    print(f"\n--- Overall Progress ---")
    print(f"  [{bar}] {pct_done:.1f}%  ({done}/{total} tasks)")
    print(f"  Available: {available}  Claimed: {claimed}  Review: {review}  Changes: {changes}  Blocked: {blocked}")

    # File locks
    locks = conn.execute("SELECT * FROM file_locks ORDER BY locked_by, file_path").fetchall()
    print(f"\n--- File Locks ({len(locks)}) ---")
    if locks:
        current_model = None
        for lock in locks:
            if lock["locked_by"] != current_model:
                current_model = lock["locked_by"]
                print(f"  {current_model}:")
            print(f"    {lock['file_path']} (task {lock['task_id']}, expires {lock['expires_at']})")
    else:
        print("  (none)")

    # Pending reviews
    reviews = conn.execute(
        "SELECT id, title, assigned_to, reviewer FROM tasks WHERE status='review_pending'"
    ).fetchall()
    print(f"\n--- Pending Reviews ({len(reviews)}) ---")
    for r in reviews:
        reviewer_info = f" [reviewer: {r['reviewer']}]" if r["reviewer"] else " [needs reviewer]"
        print(f"  {r['id']:5s} {r['title']} (by {r['assigned_to']}){reviewer_info}")

    # Tasks needing changes
    changes_tasks = conn.execute(
        "SELECT id, title, assigned_to FROM tasks WHERE status='changes_requested'"
    ).fetchall()
    if changes_tasks:
        print(f"\n--- Changes Requested ({len(changes_tasks)}) ---")
        for t in changes_tasks:
            print(f"  {t['id']:5s} {t['title']} (assigned to {t['assigned_to']})")

    # Recent events
    events = conn.execute(
        "SELECT * FROM event_log ORDER BY timestamp DESC LIMIT 10"
    ).fetchall()
    print(f"\n--- Recent Events ---")
    for e in events:
        task = f" task={e['task_id']}" if e["task_id"] else ""
        model = f" [{e['model_name']}]" if e["model_name"] else ""
        details = f" {e['details']}" if e["details"] else ""
        print(f"  {e['timestamp']}{model} {e['event_type']}{task}{details}")

    print()
    conn.close()


if __name__ == "__main__":
    main()
