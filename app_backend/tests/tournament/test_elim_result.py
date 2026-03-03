from uuid import uuid4

from metta.app_backend.tournament.commissioners.teams.config import (
    AllOfElim,
    ElimResult,
    FractionElim,
    ThresholdElim,
)


def test_intersect_removes_eliminated_that_survived():
    a = uuid4()
    b = uuid4()
    c = uuid4()

    left = ElimResult(survivors={a, b}, eliminated={c: "low score"})
    right = ElimResult(survivors={a, c}, eliminated={b: "bottom half"})

    result = left.intersect(right)
    assert result.survivors == {a}
    assert b in result.eliminated
    assert c in result.eliminated
    assert a not in result.eliminated


def test_intersect_no_runtime_error_on_overlapping_elim_and_survivor():
    a = uuid4()
    b = uuid4()
    c = uuid4()

    left = ElimResult(survivors={a, b, c}, eliminated={})
    right = ElimResult(survivors={a}, eliminated={b: "rule1", c: "rule2"})

    result = left.intersect(right)
    assert result.survivors == {a}
    assert b in result.eliminated
    assert c in result.eliminated


def test_allof_elim_overlapping_rules():
    policies = {uuid4(): score for score in [0.1, 0.3, 0.5, 0.7, 0.9]}
    rules = AllOfElim(
        rules=[
            ThresholdElim(min_score=0.25),
            FractionElim(fraction=0.5),
        ]
    )
    result = rules.apply(policies)
    for pv_id in result.survivors:
        assert policies[pv_id] >= 0.25
    for pv_id in result.eliminated:
        assert pv_id not in result.survivors
