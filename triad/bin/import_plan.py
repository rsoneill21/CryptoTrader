#!/usr/bin/env python3
"""Parse PLAN.md and import tasks into the Triad database.

Reads the markdown task tables and creates entries with correct statuses:
- Phase 1 tasks: done
- Phase 2 tasks: available (Phase 1 complete)
- Phase 6 tasks: available (can run in parallel with Phase 2 per dependency graph)
- All other tasks: blocked (dependencies not yet met)
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import PLAN_PATH, get_connection, load_config, log_event, now_sqlite


def parse_plan(plan_text):
    """Parse PLAN.md task tables into structured data."""
    tasks = []
    current_phase = None
    current_phase_num = None

    for line in plan_text.split("\n"):
        # Detect phase headers
        phase_match = re.match(r"^### Phase (\d+):", line)
        if phase_match:
            current_phase_num = int(phase_match.group(1))
            current_phase = line.strip("# ").strip()
            continue

        # Parse table rows (skip header and separator rows)
        if current_phase_num and line.startswith("|") and not line.startswith("|--") and not line.startswith("| ID"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 5:
                task_id = cells[0].strip()
                title = cells[1].strip()
                status_raw = cells[2].strip()
                files_raw = cells[3].strip()
                criteria = cells[4].strip()

                # Parse files from backtick-quoted paths
                files = re.findall(r"`([^`]+)`", files_raw)

                # Determine status
                if "done" in status_raw.lower():
                    status = "done"
                else:
                    status = "pending"  # Will be resolved to available/blocked below

                tasks.append({
                    "id": task_id,
                    "phase": current_phase_num,
                    "title": title,
                    "description": criteria,
                    "status": status,
                    "files": files,
                })

    return tasks


def resolve_dependencies(tasks, config):
    """Determine task dependencies from phase dependency graph."""
    phase_deps = config.get("phase_dependencies", {})

    for task in tasks:
        if task["status"] == "done":
            continue

        phase = str(task["phase"])
        dep_phases = phase_deps.get(phase, [])

        # A task depends on all tasks from prerequisite phases
        depends_on = []
        for dep_phase in dep_phases:
            dep_phase_int = int(dep_phase)
            for other in tasks:
                if other["phase"] == dep_phase_int:
                    depends_on.append(other["id"])

        task["depends_on"] = depends_on

        # Check if all dependencies are done
        all_deps_done = all(
            any(t["id"] == dep_id and t["status"] == "done" for t in tasks)
            for dep_id in depends_on
        ) if depends_on else True

        if all_deps_done:
            task["status"] = "available"
        else:
            task["status"] = "blocked"

    return tasks


def import_tasks(tasks, conn):
    """Insert tasks into the database."""
    now = now_sqlite()
    inserted = 0
    skipped = 0

    for task in tasks:
        # Check if task already exists
        existing = conn.execute("SELECT id FROM tasks WHERE id = ?", (task["id"],)).fetchone()
        if existing:
            skipped += 1
            continue

        conn.execute(
            """INSERT INTO tasks (id, phase, title, description, status, files_json, depends_on, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task["id"],
                task["phase"],
                task["title"],
                task["description"],
                task["status"],
                json.dumps(task.get("files", [])),
                json.dumps(task.get("depends_on", [])),
                now if task["status"] == "done" else None,
            ),
        )
        inserted += 1

        log_event(conn, "task_imported", task_id=task["id"],
                  details=f"Phase {task['phase']}, status={task['status']}")

    return inserted, skipped


def main():
    if not PLAN_PATH.exists():
        print(f"ERROR: PLAN.md not found at {PLAN_PATH}")
        sys.exit(1)

    plan_text = PLAN_PATH.read_text()
    config = load_config()

    tasks = parse_plan(plan_text)
    if not tasks:
        print("ERROR: No tasks parsed from PLAN.md")
        sys.exit(1)

    tasks = resolve_dependencies(tasks, config)

    conn = get_connection()
    inserted, skipped = import_tasks(tasks, conn)
    conn.commit()

    # Print summary
    status_counts = {}
    for t in tasks:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1

    print(f"Imported {inserted} tasks ({skipped} skipped as existing)")
    print(f"Status breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    conn.close()


if __name__ == "__main__":
    main()
