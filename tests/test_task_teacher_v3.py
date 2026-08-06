"""Behavior tests for agents/task_teacher_v3/main.py.

Extends tests/test_task_teacher_v2.py's synthetic-obs pattern with ongoing
crops (Tomato, Strawberry). Per the approved design in
docs/superpowers/specs/2026-08-02-task-teacher-v3-design.md. Only tests
what's new or different about v3 -- hiring, multi-unit assignment, and
day-boundary behavior are unchanged from v2 (same shared tasking.py
functions) and already covered by tests/test_task_teacher_v2.py.
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
V3_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


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
        "money": 2000.0,
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


def make_ongoing_plant_tile(crop, planted_day, watered_today, yield_units):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "watered_today": watered_today,
        "consecutive_unwatered": 0,
        "yield_units": yield_units,
        "max_lifespan_step": -1,
        "fertilized_until_day": -1,
    }


def test_candidate_crops_include_ongoing_crops():
    module = load_agent_module("task_teacher_v3")
    assert "TOMATO" in module.CANDIDATE_CROPS
    assert "STRAWBERRY" in module.CANDIDATE_CROPS
    # One-time crops are still there too -- v3 extends v2, doesn't replace it.
    assert "WHEAT" in module.CANDIDATE_CROPS
    assert "CARROT" in module.CANDIDATE_CROPS
    assert "MELON" in module.CANDIDATE_CROPS


def test_plants_ongoing_crop_on_empty_tile_at_base_prices():
    module = load_agent_module("task_teacher_v3")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    realistic_prices = {"WHEAT": 25, "CARROT": 35, "MELON": 250, "TOMATO": 60, "STRAWBERRY": 120}
    obs = make_obs(farmer=(4, 4), tiles=tiles, prices=realistic_prices, day=0)
    action = module.agent(obs, V3_CONFIG)
    # Farmer is standing on an empty tile with no seed held -- expect a
    # BUY_SEED order queued for whichever crop scored highest that day
    # (day-aware scoring; the specific winner is an economy.py concern
    # already tested in tests/test_tasking.py, not re-derived here).
    buy_orders = [o for o in action["market"] if o[0] == "BUY_SEED"]
    assert len(buy_orders) == 1


def test_harvests_ongoing_crop_repeatedly_without_the_tile_ever_clearing():
    """The core behavioral difference from one-time crops: harvesting an
    ongoing crop must not remove it from the farm, and the same tile must
    generate a fresh HARVEST task once yield reaccumulates."""
    module = load_agent_module("task_teacher_v3")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_ongoing_plant_tile("TOMATO", planted_day=0, watered_today=True, yield_units=1)
    obs = make_obs(farmer=(4, 4), tiles=tiles, day=8)
    action = module.agent(obs, V3_CONFIG)
    assert action["farmer"] == ["HARVEST"]

    # Simulate the environment's own post-harvest state: yield_units reset
    # to 0, tile still present (kind stays PLANT -- this is the real
    # environment's behavior for ongoing crops, verified against
    # kaggriculture.py's HARVEST handler in the design doc §2).
    tiles[4][4] = make_ongoing_plant_tile("TOMATO", planted_day=0, watered_today=True, yield_units=0)
    obs_after_harvest = make_obs(farmer=(4, 4), tiles=tiles, day=8, hour=1)
    action_after = module.agent(obs_after_harvest, V3_CONFIG)
    # Nothing to harvest yet -- watered already, no yield, so no HARVEST
    # task exists for this tile; farmer should not be stuck harvesting air.
    assert action_after["farmer"] != ["HARVEST"]

    # A later day, once a fresh tick has landed (yield_units > 0 again):
    tiles[4][4] = make_ongoing_plant_tile("TOMATO", planted_day=0, watered_today=True, yield_units=1)
    obs_next_tick = make_obs(farmer=(4, 4), tiles=tiles, day=9)
    action_next_tick = module.agent(obs_next_tick, V3_CONFIG)
    assert action_next_tick["farmer"] == ["HARVEST"]


def test_waters_ongoing_crop_tile_even_though_no_yield_bonus_applies():
    module = load_agent_module("task_teacher_v3")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_ongoing_plant_tile("TOMATO", planted_day=0, watered_today=False, yield_units=0)
    obs = make_obs(farmer=(4, 4), tiles=tiles, day=1)
    action = module.agent(obs, V3_CONFIG)
    assert action["farmer"] == ["WATER"]


def test_simulator_full_episode_two_seats_done_and_finite():
    for agents in (["agents/task_teacher_v3/main.py", "starter"], ["starter", "agents/task_teacher_v3/main.py"]):
        env = make("kaggriculture", configuration={"episodeSteps": 240, "seed": 42}, debug=True)
        env.run(agents)
        final = env.steps[-1]
        assert all(s.status == "DONE" for s in final)
        assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
