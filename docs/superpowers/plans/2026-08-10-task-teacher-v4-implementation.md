# Task Teacher v4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `task_teacher_v4` — v2-forward teacher with ROI-gated NE land purchase and a Goose loop (coop → buy/pickup/place → feed/care → harvest/sell eggs), per `docs/superpowers/specs/2026-08-10-task-teacher-v4-design.md`.

**Architecture:** Extend `tasking.py`'s task graph with new `TaskKind`s (`BUILD_COOP`, `PLACE`, `FEED`, `CARE`, `PICKUP`); add `should_buy_land` (hire-then-land, NE-only); add economy helpers for shed-access tiles and wheat feed reserve; new immutable `agents/task_teacher_v4/main.py` copied from v2 wires market (`BUY_LAND`, `BUY_ANIMAL`, sell `EGG`) and resolves the new actions. Existing agent mains stay untouched; `generate_tasks` gains optional `shed` / inventory kwargs with defaults so v1/v2/v3 call sites keep working.

**Tech Stack:** Python 3.11, pytest, `kaggle_environments==1.29.3` (pinned), `src/kaggriculture_lib`.

## Global Constraints

- No Cow/Sheep/pasture, no `COLLECT_FERTILIZER`/`FERTILIZE`, no SW/SE land, no learned policy (design §1).
- Minimal `PICKUP` **is** in scope for `WHEAT` and `GOOSE` only (env-required).
- Every existing test in `tests/test_economy.py`, `tests/test_tasking.py`, `tests/test_task_teacher_v1.py`, `tests/test_task_teacher_v2.py`, `tests/test_task_teacher_v3.py`, `tests/test_package_agent.py` must keep passing unmodified.
- Never edit existing `agents/*/main.py` — only create `agents/task_teacher_v4/main.py`.
- Build test-first: RED → GREEN per `superpowers:test-driven-development`.
- Locked constants (design §7 resolved here):
  - `MAX_GEESE = 2`
  - `LAND_MIN_DAYS_REMAINING = 12`
  - `LAND_BUDGET_RESERVE = 400` (cash cushion beyond land cost)
  - `MIN_HANDS_BEFORE_LAND = 3`
  - `NW_SATURATION_PLANTS = 18` (min PLANT tiles on farm before land is considered)
  - CARE emitted whenever animal present and not `cared_today` (after FEED priority)
- Promotion: full protocol only (100-ep acceptance, 20-pair screen, 50-pair if needed, regressions). Honesty rule: do not force-promote on ~identity vs v2.
- Run `source .venv/bin/activate` before python/pytest; `PYTHONPATH=src` outside pytest.
- Prefer branch `feat/task-teacher-v4` from current `main` (after packaging fix) or from merged v3 tip — do not implement on `main`.

## File map

| File | Responsibility |
| --- | --- |
| `src/kaggriculture_lib/economy.py` | `shed_access_tiles`, `wheat_reserved_for_feed` |
| `src/kaggriculture_lib/tasking.py` | New TaskKinds; `should_buy_land`; `generate_tasks` animal/structure/PICKUP branches |
| `agents/task_teacher_v4/main.py` | Agent wiring |
| `tests/test_economy.py` | Economy helper tests |
| `tests/test_tasking.py` | Land gate + task generation tests |
| `tests/test_task_teacher_v4.py` | Agent behavior + short episode |
| `tests/test_package_agent.py` | Standalone package smoke |

---

### Task 1: `economy.shed_access_tiles`

**Files:**
- Modify: `src/kaggriculture_lib/economy.py` (add after `land_cost`)
- Test: `tests/test_economy.py`

**Interfaces:**
- Produces: `economy.shed_access_tiles(board_size: int) -> list[tuple[int, int]]`

- [ ] **Step 1: Write the failing test**

```python
def test_shed_access_tiles_matches_env_for_board_size_10():
    # Mirrors kaggriculture.py `_shed_access_tiles` for boardSize=10:
    # half=5 → [(4,4), (5,4), (4,5), (5,5)] in NWSE order.
    assert economy.shed_access_tiles(10) == [(4, 4), (5, 4), (4, 5), (5, 5)]


def test_shed_access_tiles_scales_with_board_size():
    assert economy.shed_access_tiles(8) == [(3, 3), (4, 3), (3, 4), (4, 4)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -k shed_access_tiles -v`
Expected: FAIL with `AttributeError: ... no attribute 'shed_access_tiles'`

- [ ] **Step 3: Write minimal implementation**

```python
def shed_access_tiles(board_size: int) -> list[tuple[int, int]]:
    """Four inner-corner tiles around the shed, NWSE order.

    Mirrors kaggle-environments==1.29.3's kaggriculture.py `_shed_access_tiles`.
    """
    half = board_size // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -k shed_access_tiles -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/kaggriculture_lib/economy.py tests/test_economy.py
git commit -m "feat: add shed_access_tiles mirroring env shed-adjacent tiles"
```

---

### Task 2: `economy.wheat_reserved_for_feed`

**Files:**
- Modify: `src/kaggriculture_lib/economy.py`
- Test: `tests/test_economy.py`

**Interfaces:**
- Produces: `economy.wheat_reserved_for_feed(geese_count: int, days_horizon: int) -> int`

- [ ] **Step 1: Write the failing tests**

```python
def test_wheat_reserved_for_feed_is_geese_times_days():
    # One wheat per goose per day (FEED consumes 1 WHEAT from inventory).
    assert economy.wheat_reserved_for_feed(geese_count=2, days_horizon=5) == 10


def test_wheat_reserved_for_feed_zero_when_no_geese():
    assert economy.wheat_reserved_for_feed(geese_count=0, days_horizon=30) == 0


def test_wheat_reserved_for_feed_clamps_non_positive_horizon():
    assert economy.wheat_reserved_for_feed(geese_count=2, days_horizon=0) == 0
    assert economy.wheat_reserved_for_feed(geese_count=2, days_horizon=-3) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -k wheat_reserved_for_feed -v`
Expected: FAIL with missing attribute

- [ ] **Step 3: Write minimal implementation**

```python
def wheat_reserved_for_feed(geese_count: int, days_horizon: int) -> int:
    """Wheat units to keep (not sell) so geese can be fed for `days_horizon` days."""
    if geese_count <= 0 or days_horizon <= 0:
        return 0
    return geese_count * days_horizon
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -k wheat_reserved_for_feed -v`
Expected: 3 passed

- [ ] **Step 5: Full economy file**

Run: `source .venv/bin/activate && python -m pytest tests/test_economy.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/economy.py tests/test_economy.py
git commit -m "feat: add wheat_reserved_for_feed for goose feed budgeting"
```

---

### Task 3: Extend `TaskKind` enum

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py` (`TaskKind`)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Produces: `TaskKind.BUILD_COOP`, `PLACE`, `FEED`, `CARE`, `PICKUP`

- [ ] **Step 1: Write the failing test**

```python
def test_task_kind_includes_v4_animal_and_pickup_kinds():
    from kaggriculture_lib.tasking import TaskKind

    for name in ("BUILD_COOP", "PLACE", "FEED", "CARE", "PICKUP"):
        assert hasattr(TaskKind, name)
        assert TaskKind[name].value == name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k task_kind_includes_v4 -v`
Expected: FAIL (missing enum members)

- [ ] **Step 3: Write minimal implementation**

Replace `TaskKind` with:

```python
class TaskKind(str, Enum):
    PLANT = "PLANT"
    WATER = "WATER"
    HARVEST = "HARVEST"
    DIG = "DIG"
    BUILD_COOP = "BUILD_COOP"
    PLACE = "PLACE"
    FEED = "FEED"
    CARE = "CARE"
    PICKUP = "PICKUP"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k task_kind_includes_v4 -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: extend TaskKind with coop/animal/pickup actions for v4"
```

---

### Task 4: `should_buy_land`

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py` (near `should_hire`)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: `economy.land_cost`, `estimate_hire_value`
- Produces: `should_buy_land(...) -> bool`
- Constants on module: `LAND_MIN_DAYS_REMAINING=12`, `LAND_BUDGET_RESERVE=400`, `MIN_HANDS_BEFORE_LAND=3`, `NW_SATURATION_PLANTS=18`

- [ ] **Step 1: Write the failing tests**

```python
def test_should_buy_land_true_when_nw_saturated_and_affordable():
    from kaggriculture_lib.tasking import should_buy_land

    assert should_buy_land(
        unlocked_quadrants=["NW"],
        money=2000.0,
        projected_load=10,
        remaining_turns_today=20,
        existing_hands=3,
        day=5,
        last_day=29,
        reserved_for_hire=0.0,
        plant_tile_count=20,
    )


def test_should_buy_land_false_when_ne_already_owned():
    from kaggriculture_lib.tasking import should_buy_land

    assert not should_buy_land(
        unlocked_quadrants=["NW", "NE"],
        money=5000.0,
        projected_load=10,
        remaining_turns_today=20,
        existing_hands=5,
        day=5,
        last_day=29,
        reserved_for_hire=0.0,
        plant_tile_count=25,
    )


def test_should_buy_land_false_when_hire_still_valuable():
    from kaggriculture_lib.tasking import should_buy_land

    # Huge load + few hands → estimate_hire_value > 0 → land deferred.
    assert not should_buy_land(
        unlocked_quadrants=["NW"],
        money=5000.0,
        projected_load=200,
        remaining_turns_today=20,
        existing_hands=3,
        day=5,
        last_day=29,
        reserved_for_hire=0.0,
        plant_tile_count=20,
    )


def test_should_buy_land_false_when_too_late_in_season():
    from kaggriculture_lib.tasking import should_buy_land

    assert not should_buy_land(
        unlocked_quadrants=["NW"],
        money=5000.0,
        projected_load=10,
        remaining_turns_today=20,
        existing_hands=3,
        day=20,
        last_day=29,  # only 9 days left < 12
        reserved_for_hire=0.0,
        plant_tile_count=20,
    )


def test_should_buy_land_false_when_cash_after_hire_reserve_too_low():
    from kaggriculture_lib.tasking import should_buy_land

    # land 1000 + reserve 400 = 1400 needed; money-reserved = 1300.
    assert not should_buy_land(
        unlocked_quadrants=["NW"],
        money=1500.0,
        projected_load=10,
        remaining_turns_today=20,
        existing_hands=3,
        day=5,
        last_day=29,
        reserved_for_hire=200.0,
        plant_tile_count=20,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k should_buy_land -v`
Expected: FAIL with ImportError / missing name

- [ ] **Step 3: Write minimal implementation**

```python
LAND_MIN_DAYS_REMAINING = 12
LAND_BUDGET_RESERVE = 400
MIN_HANDS_BEFORE_LAND = 3
NW_SATURATION_PLANTS = 18


def should_buy_land(
    unlocked_quadrants: list[str],
    money: float,
    projected_load: int,
    remaining_turns_today: int,
    existing_hands: int,
    day: int,
    last_day: int,
    reserved_for_hire: float,
    plant_tile_count: int,
) -> bool:
    """Whether to emit BUY_LAND for NE this turn (v4 hard-cap: one extra quadrant)."""
    if len(unlocked_quadrants) != 1:
        return False
    if plant_tile_count < NW_SATURATION_PLANTS:
        return False
    if existing_hands < MIN_HANDS_BEFORE_LAND:
        return False
    if last_day - day < LAND_MIN_DAYS_REMAINING:
        return False
    cost = economy.land_cost(0)
    if cost is None:
        return False
    if money - reserved_for_hire < cost + LAND_BUDGET_RESERVE:
        return False
    if estimate_hire_value(projected_load, remaining_turns_today, existing_hands) > 0:
        return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k should_buy_land -v`
Expected: 5 passed

- [ ] **Step 5: Full tasking file**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: add should_buy_land gate (NE-only, hire-then-land)"
```

---

### Task 5: `generate_tasks` — animal tile FEED/CARE/HARVEST

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py` (`generate_tasks`)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Extends `generate_tasks` with optional `shed: dict | None = None` (unused until Task 6) — animal branch needs only tiles.
- Animal tiles: `isinstance(tile, dict) and "animal" in tile`

- [ ] **Step 1: Write the failing tests**

```python
def make_goose_tile(placed_day, fed_today, cared_today, yield_units, consecutive_unfed=0):
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


def test_generate_tasks_unfed_goose_produces_feed_not_care():
    from kaggriculture_lib.tasking import TaskKind, PriorityTier, generate_tasks

    tiles = make_tiles({(2, 2): make_goose_tile(0, fed_today=False, cared_today=False, yield_units=0, consecutive_unfed=1)})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=5,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    tile_tasks = [t for t in tasks if t.target == (2, 2)]
    assert len(tile_tasks) == 1
    assert tile_tasks[0].task_id.kind == TaskKind.FEED
    assert tile_tasks[0].priority_tier == PriorityTier.EMERGENCY


def test_generate_tasks_fed_uncared_goose_produces_care():
    from kaggriculture_lib.tasking import TaskKind, PriorityTier, generate_tasks

    tiles = make_tiles({(2, 2): make_goose_tile(0, fed_today=True, cared_today=False, yield_units=0)})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=5,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    tile_tasks = [t for t in tasks if t.target == (2, 2)]
    assert len(tile_tasks) == 1
    assert tile_tasks[0].task_id.kind == TaskKind.CARE
    assert tile_tasks[0].priority_tier == PriorityTier.DAILY_CARE


def test_generate_tasks_goose_with_yield_produces_harvest():
    from kaggriculture_lib.tasking import TaskKind, PriorityTier, generate_tasks

    tiles = make_tiles({(2, 2): make_goose_tile(0, fed_today=True, cared_today=True, yield_units=2)})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=5,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
    )
    harvest = [t for t in tasks if t.target == (2, 2) and t.task_id.kind == TaskKind.HARVEST]
    assert len(harvest) == 1
    assert harvest[0].priority_tier == PriorityTier.DECAYING_YIELD
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k "unfed_goose or fed_uncared_goose or goose_with_yield" -v`
Expected: FAIL (no animal branch — no tasks or wrong kinds)

- [ ] **Step 3: Write minimal implementation**

In `generate_tasks`, after the WEED branch (before end of loop), add:

```python
            elif isinstance(tile, dict) and "animal" in tile:
                if not tile["fed_today"]:
                    tier = (
                        PriorityTier.EMERGENCY
                        if tile.get("consecutive_unfed", 0) >= 1
                        else PriorityTier.DAILY_CARE
                    )
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.FEED, x=x, y=y),
                            target=(x, y),
                            priority_tier=tier,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                            resource_needs=(ResourceNeed(item="WHEAT", quantity=1, source="INVENTORY"),),
                        )
                    )
                else:
                    if tile.get("yield_units", 0) > 0:
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
                    elif not tile["cared_today"]:
                        tasks.append(
                            Task(
                                task_id=TaskId(kind=TaskKind.CARE, x=x, y=y),
                                target=(x, y),
                                priority_tier=PriorityTier.DAILY_CARE,
                                deadline_step=None,
                                expected_value=0.0,
                                action_cost=1,
                            )
                        )
```

Priority when fed: HARVEST before CARE if yield > 0 (eggs first). When unfed: only FEED.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k "unfed_goose or fed_uncared_goose or goose_with_yield" -v`
Expected: 3 passed

- [ ] **Step 5: Full tasking file**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: generate_tasks emits FEED/CARE/HARVEST for animal tiles"
```

---

### Task 6: `generate_tasks` — BUILD_COOP, empty COOP+PLACE signal, PICKUP

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py` (`generate_tasks` signature + branches)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Signature becomes:

```python
def generate_tasks(
    tiles, unlocked_quadrants, day, last_day, market_prices, candidate_crops,
    board_size=10,
    shed: dict | None = None,
    want_coop: bool = False,
    unit_wants_pickup: tuple[str, ...] = (),
) -> list[Task]:
```

- `want_coop=True` and no COOP/animal coop on board → emit one `BUILD_COOP` on a chosen empty unlocked tile (prefer first shed-access empty tile in unlocked set, else first empty unlocked tile scan order).
- Empty `{"kind": "COOP"}` without animal + goose available via pickup path: emit `PLACE` only when `"GOOSE"` in `unit_wants_pickup` is false wait — PLACE needs goose **in inventory**. Agent will set `unit_wants_pickup` based on inventory gaps; for PLACE task emission: emit PLACE on empty coop when `shed` has GOOSE **or** inventories already hold goose — pass `goose_in_inventory: bool = False`.

Simpler API for this task:

```python
shed: dict | None = None,
want_coop: bool = False,
goose_in_any_inventory: bool = False,
wheat_needed_for_feed: bool = False,
```

- PICKUP GOOSE: if shed has GOOSE and not `goose_in_any_inventory` and (empty coop exists or want place path)
- PICKUP WHEAT: if `wheat_needed_for_feed` and shed has WHEAT
- PICKUP target: first `economy.shed_access_tiles(board_size)` tile that is unlocked

- [ ] **Step 1: Write the failing tests**

```python
def test_generate_tasks_want_coop_emits_build_coop_on_empty_tile():
    from kaggriculture_lib.tasking import TaskKind, generate_tasks

    tiles = make_tiles()
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=3,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
        want_coop=True,
    )
    builds = [t for t in tasks if t.task_id.kind == TaskKind.BUILD_COOP]
    assert len(builds) == 1
    bx, by = builds[0].target
    assert tiles[by][bx] is None


def test_generate_tasks_pickup_goose_when_shed_has_goose_and_empty_coop():
    from kaggriculture_lib.tasking import TaskKind, generate_tasks

    tiles = make_tiles({(3, 3): {"kind": "COOP"}})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=3,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
        shed={"GOOSE": 1},
        goose_in_any_inventory=False,
    )
    pickups = [t for t in tasks if t.task_id.kind == TaskKind.PICKUP and t.task_id.item == "GOOSE"]
    assert len(pickups) == 1
    assert pickups[0].target in economy.shed_access_tiles(BOARD_SIZE)


def test_generate_tasks_place_goose_when_inventory_has_goose_and_empty_coop():
    from kaggriculture_lib.tasking import TaskKind, generate_tasks

    tiles = make_tiles({(3, 3): {"kind": "COOP"}})
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=3,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        board_size=BOARD_SIZE,
        goose_in_any_inventory=True,
    )
    places = [t for t in tasks if t.task_id.kind == TaskKind.PLACE and t.target == (3, 3)]
    assert len(places) == 1
    assert places[0].task_id.item == "GOOSE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k "want_coop_emits or pickup_goose_when or place_goose_when" -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Extend `generate_tasks` signature with the optional kwargs (defaults preserve old behavior). After the tile loop (or inside for empty COOP / empty tiles):

1. Detect `has_coop_structure`, `has_empty_coop`, `has_animal` while scanning.
2. For empty `{"kind":"COOP"}` without animal: if `goose_in_any_inventory`, append PLACE task.
3. After loop: if `want_coop` and not `has_coop_structure` and not `has_animal` with coop — pick build target and append BUILD_COOP (skip if that tile already got a PLANT task — prefer removing PLANT on that tile or choose a tile that wasn't planted: **choose first empty unlocked tile that is also a shed-access tile if empty, else first empty unlocked; if that tile already has a PLANT task in `tasks`, skip emitting PLANT for that coordinate by selecting build target before plant generation OR filter plant tasks for that tile**).

Practical order inside loop for `tile is None`:
```python
if tile is None:
    if want_coop and not coop_planned and (x, y) == build_target:
        # emit BUILD_COOP instead of PLANT
        coop_planned = True
        ...
        continue
    # else existing PLANT logic
```

Precompute `build_target` before the loop when `want_coop`.

PICKUP after loop:
```python
if shed:
    access = [p for p in economy.shed_access_tiles(board_size) if _quadrant_of(p[0], p[1], board_size) in unlocked]
    if access:
        ax, ay = access[0]
        if shed.get("GOOSE", 0) > 0 and not goose_in_any_inventory and has_empty_coop:
            tasks.append(Task(... PICKUP GOOSE ...))
        if wheat_needed_for_feed and shed.get("WHEAT", 0) > 0:
            tasks.append(Task(... PICKUP WHEAT ...))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py -k "want_coop_emits or pickup_goose_when or place_goose_when" -v`
Expected: 3 passed

- [ ] **Step 5: Full suite smoke on tasking + teacher v1/v2**

Run: `source .venv/bin/activate && python -m pytest tests/test_tasking.py tests/test_task_teacher_v1.py tests/test_task_teacher_v2.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: generate_tasks supports BUILD_COOP, PLACE, and shed PICKUP"
```

---

### Task 7: Create `agents/task_teacher_v4/main.py` + tests

**Files:**
- Create: `agents/task_teacher_v4/main.py`
- Create: `tests/test_task_teacher_v4.py`

**Interfaces:**
- `agent(obs, config=None) -> dict` — same contract
- `CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON")` (v2 list)
- `MAX_GEESE = 2`
- Sell list includes `EGG`
- Budget stack: hire → land → buy animal → seeds; wheat sell respects `wheat_reserved_for_feed`

- [ ] **Step 1: Write failing tests** in `tests/test_task_teacher_v4.py` (mirror v2/v3 `make_obs` helpers):

```python
def test_candidate_crops_match_v2():
    module = load_agent_module("task_teacher_v4")
    assert module.CANDIDATE_CROPS == ("WHEAT", "CARROT", "MELON")


def test_emits_buy_land_when_gate_would_pass():
    # Construct obs: NW only, money high, 3 hands, many plant tiles, late enough day.
    # Exact fixture: follow patterns in test_task_teacher_v2; assert ["BUY_LAND"] in market.


def test_feeds_unfed_goose_when_wheat_in_inventory():
    # Goose tile at farmer position, wheat in inventories[0], fed_today=False → farmer == ["FEED"]


def test_picks_up_goose_from_shed_when_empty_coop_exists():
    # Farmer on shed-access tile, shed GOOSE>=1, empty COOP elsewhere → ["PICKUP","GOOSE",1] or route toward shed


def test_simulator_full_episode_two_seats_done_and_finite():
    # Same as v3 short episode vs starter, 240 steps, both seats
```

Fill fixtures completely in the test file (copy `make_obs` from v2 tests; do not leave stubs).

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_task_teacher_v4.py -v`
Expected: FAIL — module missing

- [ ] **Step 3: Create agent**

Copy `agents/task_teacher_v2/main.py` → `agents/task_teacher_v4/main.py`, then:

1. Update docstring for v4 scope.
2. Import `should_buy_land`, `MAX` constants as needed, `wheat_reserved_for_feed`, `shed_access_tiles`.
3. Count geese / empty coop / plant tiles from `me["tiles"]`.
4. Call `generate_tasks(..., want_coop=..., shed=..., goose_in_any_inventory=..., wheat_needed_for_feed=...)`.
5. After hire reservation, call `should_buy_land(...)`; append `["BUY_LAND"]` and reduce `available_money`.
6. If geese_count < MAX_GEESE and (empty coop or want new coop) and money >= 300 after reserves: append `["BUY_ANIMAL","GOOSE"]`.
7. Sell: crops in `CANDIDATE_CROPS` plus `EGG`; for wheat, sell `max(0, shed["WHEAT"] - wheat_reserved_for_feed(geese_count, max(1, last_day-day)))`.
8. Extend `resolve_unit_action` for `FEED`, `CARE`, `BUILD_COOP`, `PLACE`, `PICKUP` (PICKUP needs quantity 1).

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_task_teacher_v4.py -v`
Expected: all pass (adjust fixtures only if assigner ambiguity — not agent scope)

- [ ] **Step 5: Full suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add agents/task_teacher_v4/main.py tests/test_task_teacher_v4.py
git commit -m "feat: add task_teacher_v4 with land purchase and Goose loop"
```

---

### Task 8: Packaging smoke

**Files:**
- Modify: `tests/test_package_agent.py`

- [ ] **Step 1: Write the failing test**

```python
def test_packaged_task_teacher_v4_runs_standalone_without_pythonpath():
    out_path = REPO_ROOT / "build" / "task_teacher_v4" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v4", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)
```

- [ ] **Step 2: Run test**

Run: `source .venv/bin/activate && python -m pytest tests/test_package_agent.py -k task_teacher_v4 -v`
Expected: PASS (auto-discovery) or diagnose packaging if FAIL

- [ ] **Step 3: Full suite + commit**

```bash
git add tests/test_package_agent.py
git commit -m "test: verify task_teacher_v4 packages and runs standalone"
```

---

### Task 9: Acceptance + evaluation gate

**Files:** none for code — scratch measurement script + docs updates.

- [ ] **Step 1: 100-episode acceptance** vs `starter` (seeds 70000–70099), assert DONE/finite, and count `BUY_LAND` / `BUY_ANIMAL` / `FEED` / `PICKUP` actions > 0 across episodes when money allows.

- [ ] **Step 2: 20-pair screen** vs `task_teacher_v2` seed 71000.

- [ ] **Step 3:** If CI wholly below 0.50 → stop, do not escalate. If above or straddling → 50-pair seed 72000.

- [ ] **Step 4: Regression** vs `roi_teacher_v3` + `starter` seed 73000.

- [ ] **Step 5: Record** in `docs/4_agent_version_log.md`, `docs/6_next_steps.md`, `README.md`, `docs/3_agent_strategy.md` (promote or honest non-promote). Update design doc status to approved/implemented.

- [ ] **Step 6: Final pytest + commit docs** (push only if user/plan requests).

Stop after Task 8 for human review before Task 9 if the user asks — default for this plan: **ask before Task 9** (same checkpoint as v3).

---

## Spec coverage self-check

| Spec requirement | Task |
| --- | --- |
| `shed_access_tiles` / PICKUP adjacency | Task 1, 6 |
| Wheat feed reserve | Task 2, 7 |
| TaskKinds | Task 3 |
| `should_buy_land` NE-only hire-then-land | Task 4 |
| FEED/CARE/HARVEST animals | Task 5 |
| BUILD_COOP / PLACE / PICKUP | Task 6 |
| Agent v4 + sell EGG + budget stack | Task 7 |
| Packaging | Task 8 |
| Evaluation + honesty rule | Task 9 |
| No fertilizer / no Cow-Sheep / immutable old agents | Global constraints |

## Placeholder scan

No TBD/TODO steps; constants locked; evaluation asks before run by default.
