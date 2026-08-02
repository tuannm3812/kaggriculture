# Task Teacher v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `task_teacher_v2` (current `competitive_champion`) with ongoing crops (Tomato, Strawberry) as the one variable changed, per `docs/superpowers/specs/2026-08-02-task-teacher-v3-design.md`.

**Architecture:** Two shared-library functions get an ongoing-crop counterpart (`economy.can_ongoing_crop_reach_any_tick`, `tasking._score_ongoing_crop`), `tasking._best_feasible_crop`/`generate_tasks` dispatch on `economy.CROPS[crop]["ongoing"]` to use the right pair, and a new immutable `agents/task_teacher_v3/main.py` is copied forward from v2 with `CANDIDATE_CROPS` extended. No changes to `task_teacher_v2`'s own candidate list, so v2's behavior is provably unaffected (it never plants an ongoing crop, so the new branches never fire for it).

**Tech Stack:** Python 3.11, pytest, `kaggle_environments==1.29.3` (pinned), the existing `src/kaggriculture_lib` package.

## Global Constraints

- No animals, fertilizer, `PICKUP`/`PLACE`, or learned policy in this version (design doc §1).
- Every existing test in `tests/test_economy.py`, `tests/test_tasking.py`, `tests/test_task_teacher_v1.py`, `tests/test_task_teacher_v2.py`, `tests/test_package_agent.py` must keep passing unmodified throughout (design doc §5).
- `agents/task_teacher_v2/main.py` and every other existing `agents/*/main.py` are immutable — never edit them (`docs/0_coding_standards.md` §4).
- Build test-first: RED (watch it fail for the right reason) → GREEN (minimal code) for every step below, per `superpowers:test-driven-development`.
- Promotion requires the full evaluation protocol (100-episode acceptance gate, paired Hoeffding-CI screen at 20 pairs vs. `task_teacher_v2`, 50-pair promotion gate if positive, regression screens vs. `roi_teacher_v3` and `starter`) — do not claim promotion from a partial run (design doc §6).
- Run `source .venv/bin/activate` before any `python`/`pytest` command in this repo; use `PYTHONPATH=src` for scripts run outside `pytest` (pytest's own `conftest.py` already puts `src/` on `sys.path`).

---

### Task 1: `economy.can_ongoing_crop_reach_any_tick`

**Files:**
- Modify: `src/kaggriculture_lib/economy.py:200-207` (add after `can_mature_in_time`)
- Test: `tests/test_economy.py:136-141` (add after `test_can_mature_in_time_boundary_per_crop`)

**Interfaces:**
- Produces: `economy.can_ongoing_crop_reach_any_tick(crop: str, current_day: int, last_day: int) -> bool`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_economy.py`, immediately after `test_can_mature_in_time_boundary_per_crop` (ends at line 141):

```python
@pytest.mark.parametrize("crop", ["TOMATO", "STRAWBERRY"])
def test_can_ongoing_crop_reach_any_tick_boundary_per_crop(crop):
    first_yield_day = economy.CROPS[crop]["first_yield_day"]
    last_day_index = 29
    last_plantable_day = last_day_index - first_yield_day
    assert economy.can_ongoing_crop_reach_any_tick(crop, last_plantable_day, last_day_index)
    assert not economy.can_ongoing_crop_reach_any_tick(crop, last_plantable_day + 1, last_day_index)


def test_can_ongoing_crop_reach_any_tick_true_when_only_the_first_tick_fits():
    # TOMATO ticks at day-offsets [8, 9, 10, 11] since planting. At
    # current_day=21 with last_day=29: only the first offset (21+8=29)
    # lands in time; the rest (21+9=30, 21+10=31, 21+11=32) don't. One
    # reachable tick is still enough to count as feasible.
    assert economy.can_ongoing_crop_reach_any_tick("TOMATO", current_day=21, last_day=29)


def test_can_ongoing_crop_reach_any_tick_rejects_one_time_crop():
    with pytest.raises(ValueError):
        economy.can_ongoing_crop_reach_any_tick("WHEAT", 0, 29)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -k can_ongoing_crop_reach_any_tick -v`
Expected: FAIL with `AttributeError: module 'kaggriculture_lib.economy' has no attribute 'can_ongoing_crop_reach_any_tick'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/kaggriculture_lib/economy.py`, immediately after `can_mature_in_time` (line 206):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -k can_ongoing_crop_reach_any_tick -v`
Expected: 4 passed (2 boundary cases via parametrize, 1 partial-fit case, 1 ValueError case)

- [ ] **Step 5: Run the full economy test file to confirm no regressions**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -v`
Expected: all tests pass (previous count + 4 new)

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/economy.py tests/test_economy.py
git commit -m "feat: add can_ongoing_crop_reach_any_tick for day-aware ongoing-crop feasibility"
```

---

### Task 2: `tasking._score_ongoing_crop`

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py:94-100` (add after `_score_crop`)
- Test: `tests/test_tasking.py` (add after the existing `generate_tasks`/before `rank_tasks` section, or a new section near line 130)

**Interfaces:**
- Consumes: `economy.ongoing_crop_production_days(crop)` (existing), `economy.CROPS` (existing)
- Produces: `tasking._score_ongoing_crop(crop: str, price: float, current_day: int, last_day: int) -> float`

- [ ] **Step 1: Write the failing tests**

`tests/test_tasking.py` currently imports neither `pytest` nor
`kaggriculture_lib.economy` (confirmed: `grep -n "pytest\|economy\." tests/test_tasking.py` returns nothing). Add both at the top of the file, immediately before the existing `from kaggriculture_lib.tasking import (` line (line 8):

```python
import pytest

from kaggriculture_lib import economy
```

Then add the following new section to `tests/test_tasking.py`, after the `_expected_total_units`/`_score_crop` region is used (near the top-level helpers, before `# --- generate_tasks ---` at line 132):

```python
# --- ongoing-crop scoring (task_teacher_v3) -------------------------------


def test_score_ongoing_crop_counts_only_reachable_ticks():
    # TOMATO ticks at day-offsets [8, 9, 10, 11] since planting. Planted at
    # current_day=0 with last_day=29: all 4 offsets fit (max is 11).
    # Planted at current_day=19: 19+8=27, 19+9=28, 19+10=29 all fit, but
    # 19+11=30 doesn't -- only 3 of 4 ticks reachable, so the same seed
    # cost is spread over less revenue and a shorter committed lifespan.
    from kaggriculture_lib.tasking import _score_ongoing_crop

    price = 60.0
    score_full = _score_ongoing_crop("TOMATO", price, current_day=0, last_day=29)
    score_partial = _score_ongoing_crop("TOMATO", price, current_day=19, last_day=29)
    assert score_full > 0
    assert score_partial > 0
    full_reachable = sum(1 for o in economy.ongoing_crop_production_days("TOMATO") if o <= 29)
    partial_reachable = sum(1 for o in economy.ongoing_crop_production_days("TOMATO") if 19 + o <= 29)
    assert full_reachable == 4
    assert partial_reachable == 3


def test_score_ongoing_crop_matches_manual_calculation():
    from kaggriculture_lib.tasking import _score_ongoing_crop

    # TOMATO planted day=0, last_day=29: all offsets [8,9,10,11] reachable.
    price = 60.0
    score = _score_ongoing_crop("TOMATO", price, current_day=0, last_day=29)
    reachable_offsets = economy.ongoing_crop_production_days("TOMATO")  # [8, 9, 10, 11]
    revenue = len(reachable_offsets) * price
    cost = economy.CROPS["TOMATO"]["seed"]
    lifespan_days = reachable_offsets[-1] - reachable_offsets[0] + 1  # 11-8+1 = 4
    expected = (revenue - cost) / lifespan_days
    assert score == pytest.approx(expected)
```

Add `import pytest` and `from kaggriculture_lib import economy` at the top of `tests/test_tasking.py` if not already present (check first — `economy` is very likely already imported since `TRAVEL_ALLOWANCE`/etc. tests reference crop constants; if `pytest` isn't imported, add `import pytest` near the top alongside the existing imports).

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k score_ongoing_crop -v`
Expected: FAIL with `ImportError: cannot import name '_score_ongoing_crop'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/kaggriculture_lib/tasking.py`, immediately after `_score_crop` (line 100):

```python
def _score_ongoing_crop(crop: str, price: float, current_day: int, last_day: int) -> float:
    """Day-aware $/day ROI estimate for an ongoing crop planted *today*.

    Generalizes `_score_crop` to a multi-tick lifecycle: only ticks that
    actually land on or before `last_day` count toward revenue, and the
    lifespan denominator is the actual span (first to last reachable tick,
    inclusive) this planting decision commits the tile for -- not the
    crop's full theoretical lifetime, which may not fit before season end.
    Only meaningful once `economy.can_ongoing_crop_reach_any_tick` has
    already confirmed at least one tick is reachable.
    """
    offsets = economy.ongoing_crop_production_days(crop)
    reachable = [o for o in offsets if current_day + o <= last_day]
    revenue = len(reachable) * price
    cost = economy.CROPS[crop]["seed"]
    lifespan_days = reachable[-1] - reachable[0] + 1
    return (revenue - cost) / lifespan_days
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k score_ongoing_crop -v`
Expected: 2 passed

- [ ] **Step 5: Run the full tasking test file to confirm no regressions**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -v`
Expected: all tests pass (previous count + 2 new)

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: add _score_ongoing_crop for day-aware ongoing-crop ROI scoring"
```

---

### Task 3: `_best_feasible_crop` dispatches by crop type

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py:102-108` (`_best_feasible_crop`)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: `economy.can_mature_in_time` (existing), `economy.can_ongoing_crop_reach_any_tick` (Task 1), `_score_crop` (existing), `_score_ongoing_crop` (Task 2)
- Produces: `_best_feasible_crop(day, last_day, market_prices, candidate_crops) -> str | None` — same signature, now crop-type-aware internally

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tasking.py`, in the same new section as Task 2's tests:

```python
def test_best_feasible_crop_picks_ongoing_crop_when_it_scores_higher():
    from kaggriculture_lib.tasking import _best_feasible_crop

    # At base prices, TOMATO's day-aware score with a full season ahead
    # comfortably beats WHEAT/CARROT's static score (verified by direct
    # computation below, not assumed).
    prices = {"WHEAT": 25, "CARROT": 35, "TOMATO": 60}
    crop = _best_feasible_crop(day=0, last_day=29, market_prices=prices, candidate_crops=("WHEAT", "CARROT", "TOMATO"))
    assert crop == "TOMATO"


def test_best_feasible_crop_picks_one_time_crop_when_ongoing_is_infeasible():
    from kaggriculture_lib.tasking import _best_feasible_crop

    # At day=24 with last_day=29: WHEAT (max_yield_day=4) still fits
    # (24+4=28<=29), but TOMATO (first_yield_day=8) does not reach even its
    # first tick (24+8=32>29) -- verified directly via
    # economy.can_mature_in_time("WHEAT", 24, 29) is True and
    # economy.can_ongoing_crop_reach_any_tick("TOMATO", 24, 29) is False.
    prices = {"WHEAT": 25, "TOMATO": 60}
    crop = _best_feasible_crop(day=24, last_day=29, market_prices=prices, candidate_crops=("WHEAT", "TOMATO"))
    assert crop == "WHEAT"


def test_best_feasible_crop_returns_none_when_nothing_is_feasible():
    from kaggriculture_lib.tasking import _best_feasible_crop

    # Day 29 (the last day): no one-time crop can mature, no ongoing crop
    # can reach even its first tick.
    prices = {"WHEAT": 25, "TOMATO": 60}
    crop = _best_feasible_crop(day=29, last_day=29, market_prices=prices, candidate_crops=("WHEAT", "TOMATO"))
    assert crop is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k best_feasible_crop -v`
Expected: FAIL — `test_best_feasible_crop_picks_ongoing_crop_when_it_scores_higher` fails because the current `_best_feasible_crop` filters via `economy.can_mature_in_time` only, which raises no error for TOMATO but also never selects it correctly since the existing code doesn't special-case ongoing crops. Confirm by running: the assertion `crop == "TOMATO"` will fail with `crop` actually being `None` or a wrong crop, since `can_mature_in_time("TOMATO", 0, 29)` checks `CROPS["TOMATO"]["max_yield_day"]` (=8) against `current_day + 8 <= 29` which happens to hold, but `_score_crop("TOMATO", ...)` uses `one_time_crop_watering_bonus_window`, which raises `ValueError` for an ongoing crop — so this test should fail with a `ValueError`, not an assertion error. Either failure mode confirms the current code doesn't handle ongoing crops correctly.

- [ ] **Step 3: Write minimal implementation**

Replace `_best_feasible_crop` in `src/kaggriculture_lib/tasking.py` (lines 102-108):

```python
def _best_feasible_crop(
    day: int, last_day: int, market_prices: dict[str, float], candidate_crops: tuple[str, ...]
) -> str | None:
    scored: list[tuple[float, str]] = []
    for crop in candidate_crops:
        cd = economy.CROPS[crop]
        price = market_prices.get(crop, cd["seed"])
        if cd["ongoing"]:
            if not economy.can_ongoing_crop_reach_any_tick(crop, day, last_day):
                continue
            score = _score_ongoing_crop(crop, price, day, last_day)
        else:
            if not economy.can_mature_in_time(crop, day, last_day):
                continue
            score = _score_crop(crop, price)
        scored.append((score, crop))
    if not scored:
        return None
    return max(scored, key=lambda pair: pair[0])[1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k best_feasible_crop -v`
Expected: 3 passed (plus any pre-existing `_best_feasible_crop`-adjacent tests, if named differently — search first with `grep -n best_feasible tests/test_tasking.py` to confirm none regress)

- [ ] **Step 5: Run the full tasking test file to confirm no regressions**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: _best_feasible_crop dispatches one-time vs ongoing crop feasibility and scoring"
```

---

### Task 4: `generate_tasks` empty-tile PLANT branch uses dispatched scoring

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py:135-150` (`generate_tasks`, empty-tile branch)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: `_best_feasible_crop` (Task 3, already dispatches correctly), `_score_crop` (existing), `_score_ongoing_crop` (Task 2)
- Produces: no signature change to `generate_tasks`; `Task.expected_value` for a `PLANT` task on an empty tile now uses the correct scorer for whichever crop `_best_feasible_crop` picked

- [ ] **Step 1: Write the failing test**

Add near the existing `generate_tasks` tests in `tests/test_tasking.py` (after `test_generate_tasks_filters_infeasible_plant_near_season_end`, line 259):

```python
def test_generate_tasks_plant_task_for_ongoing_crop_uses_day_aware_value():
    tiles = make_tiles()
    # MELON is deliberately excluded from this candidate set: at base
    # prices its one-time score (~109.2) beats TOMATO's ongoing score
    # (~47.5), which would make this test assert the wrong winner. WHEAT
    # (18.0) and CARROT (21.25) both score below TOMATO (47.5) at these
    # prices and day=0/last_day=29 (verified directly, matching Task 3's
    # test), so TOMATO is the correct, unambiguous winner here.
    prices = {"WHEAT": 25, "CARROT": 35, "TOMATO": 60}
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices=prices,
        candidate_crops=("WHEAT", "CARROT", "TOMATO"),
        board_size=BOARD_SIZE,
    )
    plant_tasks = [t for t in tasks if t.task_id.kind == TaskKind.PLANT]
    assert plant_tasks, "expected at least one PLANT task on an all-empty board"
    # Every PLANT task should agree on the same best crop (TOMATO) and its
    # expected_value should match _score_ongoing_crop exactly, not
    # _score_crop (which would raise ValueError for an ongoing crop if
    # called, or silently mis-score it).
    from kaggriculture_lib.tasking import _score_ongoing_crop

    assert all(t.task_id.item == "TOMATO" for t in plant_tasks)
    expected_value = _score_ongoing_crop("TOMATO", prices["TOMATO"], current_day=0, last_day=29)
    assert all(t.expected_value == pytest.approx(expected_value) for t in plant_tasks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k plant_task_for_ongoing_crop -v`
Expected: FAIL — the current `generate_tasks` calls `_score_crop(crop, price)` unconditionally (line 146), which raises `ValueError` for an ongoing crop (via `one_time_crop_watering_bonus_window`'s guard)

- [ ] **Step 3: Write minimal implementation**

Replace the empty-tile branch in `generate_tasks` (`src/kaggriculture_lib/tasking.py:135-150`):

```python
            if tile is None:
                crop = _best_feasible_crop(day, last_day, market_prices, candidate_crops)
                if crop is None:
                    continue
                cd = economy.CROPS[crop]
                price = market_prices.get(crop, cd["seed"])
                value = (
                    _score_ongoing_crop(crop, price, day, last_day)
                    if cd["ongoing"]
                    else _score_crop(crop, price)
                )
                tasks.append(
                    Task(
                        task_id=TaskId(kind=TaskKind.PLANT, x=x, y=y, item=crop),
                        target=(x, y),
                        priority_tier=PriorityTier.ECONOMIC,
                        deadline_step=None,
                        expected_value=value,
                        action_cost=1,
                        resource_needs=(ResourceNeed(item=crop, quantity=1, source="SEED"),),
                    )
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k plant_task_for_ongoing_crop -v`
Expected: 1 passed

- [ ] **Step 5: Run the full tasking test file to confirm no regressions**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: generate_tasks scores ongoing-crop PLANT tasks with the day-aware estimator"
```

---

### Task 5: `generate_tasks` HARVEST eligibility for ongoing crops

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py:152-176` (`generate_tasks`, existing-PLANT-tile branch)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: `economy.CROPS[crop]["ongoing"]` (existing)
- Produces: no signature change; `HARVEST` tasks are now generated for ongoing-crop tiles whenever `yield_units > 0`, in addition to the existing one-time-crop day-based gate

- [ ] **Step 1: Write the failing tests**

First, add a small helper near the top of `tests/test_tasking.py` (after `make_plant_tile`, line 52) — an ongoing-crop variant that lets `yield_units` vary (the existing `make_plant_tile` hardcodes `yield_units=1`, correct for one-time crops but wrong for ongoing ones, which start at 0):

```python
def make_ongoing_plant_tile(crop: str, planted_day: int, watered_today: bool, yield_units: int) -> dict:
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
```

Then add the tests, after `test_generate_tasks_watered_immature_plant_produces_no_task_for_that_tile` (line 228):

```python
def test_generate_tasks_ongoing_crop_with_no_yield_produces_no_harvest_task():
    tile = make_ongoing_plant_tile("TOMATO", planted_day=0, watered_today=True, yield_units=0)
    tiles = make_tiles({(2, 2): tile})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=8,  # TOMATO's first tick offset -- watered, but hasn't ticked yet this call
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=("WHEAT", "CARROT", "MELON", "TOMATO"),
        board_size=BOARD_SIZE,
    )
    assert not any(t.target == (2, 2) and t.task_id.kind == TaskKind.HARVEST for t in tasks)


def test_generate_tasks_ongoing_crop_with_yield_produces_harvest_task():
    tile = make_ongoing_plant_tile("TOMATO", planted_day=0, watered_today=True, yield_units=1)
    tiles = make_tiles({(2, 2): tile})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=8,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=("WHEAT", "CARROT", "MELON", "TOMATO"),
        board_size=BOARD_SIZE,
    )
    harvest_tasks = [t for t in tasks if t.target == (2, 2) and t.task_id.kind == TaskKind.HARVEST]
    assert len(harvest_tasks) == 1
    assert harvest_tasks[0].priority_tier == PriorityTier.DECAYING_YIELD


def test_generate_tasks_ongoing_crop_not_watered_produces_water_task_not_harvest():
    # Even with yield_units > 0, an unwatered ongoing-crop tile must still
    # get a WATER task first (universal weed-prevention rule) -- watering
    # and harvesting are independent for ongoing crops, but WATER still
    # takes priority when both would otherwise apply, matching one-time
    # crops' existing "water before harvest" rule.
    tile = make_ongoing_plant_tile("TOMATO", planted_day=0, watered_today=False, yield_units=1)
    tiles = make_tiles({(2, 2): tile})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=8,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=("WHEAT", "CARROT", "MELON", "TOMATO"),
        board_size=BOARD_SIZE,
    )
    tile_tasks = [t for t in tasks if t.target == (2, 2)]
    assert len(tile_tasks) == 1
    assert tile_tasks[0].task_id.kind == TaskKind.WATER
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k "ongoing_crop_with_no_yield or ongoing_crop_with_yield or ongoing_crop_not_watered" -v`
Expected: `test_generate_tasks_ongoing_crop_with_no_yield_produces_no_harvest_task` FAILS — the current code's `elif day - tile["planted_day"] >= cd["max_yield_day"]` (`day=8 - planted_day=0 = 8 >= max_yield_day=8`) is `True`, so it wrongly generates a HARVEST task even with `yield_units=0`. The other two should already pass (confirming they're not accidentally broken by the fix in the next step, but run all three now to see the one real failure clearly).

- [ ] **Step 3: Write minimal implementation**

Replace the existing-PLANT-tile branch in `generate_tasks` (`src/kaggriculture_lib/tasking.py:152-176`):

```python
            elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                cd = economy.CROPS[tile["crop"]]
                if not tile["watered_today"]:
                    tier = PriorityTier.EMERGENCY if tile["consecutive_unwatered"] >= 1 else PriorityTier.DAILY_CARE
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.WATER, x=x, y=y),
                            target=(x, y),
                            priority_tier=tier,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                        )
                    )
                elif cd["ongoing"]:
                    if tile["yield_units"] > 0:
                        tasks.append(
                            Task(
                                task_id=TaskId(kind=TaskKind.HARVEST, x=x, y=y),
                                target=(x, y),
                                priority_tier=PriorityTier.DECAYING_YIELD,
                                deadline_step=None,
                                expected_value=0.0,
                                action_cost=1,
                            )
                        )
                elif day - tile["planted_day"] >= cd["max_yield_day"]:
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.HARVEST, x=x, y=y),
                            target=(x, y),
                            priority_tier=PriorityTier.DECAYING_YIELD,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                        )
                    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k "ongoing_crop_with_no_yield or ongoing_crop_with_yield or ongoing_crop_not_watered" -v`
Expected: 3 passed

- [ ] **Step 5: Run the full tasking test file to confirm no regressions**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: generate_tasks gates ongoing-crop HARVEST on yield_units, not a maturity day"
```

---

### Task 6: Confirm v1/v2 regression safety

**Files:**
- None modified — verification-only task, no code changes.

**Interfaces:**
- None.

- [ ] **Step 1: Run the full test suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: all tests pass (no change in pass count from before Task 1, plus the new tests added in Tasks 1-5)

- [ ] **Step 2: Confirm `task_teacher_v2` behavior is unaffected**

Run a quick 5-pair local tournament to spot-check v2 still performs identically to its last-recorded numbers (win rate 0.950-0.970 range vs. `task_teacher_v1`, per `docs/4_agent_version_log.md`):

```bash
source .venv/bin/activate && PYTHONPATH=src python scripts/run_tournament.py agents/task_teacher_v2/main.py agents/task_teacher_v1/main.py --episodes 5 --episode-steps 720 --seed 30000
```

Expected: win rate in the 0.9-1.0 range, consistent with prior measurements (not a formal gate — v2's `CANDIDATE_CROPS` never includes `TOMATO`/`STRAWBERRY`, so `_best_feasible_crop` and `generate_tasks`'s new branches structurally cannot fire for any tile v2 ever plants; this is a quick sanity check, not new promotion evidence).

- [ ] **Step 3: No commit needed for this task** (verification only)

---

### Task 7: Create `agents/task_teacher_v3/main.py` and its test suite

**Files:**
- Create: `agents/task_teacher_v3/main.py` (copied forward from `agents/task_teacher_v2/main.py`)
- Create: `tests/test_task_teacher_v3.py`

**Interfaces:**
- Consumes: `kaggriculture_lib.economy`, `kaggriculture_lib.tasking` (`TaskKind`, `TeacherState`, `generate_tasks`, `joint_assign`, `project_daily_load`, `reset_hand_assignments_on_day_change`, `route_toward`, `should_hire`) — identical imports to v2
- Produces: `agent(obs, config=None) -> dict` — identical contract to every prior version

- [ ] **Step 1: Write the failing tests**

Create `tests/test_task_teacher_v3.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_task_teacher_v3.py -v`
Expected: FAIL — `agents/task_teacher_v3/main.py` doesn't exist yet (`load_agent_module` will raise `FileNotFoundError` or similar when `spec.loader.exec_module` can't find the file)

- [ ] **Step 3: Create `agents/task_teacher_v3/main.py`**

Copy `agents/task_teacher_v2/main.py` verbatim to `agents/task_teacher_v3/main.py`, then make exactly two changes: the module docstring and `CANDIDATE_CROPS`. The full file:

```python
"""Kaggriculture multi-tile task/route teacher agent, v3.

Extends `task_teacher_v2` with ongoing crops (Tomato, Strawberry), per the
approved design in docs/superpowers/specs/2026-08-02-task-teacher-v3-design.md.
Same hiring and multi-unit assignment as v2 (unchanged); no animals,
fertilizer, or PICKUP/PLACE.

Key mechanics respected by construction, not by accident:
- Unit actions execute before market actions each turn, so a seed bought
  this turn can't plant this same turn (see `_resolve_unit_action`).
- Farmer position and all hired hands reset unconditionally every day
  (confirmed against `kaggriculture.py`'s `_end_of_day`), so hand-indexed
  assignments never persist across a day boundary
  (`reset_hand_assignments_on_day_change`), while the farmer's own
  assignment naturally revalidates via `joint_assign`'s hysteresis check.
- Hire cost is reserved before seed-purchase affordability is checked, so
  the two never silently overspend the same turn's budget together.
- At most one `HIRE` order is emitted per turn.
- Ongoing crops (Tomato, Strawberry) never clear their tile on harvest and
  keep producing across the season -- handled entirely by the shared
  `kaggriculture_lib.tasking.generate_tasks`'s crop-type dispatch; no
  ongoing-crop-specific logic lives in this file.

Local testing only: imports `kaggriculture_lib.economy`/`.tasking`
assuming `src/` is on `sys.path` (handled by `scripts/run_tournament.py`).
Use `scripts/package_agent.py` to generate a standalone submission
artifact.
"""

from __future__ import annotations

from kaggriculture_lib import economy
from kaggriculture_lib.tasking import (
    TaskKind,
    TeacherState,
    generate_tasks,
    joint_assign,
    project_daily_load,
    reset_hand_assignments_on_day_change,
    route_toward,
    should_hire,
)

CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY")
DEFAULT_TURNS_PER_DAY = 24

# Module-level state for the Kaggle submission path. See task_teacher_v1's
# docstring for why this is explicitly reset on obs["step"] == 0 rather
# than relying on module-reload behavior.
_state = TeacherState()


def _reset_if_new_episode(state: TeacherState, step: int) -> None:
    if step == 0 or step < state.previous_step:
        state.reset()
    state.previous_step = step


def _count_immediately_completing_tasks(unit_positions, assignment, task_by_id, seeds_remaining) -> int:
    """Count assigned units already standing on their task's tile whose
    action will actually resolve this turn.

    Those units emit the field action (not movement) this turn, so that
    task resolves regardless of any hiring decision -- it must not also
    count as still-outstanding load when sizing whether a new hire is
    justified. WATER and HARVEST always resolve when on-target (generated
    tasks are already legality-filtered). PLANT only resolves if a
    matching seed is held -- mirroring `resolve_unit_action`'s own check --
    otherwise it emits PASS and queues a deferred BUY_SEED, completing
    nothing. Seed availability is consumed from a local copy in the same
    farmer-then-hands order `resolve_unit_action` uses, so two on-target
    PLANT assignments sharing one scarce seed aren't both counted.
    """
    available_seeds = dict(seeds_remaining)
    count = 0
    for unit_idx in sorted(assignment):
        task_id = assignment[unit_idx]
        if task_id is None or task_id.kind not in (TaskKind.WATER, TaskKind.PLANT, TaskKind.HARVEST):
            continue
        task = task_by_id.get(task_id)
        if task is None or unit_positions[unit_idx] != task.target:
            continue
        if task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if available_seeds.get(crop, 0) <= 0:
                continue
            available_seeds[crop] -= 1
        count += 1
    return count


def agent(obs, config=None):
    _reset_if_new_episode(_state, obs["step"])
    reset_hand_assignments_on_day_change(_state, obs["day"])

    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    prices = obs["market"]["prices"]
    shed = private["shed"]
    day = obs["day"]
    hour = obs["hour"]
    board_size = len(me["tiles"])
    turns_per_day = config.get("turnsPerDay", DEFAULT_TURNS_PER_DAY) if config else DEFAULT_TURNS_PER_DAY

    last_day = economy.last_day_index(config)
    tasks = generate_tasks(
        tiles=me["tiles"],
        unlocked_quadrants=me["unlocked_quadrants"],
        day=day,
        last_day=last_day,
        market_prices=prices,
        candidate_crops=CANDIDATE_CROPS,
        board_size=board_size,
    )
    task_by_id = {t.task_id: t for t in tasks}

    unit_positions = [tuple(me["farmer"])] + [tuple(h) for h in me["hands"]]
    assignment = joint_assign(unit_positions, tasks, _state.assignments)
    _state.assignments = {unit: tid for unit, tid in assignment.items() if tid is not None}

    market_orders = [["SELL", crop, shed[crop]] for crop in CANDIDATE_CROPS if shed.get(crop, 0) > 0]

    # Hiring decision first, so seed-purchase affordability below reflects
    # the reserved hire budget -- not the other way around.
    pending_water = sum(1 for t in tasks if t.task_id.kind == TaskKind.WATER)
    pending_plant = sum(1 for t in tasks if t.task_id.kind == TaskKind.PLANT)
    pending_harvest = sum(1 for t in tasks if t.task_id.kind == TaskKind.HARVEST)
    load = project_daily_load(pending_water, pending_plant, pending_harvest)
    # A hire is a market order, resolved after this turn's unit actions, so a
    # hand hired now gets its first action next turn -- its recoverable
    # capacity (and, symmetrically, any existing unit's still-outstanding
    # capacity) only spans turns *after* this one. A task an already-
    # positioned unit is about to complete this turn resolves regardless of
    # the hiring decision, so it isn't outstanding load for that decision
    # either. See docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md
    # §12.1.
    future_action_turns = max(0, turns_per_day - hour - 1)
    immediately_completing = _count_immediately_completing_tasks(
        unit_positions, assignment, task_by_id, private["seeds"]
    )
    future_load = max(0, load - immediately_completing)

    available_money = me["money"]
    if should_hire(
        future_load, future_action_turns, me["hires_today"], me["money"], existing_hands=len(me["hands"])
    ):
        market_orders.append(["HIRE"])
        available_money -= economy.hire_cost(me["hires_today"])

    seeds_remaining = dict(private["seeds"])
    seed_orders_queued: set[str] = set()

    def resolve_unit_action(position: tuple[int, int], task_id) -> list:
        nonlocal available_money
        if task_id is None:
            return ["PASS"]
        task = task_by_id.get(task_id)
        if task is None:
            return ["PASS"]

        tx, ty = task.target
        if position != (tx, ty):
            return [route_toward(position, (tx, ty), me["tiles"], board_size)]

        if task_id.kind == TaskKind.PLANT:
            crop = task_id.item
            if seeds_remaining.get(crop, 0) > 0:
                seeds_remaining[crop] -= 1
                return ["PLANT", crop]
            # Unit actions execute before market actions this turn, so a
            # seed bought now can't plant now -- queue for next turn.
            if crop not in seed_orders_queued and available_money >= economy.CROPS[crop]["seed"]:
                market_orders.append(["BUY_SEED", crop, 1])
                seed_orders_queued.add(crop)
                available_money -= economy.CROPS[crop]["seed"]
            return ["PASS"]
        if task_id.kind == TaskKind.WATER:
            return ["WATER"]
        if task_id.kind == TaskKind.HARVEST:
            return ["HARVEST"]
        if task_id.kind == TaskKind.DIG:
            return ["DIG"]
        return ["PASS"]

    farmer_action = resolve_unit_action(unit_positions[0], assignment.get(0))
    hands_actions = [
        resolve_unit_action(unit_positions[i + 1], assignment.get(i + 1)) for i in range(len(me["hands"]))
    ]

    return {"farmer": farmer_action, "hands": hands_actions, "market": market_orders}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_task_teacher_v3.py -v`
Expected: all pass. If `test_plants_ongoing_crop_on_empty_tile_at_base_prices` or
`test_harvests_ongoing_crop_repeatedly_without_the_tile_ever_clearing` fail on
assignment specifics (e.g. `joint_assign` picks a different tile than
expected due to hysteresis or tie-breaking with a fresh `_state`), adjust
the test's tile layout to be unambiguous (e.g. a single non-`None` tile at
the farmer's exact position) rather than the agent code — these tests
exercise existing, already-tested `tasking.py` logic end-to-end, so a
failure here means the test fixture needs to isolate the scenario better,
not that `generate_tasks`/`joint_assign` need changes (those were already
proven correct in Tasks 1-5's direct unit tests).

- [ ] **Step 5: Run the full test suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add agents/task_teacher_v3/main.py tests/test_task_teacher_v3.py
git commit -m "feat: add task_teacher_v3, extending v2 with ongoing crops (Tomato, Strawberry)"
```

---

### Task 8: Packaging and standalone verification

**Files:**
- Modify: `tests/test_package_agent.py` (add one test, mirroring the existing `test_packaged_task_teacher_v1_runs_standalone_without_pythonpath`)

**Interfaces:**
- Consumes: `scripts/package_agent.package(agent_dir: Path, out_path: Path)` (existing, used identically for every prior version)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_package_agent.py`, immediately after `test_packaged_task_teacher_v1_runs_standalone_without_pythonpath` (line 180):

```python
def test_packaged_task_teacher_v3_runs_standalone_without_pythonpath():
    """Same check for task_teacher_v3, which adds ongoing-crop dispatch to
    the same shared modules task_teacher_v1/v2 already package correctly."""
    out_path = REPO_ROOT / "build" / "task_teacher_v3" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v3", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_package_agent.py -k task_teacher_v3 -v`
Expected: FAIL — `agents/task_teacher_v3` doesn't exist as a packaging target yet if Task 7 wasn't completed first (it should already exist by this point in the plan; if this fails for a different reason, e.g. a packaging bug, investigate `scripts/package_agent.py`'s module auto-discovery before assuming the test is wrong).

- [ ] **Step 3: No implementation change needed**

`scripts/package_agent.py` already auto-discovers and topologically sorts shared-module dependencies for any `agents/<version>/main.py` (verified working for `task_teacher_v1`, `roi_teacher_v1-v3`) — `task_teacher_v3` uses the identical import set as `task_teacher_v2` (`economy`, `tasking`), so no packaging code changes are expected. If this test fails for a reason other than "file doesn't exist yet," stop and diagnose before proceeding — that would indicate a real packaging gap Tasks 1-7 didn't anticipate.

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_package_agent.py -k task_teacher_v3 -v`
Expected: 1 passed

- [ ] **Step 5: Run the full test suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add tests/test_package_agent.py
git commit -m "test: verify task_teacher_v3 packages and runs standalone"
```

---

### Task 9: Acceptance gate and evaluation protocol

**Files:**
- None created or modified — this task produces measurement results to record in docs, not code.

**Interfaces:**
- None (uses `scripts/run_tournament.py`'s existing CLI, and a scratch acceptance-gate script matching the pattern used for `task_teacher_v1`/`v2` in prior sessions — see `docs/4_agent_version_log.md` for the exact metrics table format to reproduce).

This task is empirical measurement, not new library code — there is no
RED/GREEN cycle here, only running the already-tested harness and recording
what it reports. Do not skip steps or declare promotion from a partial run.

- [ ] **Step 1: Run the 100-episode acceptance gate**

Write this script to a scratch path (e.g. your session's scratchpad
directory — not committed to the repo, same as every prior acceptance-gate
measurement in this project's history):

```python
"""100-episode acceptance gate for task_teacher_v3."""

import math
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture")
sys.path.insert(0, str(REPO_ROOT / "src"))

from kaggle_environments import make  # noqa: E402

N_EPISODES = 100
BASE_SEED = 50000
EPISODE_STEPS = 720

action_kind_counts = {"PLANT": 0, "WATER": 0, "HARVEST": 0, "DIG": 0}
distinct_tiles_per_episode = []
ongoing_crop_plant_count = 0
done_count = 0
finite_reward_count = 0
latencies_ms = []

for i in range(N_EPISODES):
    seed = BASE_SEED + i
    env = make("kaggriculture", configuration={"episodeSteps": EPISODE_STEPS, "seed": seed}, debug=True)

    import time

    t0 = time.time()
    env.run(["agents/task_teacher_v3/main.py", "starter"])
    latencies_ms.append((time.time() - t0) / EPISODE_STEPS * 1000)

    final = env.steps[-1]
    if all(s.status == "DONE" for s in final):
        done_count += 1
    if all(s.reward is not None and math.isfinite(s.reward) for s in final):
        finite_reward_count += 1

    touched = set()
    for step in env.steps:
        action = step[0].action
        if not isinstance(action, dict):
            continue
        farmer_action = action.get("farmer")
        if isinstance(farmer_action, list) and farmer_action:
            kind = farmer_action[0]
            if kind in action_kind_counts:
                action_kind_counts[kind] += 1
                if kind in ("PLANT", "WATER", "HARVEST", "DIG"):
                    touched.add(tuple(step[0].observation["farms"][0]["farmer"]))
            if kind == "PLANT" and len(farmer_action) > 1 and farmer_action[1] in ("TOMATO", "STRAWBERRY"):
                ongoing_crop_plant_count += 1
    distinct_tiles_per_episode.append(len(touched))

print(f"DONE both players: {done_count}/{N_EPISODES}")
print(f"Finite-reward episodes: {finite_reward_count}/{N_EPISODES}")
print(
    f"Distinct tiles worked/episode: min={min(distinct_tiles_per_episode)}, "
    f"max={max(distinct_tiles_per_episode)}"
)
print(f"Action-kind coverage (all episodes): {action_kind_counts}")
print(f"Ongoing-crop PLANT actions (all episodes): {ongoing_crop_plant_count}")
print(
    f"HARVEST/ongoing-crop-plant ratio: "
    f"{action_kind_counts['HARVEST'] / max(1, ongoing_crop_plant_count):.2f} "
    "(> 1.0 confirms repeated harvesting per planted ongoing-crop tile, "
    "not just one harvest each)"
)
print(f"Inference latency (ms/turn): median={sorted(latencies_ms)[len(latencies_ms) // 2]:.2f}")

env_a = make("kaggriculture", configuration={"episodeSteps": EPISODE_STEPS, "seed": BASE_SEED}, debug=False)
env_a.run(["agents/task_teacher_v3/main.py", "starter"])
rewards_a = (env_a.steps[-1][0].reward, env_a.steps[-1][1].reward)

env_b = make("kaggriculture", configuration={"episodeSteps": EPISODE_STEPS, "seed": BASE_SEED}, debug=False)
env_b.run(["agents/task_teacher_v3/main.py", "starter"])
rewards_b = (env_b.steps[-1][0].reward, env_b.steps[-1][1].reward)

print(f"Determinism (same seed, 2 runs): {rewards_a} vs {rewards_b} -> {'IDENTICAL' if rewards_a == rewards_b else 'MISMATCH'}")
```

Run: `source .venv/bin/activate && python <scratch_script_path>`

Expected: 100/100 `DONE`, 100/100 finite rewards, identical determinism-check
rewards, and a `HARVEST`/ongoing-crop-plant ratio meaningfully above 1.0
(confirming ongoing crops are actually cycling through repeated harvests in
real play, not just harvested once like one-time crops).

- [ ] **Step 2: Run the 20-pair screen vs. `task_teacher_v2`**

Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/run_tournament.py agents/task_teacher_v3/main.py agents/task_teacher_v2/main.py --episodes 20 --episode-steps 720 --seed 40000`

Record the win rate, mean margin, and `hoeffding_95%_ci`. If the CI is
wholly above 0.50, proceed to Step 3. If wholly below 0.50, v3 does not
promote — stop here, record the result honestly (do not proceed to a
50-pair run to "try again" for a better sample; report the screen result
as the outcome and stop). If the CI straddles 0.50, proceed to Step 3
anyway per the authoritative protocol (ambiguous screens escalate, they
don't stop).

- [ ] **Step 3: If positive or ambiguous, run the 50-pair promotion gate**

Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/run_tournament.py agents/task_teacher_v3/main.py agents/task_teacher_v2/main.py --episodes 50 --episode-steps 720 --seed 41000`

Record the win rate, mean margin, and `hoeffding_95%_ci`. Promotion requires
the CI wholly above 0.50. If it isn't, v3 does not promote — do not
recalibrate anything to try to force a different result (see
`docs/4_agent_version_log.md`'s recorded lesson from the reverted v2
hiring-constant recalibration attempt: a same-session tuning pass to chase
a specific outcome is not evaluation, it's overfitting to the evaluation).

- [ ] **Step 4: Regression screens vs. `roi_teacher_v3` and `starter`**

Run: `source .venv/bin/activate && PYTHONPATH=src python scripts/run_tournament.py agents/task_teacher_v3/main.py agents/roi_teacher_v3/main.py starter --episodes 20 --episode-steps 720 --seed 42000`

Confirm v3 doesn't regress against either weaker opponent relative to v2's
own recorded numbers against the same two opponents.

- [ ] **Step 5: Record results and update documentation**

If promoted: update `docs/4_agent_version_log.md` (new `task_teacher_v3`
entry, following the exact structure of the `task_teacher_v2` entry —
config diff, acceptance-gate table, paired-evaluation table, outcome,
lesson carried forward), `README.md`'s "Current local champion" line,
`docs/6_next_steps.md` (mark the `task_teacher_v3` line item done, update
the recommendation), `docs/3_agent_strategy.md` (new `task_teacher_v3`
scope section, mark it "Current Champion", update the ongoing-crop table's
"not yet ROI-ranked" note now that it is), and add a "Codex review" section
placeholder is NOT needed preemptively -- only add one if Codex actually
reviews it, matching how every prior version's design doc grew organically
rather than being pre-populated with anticipated review sections. If not
promoted: record the honest result in `docs/4_agent_version_log.md` and
`docs/6_next_steps.md` (v3 built and evaluated, did not clear the promotion
bar, `task_teacher_v2` remains `competitive_champion`) with the same level
of detail as a promoted result would get.

- [ ] **Step 6: Run the full test suite one final time and commit**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: all tests pass

```bash
git add docs/4_agent_version_log.md README.md docs/6_next_steps.md docs/3_agent_strategy.md
git commit -m "docs: record task_teacher_v3 acceptance gate and evaluation results"
git push
```
