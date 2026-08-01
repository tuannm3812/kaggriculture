"""Behavior tests for agents/task_teacher_v1/main.py.

Mirrors tests/test_agents.py's synthetic-obs pattern for roi_teacher_v1-v3,
adapted for a multi-tile farm. Per the approved design in
docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md.
"""

import math
import sys
from pathlib import Path

from conftest import load_agent_module

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from kaggle_environments import make  # noqa: E402

BOARD_SIZE = 10
V1_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


def make_obs(*, day=0, money=3000.0, farmer=(4, 4), tiles=None, farmer_inventory=None, shed=None, seeds=None, prices=None):
    board = tiles if tiles is not None else [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    opponent_tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    fx, fy = farmer
    farm_template = {
        "farmer": None,
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    me = {**farm_template, "money": money, "tiles": board, "farmer": [fx, fy]}
    opponent = {**farm_template, "money": 3000.0, "tiles": opponent_tiles, "farmer": [fx, fy]}
    return {
        "player": 0,
        "step": day * 24,
        "day": day,
        "hour": 0,
        "farms": [me, opponent],
        "market": {"inventory": {}, "prices": prices if prices is not None else {}},
        "town": {"unlocked_shops": []},
        "private": {
            "shed": shed or {},
            "seeds": seeds or {},
            "inventories": [farmer_inventory or {}],
        },
    }


def make_plant_tile(crop, planted_day, watered_today, consecutive_unwatered=0):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "watered_today": watered_today,
        "consecutive_unwatered": consecutive_unwatered,
        "yield_units": 1,
        "max_lifespan_step": -1,
        "fertilized_until_day": -1,
    }


def test_agent_plants_when_already_at_empty_tile_with_seed_held():
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    # Realistic prices for all three candidates (docs/3_agent_strategy.md:
    # Melon dominates ROI/day at base price) -- hold the seed for whichever
    # crop the scorer will actually pick, so this tests "plant when at
    # target with the matching seed held," not an unrelated mismatch.
    realistic_prices = {"WHEAT": 25, "CARROT": 35, "MELON": 250}
    obs = make_obs(farmer=(4, 4), tiles=tiles, seeds={"MELON": 1}, prices=realistic_prices)
    action = module.agent(obs, V1_CONFIG)
    assert action["farmer"][0] == "PLANT"
    assert action["farmer"][1] == "MELON"


def test_agent_moves_toward_target_tile_when_not_already_there():
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    # Weed at (0,0); farmer starts far away at (4,4) -- DIG should outrank
    # a same-tier PLANT decision at the farmer's own empty tile once
    # distance is factored in, but regardless the farmer must move there
    # eventually. Use a case where the *only* task is far away.
    tiles[0][0] = {"kind": "WEED"}
    obs = make_obs(farmer=(4, 4), tiles=[[None] * BOARD_SIZE for _ in range(BOARD_SIZE)])
    # Put the farmer itself on a tile with nothing feasible nearby except
    # the far weed by making every other tile infeasible: use day so late
    # that no crop can be planted, leaving DIG as the only task.
    obs = make_obs(farmer=(4, 4), tiles=tiles, day=28)
    action = module.agent(obs, V1_CONFIG)
    assert action["farmer"][0] in ("NORTH", "SOUTH", "EAST", "WEST")


def test_agent_waters_unwatered_plant_when_standing_on_it():
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    obs = make_obs(farmer=(4, 4), tiles=tiles, day=1)
    action = module.agent(obs, V1_CONFIG)
    assert action["farmer"] == ["WATER"]


def test_agent_harvests_mature_watered_plant_when_standing_on_it():
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_plant_tile("WHEAT", planted_day=0, watered_today=True)
    obs = make_obs(farmer=(4, 4), tiles=tiles, day=4)  # WHEAT max_yield_day == 4
    action = module.agent(obs, V1_CONFIG)
    assert action["farmer"] == ["HARVEST"]


def test_agent_digs_weed_when_standing_on_it():
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = {"kind": "WEED"}
    obs = make_obs(farmer=(4, 4), tiles=tiles)
    action = module.agent(obs, V1_CONFIG)
    assert action["farmer"] == ["DIG"]


def test_agent_sells_shed_contents():
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(farmer=(4, 4), tiles=tiles, shed={"WHEAT": 5})
    action = module.agent(obs, V1_CONFIG)
    assert ["SELL", "WHEAT", 5] in action["market"]


def test_market_timing_seed_bought_this_turn_is_not_planted_this_turn():
    """Real bug class flagged by Codex's review: unit actions execute
    before market actions each turn, so a seed bought this turn cannot
    satisfy a PLANT task this same turn."""
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(farmer=(4, 4), tiles=tiles, seeds={}, money=3000, prices={"CARROT": 35})
    action = module.agent(obs, V1_CONFIG)
    assert action["farmer"] != ["PLANT", "CARROT"]
    assert any(o[0] == "BUY_SEED" for o in action["market"])


def test_teacher_state_resets_on_new_episode():
    module = load_agent_module("task_teacher_v1")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = {"kind": "WEED"}
    obs_mid_episode = make_obs(farmer=(4, 4), tiles=tiles, day=5)
    module.agent(obs_mid_episode, V1_CONFIG)
    assert module._state.assignments.get(0) is not None

    # A brand-new episode (step == 0) must clear stale assignment state,
    # even though this is the same Python module/process.
    fresh_tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs_new_episode = make_obs(farmer=(0, 0), tiles=fresh_tiles, day=0)
    obs_new_episode["step"] = 0
    module.agent(obs_new_episode, V1_CONFIG)
    # The weed task from the previous episode must not still be assigned.
    assigned = module._state.assignments.get(0)
    assert assigned is None or assigned.kind != "WEED"


# --- Acceptance-gate regression (small-scale; full 100-episode gate run
# was measured by hand and recorded in docs/4_agent_version_log.md) --------


def test_acceptance_gate_regression_sample():
    """Small-sample regression guard for the full acceptance gate: 100%
    DONE, finite rewards, and reasonable multi-tile coverage across a
    handful of seeds. Full 100-episode measurement is in the version log,
    not re-run here every test invocation for speed."""
    n_episodes = 5
    distinct_tiles_per_episode = []

    for i in range(n_episodes):
        env = make(
            "kaggriculture", configuration={"episodeSteps": 720, "seed": 9000 + i}, debug=True
        )
        env.run(["agents/task_teacher_v1/main.py", "starter"])

        final = env.steps[-1]
        assert all(s.status == "DONE" for s in final)
        assert all(s.reward is not None and math.isfinite(s.reward) for s in final)

        touched = set()
        for step in env.steps:
            action = step[0].action
            if isinstance(action, dict) and isinstance(action.get("farmer"), list) and action["farmer"]:
                if action["farmer"][0] in ("PLANT", "WATER", "HARVEST", "DIG"):
                    touched.add(tuple(step[0].observation["farms"][0]["farmer"]))
        distinct_tiles_per_episode.append(len(touched))

    assert min(distinct_tiles_per_episode) >= 8
