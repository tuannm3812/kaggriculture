"""Behavior tests for agents/task_teacher_v12/main.py.
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
# `farmHandCostMult` pinned explicitly rather than inherited from
# `economy.FARM_HAND_COST_MULT`, whose value changed 10 -> 1 on 2026-08-28
# when the library was corrected to the ladder's real 1.32.4 constants.
# These tests were written against the mult=10 (expensive-hiring) regime;
# note the live ladder actually runs mult=1, so the low-money "does not
# hire" assertions below describe this regime, not ladder behaviour.
V12_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "farmHandCostMult": 10}


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


def test_caps_v12():
    module = load_agent_module("task_teacher_v12")
    assert module.MAX_COWS == 8
    assert module.MAX_SHEEP == 4
    assert module.MAX_GEESE == 4
    assert module.MAX_FEED_ACTIONS_PER_DAY == 10


def test_goose_buy_and_egg_sell():
    module = load_agent_module("task_teacher_v12")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "COOP"}
    
    obs = make_obs(
        day=11,
        hour=0,
        money=2000.0,
        farmer=(4, 4),
        tiles=tiles,
        shed={"EGG": 5, "FERTILIZER": 10},
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V12_CONFIG)
    # Geese don't need unlocked quadrants, should buy one since money is high
    assert any(order[0] == "BUY_ANIMAL" and order[1] == "GOOSE" for order in action["market"])
    # Should sell eggs and fertilizer
    assert ["SELL", "EGG", 5] in action["market"]
    assert ["SELL", "FERTILIZER", 10] in action["market"]


def test_terminal_liquidation():
    module = load_agent_module("task_teacher_v12")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    
    obs = make_obs(
        day=29,
        hour=20,
        money=10_000.0,
        farmer=(4, 4),
        tiles=tiles,
        shed={"WHEAT": 10, "FERTILIZER": 5, "MILK": 3, "STRAWBERRY": 12},
    )
    action = module.agent(obs, V12_CONFIG)
    # Day 29 Hour 20 should trigger terminal liquidation: selling WHEAT even if animals exist
    assert ["SELL", "WHEAT", 10] in action["market"]
    assert ["SELL", "FERTILIZER", 5] in action["market"]
    assert ["SELL", "MILK", 3] in action["market"]
    assert ["SELL", "STRAWBERRY", 12] in action["market"]


def test_early_game_zero_hands_floor():
    module = load_agent_module("task_teacher_v12")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    
    obs = make_obs(
        day=5,
        hour=0,
        money=800.0,  # Below $1500, should keep hands_floor = 0
        farmer=(4, 4),
        tiles=tiles,
    )
    action = module.agent(obs, V12_CONFIG)
    # Should not queue HIRE since hands_floor is 0
    assert not any(order[0] == "HIRE" for order in action["market"])


def test_simulator_full_episode_v12():
    module = load_agent_module("task_teacher_v12")
    env = make("kaggriculture", configuration={"episodeSteps": 240}, debug=True)
    env.run([module.agent, module.agent])
    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final)
    assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
