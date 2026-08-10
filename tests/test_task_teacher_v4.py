"""Behavior tests for agents/task_teacher_v4/main.py.

Extends tests/test_task_teacher_v2.py's synthetic-obs pattern with land
purchase (NE) and the Goose loop (BUILD_COOP / BUY_ANIMAL / PICKUP / PLACE
/ FEED / CARE). Per the approved design in
docs/superpowers/specs/2026-08-10-task-teacher-v4-design.md. Only tests
what's new or different about v4 -- hiring, multi-unit assignment, and
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
from kaggriculture_lib import economy  # noqa: E402

BOARD_SIZE = 10
V4_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


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


def make_goose_tile(fed_today, cared_today=False, yield_units=0, consecutive_unfed=0, placed_day=0):
    return {
        "kind": "COOP",
        "animal": "GOOSE",
        "placed_day": placed_day,
        "yield_units": yield_units,
        "consecutive_unfed": consecutive_unfed,
        "fed_today": fed_today,
        "cared_today": cared_today,
        "fertilizer_available": False,
        "pending_care_bonus": 0,
    }


def test_candidate_crops_match_v2():
    module = load_agent_module("task_teacher_v4")
    assert module.CANDIDATE_CROPS == ("WHEAT", "CARROT", "MELON")


def test_max_geese_is_two():
    module = load_agent_module("task_teacher_v4")
    assert module.MAX_GEESE == 2


def test_goose_cost_matches_economy():
    module = load_agent_module("task_teacher_v4")
    assert module.GOOSE_COST == economy.ANIMALS["GOOSE"]["cost"] == 300


def test_emits_buy_land_when_gate_would_pass():
    """Construct an obs that satisfies every should_buy_land clause: NW
    only, comfortably affordable, 3 hands (>= MIN_HANDS_BEFORE_LAND), 25
    saturated (already-growing, already-watered, not-yet-harvestable)
    plant tiles (>= NW_SATURATION_PLANTS=18, and hire has zero value since
    3 hands' worth of capacity already covers the tiny remaining load),
    and 14 days left in the season (>= LAND_MIN_DAYS_REMAINING=12)."""
    module = load_agent_module("task_teacher_v4")
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
    action = module.agent(obs, V4_CONFIG)
    assert ["BUY_LAND"] in action["market"]


def test_does_not_emit_buy_land_when_ne_already_owned():
    module = load_agent_module("task_teacher_v4")
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
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V4_CONFIG)
    assert ["BUY_LAND"] not in action["market"]


def test_acts_on_ne_tile_when_ne_unlocked():
    """Agent must act on NE once unlocked (design §7.4 / branch-review gap)."""
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    # Saturate NW with already-watered plants so they emit no WATER/HARVEST.
    for y in range(5):
        for x in range(5):
            tiles[y][x] = make_plant_tile("WHEAT", planted_day=0, watered_today=True, consecutive_unwatered=0)
    tiles[2][6] = make_plant_tile("WHEAT", planted_day=0, watered_today=False, consecutive_unwatered=1)
    obs = make_obs(
        day=1,
        hour=0,
        money=500,
        farmer=(6, 2),
        tiles=tiles,
        unlocked_quadrants=["NW", "NE"],
    )
    action = module.agent(obs, V4_CONFIG)
    assert action["farmer"] == ["WATER"]


def test_feeds_unfed_goose_when_wheat_in_inventory():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_goose_tile(fed_today=False)
    obs = make_obs(farmer=(4, 4), tiles=tiles, farmer_inventory={"WHEAT": 5})
    action = module.agent(obs, V4_CONFIG)
    assert action["farmer"] == ["FEED"]


def test_does_not_feed_already_fed_goose():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_goose_tile(fed_today=True)
    obs = make_obs(farmer=(4, 4), tiles=tiles, farmer_inventory={"WHEAT": 5})
    action = module.agent(obs, V4_CONFIG)
    assert action["farmer"] != ["FEED"]


def test_picks_up_goose_from_shed_when_empty_coop_exists():
    """Farmer stands on the one unlocked (NW) shed-access tile with an
    empty COOP elsewhere and a Goose sitting in the shed -- no Goose in
    any inventory yet, so PICKUP must run before PLACE can ever succeed.
    The farmer's own tile is pre-seeded with an already-growing, already-
    watered plant so it doesn't also compete as a same-distance PLANT
    task target."""
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_plant_tile("WHEAT", planted_day=10, watered_today=True, consecutive_unwatered=0)
    tiles[1][1] = {"kind": "COOP"}
    obs = make_obs(farmer=(4, 4), tiles=tiles, shed={"GOOSE": 1}, day=10)
    action = module.agent(obs, V4_CONFIG)
    assert action["farmer"] == ["PICKUP", "GOOSE", 1]


def test_places_goose_when_already_in_inventory_and_on_empty_coop():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = {"kind": "COOP"}
    obs = make_obs(farmer=(4, 4), tiles=tiles, farmer_inventory={"GOOSE": 1})
    action = module.agent(obs, V4_CONFIG)
    assert action["farmer"] == ["PLACE", "GOOSE"]


def test_builds_coop_when_no_coop_exists_and_geese_under_cap():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    # Shed-access tiles are the preferred BUILD_COOP target (keeps future
    # PICKUP/PLACE close) -- farmer starts there by default in make_obs.
    obs = make_obs(farmer=(4, 4), tiles=tiles)
    action = module.agent(obs, V4_CONFIG)
    assert action["farmer"] == ["BUILD_COOP"]


def test_buys_goose_when_empty_coop_exists_and_affordable():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "COOP"}
    obs = make_obs(farmer=(4, 4), tiles=tiles, money=10_000.0)
    action = module.agent(obs, V4_CONFIG)
    assert ["BUY_ANIMAL", "GOOSE", 1] in action["market"]


def test_does_not_buy_goose_when_already_at_max_geese():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_goose_tile(fed_today=True)
    tiles[5][5] = make_goose_tile(fed_today=True)
    tiles[1][1] = {"kind": "COOP"}
    obs = make_obs(farmer=(4, 4), tiles=tiles, money=10_000.0)
    action = module.agent(obs, V4_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])


def test_does_not_buy_goose_when_shed_already_holds_max_geese():
    """BUY_ANIMAL deposits into the shed, so shed stock must count toward
    MAX_GEESE — otherwise the agent re-buys every turn (Task 9 failure mode)."""
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "COOP"}
    obs = make_obs(
        farmer=(4, 4),
        tiles=tiles,
        money=10_000.0,
        shed={"GOOSE": module.MAX_GEESE},
    )
    action = module.agent(obs, V4_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])


def test_does_not_buy_goose_when_placed_plus_shed_reach_max():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_goose_tile(fed_today=True)
    tiles[1][1] = {"kind": "COOP"}
    obs = make_obs(
        farmer=(4, 4),
        tiles=tiles,
        money=10_000.0,
        shed={"GOOSE": module.MAX_GEESE - 1},
    )
    action = module.agent(obs, V4_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])


def test_does_not_buy_goose_when_inventory_fills_remaining_cap():
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_goose_tile(fed_today=True)
    tiles[1][1] = {"kind": "COOP"}
    obs = make_obs(
        farmer=(4, 4),
        tiles=tiles,
        money=10_000.0,
        farmer_inventory={"GOOSE": module.MAX_GEESE - 1},
    )
    action = module.agent(obs, V4_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])


def test_sells_eggs_from_shed():
    module = load_agent_module("task_teacher_v4")
    obs = make_obs(farmer=(4, 4), shed={"EGG": 7})
    action = module.agent(obs, V4_CONFIG)
    assert ["SELL", "EGG", 7] in action["market"]


def test_wheat_sell_respects_feed_reserve():
    """One goose held, 20 days left in the season -> reserve = 1 * 20 =
    20 wheat kept back; only the surplus above that is sold."""
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_goose_tile(fed_today=True)
    day = 9
    obs = make_obs(farmer=(4, 4), tiles=tiles, shed={"WHEAT": 50}, day=day)
    action = module.agent(obs, V4_CONFIG)
    last_day = economy.last_day_index(V4_CONFIG)
    reserve = economy.wheat_reserved_for_feed(1, max(1, last_day - day))
    expected_sellable = 50 - reserve
    sell_orders = [o for o in action["market"] if o[0] == "SELL" and o[1] == "WHEAT"]
    assert len(sell_orders) == 1
    assert sell_orders[0][2] == expected_sellable
    assert expected_sellable < 50


def test_does_not_sell_wheat_below_feed_reserve():
    """All held wheat is within the feed reserve -> no WHEAT SELL order at
    all (matches the `max(0, ...)` floor, not a negative sell quantity)."""
    module = load_agent_module("task_teacher_v4")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[4][4] = make_goose_tile(fed_today=True)
    obs = make_obs(farmer=(4, 4), tiles=tiles, shed={"WHEAT": 2}, day=0)
    action = module.agent(obs, V4_CONFIG)
    sell_orders = [o for o in action["market"] if o[0] == "SELL" and o[1] == "WHEAT"]
    assert sell_orders == []


def test_simulator_full_episode_two_seats_done_and_finite():
    for agents in (["agents/task_teacher_v4/main.py", "starter"], ["starter", "agents/task_teacher_v4/main.py"]):
        env = make("kaggriculture", configuration={"episodeSteps": 240, "seed": 42}, debug=True)
        env.run(agents)
        final = env.steps[-1]
        assert all(s.status == "DONE" for s in final)
        assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
