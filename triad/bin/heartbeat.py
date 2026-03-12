#!/usr/bin/env python3
"""Refresh heartbeat and extend file locks for a working model.

Should be called every ~5 minutes while working on a task.

Usage: python heartbeat.py <model_name>
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, load_config, now_sqlite


def main():
    if len(sys.argv) < 2:
        print("Usage: python heartbeat.py <model_name>")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    config = load_config()
    lock_minutes = config.get("lock_timeout_minutes", 30)

    conn = get_connection()
    now = now_sqlite()
    expires = (datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)).strftime("%Y-%m-%d %H:%M:%S")

    # Update heartbeat
    conn.execute(
        "UPDATE workers SET last_heartbeat=? WHERE model_name=?",
        (now, model),
    )

    # Extend file locks
    updated = conn.execute(
        "UPDATE file_locks SET expires_at=? WHERE locked_by=?",
        (expires, model),
    ).rowcount

    conn.commit()
    conn.close()

    print(f"Heartbeat updated for {model}. {updated} file lock(s) extended to {expires}.")


if __name__ == "__main__":
    main()
