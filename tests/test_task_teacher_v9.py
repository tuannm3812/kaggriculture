"""Behavior tests for agents/task_teacher_v9/main.py.

v5 + bounded inventory-aware Cow/pasture/milk loop + direct wheat feed buying.
"""

import math
import sys
from pathlib import Path

import pytest
from conftest import load_agent_module

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from kaggle_environments import make  # noqa: E402

BOARD_SIZE = 10
V9_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


def make_obs(
    *,
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
):
    board = tiles if tiles is not None else [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    opponent_tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    hands = hands or []
    fx, fy = farmer
    me = {
        "money": money,
        "tiles": board,
        "farmer": [fx, fy],
        "hands": [list(h) for h in hands],
        "unlocked_quadrants": unlocked_quadrants if unlocked_quadrants is not None else ["NW"],
        "hires_today": hires_today,
    }
    opponent = {
        "money": 3000.0,
        "tiles": opponent_tiles,
        "farmer": [fx, fy],
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    inventories = [farmer_inventory or {}] + [inv or {} for inv in (hand_inventories or [{}] * len(hands))]
    return {
        "player": 0,
        "step": day * 24 + hour,
        "day": day,
        "hour": hour,
        "farms": [me, opponent],
        "market": {"inventory": {}, "prices": prices if prices is not None else {}},
        "town": {"unlocked_shops": []},
        "private": {
            "shed": shed or {},
            "seeds": seeds or {},
            "inventories": inventories,
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


def test_candidate_crops_match_v2():
    module = load_agent_module("task_teacher_v9")
    assert module.CANDIDATE_CROPS == ("WHEAT", "CARROT", "MELON")


def test_caps():
    module = load_agent_module("task_teacher_v9")
    assert module.MAX_GEESE == 0
    assert module.MAX_COWS == 3
    assert module.MAX_FEED_ACTIONS_PER_DAY == 6


def test_emits_buy_land_when_gate_would_pass():
    module = load_agent_module("task_teacher_v9")
    day = 15
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = make_plant_tile("WHEAT", planted_day=day, watered_today=True, consecutive_unwatered=0)
    obs = make_obs(
        day=day,
        hour=0,
        money=1_000_000,
        farmer=(4, 4),
        hands=[(1, 1), (2, 2), (3, 3)],
        tiles=tiles,
    )
    action = module.agent(obs, V9_CONFIG)
    assert ["BUY_LAND"] in action["market"]


def test_buys_cow_when_empty_pasture_and_cash_after_ne():
    module = load_agent_module("task_teacher_v9")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "PASTURE"}
    obs = make_obs(
        day=11,
        farmer=(4, 4),
        tiles=tiles,
        money=10_000.0,
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V9_CONFIG)
    assert ["BUY_ANIMAL", "COW", 1] in action["market"]


def test_does_not_buy_cow_before_ne_unlocked():
    module = load_agent_module("task_teacher_v9")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "PASTURE"}
    obs = make_obs(farmer=(4, 4), tiles=tiles, money=10_000.0, unlocked_quadrants=["NW"])
    action = module.agent(obs, V9_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])


def test_does_not_buy_cow_when_at_owned_cap_via_shed():
    module = load_agent_module("task_teacher_v9")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "PASTURE"}
    obs = make_obs(
        farmer=(4, 4),
        tiles=tiles,
        money=10_000.0,
        shed={"COW": module.MAX_COWS},
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V9_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])


def test_buys_cow_and_queues_pasture_when_under_cap_and_no_empty_pasture():
    module = load_agent_module("task_teacher_v9")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(
        day=11,
        farmer=(4, 4),
        tiles=tiles,
        money=10_000.0,
        shed={},
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V9_CONFIG)
    assert ["BUY_ANIMAL", "COW", 1] in action["market"]
    unit_actions = [action["farmer"]] + list(action["hands"])
    assert any(a[0] in ("BUILD_PASTURE", "NORTH", "SOUTH", "EAST", "WEST") for a in unit_actions)


def test_direct_wheat_buy_when_feed_is_low():
    module = load_agent_module("task_teacher_v9")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    # 1 placed cow
    tiles[1][1] = {
        "kind": "PASTURE",
        "animal": "COW",
        "placed_day": 0,
        "yield_units": 0,
        "consecutive_unfed": 0,
        "fed_today": False,
        "cared_today": False,
        "fertilizer_available": False,
        "pending_care_bonus": 0,
    }
    
    # total wheat in inventories + shed = 0, owned_cows = 1
    obs = make_obs(
        farmer=(4, 4),
        tiles=tiles,
        money=1000.0,
        shed={},
        farmer_inventory={},
        unlocked_quadrants=["NW", "NE"],
        prices={"WHEAT": 25.0},
    )
    action = module.agent(obs, V9_CONFIG)
    # target_wheat = 1 * 2 = 2. Total is 0, so we buy 2.
    assert ["BUY_PRODUCT", "WHEAT", 2] in action["market"]


def test_simulator_full_episode_two_seats_done_and_finite():
    module = load_agent_module("task_teacher_v9")
    env = make("kaggriculture", configuration={"episodeSteps": 240}, debug=True)
    env.run([module.agent, module.agent])
    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final)
    assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
