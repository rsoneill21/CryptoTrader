#!/usr/bin/env python3
"""Normalize priorities so earlier phases get higher priority."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_helpers import get_connection, load_config  # noqa: E402


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

    for phase in sorted(phases):
        visit(phase)

    return order


def main() -> None:
    conn = get_connection()
    config = load_config()

    active_phases = {row[0] for row in conn.execute(
        "SELECT DISTINCT phase FROM tasks WHERE status!='done'"
    )}
    if not active_phases:
        print("No non-done tasks found. Nothing to align.")
        return

    phase_deps: dict[int, Sequence[int]] = {}
    for key, deps in config.get("phase_dependencies", {}).items():
        phase_deps[int(key)] = [int(dep) for dep in deps]

    all_phases = set(active_phases) | set(phase_deps.keys())
    phase_order = _topo_sort(all_phases, phase_deps)
    filtered_order = [phase for phase in phase_order if phase in active_phases]
    if not filtered_order:
        print("No active phases in dependency graph. Nothing to do.")
        return

    priority_map = {}
    max_priority = len(filtered_order)
    for idx, phase in enumerate(filtered_order):
        priority_map[phase] = max_priority - idx

    updates: list[tuple[int, str]] = []
    summary: dict[int, int] = defaultdict(int)
    for phase, target_priority in priority_map.items():
        cursor = conn.execute(
            "SELECT id, priority FROM tasks WHERE status!='done' AND phase=?",
            (phase,),
        )
        for row in cursor:
            current = row[1] if row[1] is not None else 0
            if current != target_priority:
                updates.append((target_priority, row[0]))
                summary[phase] += 1

    if not updates:
        print("All non-done tasks already have the prioritized order.")
        conn.close()
        return

    conn.executemany("UPDATE tasks SET priority=? WHERE id=?", updates)
    conn.commit()
    print("Updated priorities for the following phases:")
    for phase in sorted(summary):
        print(f"  Phase {phase}: {summary[phase]} tasks -> priority {priority_map[phase]}")

    print("New priority scheme:")
    for phase in filtered_order:
        print(f"  Phase {phase}: priority {priority_map[phase]}")

    conn.close()


if __name__ == "__main__":
    main()
