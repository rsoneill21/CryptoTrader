"""Shared database connection and path helpers for the Triad coordination system."""

import json
import os
import sqlite3
from pathlib import Path

# Resolve paths relative to the triad/ directory
TRIAD_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = TRIAD_DIR.parent
DB_PATH = TRIAD_DIR / "triad.db"
SCHEMA_PATH = TRIAD_DIR / "schema.sql"
CONFIG_PATH = TRIAD_DIR / "config.json"
PLAN_PATH = TRIAD_DIR / "PLAN.md"

VALID_MODELS = ["claude", "codex", "gemini"]


def get_connection(readonly=False):
    """Get a SQLite connection with WAL mode and busy timeout."""
    if readonly:
        uri = f"file:{DB_PATH}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def load_config():
    """Load the triad configuration."""
    with open(CONFIG_PATH) as f:
        return json.load(f)


def validate_model(model_name):
    """Validate that a model name is recognized."""
    name = model_name.lower()
    if name not in VALID_MODELS:
        raise ValueError(f"Unknown model: {model_name}. Must be one of: {', '.join(VALID_MODELS)}")
    return name


def log_event(conn, event_type, model_name=None, task_id=None, details=None):
    """Write an entry to the event_log table."""
    conn.execute(
        "INSERT INTO event_log (event_type, model_name, task_id, details) VALUES (?, ?, ?, ?)",
        (event_type, model_name, task_id, details),
    )


def now_iso():
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_sqlite():
    """Return current UTC time in SQLite datetime format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
