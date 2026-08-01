"""Validate src/kaggriculture_lib/economy.py against the real environment.

Per docs/0_coding_standards.md §2: every reimplemented formula must be
tested against calling the actual installed `kaggriculture.py`'s equivalent
function directly, not just against the README's prose description.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kaggriculture_lib import economy  # noqa: E402

real = pytest.importorskip(
    "kaggle_environments.envs.kaggriculture.kaggriculture",
    reason="kaggriculture env not installed locally (see docs/2_environment_notes.md)",
)

RESOURCES = list(economy.MARKET_PARAMS)


@pytest.mark.parametrize("item", RESOURCES)
def test_market_params_match_real_module(item):
    assert economy.MARKET_PARAMS[item] == real.MARKET_PARAMS[item]


@pytest.mark.parametrize("item", RESOURCES)
@pytest.mark.parametrize(
    "inventory_offset",
    [-2 * 400, -400, 0, 400, 2 * 400, 10 * 400],
    ids=["I0-2T'", "I0-T'", "I0", "I0+T'", "I0+2T'", "I0+10T'"],
)
def test_market_price_matches_real_module(item, inventory_offset):
    """Uses a shared offset (not each item's own T) to also exercise
    off-anchor points, not just each item's own T/2T sample."""
    inventory = max(0, economy.MARKET_I0 + inventory_offset)
    assert economy.market_price(item, inventory) == real.market_price(item, inventory)


# README's documented sample table (price at I0-T, I0+T, I0+2T per resource).
README_SAMPLE_PRICES = {
    "WHEAT": (45, 20, 19),
    "CARROT": (42, 10, 1),
    "TOMATO": (84, 24, 9),
    "STRAWBERRY": (204, 1, 1),
    "MELON": (300, 1, 1),
    "EGG": (70, 40, 39),
    "MILK": (256, 1, 1),
    "WOOL": (240, 1, 1),
    "FERTILIZER": (140, 60, 20),
}


@pytest.mark.parametrize("item", RESOURCES)
def test_market_price_matches_readme_sample_table(item):
    t = economy.MARKET_PARAMS[item]["T"]
    i0 = economy.MARKET_I0
    got = (
        economy.market_price(item, i0 - t),
        economy.market_price(item, i0 + t),
        economy.market_price(item, i0 + 2 * t),
    )
    assert got == README_SAMPLE_PRICES[item]


@pytest.mark.parametrize("n", range(8))
def test_hire_cost_matches_real_module(n):
    assert economy.hire_cost(n) == real._hire_cost(n)


@pytest.mark.parametrize("n_extra", [0, 1, 2, 3])
def test_land_cost_matches_real_module(n_extra):
    expected = real.LAND_PRICES[n_extra] if n_extra < len(real.LAND_ORDER) else None
    assert economy.land_cost(n_extra) == expected


@pytest.mark.parametrize("crop", ["WHEAT", "CARROT", "MELON"])
def test_one_time_watering_window_matches_max_yield_day_formula(crop):
    cd = real.CROPS[crop]
    expected_start = (cd["max_yield_day"] + 1) // 2
    start, end = economy.one_time_crop_watering_bonus_window(crop)
    assert (start, end) == (expected_start, cd["max_yield_day"])


def test_one_time_watering_window_rejects_ongoing_crop():
    with pytest.raises(ValueError):
        economy.one_time_crop_watering_bonus_window("TOMATO")


@pytest.mark.parametrize("crop", ["TOMATO", "STRAWBERRY"])
def test_ongoing_crop_production_days_matches_real_schedule(crop):
    cd = real.CROPS[crop]
    days = economy.ongoing_crop_production_days(crop)
    assert len(days) == cd["max_yield"]
    assert days[0] == cd["first_yield_day"]
    if len(days) > 1:
        assert days[1] - days[0] == cd["interval"]


def test_ongoing_crop_production_days_rejects_one_time_crop():
    with pytest.raises(ValueError):
        economy.ongoing_crop_production_days("WHEAT")


@pytest.mark.parametrize("animal", ["GOOSE", "COW", "SHEEP"])
def test_animal_production_days_matches_real_schedule(animal):
    a = real.ANIMALS[animal]
    days = economy.animal_production_days(animal)
    assert len(days) == a["max_held"]
    assert days[0] == a["first_yield_day"]
    if len(days) > 1:
        assert days[1] - days[0] == a["interval"]
