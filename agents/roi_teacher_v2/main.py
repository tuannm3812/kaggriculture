"""Kaggriculture ROI-heuristic teacher agent, v2.

One-variable change from v1 (`agents/roi_teacher_v1`), per
docs/0_coding_standards.md §4: adds MELON to the dynamic crop-selection
candidates. docs/3_agent_strategy.md's static ROI table found Melon's
$/day at base price (~109) is 5-6x wheat/carrot's (~18-21) — the highest-
value lever identified after v1's local-tournament result, ahead of
multi-tile pathing (a separate, larger change evaluated on its own).

Still single farmer, single tile (the spawn tile — no movement), no hands,
no land purchases, no animals, no ongoing crops. See v1's docstring for the
full rationale for that scope; unchanged here.

Local testing only: imports `kaggriculture_lib.economy` assuming `src/` is
on `sys.path` (handled by `scripts/run_tournament.py`). Use
`scripts/package_agent.py` to generate a standalone submission artifact.
"""

from __future__ import annotations

from kaggriculture_lib import economy

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")


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
