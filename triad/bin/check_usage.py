#!/usr/bin/env python3
"""Check usage against limits for a model.

Returns one of: OK, WARNING, ROTATE, UNAVAILABLE

Usage: python check_usage.py <model_name>
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_usage.py <model_name>")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    conn = get_connection(readonly=True)

    limits = conn.execute(
        "SELECT * FROM usage_limits WHERE model_name = ?", (model,)
    ).fetchone()

    if not limits:
        print(f"UNAVAILABLE: No usage limits configured for {model}")
        conn.close()
        return

    if not limits["is_available"]:
        print(f"UNAVAILABLE: {model} is manually disabled")
        conn.close()
        return

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

    alert_pct = limits["alert_threshold_pct"]
    rotate_pct = limits["rotation_threshold_pct"]

    checks = [
        ("tokens/hour", hour_usage["tokens"], limits["max_tokens_per_hour"]),
        ("requests/hour", hour_usage["requests"], limits["max_requests_per_hour"]),
        ("tokens/day", day_usage["tokens"], limits["max_tokens_per_day"]),
        ("requests/day", day_usage["requests"], limits["max_requests_per_day"]),
    ]

    overall_status = "OK"
    print(f"=== Usage for {model} ===")
    for label, used, limit in checks:
        if limit <= 0:
            continue
        pct = used / limit
        bar = "#" * int(pct * 20) + "-" * (20 - int(pct * 20))
        status = "OK"
        if pct >= rotate_pct:
            status = "ROTATE"
            if overall_status != "ROTATE":
                overall_status = "ROTATE"
        elif pct >= alert_pct:
            status = "WARNING"
            if overall_status == "OK":
                overall_status = "WARNING"

        print(f"  {label:15s} [{bar}] {used:>8}/{limit:<8} ({pct:.0%}) {status}")

    print(f"\nStatus: {overall_status}")
    conn.close()


if __name__ == "__main__":
    main()
