#!/usr/bin/env python3
"""Clean up expired file locks and crashed worker sessions.

- Releases file locks past their expiry time
- Marks workers as offline if no heartbeat for >stale_heartbeat_minutes
- Unclaims tasks from offline workers

Usage: python cleanup_stale.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, load_config, log_event, now_sqlite


def main():
    config = load_config()
    stale_minutes = config.get("stale_heartbeat_minutes", 10)
    conn = get_connection()
    now = now_sqlite()

    # 1. Release expired file locks
    expired_locks = conn.execute(
        "SELECT file_path, locked_by, task_id FROM file_locks WHERE expires_at <= ?",
        (now,),
    ).fetchall()

    if expired_locks:
        conn.execute("DELETE FROM file_locks WHERE expires_at <= ?", (now,))
        for lock in expired_locks:
            log_event(conn, "lock_expired", model_name=lock["locked_by"],
                      task_id=lock["task_id"], details=f"file={lock['file_path']}")

    # 2. Find stale workers (no heartbeat for stale_minutes)
    from datetime import datetime, timezone, timedelta
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).strftime("%Y-%m-%d %H:%M:%S")

    stale_workers = conn.execute(
        "SELECT model_name, current_task FROM workers WHERE last_heartbeat < ? AND status != 'offline'",
        (stale_cutoff,),
    ).fetchall()

    for worker in stale_workers:
        model = worker["model_name"]
        task_id = worker["current_task"]

        # Mark worker offline
        conn.execute(
            "UPDATE workers SET status='offline', current_task=NULL WHERE model_name=?",
            (model,),
        )

        # Release their file locks
        conn.execute("DELETE FROM file_locks WHERE locked_by=?", (model,))

        # Unclaim their task
        if task_id:
            conn.execute(
                "UPDATE tasks SET status='available', assigned_to=NULL, claimed_at=NULL WHERE id=? AND status='claimed'",
                (task_id,),
            )
            log_event(conn, "task_unclaimed_stale", model_name=model, task_id=task_id,
                      details=f"Worker stale for >{stale_minutes}min")

        log_event(conn, "worker_marked_offline", model_name=model,
                  details=f"No heartbeat since {stale_cutoff}")

    conn.commit()

    # Report
    print(f"Cleanup complete:")
    print(f"  Expired locks released: {len(expired_locks)}")
    print(f"  Stale workers marked offline: {len(stale_workers)}")
    for w in stale_workers:
        task_info = f" (task {w['current_task']} unclaimed)" if w["current_task"] else ""
        print(f"    {w['model_name']}{task_info}")

    conn.close()


if __name__ == "__main__":
    main()
