"""Kaggriculture game economy: prices, yields, and derived ROI estimates.

Every formula here mirrors the environment's own implementation exactly
(installed at `kaggle_environments/envs/kaggriculture/kaggriculture.py`, see
`docs/2_environment_notes.md` for the version pin and line-range citations
per formula). This module exists so every agent version (heuristic, BC,
PPO) shares one tested source of truth instead of re-deriving the game math
independently — see `docs/0_coding_standards.md` §2.
"""

from __future__ import annotations

import math
from typing import Literal

ShapeFn = Literal["linear", "sq", "sqrt", "log", "log10"]

MARKET_I0 = 10_000
PRICE_FLOOR = 1

# Mirrors kaggriculture.py:40-50 (MARKET_PARAMS) verbatim.
MARKET_PARAMS: dict[str, dict] = {
    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",  "above_target": 0.20},
    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt", "above_target": 0.70},
    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt", "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 1.60},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",   "above_target": 3.60},
    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",  "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 1.60},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",   "above_target": 3.20},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

# Mirrors kaggriculture.py:11-17 (CROPS) verbatim.
CROPS: dict[str, dict] = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

# Mirrors kaggriculture.py:19-23 (ANIMALS) verbatim.
ANIMALS: dict[str, dict] = {
    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 400, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

# Mirrors kaggriculture.py:82-83 (LAND_ORDER / LAND_PRICES) verbatim.
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]

FARM_HAND_COST_MULT = 1


def _shape(func: ShapeFn, x: float) -> float:
    """Mirrors kaggriculture.py:53-60 (`_shape`)."""
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "log10":
        return math.log10(1.0 + x)
    return x


def market_price(item: str, inventory: float, params: dict | None = None) -> int:
    """Current sale price for `item` at the given market inventory level.

    Mirrors kaggriculture.py:177-191 (`market_price`) exactly:
    `price(inv) = base + sign*amp*f(|inv-I0|)`, floored at `PRICE_FLOOR` and
    rounded to the nearest int. `sign` is +1 (scarcity) below I0, -1 (glut)
    above it; `amp` is derived so that moving `T` units past `I0` shifts
    price by `target * base`.
    """
    p = (params or MARKET_PARAMS)[item]
    base, i0, t = p["base"], p["I0"], p["T"]
    if inventory < i0:
        f = p["below_func"]
        amp = p["below_target"] * base / _shape(f, t)
        price = base + amp * _shape(f, i0 - inventory)
    else:
        f = p["above_func"]
        amp = p["above_target"] * base / _shape(f, t)
        price = base - amp * _shape(f, inventory - i0)
    return max(PRICE_FLOOR, round(price))


def hire_cost(n_already_today: int, mult: int = FARM_HAND_COST_MULT) -> int:
    """Cost of the next hire today. Mirrors kaggriculture.py:658-667.

    `_fib(n)` is indexed so `_fib(0)=1, _fib(1)=1, _fib(2)=2, _fib(3)=3, ...`
    and resets to 0 at the start of each day (`farm["hires_today"]`).
    """
    a, b = 1, 1
    for _ in range(n_already_today):
        a, b = b, a + b
    return mult * a


def land_cost(n_unlocked_extra: int) -> int | None:
    """Cost of the next `BUY_LAND` order, or None if all land is unlocked.

    Mirrors kaggriculture.py:680-693 (`_do_buy_land`). `n_unlocked_extra` is
    the count of quadrants already bought beyond the always-unlocked NW.
    """
    if n_unlocked_extra >= len(LAND_ORDER):
        return None
    return LAND_PRICES[n_unlocked_extra]


def one_time_crop_watering_bonus_window(crop: str) -> tuple[int, int]:
    """Inclusive (start, end) age-in-days window where watering adds yield.

    Mirrors kaggriculture.py:373-386 (`WATER` handler): window starts at
    `(max_yield_day + 1) // 2` (== ceil(max_yield_day / 2)) through
    `max_yield_day` inclusive. Only meaningful for non-ongoing crops.
    """
    cd = CROPS[crop]
    if cd["ongoing"]:
        raise ValueError(f"{crop} is an ongoing-yield crop, not one-time")
    start = (cd["max_yield_day"] + 1) // 2
    return start, cd["max_yield_day"]


def ongoing_crop_production_days(crop: str) -> list[int]:
    """Days-since-planting (0-indexed) on which an ongoing crop ticks yield.

    Mirrors kaggriculture.py:738-771 (`_daily_refresh_plants`): production
    ticks when `(day_since_planting - first_yield_day) % interval == 0`,
    for up to `max_yield` ticks.
    """
    cd = CROPS[crop]
    if not cd["ongoing"]:
        raise ValueError(f"{crop} is a one-time-yield crop, not ongoing")
    days = []
    tick = 0
    day = cd["first_yield_day"]
    while tick < cd["max_yield"]:
        days.append(day)
        tick += 1
        day += cd["interval"]
    return days


def animal_production_days(animal: str) -> list[int]:
    """Days-since-placement (0-indexed) on which an animal ticks a base yield.

    Mirrors kaggriculture.py:774-802 (`_daily_refresh_animals`). Does not
    include CARE-bonus timing, which depends on per-day feed/care history
    rather than a fixed schedule.
    """
    a = ANIMALS[animal]
    days = []
    tick = 0
    day = a["first_yield_day"]
    while tick < a["max_held"]:
        days.append(day)
        tick += 1
        day += a["interval"]
    return days


def one_time_crop_static_yield_per_tile_day(crop: str, watered_in_window: bool = True) -> float:
    """Simple static estimate of average yield/tile/day over the crop's life.

    Not a substitute for simulating an actual play line — ignores fertilizer,
    weeds, and opportunity cost of the farmer's actions to water/harvest.
    Intended as a first-pass ranking signal for `docs/3_agent_strategy.md`,
    matching the design doc's Phase-1 "static $/tile/day tables" deliverable.
    """
    cd = CROPS[crop]
    base_units = 1  # tile always yields >= 1 unit on harvest (see kaggriculture.py:200-213)
    if watered_in_window:
        start, end = one_time_crop_watering_bonus_window(crop)
        bonus_days = end - start + 1
        base_units += bonus_days  # +1 unit per watered day in the bonus window
    base_units = min(base_units, cd["max_yield"])
    lifespan_days = cd["max_yield_day"] + 1  # decay begins one day after max_yield_day
    return base_units / lifespan_days
