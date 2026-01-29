#!/usr/bin/env python3
"""Register a model as an active worker in the Triad system.

Usage: python worker_register.py <model_name>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, validate_model, log_event, now_sqlite


def main():
    if len(sys.argv) < 2:
        print("Usage: python worker_register.py <model_name>")
        print("  model_name: claude | codex | gemini")
        sys.exit(1)

    model = validate_model(sys.argv[1])
    now = now_sqlite()
    conn = get_connection()

    # Upsert worker record
    conn.execute(
        """INSERT INTO workers (model_name, status, current_task, last_heartbeat, session_started_at)
           VALUES (?, 'idle', NULL, ?, ?)
           ON CONFLICT(model_name) DO UPDATE SET
             status='idle',
             current_task=NULL,
             last_heartbeat=?,
             session_started_at=?""",
        (model, now, now, now, now),
    )

    log_event(conn, "worker_registered", model_name=model, details="Session started")
    conn.commit()
    conn.close()

    print(f"Worker '{model}' registered and ready.")


if __name__ == "__main__":
    main()
