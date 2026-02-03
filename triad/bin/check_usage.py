#!/usr/bin/env python3
"""Check usage against limits for a model.

Returns one of: OK, WARNING, ROTATE, UNAVAILABLE

Usage: python check_usage.py <model_name>
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))
from db_helpers import get_connection, validate_model
from backend.db.database import log_system_error

LOG_SOURCE = "triad.check_usage"


def _log_usage_error(message: str, details: Optional[dict[str, Any]] = None) -> None:
    payload: dict[str, Any] = {"script": "check_usage"}
    if details:
        payload.update(details)
    try:
        log_system_error("error", LOG_SOURCE, message, payload)
    except Exception as exc:
        print(f"Warning: failed to log system error: {exc}", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        _log_usage_error("Missing model argument", {"args": sys.argv})
        print("Usage: python check_usage.py <model_name>")
        sys.exit(1)

    try:
        model = validate_model(sys.argv[1])
    except ValueError as exc:
        _log_usage_error(
            "Invalid model supplied to check_usage",
            {"provided": sys.argv[1], "error": str(exc)},
        )
        print(exc)
        sys.exit(1)

    tokens = 0
    requests = 0

    if "--tokens" in sys.argv:
        idx = sys.argv.index("--tokens")
        if idx + 1 < len(sys.argv):
            try:
                tokens = int(sys.argv[idx + 1])
            except ValueError as exc:
                _log_usage_error(
                    "Invalid --tokens value",
                    {"value": sys.argv[idx + 1], "error": str(exc), "model": model},
                )
                print("ERROR: --tokens must be an integer")
                sys.exit(1)
        else:
            _log_usage_error("Missing value for --tokens flag", {"model": model})
            print("ERROR: --tokens requires a value")
            sys.exit(1)

    if "--requests" in sys.argv:
        idx = sys.argv.index("--requests")
        if idx + 1 < len(sys.argv):
            try:
                requests = int(sys.argv[idx + 1])
            except ValueError as exc:
                _log_usage_error(
                    "Invalid --requests value",
                    {"value": sys.argv[idx + 1], "error": str(exc), "model": model},
                )
                print("ERROR: --requests must be an integer")
                sys.exit(1)
        else:
            _log_usage_error("Missing value for --requests flag", {"model": model})
            print("ERROR: --requests requires a value")
            sys.exit(1)

    if tokens == 0 and requests == 0:
        _log_usage_error(
            "No usage counts provided to check_usage", {"model": model}
        )
        print("ERROR: Provide at least --tokens or --requests")
        sys.exit(1)

    conn = get_connection(readonly=True)
    try:
        limits = conn.execute(
            "SELECT * FROM usage_limits WHERE model_name = ?", (model,)
        ).fetchone()

        if not limits:
            print(f"UNAVAILABLE: No usage limits configured for {model}")
            return

        if not limits["is_available"]:
            print(f"UNAVAILABLE: {model} is manually disabled")
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
            bar = "#" * int(pct * 20) + "-" * max(0, 20 - int(pct * 20))
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
    except Exception as exc:
        _log_usage_error(
            "Unexpected error while checking usage",
            {"model": model, "error": str(exc)},
        )
        print(f"ERROR: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
