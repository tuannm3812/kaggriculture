"""Behavior tests for agents/*/main.py decision logic.

Calls each agent's `agent(obs[, config])` directly against hand-built
observation dicts, rather than running a full episode — isolates the
decision logic itself from environment-simulation correctness (already
covered by tests/test_economy.py) and from tournament-level integration
(tests/test_tournament.py). Added per Codex's 2026-08-01 code review (see
the design doc): the only tests before this covered economy.py, not agent
behavior itself.
"""

from kaggriculture_lib import economy

from conftest import load_agent_module

BOARD_SIZE = 10
FARMER_POS = (4, 4)  # a shed-access tile for board_size=10, per kaggriculture.py

V1, V2, V3 = "roi_teacher_v1", "roi_teacher_v2", "roi_teacher_v3"
ALL_VERSIONS = (V1, V2, V3)
MULTI_CROP_VERSIONS = (V2, V3)  # versions with MELON in CANDIDATE_CROPS

BASE_PRICES = {item: p["base"] for item, p in economy.MARKET_PARAMS.items()}


def make_obs(*, day=0, money=2000.0, tile=None, farmer_inventory=None, shed=None, seeds=None, prices=None):
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    fx, fy = FARMER_POS
    tiles[fy][fx] = tile
    opponent_tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    farm_template = {
        "tiles": None,
        "farmer": [fx, fy],
        "hands": [],
        "unlocked_quadrants": ["NW"],
        "hires_today": 0,
    }
    me = {**farm_template, "money": money, "tiles": tiles}
    opponent = {**farm_template, "money": 3000.0, "tiles": opponent_tiles}
    return {
        "player": 0,
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


def make_plant_tile(crop, planted_day, watered_today):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": planted_day,
        "watered_today": watered_today,
        "consecutive_unwatered": 0,
        "yield_units": 1,
        "max_lifespan_step": -1,
        "fertilized_until_day": -1,
    }


def run_agent(module, obs, config=None):
    """Call agent(obs) or agent(obs, config) depending on the module's arity,
    mirroring kaggle_environments/agent.py's own truncate-by-argcount call."""
    argcount = module.agent.__code__.co_argcount
    args = [obs, config][:argcount]
    return module.agent(*args)


def test_shed_contents_queue_matching_sell_orders():
    module = load_agent_module(V1)
    obs = make_obs(shed={"WHEAT": 3, "CARROT": 0})
    action = run_agent(module, obs)
    assert ["SELL", "WHEAT", 3] in action["market"]
    assert not any(order[1] == "CARROT" for order in action["market"] if order[0] == "SELL")


def test_weed_tile_digs():
    module = load_agent_module(V1)
    obs = make_obs(tile={"kind": "WEED"})
    action = run_agent(module, obs)
    assert action["farmer"] == ["DIG"]


def test_plant_not_watered_waters_before_harvesting():
    """Even on a day the crop could legally be harvested, watering must
    happen first (it's what accrues that day's bonus yield)."""
    module = load_agent_module(V1)
    tile = make_plant_tile("CARROT", planted_day=0, watered_today=False)
    obs = make_obs(day=economy.CROPS["CARROT"]["max_yield_day"], tile=tile)
    action = run_agent(module, obs)
    assert action["farmer"] == ["WATER"]


def test_plant_watered_and_mature_harvests():
    module = load_agent_module(V1)
    tile = make_plant_tile("CARROT", planted_day=0, watered_today=True)
    obs = make_obs(day=economy.CROPS["CARROT"]["max_yield_day"], tile=tile)
    action = run_agent(module, obs)
    assert action["farmer"] == ["HARVEST"]


def test_plant_watered_but_not_yet_mature_passes():
    module = load_agent_module(V1)
    tile = make_plant_tile("CARROT", planted_day=0, watered_today=True)
    obs = make_obs(day=economy.CROPS["CARROT"]["max_yield_day"] - 1, tile=tile)
    action = run_agent(module, obs)
    assert action["farmer"] == ["PASS"]


def test_farmer_inventory_triggers_drop_before_replanting():
    module = load_agent_module(V1)
    obs = make_obs(tile=None, farmer_inventory={"CARROT": 2}, seeds={"WHEAT": 1}, money=2000)
    action = run_agent(module, obs)
    assert action["farmer"] == ["DROP"]


def test_insufficient_money_skips_seed_purchase():
    module = load_agent_module(V1)
    cheapest_seed_cost = min(economy.CROPS[c]["seed"] for c in module.CANDIDATE_CROPS)
    obs = make_obs(tile=None, money=cheapest_seed_cost - 1, prices=BASE_PRICES)
    action = run_agent(module, obs)
    assert action["farmer"] == ["PASS"]
    assert not any(order[0] == "BUY_SEED" for order in action["market"])


def test_empty_tile_buys_best_scoring_crop_seed_at_base_prices():
    module = load_agent_module(V1)
    obs = make_obs(tile=None, money=2000, prices=BASE_PRICES)
    action = run_agent(module, obs)
    buy_orders = [o for o in action["market"] if o[0] == "BUY_SEED"]
    assert len(buy_orders) == 1
    assert buy_orders[0][1] == "CARROT"  # highest static ROI/day among WHEAT/CARROT at base price


def test_empty_tile_plants_directly_when_seed_already_held():
    module = load_agent_module(V1)
    obs = make_obs(tile=None, seeds={"CARROT": 1}, prices=BASE_PRICES)
    action = run_agent(module, obs)
    assert action["farmer"] == ["PLANT", "CARROT"]
    assert not any(o[0] == "BUY_SEED" for o in action["market"])


def test_v2_v3_prefer_melon_at_base_prices():
    for version in MULTI_CROP_VERSIONS:
        module = load_agent_module(version)
        obs = make_obs(tile=None, money=2000, prices=BASE_PRICES)
        action = run_agent(module, obs)
        buy_orders = [o for o in action["market"] if o[0] == "BUY_SEED"]
        assert buy_orders == [["BUY_SEED", "MELON", 1]], version


# --- v3 season-horizon gate ---------------------------------------------

EPISODE_STEPS = 720
TURNS_PER_DAY = 24
LAST_DAY_INDEX = EPISODE_STEPS // TURNS_PER_DAY - 1  # 29 at defaults
V3_CONFIG = {"episodeSteps": EPISODE_STEPS, "turnsPerDay": TURNS_PER_DAY}


def test_v3_last_day_index_matches_default_config():
    module = load_agent_module(V3)
    assert module._last_day_index(V3_CONFIG) == LAST_DAY_INDEX


def test_v3_can_mature_in_time_boundary_per_crop():
    module = load_agent_module(V3)
    for crop in module.CANDIDATE_CROPS:
        max_yield_day = economy.CROPS[crop]["max_yield_day"]
        last_plantable_day = LAST_DAY_INDEX - max_yield_day
        assert module._can_mature_in_time(crop, last_plantable_day, LAST_DAY_INDEX)
        assert not module._can_mature_in_time(crop, last_plantable_day + 1, LAST_DAY_INDEX)


def _day_too_late_for_every_candidate(module) -> int:
    """One day past the *most lenient* candidate's last-plantable day — the
    shortest-maturity crop (smallest max_yield_day) gives the latest
    possible cutoff, so going one day past that guarantees every candidate
    is infeasible."""
    min_max_yield_day = min(economy.CROPS[c]["max_yield_day"] for c in module.CANDIDATE_CROPS)
    return LAST_DAY_INDEX - min_max_yield_day + 1


def test_v3_holds_instead_of_planting_when_no_crop_can_mature():
    module = load_agent_module(V3)
    too_late_day = _day_too_late_for_every_candidate(module)
    obs = make_obs(tile=None, day=too_late_day, money=2000, prices=BASE_PRICES)
    action = run_agent(module, obs, V3_CONFIG)
    assert action["farmer"] == ["PASS"]
    assert not any(o[0] == "BUY_SEED" for o in action["market"])


def test_v3_still_plants_a_short_maturity_crop_near_season_end():
    module = load_agent_module(V3)
    # Only CARROT (max_yield_day=3) can still mature; WHEAT/MELON cannot.
    day = LAST_DAY_INDEX - economy.CROPS["CARROT"]["max_yield_day"]
    assert day + economy.CROPS["WHEAT"]["max_yield_day"] > LAST_DAY_INDEX
    assert day + economy.CROPS["MELON"]["max_yield_day"] > LAST_DAY_INDEX
    obs = make_obs(tile=None, day=day, money=2000, prices=BASE_PRICES)
    action = run_agent(module, obs, V3_CONFIG)
    buy_orders = [o for o in action["market"] if o[0] == "BUY_SEED"]
    assert buy_orders == [["BUY_SEED", "CARROT", 1]]


def test_v1_v2_have_no_horizon_awareness_by_contrast():
    """Characterizes the bug Codex's review found: v1/v2 will still buy a
    seed even when it's too late in the season for it to ever mature."""
    for version in ALL_VERSIONS:
        if version == V3:
            continue
        module = load_agent_module(version)
        too_late_day = _day_too_late_for_every_candidate(module)
        obs = make_obs(tile=None, day=too_late_day, money=2000, prices=BASE_PRICES)
        action = run_agent(module, obs)
        assert any(o[0] == "BUY_SEED" for o in action["market"]), (
            f"{version} was expected to (still, bug-for-bug) buy a seed "
            "too late to mature — if this now fails, v1/v2 gained horizon "
            "awareness and this characterization test should be removed."
        )
