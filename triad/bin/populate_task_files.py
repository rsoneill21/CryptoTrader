#!/usr/bin/env python3
"""Fill in files_json for feature tasks so workers know which files to lock."""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from db_helpers import PROJECT_ROOT, get_connection, log_event


FEATURES_DB_PATH = PROJECT_ROOT / "features.db"
DEFAULT_FRONT_FILES = [
    "frontend/src/App.js",
    "frontend/src/main.jsx",
    "frontend/src/pages/Dashboard.js",
    "frontend/src/pages/LiveTrading.js",
]
DEFAULT_BACK_FILES = [
    "backend/main.py",
    "backend/api/__init__.py",
    "backend/api/system.py",
]


def slugify(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"[^0-9a-z]", "", text.lower())


def extract_keywords(text: str) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"[a-z0-9]{4,}", text.lower())
    return sorted(set(tokens))


def collect_git_files() -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = []
        for path in PROJECT_ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(PROJECT_ROOT)
            if ".git" in rel.parts or "node_modules" in rel.parts or "venv" in rel.parts:
                continue
            files.append(str(rel))
        return files


def normalize_path(path: str) -> str:
    return re.sub(r"[^0-9a-z]", "", path.lower())


def build_context(task: sqlite3.Row, feature: dict | None) -> str:
    pieces = []
    if feature:
        if feature.get("name"):
            pieces.append(feature["name"])
        if feature.get("description"):
            pieces.append(feature["description"])
        steps = feature.get("steps")
        if steps:
            pieces.append(" ".join(steps))
    pieces.append(task["title"])
    if task["description"]:
        pieces.append(task["description"])
    return " ".join(pieces)


def find_feature_row(features_conn: sqlite3.Connection, task_id: str) -> dict | None:
    if not task_id.startswith("feature-"):
        return None
    try:
        _, raw_id = task_id.split("-", 1)
        feature_id = int(raw_id)
    except (ValueError, IndexError):
        return None
    row = features_conn.execute(
        "SELECT id, name, category, description, steps FROM features WHERE id = ?",
        (feature_id,),
    ).fetchone()
    if not row:
        return None
    steps = row[4]
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except json.JSONDecodeError:
            steps = []
    return {
        "id": row[0],
        "name": row[1],
        "category": row[2],
        "description": row[3],
        "steps": steps or [],
    }


def select_candidates(
    text: str,
    slug: str,
    keywords: list[str],
    file_index: dict[str, str],
    max_files: int,
) -> list[str]:
    matches = []
    if slug:
        matches.extend([path for path, norm in file_index.items() if slug in norm])
    if not matches:
        matches.extend([path for path, norm in file_index.items() if any(kw in norm for kw in keywords)])
    seen = []
    for path in matches:
        if path not in seen:
            seen.append(path)
    seen.sort(key=lambda p: (len(p), p))
    return seen[:max_files]


def fallback_files(context_text: str) -> list[str]:
    fallback = []
    context_lower = context_text.lower()
    if any(term in context_lower for term in ("frontend", "react", "ui", "layout", "page")):
        fallback.extend(DEFAULT_FRONT_FILES)
    if any(term in context_lower for term in ("backend", "api", "service", "server", "auth", "db", "trade", "strategy")):
        fallback.extend(DEFAULT_BACK_FILES)
    if not fallback:
        fallback.extend(DEFAULT_FRONT_FILES[:1])
        fallback.extend(DEFAULT_BACK_FILES[:1])
    return [path for path in fallback if (PROJECT_ROOT / path).exists()]


def update_task_files(conn: sqlite3.Connection, task_id: str, files: list[str]) -> None:
    conn.execute(
        "UPDATE tasks SET files_json = ? WHERE id = ?",
        (json.dumps(files), task_id),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", "-n", type=int, default=5, help="Max number of tasks to update")
    parser.add_argument("--max-files", type=int, default=5, help="Max files per task")
    parser.add_argument("--quiet", action="store_true", help="Suppress informational output")
    args = parser.parse_args()

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    features_conn: sqlite3.Connection | None = None
    if FEATURES_DB_PATH.exists():
        features_conn = sqlite3.connect(FEATURES_DB_PATH)
        features_conn.row_factory = sqlite3.Row

    tasks = conn.execute(
        "SELECT id, title, description, status FROM tasks WHERE (files_json IS NULL OR files_json = '[]') AND status IN ('available','blocked','changes_requested') ORDER BY priority DESC, id LIMIT ?",
        (args.limit,),
    ).fetchall()

    if not tasks:
        if not args.quiet:
            print("[DISCOVER] No tasks need files_json")
        if features_conn:
            features_conn.close()
        conn.close()
        return 0

    file_index = {path: normalize_path(path) for path in collect_git_files()}
    updates = 0

    for task in tasks:
        feature_info = None
        if features_conn:
            feature_info = find_feature_row(features_conn, task["id"])
        context = build_context(task, feature_info)
        slug = slugify(context)
        keywords = extract_keywords(context)
        candidates = select_candidates(context, slug, keywords, file_index, args.max_files)
        if not candidates:
            candidates = fallback_files(context)
        if not candidates:
            continue
        update_task_files(conn, task["id"], candidates)
        updates += 1
        log_event(
            conn,
            "files_discovered",
            task_id=task["id"],
            details=f"{len(candidates)} files inferred",
        )
        if not args.quiet:
            print(f"[DISCOVER] Task {task['id']} -> {candidates}")

    conn.commit()
    if features_conn:
        features_conn.close()
    conn.close()

    if not args.quiet:
        print(f"[DISCOVER] Updated {updates} task(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
