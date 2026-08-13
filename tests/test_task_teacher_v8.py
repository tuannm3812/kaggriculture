"""Behavior tests for agents/task_teacher_v8/main.py.

Hire parity + gated SW land. Per
docs/superpowers/specs/2026-08-13-task-teacher-v8-design.md.
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
V8_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "farmHandCostMult": 1}


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


def _fill_plants(n, day):
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    count = 0
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if count >= n:
                return tiles
            tiles[y][x] = make_plant_tile("MELON", planted_day=day, watered_today=True)
            count += 1
    return tiles


def test_caps():
    module = load_agent_module("task_teacher_v8")
    assert module.MAX_GEESE == 0
    assert module.MAX_EXTRA_QUADRANTS == 2
    assert module.SW_BUDGET_RESERVE_V8 == 3000
    assert module.MAX_HANDS == 8
    assert module.HIRE_DECISION_MULT == 10
    assert module.CANDIDATE_CROPS == ("WHEAT", "CARROT", "MELON")


def test_does_not_hire_at_max_hands():
    module = load_agent_module("task_teacher_v8")
    day = 5
    hands = [(i, i) for i in range(module.MAX_HANDS)]
    obs = make_obs(
        day=day,
        hour=0,
        money=1_000_000,
        farmer=(4, 4),
        hands=hands,
        tiles=_fill_plants(25, day),
    )
    # Huge pending water load via unwatered plants would otherwise hire.
    for y in range(5):
        for x in range(5):
            obs["farms"][0]["tiles"][y][x] = make_plant_tile(
                "MELON", planted_day=day, watered_today=False, consecutive_unwatered=1
            )
    action = module.agent(obs, V8_CONFIG)
    assert ["HIRE"] not in action["market"]


def test_emits_buy_land_ne_when_gate_would_pass():
    module = load_agent_module("task_teacher_v8")
    day = 15
    obs = make_obs(
        day=day,
        hour=0,
        money=1_000_000,
        farmer=(4, 4),
        hands=[(1, 1), (2, 2), (3, 3)],
        tiles=_fill_plants(25, day),
    )
    action = module.agent(obs, V8_CONFIG)
    assert ["BUY_LAND"] in action["market"]


def test_emits_buy_land_sw_when_ne_owned_and_cash_clears():
    module = load_agent_module("task_teacher_v8")
    day = 15
    obs = make_obs(
        day=day,
        hour=0,
        money=1_000_000,
        farmer=(4, 4),
        hands=[(1, 1), (2, 2), (3, 3)],
        tiles=_fill_plants(25, day),
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V8_CONFIG)
    assert ["BUY_LAND"] in action["market"]


def test_does_not_buy_sw_when_cash_only_clears_ne_bar():
    module = load_agent_module("task_teacher_v8")
    day = 15
    # Need 2000 + 3000 = 5000 after hire reserve; 3500 fails.
    obs = make_obs(
        day=day,
        hour=0,
        money=3500.0,
        farmer=(4, 4),
        hands=[(1, 1), (2, 2), (3, 3)],
        tiles=_fill_plants(25, day),
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V8_CONFIG)
    assert ["BUY_LAND"] not in action["market"]


def test_never_buys_fourth_quadrant_when_sw_already_owned():
    module = load_agent_module("task_teacher_v8")
    day = 15
    obs = make_obs(
        day=day,
        hour=0,
        money=1_000_000,
        farmer=(4, 4),
        hands=[(1, 1), (2, 2), (3, 3)],
        tiles=_fill_plants(40, day),
        unlocked_quadrants=["NW", "NE", "SW"],
    )
    action = module.agent(obs, V8_CONFIG)
    assert ["BUY_LAND"] not in action["market"]


def test_never_buys_animal():
    module = load_agent_module("task_teacher_v8")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "PASTURE"}
    obs = make_obs(
        farmer=(4, 4),
        tiles=tiles,
        money=10_000.0,
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V8_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])


def test_simulator_full_episode_two_seats_done_and_finite():
    module = load_agent_module("task_teacher_v8")
    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 240, "startingMoney": 3000, "farmHandCostMult": 1},
        debug=True,
    )
    env.run([module.agent, module.agent])
    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final)
    assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
