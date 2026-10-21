"""Dependency engine: derives automatic statuses, blockers and the critical path to Form 4.

Pure functions over plain data, so it is cheap to run on every change and easy to test.
"""

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter

from app.core.enums import RequirementStatus as S

DONE = frozenset({S.done, S.not_applicable})
# Statuses the engine owns. Anything else was set by a person and is never overwritten.
AUTOMATIC = frozenset({S.not_started, S.blocked, S.ready})


@dataclass(frozen=True)
class Node[K: Hashable]:
    id: K
    status: S
    estimated_days: int = 1
    is_form4_gate: bool = False


@dataclass
class EngineResult[K: Hashable]:
    statuses: dict[K, S]
    # Direct dependencies that are not done yet, for every requirement.
    blocked_by: dict[K, list[K]]
    critical_path: list[K] = field(default_factory=list)
    remaining_days: int = 0


class DependencyCycleError(ValueError):
    def __init__(self, cycle: list[Hashable]):
        super().__init__(f"dependency cycle: {cycle}")
        self.cycle = cycle


def check_acyclic[K: Hashable](deps: Mapping[K, Iterable[K]]) -> None:
    try:
        tuple(TopologicalSorter({k: tuple(v) for k, v in deps.items()}).static_order())
    except CycleError as e:
        raise DependencyCycleError(list(e.args[1])) from e


def evaluate[K: Hashable](
    nodes: Iterable[Node[K]], deps: Mapping[K, Iterable[K]]
) -> EngineResult[K]:
    by_id = {n.id: n for n in nodes}
    graph = {k: tuple(d for d in deps.get(k, ()) if d in by_id) for k in by_id}
    check_acyclic(graph)

    blocked_by = {k: [d for d in graph[k] if by_id[d].status not in DONE] for k in by_id}

    statuses: dict[K, S] = {}
    for k, node in by_id.items():
        if node.status in AUTOMATIC:
            statuses[k] = S.blocked if blocked_by[k] else S.ready
        else:
            statuses[k] = node.status

    path, days = _critical_path(by_id, graph, statuses)
    return EngineResult(statuses, blocked_by, path, days)


def _critical_path[K: Hashable](
    by_id: Mapping[K, Node[K]], graph: Mapping[K, tuple[K, ...]], statuses: Mapping[K, S]
) -> tuple[list[K], int]:
    """Longest chain of remaining work that ends at a Form 4 gate (or anywhere, if none)."""
    if not by_id:
        return [], 0

    def remaining(k: K) -> int:
        return 0 if statuses[k] in DONE else max(by_id[k].estimated_days, 0)

    dist: dict[K, int] = {}
    prev: dict[K, K | None] = {}
    for k in TopologicalSorter(graph).static_order():
        best = max(graph[k], key=lambda d: dist[d], default=None)
        dist[k] = remaining(k) + (dist[best] if best is not None else 0)
        prev[k] = best

    gates = [k for k, n in by_id.items() if n.is_form4_gate] or list(by_id)
    target = max(gates, key=lambda k: dist[k])

    path: list[K] = []
    cursor: K | None = target
    while cursor is not None:
        if statuses[cursor] not in DONE:
            path.append(cursor)
        cursor = prev[cursor]
    path.reverse()
    return path, dist[target]
