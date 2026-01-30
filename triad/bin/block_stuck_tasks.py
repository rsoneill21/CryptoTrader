#!/usr/bin/env python3
"""Automatically block tasks that have been claimed repeatedly without progress."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from db_helpers import get_connection, load_config, log_event


def _parse_timestamp(ts: str | None) -> datetime | None:
    if not ts:
        return None
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", "-n", type=int, default=3, help="Max tasks to block per run")
    parser.add_argument("--claims", type=int, help="Override the configured claim count threshold")
    parser.add_argument("--idle-minutes", type=int, help="Override the configured idle timeout (minutes)")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational output")
    args = parser.parse_args()

    config = load_config()
    claims_threshold = args.claims or config.get("stuck_task_claims_before_block", 3)
    idle_minutes = args.idle_minutes or config.get("stuck_task_idle_minutes", 30)
    idle_delta = idle_minutes * 60
    limit = args.limit

    now = datetime.now(timezone.utc)
    conn = get_connection()
    conn.row_factory = False

    rows = conn.execute(
        """
        SELECT t.id, t.status, COUNT(e.id) AS claim_count, MAX(e.timestamp) AS last_claim
        FROM tasks t
        JOIN event_log e ON e.task_id = t.id AND e.event_type = 'task_claimed'
        WHERE t.status IN ('available','claimed','changes_requested','review_pending')
        GROUP BY t.id
        HAVING COUNT(e.id) >= ?
        ORDER BY MAX(e.timestamp) ASC
        LIMIT ?
        """,
        (claims_threshold, limit * 5),
    ).fetchall()

    blocked = []

    for row in rows:
        if len(blocked) >= limit:
            break
        last_claim = _parse_timestamp(row[3])
        if not last_claim:
            continue
        if (now - last_claim).total_seconds() < idle_delta:
            continue

        task_id = row[0]
        conn.execute("DELETE FROM file_locks WHERE task_id=?", (task_id,))
        conn.execute(
            """
            UPDATE tasks
            SET status='blocked',
                assigned_to=NULL,
                reviewer=NULL,
                claimed_at=NULL
            WHERE id = ?
            """,
            (task_id,),
        )
        worker_rows = conn.execute(
            "SELECT model_name FROM workers WHERE current_task = ?", (task_id,)
        ).fetchall()
        for worker in worker_rows:
            conn.execute(
                "UPDATE workers SET current_task=NULL WHERE model_name = ?",
                (worker[0],),
            )

        log_event(
            conn,
            "task_auto_blocked",
            task_id=task_id,
            details=f"claims={row[2]}, idle_minutes={idle_minutes}",
        )

        blocked.append(task_id)
        if not args.quiet:
            print(f"[BLOCK] Task {task_id} blocked after {row[2]} claims (last claim {last_claim})")

    if blocked:
        conn.commit()
    else:
        conn.rollback()

    conn.close()

    if not args.quiet:
        print(f"[BLOCK] Tasks blocked: {len(blocked)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
