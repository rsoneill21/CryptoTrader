-- Triad Parallel Coordination System - Database Schema
-- SQLite with WAL mode for safe concurrent access

PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

-- Tasks from PLAN.md
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,                    -- e.g. "2.1", "3.4"
    phase INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'available'
        CHECK(status IN ('available','blocked','claimed','review_pending','changes_requested','done')),
    assigned_to TEXT,                       -- model name or NULL
    reviewer TEXT,                          -- model reviewing this task
    files_json TEXT DEFAULT '[]',           -- JSON array of file paths
    depends_on TEXT DEFAULT '[]',           -- JSON array of task IDs
    priority INTEGER DEFAULT 0,            -- higher = more important
    commit_hash TEXT,                       -- git commit when submitted
    claimed_at TEXT,                        -- ISO 8601 timestamp
    review_submitted_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_phase ON tasks(phase);

-- File-level locking to prevent conflicts
CREATE TABLE IF NOT EXISTS file_locks (
    file_path TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    locked_by TEXT NOT NULL,               -- model name
    locked_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL               -- default 30 min from lock time
);

CREATE INDEX IF NOT EXISTS idx_file_locks_locked_by ON file_locks(locked_by);
CREATE INDEX IF NOT EXISTS idx_file_locks_expires ON file_locks(expires_at);

-- Worker (model) state tracking
CREATE TABLE IF NOT EXISTS workers (
    model_name TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'idle'
        CHECK(status IN ('idle','working','reviewing','offline')),
    current_task TEXT REFERENCES tasks(id),
    last_heartbeat TEXT DEFAULT (datetime('now')),
    session_started_at TEXT DEFAULT (datetime('now'))
);

-- Usage tracking for rotation
CREATE TABLE IF NOT EXISTS usage_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    requests_made INTEGER DEFAULT 0,
    recorded_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage_model ON usage_tracking(model_name);
CREATE INDEX IF NOT EXISTS idx_usage_recorded ON usage_tracking(recorded_at);

-- Per-model usage limits
CREATE TABLE IF NOT EXISTS usage_limits (
    model_name TEXT PRIMARY KEY,
    max_tokens_per_hour INTEGER DEFAULT 100000,
    max_tokens_per_day INTEGER DEFAULT 1000000,
    max_requests_per_hour INTEGER DEFAULT 60,
    max_requests_per_day INTEGER DEFAULT 500,
    alert_threshold_pct REAL DEFAULT 0.7,   -- warn at 70%
    rotation_threshold_pct REAL DEFAULT 0.85, -- rotate at 85%
    is_available INTEGER DEFAULT 1           -- 0 = manually disabled
);

-- Event log for audit trail
CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    model_name TEXT,
    task_id TEXT,
    details TEXT,
    timestamp TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_events_model ON event_log(model_name);
CREATE INDEX IF NOT EXISTS idx_events_time ON event_log(timestamp);
