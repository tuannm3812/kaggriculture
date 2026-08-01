"""Behavior tests for agents/task_teacher_v2/main.py.

Extends tests/test_task_teacher_v1.py's synthetic-obs pattern to multiple
units (farmer + hands) and hiring. Per the approved design in
docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md.
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
V2_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


def make_obs(
    *,
    day=0,
    hour=0,
    money=3000.0,
    farmer=(4, 4),
    hands=None,
    hires_today=0,
    tiles=None,
    farmer_inventory=None,
    hand_inventories=None,
    shed=None,
    seeds=None,
    prices=None,
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
        "unlocked_quadrants": ["NW"],
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


def test_farmer_and_hand_get_distinct_tasks_not_duplicated():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = {"kind": "WEED"}  # at the farmer's position
    tiles[2][2] = {"kind": "WEED"}  # at the hand's position
    obs = make_obs(farmer=(4, 4), hands=[(2, 2)], tiles=tiles)
    action = module.agent(obs, V2_CONFIG)

    assert action["farmer"] == ["DIG"]
    assert len(action["hands"]) == 1
    assert action["hands"][0] == ["DIG"]


def test_hand_action_list_length_matches_hands_list():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(farmer=(4, 4), hands=[(1, 1), (8, 8)], tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    assert len(action["hands"]) == 2


def test_hires_when_service_load_is_overloaded():
    module = load_agent_module("task_teacher_v2")
    # Many unwatered plants -> heavy pending-water obligation, comfortably
    # early in the day (lots of remaining turns to justify hiring), no
    # hands yet, plenty of money.
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for i in range(20):
        x, y = i % BOARD_SIZE, i // BOARD_SIZE  # 20 tiles across rows 0-1
        tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    obs = make_obs(farmer=(4, 4), hands=[], hour=0, money=3000, tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    assert any(order[0] == "HIRE" for order in action["market"])


def test_does_not_hire_when_not_overloaded():
    module = load_agent_module("task_teacher_v2")
    # An all-empty farm is NOT a "nothing to do" scenario -- every empty
    # tile is a PLANT opportunity (25 of them), which genuinely can exceed
    # one farmer's capacity and justify hiring. For a truly empty task
    # list, use a day late enough that no candidate crop can mature (so no
    # PLANT tasks get generated at all -- see economy.can_mature_in_time).
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    obs = make_obs(farmer=(4, 4), hands=[], hour=0, money=3000, day=29, tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    assert not any(order[0] == "HIRE" for order in action["market"])


def test_at_most_one_hire_order_per_turn():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if (x, y) != (4, 4):
                tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=False)
    obs = make_obs(farmer=(4, 4), hands=[], hour=0, money=100000, tiles=tiles)
    action = module.agent(obs, V2_CONFIG)
    hire_orders = [order for order in action["market"] if order[0] == "HIRE"]
    assert len(hire_orders) <= 1


def test_hand_assignments_clear_on_day_boundary():
    module = load_agent_module("task_teacher_v2")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[2][2] = {"kind": "WEED"}
    obs_day0 = make_obs(farmer=(4, 4), hands=[(2, 2)], day=0, tiles=tiles)
    module.agent(obs_day0, V2_CONFIG)
    assert 1 in module._state.assignments

    # New day: hands vanish in the real game. No hands in this turn's obs.
    obs_day1 = make_obs(farmer=(4, 4), hands=[], day=1, tiles=tiles)
    module.agent(obs_day1, V2_CONFIG)
    assert 1 not in module._state.assignments


def test_simulator_full_episode_two_seats_done_and_finite():
    for agents in (["agents/task_teacher_v2/main.py", "starter"], ["starter", "agents/task_teacher_v2/main.py"]):
        env = make("kaggriculture", configuration={"episodeSteps": 240, "seed": 42}, debug=True)
        env.run(agents)
        final = env.steps[-1]
        assert all(s.status == "DONE" for s in final)
        assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
