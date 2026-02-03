#!/usr/bin/env python3
"""Submit a review decision and handle dependency cascade.

On approval: marks task done and unblocks dependent tasks whose deps are all done.
On request_changes: moves task back to changes_requested for the implementer.

Usage: python submit_review.py <model_name> <task_id> approve|request_changes [--notes "feedback"]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, log_event, now_sqlite


def unblock_dependents(conn, completed_task_id):
    """Check all blocked tasks and unblock those whose dependencies are now all done."""
    blocked_tasks = conn.execute(
        "SELECT id, depends_on FROM tasks WHERE status = 'blocked'"
    ).fetchall()

    unblocked = []
    for task in blocked_tasks:
        deps = json.loads(task["depends_on"]) if task["depends_on"] else []
        if not deps:
            continue

        # Check if ALL dependencies are done
        if deps:
            placeholders = ",".join("?" for _ in deps)
            done_count = conn.execute(
                f"SELECT COUNT(*) as cnt FROM tasks WHERE id IN ({placeholders}) AND status = 'done'",
                deps,
            ).fetchone()["cnt"]

            if done_count == len(deps):
                conn.execute(
                    "UPDATE tasks SET status = 'available' WHERE id = ?",
                    (task["id"],),
                )
                log_event(conn, "task_unblocked", task_id=task["id"],
                          details=f"All {len(deps)} dependencies satisfied")
                unblocked.append(task["id"])

    return unblocked


def main():
    if len(sys.argv) < 4:
        print("Usage: python submit_review.py <model_name> <task_id> approve|request_changes [--notes \"feedback\"]")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    task_id = sys.argv[2]
    decision = sys.argv[3].lower()

    if decision not in ("approve", "request_changes"):
        print("ERROR: Decision must be 'approve' or 'request_changes'")
        sys.exit(1)

    notes = None
    if "--notes" in sys.argv:
        idx = sys.argv.index("--notes")
        if idx + 1 < len(sys.argv):
            notes = sys.argv[idx + 1]

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            print(f"ERROR: Task {task_id} not found")
            conn.rollback()
            sys.exit(1)

        if task["reviewer"] != model:
            print(f"ERROR: Task {task_id} is not being reviewed by {model}")
            conn.rollback()
            sys.exit(1)

        now = now_sqlite()

        if decision == "approve":
            conn.execute(
                "UPDATE tasks SET status='done', completed_at=? WHERE id=?",
                (now, task_id),
            )
            log_event(conn, "review_approved", model_name=model, task_id=task_id,
                      details=notes)

            # Dependency cascade
            unblocked = unblock_dependents(conn, task_id)

            # Update worker state
            conn.execute(
                "UPDATE workers SET status='idle', current_task=NULL WHERE model_name=?",
                (model,),
            )

            conn.commit()

            print(f"APPROVED: Task {task_id} marked as done")
            if unblocked:
                print(f"  Unblocked {len(unblocked)} task(s): {', '.join(unblocked)}")
            if notes:
                print(f"  Notes: {notes}")
            if task_id == "feature-139":
                print(
                    "  Mobile table reminder: confirm vertical stacking + horizontal scrolling still work "
                    "for data tables on phones before closing the review."
                )

        else:  # request_changes
            conn.execute(
                "UPDATE tasks SET status='changes_requested', reviewer=NULL WHERE id=?",
                (task_id,),
            )
            log_event(conn, "review_changes_requested", model_name=model, task_id=task_id,
                      details=notes)

            # Update worker state
            conn.execute(
                "UPDATE workers SET status='idle', current_task=NULL WHERE model_name=?",
                (model,),
            )

            conn.commit()

            print(f"CHANGES REQUESTED: Task {task_id} sent back to {task['assigned_to']}")
            if notes:
                print(f"  Feedback: {notes}")
            if task_id == "feature-139":
                print(
                    "  Mobile table reminder: keep validating the responsive table layout (stacking and horizontal scrolling) "
                    "before resubmitting."
                )

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
