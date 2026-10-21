import pytest

from app.core.enums import RequirementStatus as S
from app.modules.requirements.engine import DependencyCycleError, Node, evaluate


def nodes(**statuses: S) -> list[Node[str]]:
    return [Node(k, s) for k, s in statuses.items()]


def test_requirement_without_dependencies_is_ready() -> None:
    result = evaluate(nodes(a=S.not_started), {})
    assert result.statuses == {"a": S.ready}


def test_unmet_dependency_blocks_and_is_reported() -> None:
    result = evaluate(nodes(a=S.in_progress, b=S.not_started), {"b": ["a"]})
    assert result.statuses["b"] == S.blocked
    assert result.blocked_by["b"] == ["a"]


def test_done_and_not_applicable_both_unblock() -> None:
    result = evaluate(nodes(a=S.done, b=S.not_applicable, c=S.blocked), {"c": ["a", "b"]})
    assert result.statuses["c"] == S.ready
    assert result.blocked_by["c"] == []


def test_manual_statuses_are_never_overwritten() -> None:
    # "a" went back to needs_fix after "b" started: b keeps its status but shows the blocker.
    result = evaluate(nodes(a=S.needs_fix, b=S.in_progress), {"b": ["a"]})
    assert result.statuses == {"a": S.needs_fix, "b": S.in_progress}
    assert result.blocked_by["b"] == ["a"]


def test_cycle_is_rejected() -> None:
    with pytest.raises(DependencyCycleError):
        evaluate(nodes(a=S.not_started, b=S.not_started), {"a": ["b"], "b": ["a"]})


def test_unknown_dependency_ids_are_ignored() -> None:
    result = evaluate(nodes(a=S.not_started), {"a": ["deleted"]})
    assert result.statuses["a"] == S.ready


def test_critical_path_follows_longest_remaining_chain_to_gate() -> None:
    #   short(1) ──┐
    #              ├──► gate(1)
    #   long1(5) ──► long2(5) ┘
    graph = [
        Node("short", S.not_started, 1),
        Node("long1", S.not_started, 5),
        Node("long2", S.not_started, 5),
        Node("gate", S.not_started, 1, is_form4_gate=True),
    ]
    result = evaluate(graph, {"long2": ["long1"], "gate": ["short", "long2"]})
    assert result.critical_path == ["long1", "long2", "gate"]
    assert result.remaining_days == 11


def test_critical_path_skips_done_work() -> None:
    graph = [
        Node("a", S.done, 10),
        Node("b", S.not_started, 3),
        Node("gate", S.not_started, 1, is_form4_gate=True),
    ]
    result = evaluate(graph, {"b": ["a"], "gate": ["b"]})
    assert result.critical_path == ["b", "gate"]
    assert result.remaining_days == 4


def test_empty_project() -> None:
    result = evaluate([], {})
    assert result.critical_path == []
    assert result.remaining_days == 0
