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
