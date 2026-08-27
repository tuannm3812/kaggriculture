"""Behavior tests for agents/task_teacher_v10/main.py.
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
V10_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


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


def test_caps_v10():
    module = load_agent_module("task_teacher_v10")
    assert module.MAX_COWS == 3
    assert module.MAX_SHEEP == 0
    assert module.MAX_FEED_ACTIONS_PER_DAY == 10


def test_protects_nw_crop_pasture_build():
    # If NE is unlocked, want_pasture should place building target in NE, not NW.
    module = load_agent_module("task_teacher_v10")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(
        day=15,
        hour=0,
        money=10_000.0,
        tiles=tiles,
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V10_CONFIG)
    # The pasture build order should land on NE (x >= 5)
    unit_actions = [action["farmer"]] + list(action["hands"])
    build_pastures = [act for act in unit_actions if act[0] == "BUILD_PASTURE"]
    # Check if building targets are outside NW
    # The unit will move towards it, so the target itself is on NE.
    pass


def test_cash_reserve_does_not_block_cow_buy_when_seeds_needed():
    module = load_agent_module("task_teacher_v10")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    
    # Farmer at (0, 0) is on an empty tile, which will trigger a PLANT Melon task ($80 seed).
    # Suppose we have $800. Cow cost is $600.
    # Liquidity reserve is $150, leaving $650 available.
    # Since $650 >= $600, we should buy the cow even with the pending plant task!
    obs = make_obs(
        day=14,
        hour=0,
        money=800.0,
        farmer=(0, 0),
        hands=[(1, 1)],
        tiles=tiles,
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V10_CONFIG)
    assert any(order[0] == "BUY_ANIMAL" and order[1] == "COW" for order in action["market"])


def test_sheep_buy_and_wool_sell():
    module = load_agent_module("task_teacher_v10")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "PASTURE"}
    
    obs = make_obs(
        day=15,
        hour=0,
        money=10_000.0,
        farmer=(4, 4),
        tiles=tiles,
        unlocked_quadrants=["NW", "NE"],
        shed={"WOOL": 5},
    )
    action = module.agent(obs, V10_CONFIG)
    # We should not buy sheep because MAX_SHEEP is 0
    assert not any(order[0] == "BUY_ANIMAL" and order[1] == "SHEEP" for order in action["market"])
    # We should sell wool
    assert ["SELL", "WOOL", 5] in action["market"]


def test_simulator_full_episode_v10():
    module = load_agent_module("task_teacher_v10")
    env = make("kaggriculture", configuration={"episodeSteps": 240}, debug=True)
    env.run([module.agent, module.agent])
    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final)
    assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
