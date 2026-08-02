from dataclasses import replace

import pytest

from kaggriculture_lib.replay_schema import (
    ActionOrigin,
    DecisionRecord,
    NormalizedAction,
)
from kaggriculture_lib.replay_splits import (
    SplitName,
    assign_family_splits,
    audit_split_leakage,
)


@pytest.fixture
def sample_record() -> DecisionRecord:
    return DecisionRecord(
        episode_id="89468208",
        source_policy_id="public/radiant",
        source_family="radiant-89468208",
        step=0,
        day=0,
        hour=0,
        seat=0,
        opponent_family="baseline",
        environment_version="1.29.3",
        configuration={"seed": 7},
        observation={},
        action=NormalizedAction(("PASS",), (), ()),
        action_origin=ActionOrigin.PUBLIC_ORIGINAL,
        original_action=None,
        repair_reason=None,
        terminal_result=None,
        final_banks=None,
        compatibility_ok=True,
        legality_ok=True,
        completeness_ok=True,
        duplicate=False,
    )


@pytest.fixture
def leaking_records(sample_record):
    return [
        sample_record,
        replace(sample_record, episode_id="89468209", step=1, hour=1),
    ]


@pytest.fixture
def assignments():
    return {
        "89468208": SplitName.TRAIN,
        "89468209": SplitName.VALIDATION,
    }


def test_variants_of_same_family_never_cross_splits():
    families = ["radiant-89468208", "radiant-89468208", "scenario-aware", "teacher-v2"]
    assignment = assign_family_splits(
        families,
        seed=20260802,
        validation_fraction=0.25,
        holdout_families={"scenario-aware"},
    )
    assert assignment["scenario-aware"] is SplitName.FAMILY_HOLDOUT
    assert set(assignment) == set(families)


def test_split_assignment_is_order_independent():
    forward = assign_family_splits(["a", "b", "c"], 7, 0.34, {"c"})
    reverse = assign_family_splits(["c", "b", "a"], 7, 0.34, {"c"})
    assert forward == reverse


def test_audit_rejects_episode_and_family_leakage(leaking_records, assignments):
    report = audit_split_leakage(leaking_records, assignments)
    assert not report.ok
    assert report.family_leaks == ("radiant-89468208",)


def test_audit_reports_duplicate_base_episode_ids_and_missing_assignments(sample_record):
    records = [
        sample_record,
        replace(
            sample_record,
            episode_id="89468208-terminal-controller",
            source_family="radiant-89468208-terminal-controller",
            step=1,
            hour=1,
        ),
        replace(
            sample_record,
            episode_id="unassigned",
            source_family="unassigned-family",
            step=2,
            hour=2,
        ),
    ]
    report = audit_split_leakage(
        records,
        {
            "radiant-89468208": SplitName.TRAIN,
            "radiant-89468208-terminal-controller": SplitName.VALIDATION,
        },
    )
    assert report.base_episode_leaks == ("89468208",)
    assert report.missing_assignments == ("unassigned-family",)
    assert str(report) == (
        "split leakage detected: base_episode_leaks=89468208; "
        "missing_assignments=unassigned-family"
    )


def test_assign_family_splits_rejects_invalid_fraction():
    with pytest.raises(ValueError, match="validation_fraction"):
        assign_family_splits(["a"], 7, 1.0, set())


def test_assign_family_splits_rejects_explicitly_reserved_family():
    with pytest.raises(ValueError, match="reserved"):
        assign_family_splits(
            ["ordinary-public-policy"],
            7,
            0.25,
            set(),
            reserved_families={"ordinary-public-policy"},
        )


def test_assign_family_splits_rejects_holdout_reservation_overlap():
    with pytest.raises(ValueError, match="holdout_families.*reserved_families"):
        assign_family_splits(
            ["a"],
            7,
            0.25,
            {"a"},
            reserved_families={"a"},
        )
