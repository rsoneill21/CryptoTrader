#!/usr/bin/env python3
"""Audit Triad tasks to ensure they are in the expected phase and priority order."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, load_config  # noqa: E402


def _parse_depends(depends_blob: str | None) -> list[str]:
    if not depends_blob:
        return []
    try:
        parsed = json.loads(depends_blob)
    except json.JSONDecodeError:
        return []
    return [str(entry) for entry in parsed if entry is not None]


def _topo_sort(phases: Iterable[int], deps: Mapping[int, Sequence[int]]) -> list[int]:
    order: list[int] = []
    visiting: dict[int, int] = {}

    def visit(node: int) -> None:
        state = visiting.get(node)
        if state == 1:
            raise RuntimeError(f"Cycle detected in phase graph at phase {node}")
        if state == 2:
            return
        visiting[node] = 1
        for prereq in sorted(deps.get(node, [])):
            visit(prereq)
        visiting[node] = 2
        order.append(node)

    for ph in sorted(phases):
        visit(ph)

    return order


def _status_counts(tasks: Sequence[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    return counts


def main() -> None:
    conn = get_connection(readonly=True)
    config = load_config()

    rows = conn.execute(
        "SELECT id, title, phase, priority, status, depends_on FROM tasks"
    ).fetchall()

    tasks: dict[str, dict] = {}
    phases_in_db: set[int] = set()
    for row in rows:
        phase = row["phase"]
        phases_in_db.add(phase)
        tasks[row["id"]] = {
            "id": row["id"],
            "title": row["title"],
            "phase": phase,
            "priority": row["priority"] if row["priority"] is not None else 0,
            "status": row["status"],
            "depends_on": _parse_depends(row["depends_on"]),
        }

    phase_deps: dict[int, Sequence[int]] = {}
    for phase_key, deps in config.get("phase_dependencies", {}).items():
        phase_deps[int(phase_key)] = [int(dep) for dep in deps]

    all_phases = phases_in_db | set(phase_deps.keys())
    phase_order = _topo_sort(all_phases, phase_deps)
    phase_rank = {phase: idx for idx, phase in enumerate(phase_order)}

    def _is_ready(task: dict[str, object]) -> bool:
        for dep_id in task["depends_on"]:
            dep = tasks.get(dep_id)
            if not dep or dep["status"] != "done":
                return False
        return True

    non_done = [task for task in tasks.values() if task["status"] != "done"]

    phase_summary: dict[int, dict[str, int]] = defaultdict(lambda: {"ready": 0, "not_ready": 0})
    ready_tasks: list[dict] = []
    issues: list[str] = []

    for task in non_done:
        ready = _is_ready(task)
        if ready:
            phase_summary[task["phase"]]["ready"] += 1
            ready_tasks.append(task)
            if task["status"] == "blocked":
                issues.append(
                    f"{task['id']} is ready (all deps done) but still marked blocked"
                )
        else:
            phase_summary[task["phase"]]["not_ready"] += 1
            if task["status"] in {"available", "claimed", "changes_requested"}:
                issues.append(
                    f"{task['id']} is {task['status']} even though prerequisite phases are not done"
                )

    ready_tasks_sorted = sorted(
        ready_tasks,
        key=lambda task: (
            phase_rank.get(task["phase"], max(phase_rank.values(), default=0) + 1),
            -task["priority"],
            task["id"],
        ),
    )

    print("=== Phase dependency order ===")
    print(" → ".join(str(p) for p in phase_order))
    print()

    print("=== Phase readiness ===")
    for phase in phase_order:
        totals = phase_summary.get(phase)
        if not totals:
            continue
        print(
            f"Phase {phase}: ready={totals['ready']} | waiting on earlier phases={totals['not_ready']}"
        )

    if not issues:
        print("\nAll non-done tasks are in the expected phase/priority alignment.")
    else:
        print("\n=== Phase/priority issues ===")
        for issue in issues:
            print(f"- {issue}")

    if not ready_tasks_sorted:
        print("\nNo ready tasks found; check phase dependencies before claiming work.")
        conn.close()
        return

    print("\n=== Recommended work order (phase + priority) ===")
    print("Phase | Priority | Status | ID — Title")
    print("----- | -------- | ------ | -------------------------------")
    for task in ready_tasks_sorted:
        print(
            f"{task['phase']:5d} | {task['priority']:8d} | {task['status']:6s} | "
            f"{task['id']} — {task['title']}"
        )


if __name__ == "__main__":
    main()
