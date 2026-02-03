#!/usr/bin/env python3
"""Claim a review assignment for a task in review_pending status.

A model cannot review its own work. Uses round-robin assignment.

Usage: python claim_review.py <model_name> <task_id>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, log_event, now_sqlite


def main():
    if len(sys.argv) < 3:
        print("Usage: python claim_review.py <model_name> <task_id>")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    task_id = sys.argv[2]

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            print(f"ERROR: Task {task_id} not found")
            conn.rollback()
            sys.exit(1)

        if task["status"] != "review_pending":
            print(f"ERROR: Task {task_id} has status '{task['status']}', not review_pending")
            conn.rollback()
            sys.exit(1)

        if task["assigned_to"] == model:
            print(f"ERROR: Cannot review your own work. Task {task_id} was implemented by {model}")
            conn.rollback()
            sys.exit(1)

        if task["reviewer"]:
            print(f"CONFLICT: Task {task_id} already being reviewed by {task['reviewer']}")
            conn.rollback()
            sys.exit(1)

        # Assign reviewer
        now = now_sqlite()
        conn.execute(
            "UPDATE tasks SET reviewer=? WHERE id=?",
            (model, task_id),
        )

        # Update worker state
        conn.execute(
            """INSERT INTO workers (model_name, status, current_task, last_heartbeat)
               VALUES (?, 'reviewing', ?, ?)
               ON CONFLICT(model_name) DO UPDATE SET
                 status='reviewing', current_task=?, last_heartbeat=?""",
            (model, task_id, now, task_id, now),
        )

        log_event(conn, "review_claimed", model_name=model, task_id=task_id,
                  details=f"Reviewing work by {task['assigned_to']}")

        conn.commit()

        print(f"REVIEW CLAIMED: {model} reviewing task {task_id}")
        print(f"  Title: {task['title']}")
        print(f"  Implemented by: {task['assigned_to']}")
        if task["commit_hash"]:
            print(f"  Commit: {task['commit_hash']}")
        if task["id"] == "feature-139":
            print(
                "  Mobile table reminder: verify the data-table layouts stay readable at ≈360–480px and "
                "scroll horizontally instead of overflowing the viewport."
            )

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
