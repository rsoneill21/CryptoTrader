#!/usr/bin/env python3
"""Initialize the Triad coordination database from schema.sql."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import DB_PATH, SCHEMA_PATH, get_connection, load_config


def main():
    if DB_PATH.exists():
        print(f"Database already exists at {DB_PATH}")
        if "--force" not in sys.argv:
            print("Use --force to reinitialize (WARNING: destroys existing data)")
            return
        DB_PATH.unlink()
        # Also remove WAL/SHM files if present
        for suffix in ("-wal", "-shm"):
            p = DB_PATH.parent / (DB_PATH.name + suffix)
            if p.exists():
                p.unlink()
        print("Removed existing database.")

    schema_sql = SCHEMA_PATH.read_text()
    conn = get_connection()
    conn.executescript(schema_sql)

    # Seed usage_limits from config
    config = load_config()
    for model_name, limits in config.get("usage_limits", {}).items():
        conn.execute(
            """INSERT OR REPLACE INTO usage_limits
               (model_name, max_tokens_per_hour, max_tokens_per_day,
                max_requests_per_hour, max_requests_per_day,
                alert_threshold_pct, rotation_threshold_pct, is_available)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                model_name,
                limits["max_tokens_per_hour"],
                limits["max_tokens_per_day"],
                limits["max_requests_per_hour"],
                limits["max_requests_per_day"],
                limits["alert_threshold_pct"],
                limits["rotation_threshold_pct"],
            ),
        )

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")
    print(f"Schema loaded from {SCHEMA_PATH}")
    print(f"Usage limits seeded for: {', '.join(config.get('usage_limits', {}).keys())}")


if __name__ == "__main__":
    main()
