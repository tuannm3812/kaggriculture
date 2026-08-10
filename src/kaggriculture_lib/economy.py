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

# Mirrors kaggle-environments==1.29.3's kaggriculture.py MARKET_PARAMS
# verbatim (pinned version — see requirements.txt and docs/2_environment_notes.md's
# version-gap comparison: newer releases like 1.32.2 have different
# above_target glut-sensitivity constants for premium goods).
MARKET_PARAMS: dict[str, dict] = {
    "WHEAT":      {"base":  25, "I0": MARKET_I0, "T": 400, "below_func": "sqrt",   "below_target": 0.80, "above_func": "log",  "above_target": 0.20},
    "CARROT":     {"base":  35, "I0": MARKET_I0, "T": 450, "below_func": "log",    "below_target": 0.20, "above_func": "sqrt", "above_target": 0.70},
    "TOMATO":     {"base":  60, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "sqrt", "above_target": 0.60},
    "STRAWBERRY": {"base": 120, "I0": MARKET_I0, "T": 100, "below_func": "sqrt",   "below_target": 0.70, "above_func": "linear", "above_target": 0.40},
    "MELON":      {"base": 250, "I0": MARKET_I0, "T": 300, "below_func": "log",    "below_target": 0.20, "above_func": "sq",   "above_target": 0.90},
    "EGG":        {"base":  50, "I0": MARKET_I0, "T": 332, "below_func": "linear", "below_target": 0.40, "above_func": "log",  "above_target": 0.20},
    "MILK":       {"base": 160, "I0": MARKET_I0, "T": 122, "below_func": "sqrt",   "below_target": 0.60, "above_func": "linear", "above_target": 0.40},
    "WOOL":       {"base": 200, "I0": MARKET_I0, "T": 105, "below_func": "log",    "below_target": 0.20, "above_func": "sq",   "above_target": 0.80},
    "FERTILIZER": {"base": 100, "I0": MARKET_I0, "T": 200, "below_func": "linear", "below_target": 0.40, "above_func": "linear", "above_target": 0.40},
}

# Mirrors kaggle-environments==1.29.3's kaggriculture.py CROPS verbatim.
CROPS: dict[str, dict] = {
    "WHEAT":      {"seed": 10, "first_yield_day": 2, "max_yield_day": 4, "interval": 0, "max_yield": 6, "ongoing": False},
    "CARROT":     {"seed": 20, "first_yield_day": 2, "max_yield_day": 3, "interval": 0, "max_yield": 4, "ongoing": False},
    "TOMATO":     {"seed": 50, "first_yield_day": 8, "max_yield_day": 8, "interval": 1, "max_yield": 4, "ongoing": True},
    "STRAWBERRY": {"seed": 100, "first_yield_day": 10, "max_yield_day": 10, "interval": 2, "max_yield": 4, "ongoing": True},
    "MELON":      {"seed": 80, "first_yield_day": 10, "max_yield_day": 12, "interval": 0, "max_yield": 6, "ongoing": False},
}

# Mirrors kaggle-environments==1.29.3's kaggriculture.py ANIMALS verbatim.
# Note COW cost is 600 here vs. 400 in 1.32.2 — confirmed via direct diff,
# not a transcription assumption.
ANIMALS: dict[str, dict] = {
    "GOOSE": {"cost": 300, "structure": "COOP", "first_yield_day": 4, "interval": 1, "max_held": 4, "product": "EGG"},
    "COW":   {"cost": 600, "structure": "PASTURE", "first_yield_day": 8, "interval": 2, "max_held": 6, "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "first_yield_day": 6, "interval": 3, "max_held": 6, "product": "WOOL"},
}

# Mirrors kaggle-environments==1.29.3's kaggriculture.py LAND_ORDER / LAND_PRICES verbatim.
LAND_ORDER = ["NE", "SW", "SE"]
LAND_PRICES = [1000, 2000, 4000]

# 1.29.3's default; confirmed 10x more expensive than 1.32.2's default of 1.
FARM_HAND_COST_MULT = 10


def _shape(func: ShapeFn, x: float) -> float:
    """Mirrors kaggle-environments==1.29.3's kaggriculture.py:51-60 (`_shape`)."""
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

    Mirrors kaggle-environments==1.29.3's kaggriculture.py:175-191 (`market_price`) exactly:
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
    """Cost of the next hire today. Mirrors kaggle-environments==1.29.3's
    kaggriculture.py:651-662 (`_fib`, `_hire_cost`).

    `_fib(n)` is indexed so `_fib(0)=1, _fib(1)=1, _fib(2)=2, _fib(3)=3, ...`
    and resets to 0 at the start of each day (`farm["hires_today"]`).
    """
    a, b = 1, 1
    for _ in range(n_already_today):
        a, b = b, a + b
    return mult * a


def land_cost(n_unlocked_extra: int) -> int | None:
    """Cost of the next `BUY_LAND` order, or None if all land is unlocked.

    Mirrors kaggle-environments==1.29.3's kaggriculture.py:673-688
    (`_do_buy_land`). `n_unlocked_extra` is
    the count of quadrants already bought beyond the always-unlocked NW.
    """
    if n_unlocked_extra >= len(LAND_ORDER):
        return None
    return LAND_PRICES[n_unlocked_extra]


def shed_access_tiles(board_size: int) -> list[tuple[int, int]]:
    """Four inner-corner tiles around the shed, NWSE order.

    Mirrors kaggle-environments==1.29.3's kaggriculture.py `_shed_access_tiles`.
    """
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


def one_time_crop_watering_bonus_window(crop: str) -> tuple[int, int]:
    """Inclusive (start, end) age-in-days window where watering adds yield.

    Mirrors kaggle-environments==1.29.3's kaggriculture.py:368-382
    (`WATER` handler): window starts at
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

    Mirrors kaggle-environments==1.29.3's kaggriculture.py:731-766
    (`_daily_refresh_plants`): production
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

    Mirrors kaggle-environments==1.29.3's kaggriculture.py:767-797
    (`_daily_refresh_animals`). Does not
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


DEFAULT_EPISODE_STEPS = 720
DEFAULT_TURNS_PER_DAY = 24


def last_day_index(config: dict | None) -> int:
    """0-indexed final day of the season, from the real episode config.

    Promoted from `agents/roi_teacher_v3/main.py`'s `_last_day_index` (see
    the approved `task_teacher_v1` design in
    docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md):
    every agent version that reasons about remaining season length needs
    the identical calculation, not a per-agent reimplementation.
    """
    episode_steps = config.get("episodeSteps", DEFAULT_EPISODE_STEPS) if config else DEFAULT_EPISODE_STEPS
    turns_per_day = config.get("turnsPerDay", DEFAULT_TURNS_PER_DAY) if config else DEFAULT_TURNS_PER_DAY
    season_days = episode_steps // turns_per_day
    return season_days - 1


def can_mature_in_time(crop: str, current_day: int, last_day: int) -> bool:
    """True iff a one-time crop planted today reaches `max_yield_day` age on
    or before the season's last day, leaving turns that day to harvest.

    Promoted from `agents/roi_teacher_v3/main.py`'s `_can_mature_in_time`.
    """
    return current_day + CROPS[crop]["max_yield_day"] <= last_day


def can_ongoing_crop_reach_any_tick(crop: str, current_day: int, last_day: int) -> bool:
    """True iff an ongoing crop planted today reaches at least one
    production tick on or before the season's last day.

    Generalizes `can_mature_in_time` (a single-maturity-day check) to a
    crop whose value accrues over a multi-tick schedule instead of one
    event -- see `ongoing_crop_production_days`.
    """
    if not CROPS[crop]["ongoing"]:
        raise ValueError(f"{crop} is a one-time-yield crop, not ongoing")
    return any(current_day + offset <= last_day for offset in ongoing_crop_production_days(crop))


def wheat_reserved_for_feed(geese_count: int, days_horizon: int) -> int:
    """Wheat units to keep (not sell) so geese can be fed for `days_horizon` days."""
    if geese_count <= 0 or days_horizon <= 0:
        return 0
    return geese_count * days_horizon


def one_time_crop_static_yield_per_tile_day(crop: str, watered_in_window: bool = True) -> float:
    """Simple static estimate of average yield/tile/day over the crop's life.

    Not a substitute for simulating an actual play line — ignores fertilizer,
    weeds, and opportunity cost of the farmer's actions to water/harvest.
    Intended as a first-pass ranking signal for `docs/3_agent_strategy.md`,
    matching the design doc's Phase-1 "static $/tile/day tables" deliverable.
    """
    cd = CROPS[crop]
    base_units = 1  # tile always yields >= 1 unit on harvest (see 1.29.3's kaggriculture.py:198-211, `_new_plant`)
    if watered_in_window:
        start, end = one_time_crop_watering_bonus_window(crop)
        bonus_days = end - start + 1
        base_units += bonus_days  # +1 unit per watered day in the bonus window
    base_units = min(base_units, cd["max_yield"])
    lifespan_days = cd["max_yield_day"] + 1  # decay begins one day after max_yield_day
    return base_units / lifespan_days
