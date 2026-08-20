"""Threat integration and identity tests for task_teacher_v18."""

import json
import sys
from pathlib import Path

import pytest
from conftest import load_agent_module

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from kaggle_environments import make  # noqa: E402
from kaggriculture_lib.env_config import tournament_configuration  # noqa: E402

BOARD_SIZE = 10
V18_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}
ACTION_KEYS = {"farmer", "hands", "market"}


def make_obs(
    *,
    player=0,
    step=None,
    day=0,
    hour=0,
    money=2000.0,
    farmer=(4, 4),
    hands=None,
    hires_today=0,
    tiles=None,
    farmer_inventory=None,
    hand_inventories=None,
    shed=None,
    seeds=None,
    prices=None,
    unlocked_quadrants=None,
    opponent_tiles=None,
    opponent_hands=None,
    opponent_unlocked_quadrants=None,
):
    """Build a v16-compatible observation with configurable public opposition."""
    board = tiles if tiles is not None else [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    public_opponent_tiles = (
        opponent_tiles
        if opponent_tiles is not None
        else [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    )
    hands = hands or []
    opponent_hands = opponent_hands or []
    fx, fy = farmer
    me = {
        "money": money,
        "tiles": board,
        "farmer": [fx, fy],
        "hands": [list(hand) for hand in hands],
        "unlocked_quadrants": (
            unlocked_quadrants if unlocked_quadrants is not None else ["NW"]
        ),
        "hires_today": hires_today,
    }
    opponent = {
        "money": 3000.0,
        "tiles": public_opponent_tiles,
        "farmer": [fx, fy],
        "hands": [list(hand) for hand in opponent_hands],
        "unlocked_quadrants": (
            opponent_unlocked_quadrants
            if opponent_unlocked_quadrants is not None
            else ["NW"]
        ),
        "hires_today": 0,
    }
    inventories = [farmer_inventory or {}] + [
        inventory or {} for inventory in (hand_inventories or [{}] * len(hands))
    ]
    farms = [me, opponent] if player == 0 else [opponent, me]
    return {
        "player": player,
        "step": day * 24 + hour if step is None else step,
        "day": day,
        "hour": hour,
        "farms": farms,
        "market": {"inventory": {}, "prices": prices if prices is not None else {}},
        "town": {"unlocked_shops": []},
        "private": {
            "shed": shed or {},
            "seeds": seeds or {},
            "inventories": inventories,
        },
    }


def make_animal_tile(animal="COW", *, fed_today=False):
    return {
        "kind": "PASTURE" if animal != "GOOSE" else "COOP",
        "animal": animal,
        "fed_today": fed_today,
        "consecutive_unfed": 0,
        "yield_units": 0,
        "cared_today": False,
    }


def make_plant_tile(crop="STRAWBERRY", *, day=15):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": day,
        "watered_today": True,
        "consecutive_unwatered": 0,
        "yield_units": 0,
        "max_lifespan_step": -1,
        "fertilized_until_day": -1,
    }


def make_backlog_tiles(count, *, kind="PLANT", day=15):
    """Build exactly ``count`` reachable workload tasks on a four-quadrant board."""
    tiles = [[{"kind": "DECORATION"}] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    coordinates = [(x, y) for y in range(BOARD_SIZE) for x in range(BOARD_SIZE)]
    for x, y in coordinates[:count]:
        if kind == "PLANT":
            tiles[y][x] = None
        elif kind == "HARVEST":
            tiles[y][x] = make_plant_tile("MELON", day=day - 12)
        else:
            raise ValueError(f"unsupported backlog task kind: {kind}")
    return tiles


def make_attack_labor_obs(
    *, backlog, day=15, hour=0, kind="PLANT", money=10_000.0, seeds=None, **kwargs
):
    """Create a high-cash, four-quadrant attack state with real generated tasks."""
    return make_obs(
        day=day,
        hour=hour,
        money=money,
        farmer=(0, 0),
        tiles=make_backlog_tiles(backlog, kind=kind, day=day),
        seeds={"STRAWBERRY": backlog} if seeds is None else seeds,
        unlocked_quadrants=["NW", "NE", "SW", "SE"],
        **kwargs,
    )


def make_third_land_obs(
    *,
    day=15,
    hour=23,
    money=10_000.0,
    opponent_unlocked_quadrants=None,
):
    """Build real queued-hire, assigned-seed, and feed commitments."""
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = make_animal_tile()
    return make_obs(
        day=day,
        hour=hour,
        money=money,
        farmer=(1, 0),
        hands=[(2, 0)],
        tiles=tiles,
        prices={"WHEAT": 1_000.0},
        unlocked_quadrants=["NW", "NE"],
        opponent_unlocked_quadrants=(
            opponent_unlocked_quadrants
            if opponent_unlocked_quadrants is not None
            else ["NW", "NE", "SW"]
        ),
    )


def make_fourth_land_obs(
    *,
    productive_tiles=75,
    money=13_700.0,
    day=15,
    hour=23,
    opponent_quadrants=4,
    opponent_animals=0,
):
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    unlocked = {"NW", "NE", "SW"}
    eligible = [
        (x, y)
        for y in range(BOARD_SIZE)
        for x in range(BOARD_SIZE)
        if ("N" if y < 5 else "S") + ("W" if x < 5 else "E") in unlocked
    ]
    for x, y in eligible[:productive_tiles]:
        tiles[y][x] = make_plant_tile(day=day)

    opponent_tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for index in range(opponent_animals):
        x, y = index % BOARD_SIZE, index // BOARD_SIZE
        opponent_tiles[y][x] = {"kind": "PASTURE", "animal": "COW"}

    return make_obs(
        day=day,
        hour=hour,
        money=money,
        hands=[(4, 4)] * 8,
        tiles=tiles,
        seeds={crop: 100 for crop in ("WHEAT", "CARROT", "MELON", "STRAWBERRY")},
        unlocked_quadrants=["NW", "NE", "SW"],
        opponent_tiles=opponent_tiles,
        opponent_unlocked_quadrants=["NW", "NE", "SW", "SE"][:opponent_quadrants],
    )


@pytest.mark.parametrize(
    ("quadrants", "hands", "expected_level", "expected_reason"),
    [
        (["NW"], [], "COMPACT", "compact"),
        (["NW", "NE"], [], "BUILDING", "extra_quadrant"),
        (["NW", "NE", "SW"], [], "COMPOUNDING", "three_quadrants"),
    ],
)
def test_opponent_public_counts_drive_threat_stage(
    quadrants, hands, expected_level, expected_reason
):
    module = load_agent_module("task_teacher_v18")
    action = module.agent(
        make_obs(opponent_unlocked_quadrants=quadrants, opponent_hands=hands),
        V18_CONFIG,
    )

    assert set(action) == ACTION_KEYS
    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["threat_level"] == expected_level
    assert diagnostics["threat_reason"] == expected_reason


def test_threat_state_is_monotonic_within_an_episode():
    module = load_agent_module("task_teacher_v18")
    first_action = module.agent(
        make_obs(step=0, opponent_unlocked_quadrants=["NW", "NE", "SW"]),
        V18_CONFIG,
    )
    second_action = module.agent(
        make_obs(step=1, hour=1, opponent_unlocked_quadrants=["NW"]),
        V18_CONFIG,
    )

    assert set(first_action) == ACTION_KEYS
    assert set(second_action) == ACTION_KEYS
    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["threat_level"] == "COMPOUNDING"
    assert diagnostics["threat_reason"] == "three_quadrants"
    assert diagnostics["delta_quadrants"] == -2


def test_threat_state_is_isolated_by_player():
    module = load_agent_module("task_teacher_v18")
    player_zero_action = module.agent(
        make_obs(player=0, step=0, opponent_unlocked_quadrants=["NW", "NE", "SW"]),
        V18_CONFIG,
    )
    player_one_action = module.agent(
        make_obs(player=1, step=0, opponent_unlocked_quadrants=["NW"]),
        V18_CONFIG,
    )

    assert set(player_zero_action) == ACTION_KEYS
    assert set(player_one_action) == ACTION_KEYS
    assert module.get_last_diagnostics(0)["threat_level"] == "COMPOUNDING"
    assert module.get_last_diagnostics(1)["threat_level"] == "COMPACT"


@pytest.mark.parametrize("reset_step", [0, 3])
def test_step_zero_or_decrease_resets_threat_state(reset_step):
    module = load_agent_module("task_teacher_v18")
    first_action = module.agent(
        make_obs(step=10, opponent_unlocked_quadrants=["NW", "NE", "SW"]),
        V18_CONFIG,
    )
    reset_action = module.agent(
        make_obs(step=reset_step, opponent_unlocked_quadrants=["NW"]),
        V18_CONFIG,
    )

    assert set(first_action) == ACTION_KEYS
    assert set(reset_action) == ACTION_KEYS
    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["threat_level"] == "COMPACT"
    assert diagnostics["delta_quadrants"] == 0


def test_diagnostics_are_json_safe_scalars_and_returned_as_a_copy():
    module = load_agent_module("task_teacher_v18")
    action = module.agent(make_obs(), V18_CONFIG)

    assert set(action) == ACTION_KEYS
    diagnostics = module.get_last_diagnostics(0)
    json.dumps(diagnostics)
    assert all(
        value is None or isinstance(value, (bool, int, float, str))
        for value in diagnostics.values()
    )
    assert diagnostics["threat_expansion_enabled"] is True

    diagnostics["threat_level"] = "MUTATED"
    assert module.get_last_diagnostics(0)["threat_level"] == "COMPACT"


def test_enabled_policy_uses_default_market_limit_without_config():
    """The enabled default-config path still emits a simulator-valid action."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(make_obs(), None)

    assert len(action["market"]) <= 10


def test_compounding_opponent_authorizes_third_land_with_each_commitment_once():
    """Missing the ledger integration would omit the threat-conditioned order."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(make_third_land_obs(), V18_CONFIG)

    assert action["market"].count(["BUY_LAND"]) == 1
    diagnostics = module.get_last_diagnostics(0)
    # Expensive-hire configuration caps the target at three hands, so two
    # queued hires cost 10 + 10. Two assigned WHEAT seeds cost 2 * 10.
    # Two-day feed: 2 days * 2 missing WHEAT * current price 1,000.
    assert diagnostics["ledger_reserved"] == 20 + 20 + 4_000 + 1_200 + 500
    assert diagnostics["post_land_cash"] == 10_000 - (20 + 20 + 4_000 + 1_200 + 500) - 2_000
    assert diagnostics["money"] == 10_000
    assert diagnostics["feed_shortage"] == 2
    assert diagnostics["land_cost"] == 2_000
    assert diagnostics["land_authorized"] is True
    assert diagnostics["land_reason"] == "third_land_compounding"


@pytest.mark.parametrize(
    ("day", "hour", "money", "opponent_quadrants", "expected_reason"),
    [
        (15, 23, 10_000.0, ["NW", "NE"], "third_land_threat_not_compounding"),
        (15, 22, 10_000.0, ["NW", "NE", "SW"], "third_land_not_end_of_day"),
        (18, 23, 10_000.0, ["NW", "NE", "SW"], "third_land_horizon_too_short"),
        (15, 23, 7_739.0, ["NW", "NE", "SW"], "insufficient_cash"),
    ],
)
def test_third_land_rejects_each_ineligible_integration_boundary(
    day, hour, money, opponent_quadrants, expected_reason
):
    """Every integration gate rejects independently with actionable telemetry."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_third_land_obs(
            day=day,
            hour=hour,
            money=money,
            opponent_unlocked_quadrants=opponent_quadrants,
        ),
        V18_CONFIG,
    )

    assert [order for order in action["market"] if order[0] == "BUY_LAND"] == []
    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["land_authorized"] is False
    assert diagnostics["land_reason"] == expected_reason


@pytest.mark.parametrize(
    ("opponent_quadrants", "opponent_animals"),
    [(4, 0), (3, 10)],
)
def test_fourth_land_authorizes_for_either_severe_public_threat(
    opponent_quadrants, opponent_animals
):
    """Either severe public signal can authorize exactly one fourth-land order."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_fourth_land_obs(
            opponent_quadrants=opponent_quadrants,
            opponent_animals=opponent_animals,
        ),
        V18_CONFIG,
    )

    assert action["market"].count(["BUY_LAND"]) == 1
    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["land_reason"] == "fourth_land_severe_threat"
    assert diagnostics["land_cost"] == 4_000
    assert diagnostics["ledger_reserved"] == 1_700
    assert diagnostics["post_land_cash"] == 8_000
    assert diagnostics["productive_utilization"] == 1.0


@pytest.mark.parametrize(
    ("productive_tiles", "money", "day", "hour", "expected_reason"),
    [
        (75, 13_700.0, 15, 22, "fourth_land_not_end_of_day"),
        (75, 13_700.0, 16, 23, "fourth_land_horizon_too_short"),
        (52, 13_700.0, 15, 23, "fourth_land_utilization_too_low"),
        (75, 13_699.0, 15, 23, "fourth_land_cash_below_reserve"),
    ],
)
def test_fourth_land_rejects_hour_horizon_utilization_and_cash_boundaries(
    productive_tiles, money, day, hour, expected_reason
):
    """Each fourth-land integration boundary independently prevents expansion."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_fourth_land_obs(
            productive_tiles=productive_tiles,
            money=money,
            day=day,
            hour=hour,
        ),
        V18_CONFIG,
    )

    assert [order for order in action["market"] if order[0] == "BUY_LAND"] == []
    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["land_authorized"] is False
    assert diagnostics["land_reason"] == expected_reason


def test_fourth_land_requires_three_existing_quadrants_and_never_duplicates_land():
    """At n_extra one, severe threat can authorize only the third-land branch."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_third_land_obs(opponent_unlocked_quadrants=["NW", "NE", "SW", "SE"]),
        V18_CONFIG,
    )

    assert action["market"].count(["BUY_LAND"]) == 1
    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["land_reason"] == "third_land_compounding"
    assert diagnostics["land_cost"] == 2_000


def test_enabled_first_land_seed_capacity_does_not_deduct_land_twice():
    """Four reserved seeds plus two residual-funded seeds survive one land deduction."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_obs(
            day=15,
            hour=1,
            money=3_250.0,
            hands=[(4, 4)] * 3,
            unlocked_quadrants=["NW"],
        ),
        V18_CONFIG,
    )

    assert action["market"].count(["BUY_LAND"]) == 1
    assert [order for order in action["market"] if order[0] == "BUY_SEED"] == [
        ["BUY_SEED", "MELON", 6]
    ]
    assert module.get_last_diagnostics(0)["post_land_cash"] == 230


def test_first_land_is_not_authorized_ahead_of_unfunded_required_feed():
    """Two $1,000 feed units must prevent a $1,000 land order at $2,500 cash."""
    module = load_agent_module("task_teacher_v18")
    tiles = [[{"kind": "DECORATION"}] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = make_animal_tile()

    action = module.agent(
        make_obs(
            day=15,
            hour=1,
            money=2_500.0,
            hands=[(4, 4)] * 3,
            tiles=tiles,
            prices={"WHEAT": 1_000.0},
            unlocked_quadrants=["NW"],
        ),
        V18_CONFIG,
    )

    diagnostics = module.get_last_diagnostics(0)
    assert ["BUY_PRODUCT", "WHEAT", 2] in action["market"]
    assert ["BUY_LAND"] not in action["market"]
    assert diagnostics["land_authorized"] is False
    assert diagnostics["land_reason"] == "v16_first_land_insufficient_cash"


def test_assigned_seed_orders_spend_their_reserved_bucket_exactly_once():
    """Four assigned MELON seeds remain funded when discretionary cash is zero."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_obs(
            day=15,
            hour=1,
            money=3_020.0,
            hands=[(4, 4)] * 3,
            unlocked_quadrants=["NW"],
        ),
        V18_CONFIG,
    )

    assert module.get_last_diagnostics(0)["post_land_cash"] == 0
    assert [order for order in action["market"] if order[0] == "BUY_SEED"] == [
        ["BUY_SEED", "MELON", 4]
    ]


@pytest.mark.parametrize(
    ("backlog", "expected_hands"),
    [(9, 8), (10, 9), (11, 10), (12, 10)],
)
def test_four_quadrant_attack_labor_tracks_executable_backlog(backlog, expected_hands):
    """Wrong workload thresholds must not retain the former unconditional 11 hands."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=backlog),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["executable_backlog"] == backlog
    assert diagnostics["hands_floor"] == expected_hands
    assert action["market"].count(["HIRE"]) == expected_hands
    assert diagnostics["terminal_labor_only"] is False


def test_missing_executable_workload_evidence_preserves_current_attack_workforce():
    """Unfunded planting cannot justify any attack-mode hiring."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12, money=10_000.0, seeds={}),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["executable_backlog"] == 0
    assert diagnostics["hands_floor"] == 0
    assert action["market"].count(["HIRE"]) == 0


def test_attack_backlog_uses_seed_orders_actually_planned_for_this_turn():
    """Affordable hour-one seed orders make their matching planting work useful."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12, money=10_000.0, seeds={}, hour=1),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    assert module.get_last_diagnostics(0)["executable_backlog"] == 12
    assert sum(order[2] for order in action["market"] if order[0] == "BUY_SEED") == 12


def test_attack_backlog_never_exceeds_seed_quantity_after_cash_commitments():
    """Expensive queued hires leave only two emitted seeds and two useful plant tasks."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(
            backlog=12,
            money=6_000.0,
            seeds={},
            hour=1,
            hires_today=10,
        ),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    emitted_seeds = sum(
        order[2] for order in action["market"] if order[0] == "BUY_SEED"
    )
    diagnostics = module.get_last_diagnostics(0)
    assert emitted_seeds == 2
    assert diagnostics["executable_backlog"] == emitted_seeds


def test_workload_backed_seed_order_survives_saturated_market_prefix():
    """All eleven seeds used to justify backlog outrank seven discretionary sales."""
    module = load_agent_module("task_teacher_v18")
    shed = {
        item: 1
        for item in (
            "CARROT",
            "MELON",
            "STRAWBERRY",
            "MILK",
            "WOOL",
            "EGG",
            "FERTILIZER",
        )
    }

    action = module.agent(
        make_attack_labor_obs(
            backlog=12,
            hour=1,
            seeds={"STRAWBERRY": 1},
            shed=shed,
        ),
        {**V18_CONFIG, "farmHandCostMult": 1, "maxMarketOrdersPerTurn": 10},
    )

    matching_seed_orders = [
        order
        for order in action["market"]
        if order[0] == "BUY_SEED" and order[1] == "STRAWBERRY"
    ]
    executable_backlog = module.get_last_diagnostics(0)["executable_backlog"]
    emitted_seed_quantity = sum(order[2] for order in matching_seed_orders)
    assert executable_backlog == 12
    assert executable_backlog <= 1 + emitted_seed_quantity
    assert matching_seed_orders == [["BUY_SEED", "STRAWBERRY", 11]]
    assert action["market"][0] == ["BUY_SEED", "STRAWBERRY", 11]
    assert action["market"].count(["HIRE"]) == 9
    assert not any(order[0] == "SELL" for order in action["market"])
    assert len(action["market"]) == 10


def test_final_day_non_terminal_backlog_cannot_raise_attack_labor():
    """Final-day PLANT work is excluded before it can justify a ninth hand."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12, day=29),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["executable_backlog"] == 0
    assert diagnostics["hands_floor"] == 0
    assert diagnostics["terminal_labor_only"] is True
    assert action["market"].count(["HIRE"]) == 0


def test_final_day_terminal_gate_applies_below_attack_cash_threshold():
    """Four-quadrant final-day planting cannot reach the legacy five-hand branch."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12, day=29, money=5_000.0),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["terminal_labor_only"] is True
    assert diagnostics["executable_backlog"] == 0
    assert diagnostics["hands_floor"] == 0
    assert action["market"].count(["HIRE"]) == 0


def test_final_day_terminal_backlog_can_raise_attack_labor():
    """Final-day harvest work still permits added labor when it fits the horizon."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12, day=29, kind="HARVEST"),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["executable_backlog"] == 12
    assert diagnostics["hands_floor"] == 10
    assert action["market"].count(["HIRE"]) == 10


def test_expensive_hiring_preserves_the_three_hand_cap_in_attack_mode():
    """Attack workload must not bypass the established expensive-hire safeguard."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12),
        {**V18_CONFIG, "farmHandCostMult": 5},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["hands_floor"] == 3
    assert action["market"].count(["HIRE"]) == 3


def test_attack_hiring_reserves_only_the_affordable_fibonacci_prefix():
    """A partial attack target must reserve exactly the hires cash can fund today."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12, money=6_000.0, hires_today=10),
        {**V18_CONFIG, "farmHandCostMult": 1},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert diagnostics["hands_floor"] == 7
    assert diagnostics["hire_cost_reserved"] == 4_037
    assert action["market"].count(["HIRE"]) == 7


def test_attack_hiring_uses_only_the_simulator_executable_market_slots():
    """An eleven-hand target cannot emit an eleventh order that the simulator drops."""
    module = load_agent_module("task_teacher_v18")

    action = module.agent(
        make_attack_labor_obs(backlog=12),
        {**V18_CONFIG, "farmHandCostMult": 1, "maxMarketOrdersPerTurn": 10},
    )

    diagnostics = module.get_last_diagnostics(0)
    assert len(action["market"]) == 10
    assert action["market"].count(["HIRE"]) == 10
    assert diagnostics["hands_floor"] == 10


def test_market_slot_budget_does_not_change_disabled_v16_policy():
    """The classifier-only path preserves v16's complete legacy action dictionary."""
    v16 = load_agent_module("task_teacher_v16")
    v18 = load_agent_module("task_teacher_v18")
    observation = make_attack_labor_obs(backlog=12)
    config = {
        **V18_CONFIG,
        "farmHandCostMult": 1,
        "maxMarketOrdersPerTurn": 10,
        "enableThreatExpansion": False,
    }

    assert v18.agent(observation, config) == v16.agent(observation, config)


def test_required_feed_seed_land_and_hires_precede_saturated_discretionary_orders():
    """Every essential commitment fits in the simulator's ten-order prefix."""
    module = load_agent_module("task_teacher_v18")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = make_animal_tile()
    shed = {
        item: 1
        for item in ("CARROT", "MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "FERTILIZER")
    }

    action = module.agent(
        make_obs(
            day=15,
            hour=1,
            money=10_000.0,
            farmer=(1, 0),
            tiles=tiles,
            shed=shed,
            prices={"WHEAT": 25.0},
            unlocked_quadrants=["NW"],
        ),
        {**V18_CONFIG, "maxMarketOrdersPerTurn": 10},
    )

    operations = [order[0] for order in action["market"]]
    diagnostics = module.get_last_diagnostics(0)
    assert len(action["market"]) == 10
    assert operations[:3] == ["BUY_PRODUCT", "BUY_SEED", "BUY_LAND"]
    assert operations.count("HIRE") == 3
    assert diagnostics["land_authorized"] is True
    assert diagnostics["market_orders_emitted"] == 10
    assert diagnostics["market_orders_dropped"] > 0


def test_authorized_fourth_land_stays_in_saturated_discretionary_prefix():
    """Fourth land executes before saturated sales and animal purchases."""
    module = load_agent_module("task_teacher_v18")
    obs = make_fourth_land_obs(money=30_000.0, day=14)
    obs["private"]["shed"].update({
        item: 1
        for item in ("CARROT", "MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "FERTILIZER")
    })

    action = module.agent(
        obs,
        {**V18_CONFIG, "farmHandCostMult": 1, "maxMarketOrdersPerTurn": 10},
    )

    operations = [order[0] for order in action["market"]]
    assert len(action["market"]) == 10
    assert operations[0] == "BUY_LAND"
    assert module.get_last_diagnostics(0)["market_orders_dropped"] > 0
    assert module.get_last_diagnostics(0)["land_authorized"] is True


def test_real_simulator_executes_third_land_and_unlocks_the_quadrant():
    """The real ten-order market processor executes v18's authorized third land."""
    module = load_agent_module("task_teacher_v18")
    third_land_actions = []

    def candidate(obs, config):
        action = module.agent(obs, config)
        if (
            len(obs["farms"][obs["player"]]["unlocked_quadrants"]) == 2
            and ["BUY_LAND"] in action["market"]
        ):
            third_land_actions.append(action)
        return action

    def land_rushing_opponent(obs, _config):
        hand_count = len(obs["farms"][obs["player"]]["hands"])
        return {
            "farmer": ["PASS"],
            "hands": [["PASS"] for _ in range(hand_count)],
            "market": [["BUY_LAND"]],
        }

    configuration = {
        **tournament_configuration(episode_steps=720, seed=19_001),
        "startingMoney": 30_000,
        "maxMarketOrdersPerTurn": 10,
    }
    env = make("kaggriculture", configuration=configuration, debug=True)
    env.run([candidate, land_rushing_opponent])

    final_farm = env.steps[-1][0].observation.farms[0]
    assert all(state.status == "DONE" for state in env.steps[-1])
    assert third_land_actions
    assert all(len(action["market"]) <= 10 for action in third_land_actions)
    assert final_farm["unlocked_quadrants"][:3] == ["NW", "NE", "SW"]


def test_classifier_only_ablation_is_action_identical_to_v16_for_ten_seed_pairs():
    for seed in range(18_000, 18_010):
        for seat in (0, 1):
            v16 = load_agent_module("task_teacher_v16")
            v18 = load_agent_module("task_teacher_v18")
            configuration = tournament_configuration(episode_steps=720, seed=seed)
            ablation_config = {**configuration, "enableThreatExpansion": False}
            observed_steps = []
            mismatches = []
            flag_values = []

            def compare_policy(obs, _environment_config):
                v16_action = v16.agent(obs, ablation_config)
                v18_action = v18.agent(obs, ablation_config)
                observed_steps.append(obs["step"])
                flag_values.append(
                    v18.get_last_diagnostics(obs["player"]).get(
                        "threat_expansion_enabled"
                    )
                )
                if set(v18_action) != ACTION_KEYS or v18_action != v16_action:
                    mismatches.append((obs["step"], v16_action, v18_action))
                return v16_action

            agents = (
                [compare_policy, "starter"]
                if seat == 0
                else ["starter", compare_policy]
            )
            env = make("kaggriculture", configuration=configuration, debug=True)
            env.run(agents)

            assert observed_steps == list(
                range(configuration["episodeSteps"] - 1)
            ), (seed, seat)
            assert mismatches == [], (seed, seat, mismatches[:1])
            assert flag_values and all(value is False for value in flag_values), (seed, seat)
            assert all(state.status == "DONE" for state in env.steps[-1]), (seed, seat)
