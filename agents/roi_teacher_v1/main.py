"""Kaggriculture ROI-heuristic teacher agent, v1.

Deliberately minimal, per docs/0_coding_standards.md §4's one-variable-at-a-
time discipline: single farmer, single tile (the spawn tile — no movement),
dynamically picks the better of WHEAT/CARROT by a static $/day ROI estimate,
always waters (never risks a weed), harvests once at `max_yield_day` to
capture the full watering-bonus window, and sells whatever has reached the
shed. No hands, no land purchases, no animals, no ongoing crops (tomato/
strawberry) — those are v2+ increments once this baseline has a local-
tournament and (per the design doc) a ladder result to compare against.

Purpose (per the design doc §4 and §9's RL discussion): (a) a working
ladder submission to start accumulating rating early, (b) the scripted
teacher for behavioral cloning, (c) a benchmark opponent for every later
agent version.

Local testing only: imports `kaggriculture_lib.economy` assuming `src/` is
on `sys.path` (handled by `scripts/run_tournament.py`). Actual Kaggle
submission needs a packaging step to inline this dependency into a single
file or bundle it in a `.tar.gz` — not yet built, tracked as an open item
in docs/4_agent_version_log.md before the first real submission.
"""

from __future__ import annotations

from kaggriculture_lib import economy

CANDIDATE_CROPS = ("WHEAT", "CARROT")


def _expected_total_units(crop: str) -> int:
    """Total harvestable units assuming watering every day in the bonus window."""
    cd = economy.CROPS[crop]
    start, end = economy.one_time_crop_watering_bonus_window(crop)
    bonus_days = end - start + 1
    return min(cd["max_yield"], 1 + bonus_days)


def _score_crop(crop: str, price: float) -> float:
    """Static $/day ROI estimate: (expected revenue - seed cost) / lifespan."""
    cd = economy.CROPS[crop]
    lifespan_days = cd["max_yield_day"] + 1
    revenue = _expected_total_units(crop) * price
    return (revenue - cd["seed"]) / lifespan_days


def _best_crop(market_prices: dict[str, int]) -> str:
    return max(
        CANDIDATE_CROPS,
        key=lambda crop: _score_crop(crop, market_prices.get(crop, economy.CROPS[crop]["seed"])),
    )


def agent(obs):
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    prices = obs["market"]["prices"]
    shed = private["shed"]
    farmer_inventory = private["inventories"][0] if private["inventories"] else {}

    fx, fy = me["farmer"]
    tile = me["tiles"][fy][fx]
    day = obs["day"]

    market_orders = [
        ["SELL", crop, shed[crop]] for crop in CANDIDATE_CROPS if shed.get(crop, 0) > 0
    ]

    farmer_action = ["PASS"]

    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        cd = economy.CROPS[tile["crop"]]
        if not tile["watered_today"]:
            farmer_action = ["WATER"]
        elif day - tile["planted_day"] >= cd["max_yield_day"]:
            farmer_action = ["HARVEST"]
    elif isinstance(tile, dict) and tile.get("kind") == "WEED":
        farmer_action = ["DIG"]
    elif tile is None:
        # Push any just-harvested produce to the shed before replanting —
        # the spawn tile is always shed-adjacent (kaggriculture.py's
        # `_default_spawn` picks a shed-access tile), so DROP always lands.
        if any(farmer_inventory.get(crop, 0) > 0 for crop in CANDIDATE_CROPS):
            farmer_action = ["DROP"]
        else:
            crop = _best_crop(prices)
            if private["seeds"].get(crop, 0) > 0:
                farmer_action = ["PLANT", crop]
            elif me["money"] >= economy.CROPS[crop]["seed"]:
                market_orders.append(["BUY_SEED", crop, 1])

    return {"farmer": farmer_action, "hands": [], "market": market_orders}
