"""Behavioral tests for the public opponent-threat classifier."""

import pytest

from kaggriculture_lib.adaptive_strategy import (
    CashLedger,
    LandDecision,
    ThreatLevel,
    ThreatMemory,
    ThreatSnapshot,
    authorize_land_purchase,
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


def test_cash_ledger_deducts_every_reserve_once() -> None:
    """Land affordability subtracts each planned reserve and the purchase once."""
    ledger = CashLedger(100, 200, 300, 1200, 500)

    assert ledger.total_reserved == 2300
    assert ledger.remaining(money=10_000, purchase_cost=2_000) == 5700


def test_third_land_authorizes_compounding_at_the_end_of_day_with_horizon() -> None:
    """A compounding opponent permits the third land on the eligible boundary."""
    decision = authorize_land_purchase(
        threat=ThreatLevel.COMPOUNDING,
        n_extra=1,
        day=15,
        hour=23,
        last_day=27,
        money=10_000,
        land_cost=2_000,
        ledger=CashLedger(100, 200, 300, 1200, 500),
        productive_utilization=0.0,
        opponent_quadrants=3,
        opponent_animals=4,
    )

    assert decision == LandDecision(True, "third_land_compounding", 5700)


@pytest.mark.parametrize(
    ("threat", "hour", "last_day", "money", "land_cost", "reason"),
    [
        (ThreatLevel.BUILDING, 23, 27, 10_000, 2_000, "third_land_threat_not_compounding"),
        (ThreatLevel.COMPOUNDING, 22, 27, 10_000, 2_000, "third_land_not_end_of_day"),
        (ThreatLevel.COMPOUNDING, 23, 26, 10_000, 2_000, "third_land_horizon_too_short"),
        (ThreatLevel.COMPOUNDING, 23, 27, 4_299, 2_000, "insufficient_cash"),
        (ThreatLevel.COMPOUNDING, 23, 27, 10_000, 0, "invalid_land_cost"),
    ],
)
def test_third_land_returns_a_telemetry_reason_for_each_rejected_gate(
    threat: ThreatLevel,
    hour: int,
    last_day: int,
    money: float,
    land_cost: float,
    reason: str,
) -> None:
    """Each third-land gate reports the condition that prevented expansion."""
    decision = authorize_land_purchase(
        threat, 1, 15, hour, last_day, money, land_cost,
        CashLedger(100, 200, 300, 1200, 500), 0.0, 3, 4,
    )

    assert not decision.authorized
    assert decision.reason == reason


def test_land_purchase_rejects_after_the_fourth_quadrant_is_already_open() -> None:
    """The policy never authorizes more than three extra quadrants."""
    decision = authorize_land_purchase(
        ThreatLevel.COMPOUNDING, 3, 15, 23, 29, 20_000, 4_000,
        CashLedger(0, 0, 0), 1.0, 4, 10,
    )

    assert decision == LandDecision(False, "maximum_extra_quadrants_reached", 14_300)


def test_fourth_land_authorizes_on_every_required_boundary() -> None:
    """Fourth land opens only at the precise attack-mode thresholds."""
    decision = authorize_land_purchase(
        ThreatLevel.BUILDING, 2, 15, 23, 29, 14_300, 4_000,
        CashLedger(100, 200, 300, 1200, 500), 0.70, 4, 0,
    )

    assert decision == LandDecision(True, "fourth_land_severe_threat", 8000)


@pytest.mark.parametrize(
    ("hour", "last_day", "utilization", "quadrants", "animals", "land_cost", "money", "reason"),
    [
        (22, 29, 0.70, 4, 0, 4_000, 14_300, "fourth_land_not_end_of_day"),
        (23, 28, 0.70, 4, 0, 4_000, 14_300, "fourth_land_horizon_too_short"),
        (23, 29, 0.699, 4, 0, 4_000, 14_300, "fourth_land_utilization_too_low"),
        (23, 29, 0.70, 3, 9, 4_000, 14_300, "fourth_land_threat_not_severe"),
        (23, 29, 0.70, 4, 0, 3_999, 14_300, "fourth_land_cost_must_be_4000"),
        (23, 29, 0.70, 4, 0, 4_000, 14_299, "fourth_land_cash_below_reserve"),
    ],
)
def test_fourth_land_returns_a_telemetry_reason_for_each_rejected_gate(
    hour: int,
    last_day: int,
    utilization: float,
    quadrants: int,
    animals: int,
    land_cost: float,
    money: float,
    reason: str,
) -> None:
    """Each fourth-land gate independently guards the attack expansion."""
    decision = authorize_land_purchase(
        ThreatLevel.COMPOUNDING, 2, 15, hour, last_day, money, land_cost,
        CashLedger(100, 200, 300, 1200, 500), utilization, quadrants, animals,
    )

    assert not decision.authorized
    assert decision.reason == reason


@pytest.mark.parametrize("field", ["queued_hires", "assigned_seeds", "two_day_feed", "animal_liquidity", "operating"])
@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf"), float("-inf")])
def test_cash_ledger_rejects_negative_or_nonfinite_reserves(field: str, invalid: float) -> None:
    """Invalid reserve inputs cannot be used to fabricate available cash."""
    values = {"queued_hires": 100, "assigned_seeds": 200, "two_day_feed": 300,
              "animal_liquidity": 1200, "operating": 500}
    values[field] = invalid

    with pytest.raises(ValueError):
        CashLedger(**values)


@pytest.mark.parametrize("money", [float("nan"), float("inf"), float("-inf")])
def test_cash_ledger_rejects_nonfinite_money(money: float) -> None:
    """Non-finite money cannot yield a land affordability decision."""
    with pytest.raises(ValueError):
        CashLedger(100, 200, 300).remaining(money)


@pytest.mark.parametrize("purchase_cost", [float("nan"), float("inf"), float("-inf")])
def test_cash_ledger_rejects_nonfinite_purchase_cost(purchase_cost: float) -> None:
    """Non-finite purchase prices cannot yield a land affordability decision."""
    with pytest.raises(ValueError):
        CashLedger(100, 200, 300).remaining(10_000, purchase_cost)
