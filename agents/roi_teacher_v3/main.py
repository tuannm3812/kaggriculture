"""Kaggriculture ROI-heuristic teacher agent, v3.

One-variable change from v2 (`agents/roi_teacher_v2`), per
docs/0_coding_standards.md §4: adds a season-horizon gate so the agent
never plants a crop that cannot fully mature before the episode ends.

Fixes a real gap Codex's code review found in v1/v2 (see the design doc's
2026-08-01 "Codex review of Claude's current implementation" entry):
neither version checked remaining season length before planting, so a
late-season Melon purchase could spend money that never converts back to
bank balance before the episode ends (unsold/unharvested assets don't
count at termination). `kaggle_environments` passes `(observation,
configuration)` and truncates to the agent function's actual arg count
(verified in `kaggle_environments/agent.py`), so accepting `config` here
gives the real `episodeSteps`/`turnsPerDay` rather than a hardcoded guess.

Still single farmer, single tile (the spawn tile — no movement), no hands,
no land purchases, no animals, no ongoing crops. See v1's docstring for
the full scope rationale; unchanged here.

Local testing only: imports `kaggriculture_lib.economy` assuming `src/` is
on `sys.path` (handled by `scripts/run_tournament.py`). Use
`scripts/package_agent.py` to generate a standalone submission artifact.
"""

from __future__ import annotations

from kaggriculture_lib import economy

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")

DEFAULT_EPISODE_STEPS = 720
DEFAULT_TURNS_PER_DAY = 24


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


def _last_day_index(config) -> int:
    """0-indexed final day of the season, from the real episode config."""
    episode_steps = config.get("episodeSteps", DEFAULT_EPISODE_STEPS) if config else DEFAULT_EPISODE_STEPS
    turns_per_day = config.get("turnsPerDay", DEFAULT_TURNS_PER_DAY) if config else DEFAULT_TURNS_PER_DAY
    season_days = episode_steps // turns_per_day
    return season_days - 1


def _can_mature_in_time(crop: str, current_day: int, last_day_index: int) -> bool:
    """True iff a crop planted today reaches `max_yield_day` age on or
    before the season's last day, leaving turns that day to harvest."""
    return current_day + economy.CROPS[crop]["max_yield_day"] <= last_day_index


def _feasible_crops(current_day: int, last_day_index: int) -> tuple[str, ...]:
    return tuple(c for c in CANDIDATE_CROPS if _can_mature_in_time(c, current_day, last_day_index))


def _best_crop(market_prices: dict[str, int], feasible: tuple[str, ...]) -> str | None:
    if not feasible:
        return None
    return max(
        feasible,
        key=lambda crop: _score_crop(crop, market_prices.get(crop, economy.CROPS[crop]["seed"])),
    )


def agent(obs, config=None):
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
            last_day_index = _last_day_index(config)
            feasible = _feasible_crops(day, last_day_index)
            crop = _best_crop(prices, feasible)
            if crop is not None:
                if private["seeds"].get(crop, 0) > 0:
                    farmer_action = ["PLANT", crop]
                elif me["money"] >= economy.CROPS[crop]["seed"]:
                    market_orders.append(["BUY_SEED", crop, 1])
            # else: no candidate crop can mature before season end — hold
            # (PASS), never spend on a seed that can't come back as money.

    return {"farmer": farmer_action, "hands": [], "market": market_orders}
