"""Behavioral tests for the public opponent-threat classifier."""

import pytest

from kaggriculture_lib.adaptive_strategy import (
    ThreatLevel,
    ThreatMemory,
    ThreatSnapshot,
    parse_public_threat_snapshot,
)


def snap(quadrants: int = 1, hands: int = 0, animals: int = 0) -> ThreatSnapshot:
    return ThreatSnapshot(quadrants, hands, animals)


def test_compact_boundaries() -> None:
    """A state below every threshold remains compact."""
    transition = ThreatMemory().update(0, 0, 0, 0, snap(1, 5, 2))

    assert transition.level is ThreatLevel.COMPACT
    assert transition.reason == "compact"


def test_each_building_trigger() -> None:
    """Each building signal independently raises the threat level."""
    assert ThreatMemory().update(0, 0, 0, 0, snap(2, 0, 0)).level is ThreatLevel.BUILDING
    assert ThreatMemory().update(0, 0, 0, 0, snap(1, 6, 0)).level is ThreatLevel.BUILDING
    assert ThreatMemory().update(0, 0, 0, 0, snap(1, 0, 3)).level is ThreatLevel.BUILDING


def test_each_compounding_trigger_and_reason() -> None:
    """The highest-priority matching compounding signal selects its reason."""
    cases = [
        (snap(3, 0, 0), "three_quadrants"),
        (snap(2, 0, 4), "two_quadrants_four_animals"),
        (snap(2, 8, 0), "two_quadrants_eight_hands"),
        (snap(1, 0, 6), "six_animals"),
    ]

    for snapshot, reason in cases:
        transition = ThreatMemory().update(0, 0, 0, 0, snapshot)
        assert transition.level is ThreatLevel.COMPOUNDING
        assert transition.reason == reason


def test_disappearing_animals_cannot_lower_the_threat_level() -> None:
    """A later public decrease cannot de-escalate a player within an episode."""
    memory = ThreatMemory()
    memory.update(0, 4, 1, 2, snap(1, 0, 6))

    transition = memory.update(0, 5, 1, 3, snap(1, 0, 0))

    assert transition.level is ThreatLevel.COMPOUNDING
    assert not transition.changed
    assert transition.reason == "six_animals"
    assert transition.delta_animals == -6


def test_players_keep_independent_threat_memory() -> None:
    """One opponent's escalation cannot affect a different player."""
    memory = ThreatMemory()
    memory.update(0, 2, 0, 2, snap(3, 0, 0))

    player_one = memory.update(1, 2, 0, 2, snap())

    assert player_one.level is ThreatLevel.COMPACT
    assert player_one.reason == "compact"


@pytest.mark.parametrize("next_step", [0, 3])
def test_new_or_rewound_episode_resets_player_memory(next_step: int) -> None:
    """Step zero and a decreasing step discard the previous episode state."""
    memory = ThreatMemory()
    memory.update(0, 4, 1, 2, snap(3, 0, 0))

    transition = memory.update(0, next_step, 0, 0, snap())

    assert transition.level is ThreatLevel.COMPACT
    assert transition.reason == "compact"
    assert not transition.changed
    assert transition.delta_quadrants == 0
    assert transition.delta_hands == 0
    assert transition.delta_animals == 0


def test_transition_reports_observed_public_count_increases() -> None:
    """Transitions expose deltas from the prior public snapshot."""
    memory = ThreatMemory()
    memory.update(0, 1, 0, 1, snap(1, 1, 1))

    transition = memory.update(0, 2, 0, 2, snap(2, 3, 4))

    assert (transition.delta_quadrants, transition.delta_hands, transition.delta_animals) == (1, 2, 3)


@pytest.mark.parametrize(
    "farm",
    [
        {},
        {"tiles": "not-a-list", "hands": [], "unlocked_quadrants": []},
        {"tiles": [], "hands": "not-a-list", "unlocked_quadrants": []},
        {"tiles": [], "hands": [], "unlocked_quadrants": "not-a-list"},
    ],
)
def test_malformed_public_state_returns_a_safe_snapshot(farm: dict) -> None:
    """Missing or malformed public collections never raise during parsing."""
    snapshot, reason = parse_public_threat_snapshot(farm)

    assert snapshot == snap(0, 0, 0)
    assert reason == "malformed_public_state"


def test_public_snapshot_counts_only_recognized_animals() -> None:
    """Animal counts come from public tiles and ignore non-animal tile data."""
    farm = {
        "unlocked_quadrants": ["NW", "NE"],
        "hands": [[1, 2], [3, 4]],
        "tiles": [
            [{"animal": "COW"}, {"animal": "WHEAT"}],
            [{"animal": "SHEEP"}, {"animal": "GOOSE"}],
        ],
    }

    snapshot, reason = parse_public_threat_snapshot(farm)

    assert snapshot == snap(2, 2, 3)
    assert reason is None
