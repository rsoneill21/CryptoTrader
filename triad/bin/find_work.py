#!/usr/bin/env python3
"""List available tasks for a given model.

Filters out tasks whose files conflict with currently locked files.
Also hides tasks when the model is at ROTATE usage level.

Usage: python find_work.py <model_name>
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, now_sqlite


def get_locked_files(conn, exclude_model):
    """Get set of files currently locked by OTHER models."""
    now = now_sqlite()
    rows = conn.execute(
        "SELECT file_path FROM file_locks WHERE locked_by != ? AND expires_at > ?",
        (exclude_model, now),
    ).fetchall()
    return {r["file_path"] for r in rows}


def check_usage_level(conn, model):
    """Check if model is at ROTATE level (should not claim new tasks)."""
    from datetime import datetime, timezone, timedelta

    limits = conn.execute(
        "SELECT * FROM usage_limits WHERE model_name = ?", (model,)
    ).fetchone()
    if not limits or not limits["is_available"]:
        return "UNAVAILABLE"

    now = datetime.now(timezone.utc)
    hour_ago = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    day_start = now.strftime("%Y-%m-%d 00:00:00")

    hour_usage = conn.execute(
        "SELECT COALESCE(SUM(tokens_used),0) as tokens, COALESCE(SUM(requests_made),0) as requests "
        "FROM usage_tracking WHERE model_name=? AND recorded_at >= ?",
        (model, hour_ago),
    ).fetchone()

    day_usage = conn.execute(
        "SELECT COALESCE(SUM(tokens_used),0) as tokens, COALESCE(SUM(requests_made),0) as requests "
        "FROM usage_tracking WHERE model_name=? AND recorded_at >= ?",
        (model, day_start),
    ).fetchone()

    rotation_pct = limits["rotation_threshold_pct"]

    # Check if any metric exceeds rotation threshold
    checks = [
        (hour_usage["tokens"], limits["max_tokens_per_hour"], "tokens/hour"),
        (hour_usage["requests"], limits["max_requests_per_hour"], "requests/hour"),
        (day_usage["tokens"], limits["max_tokens_per_day"], "tokens/day"),
        (day_usage["requests"], limits["max_requests_per_day"], "requests/day"),
    ]

    for used, limit, label in checks:
        if limit > 0 and used >= limit * rotation_pct:
            return "ROTATE"

    return "OK"


def main():
    if len(sys.argv) < 2:
        print("Usage: python find_work.py <model_name>")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    conn = get_connection(readonly=True)

    # Check usage
    usage_level = check_usage_level(conn, model)
    if usage_level == "UNAVAILABLE":
        print(f"Model '{model}' is marked as unavailable.")
        conn.close()
        return
    if usage_level == "ROTATE":
        print(f"WARNING: Model '{model}' has reached rotation threshold. No new tasks available.")
        print("Complete current work and let another model take over.")
        conn.close()
        return

    locked_files = get_locked_files(conn, model)

    # Find available tasks
    available = conn.execute(
        "SELECT * FROM tasks WHERE status IN ('available', 'changes_requested') ORDER BY priority DESC, id"
    ).fetchall()

    # Find pending reviews (assigned to someone else, not this model)
    reviews = conn.execute(
        "SELECT * FROM tasks WHERE status='review_pending' AND assigned_to != ? AND reviewer IS NULL",
        (model,),
    ).fetchall()

    # Filter out file conflicts
    def has_conflict(task):
        files = json.loads(task["files_json"]) if task["files_json"] else []
        return bool(set(files) & locked_files)

    available_tasks = [t for t in available if not has_conflict(t)]
    conflicting_count = len(available) - len(available_tasks)

    # Display available tasks
    print(f"=== Available Tasks for {model} ===")
    if not available_tasks:
        if conflicting_count:
            print(f"  No tasks available ({conflicting_count} hidden due to file lock conflicts)")
        else:
            print("  No tasks available")
    else:
        for t in available_tasks:
            files = json.loads(t["files_json"]) if t["files_json"] else []
            status_tag = f" [{t['status']}]" if t["status"] != "available" else ""
            print(f"  {t['id']:5s} {t['title']}{status_tag}")
            if files:
                print(f"        Files: {', '.join(files)}")
        if conflicting_count:
            print(f"\n  ({conflicting_count} additional tasks hidden due to file lock conflicts)")
    # Mobile reminders for specific tasks
    mobile_chart_tasks = [t for t in available_tasks if t["id"] == "feature-137"]
    if mobile_chart_tasks:
        print(
            "\n  Mobile chart reminder: feature-137 targets trading chart readability on phones. "
            "Inspect LiveTrading/Chart components (`frontend/src/pages/LiveTrading.js`, "
            "`frontend/src/components/Chart.js`, `ChartIndicators.js`, `ChartAnnotations.js`) "
            "and verify the axes, timeframe selector, and touch interactions remain usable at ~360px width."
        )
    mobile_form_tasks = [t for t in available_tasks if t["id"] == "feature-138"]
    if mobile_form_tasks:
        print(
            "\n  Mobile form reminder: feature-138 targets input forms on phones. "
            "Resize login/register/forgot-password/settings forms to ~360px, confirm fields stack, labels stay legible, buttons stay touch-friendly, "
            "and interactive controls (toggles, dropdowns, validation states) remain visible."
        )

    # Display review opportunities
    print(f"\n=== Reviews Available ===")
    if not reviews:
        print("  No reviews pending")
    else:
        for r in reviews:
            print(f"  {r['id']:5s} {r['title']} (by {r['assigned_to']})")

    conn.close()


if __name__ == "__main__":
    main()
