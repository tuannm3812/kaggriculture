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
    """The post-ledger $230 buys two seeds; a second land deduction would buy none."""
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
        ["BUY_SEED", "MELON", 2]
    ]
    assert module.get_last_diagnostics(0)["post_land_cash"] == 230


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
