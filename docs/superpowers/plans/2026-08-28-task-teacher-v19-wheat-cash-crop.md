# Task Teacher v19 — Wheat as a Cash Crop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make wheat a sellable cash crop — plant it to a tile target and sell the surplus above a feed reserve — closing the largest measured ladder revenue gap (opponents $1,090,522 vs our $0 across 78 episodes).

**Architecture:** Two coupled changes. A new `wheat_target_tiles` keyword parameter on `tasking.generate_tasks` (defaulting to `0`, which disables the rule) adds a wheat planting rule between the existing strawberry rule and the ROI pick. A new immutable agent `agents/task_teacher_v19/` — copied forward from `task_teacher_v17` — passes `wheat_target_tiles=20` and replaces v17's dead wheat sell gate with a feed-reserved surplus sell.

**Tech Stack:** Python 3.11, `kaggle-environments==1.32.4`, pytest. Run everything through the repo venv: `.venv/bin/python`. Shared library imports need `PYTHONPATH=src`.

## Global Constraints

- Design doc: `docs/superpowers/specs/2026-08-28-task-teacher-v19-wheat-cash-crop-design.md`. Read it before starting.
- **TDD is mandatory** (`superpowers:test-driven-development`): write the failing test, watch it fail for the right reason, then write the minimal code. No production code before a failing test.
- **`wheat_target_tiles` MUST default to `0`.** Every existing agent (`task_teacher_v2` … `v18`) must keep byte-identical task output. Task 2 is the regression guard for this and is not optional.
- **Agent versions are immutable.** Never edit `agents/task_teacher_v2` … `v18`. v19 is a new folder.
- `WHEAT_TARGET_TILES = 20` (total wheat tiles on the board, inclusive of the up-to-4 feed tiles — one shared `n_wheat` counter).
- `FEED_DAYS_BUFFER = 2` (matches the existing buy-side target `max(2, total_owned_animals * 2)`).
- Simulator is `1.32.4`; evaluation uses ladder-match config, which `scripts/run_tournament.py` already applies by default.
- Full suite must be green before Task 6's evaluation. Baseline is **592 passing**.

---

### Task 1: Add `wheat_target_tiles` to `generate_tasks`

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py:203-221` (signature), `:305-322` (crop-selection block)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `generate_tasks(..., wheat_target_tiles: int = 0)`. Task 2 asserts the default is inert; Task 3 passes `wheat_target_tiles=WHEAT_TARGET_TILES` from the v19 agent.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tasking.py`:

```python
def test_generate_tasks_plants_wheat_up_to_the_cash_crop_target():
    """Wheat is planted on empty tiles as a cash crop, not only for feed.

    Measured motivation: WHEAT is the opponents' single largest ladder
    revenue line ($1,090,522 across 78 episodes) and this agent family
    earns $0 from it, because wheat was only ever planted for animal feed
    (capped at 4 tiles). See docs/10_ladder_revenue_diagnosis.md.
    """
    tiles = [[None] * 10 for _ in range(10)]
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices={"WHEAT": 25.0, "CARROT": 35.0, "MELON": 250.0},
        candidate_crops=("WHEAT", "CARROT", "MELON"),
        wheat_target_tiles=3,
    )
    wheat_plants = [
        t for t in tasks
        if t.task_id.kind == TaskKind.PLANT and t.task_id.item == "WHEAT"
    ]
    assert len(wheat_plants) == 3


def test_generate_tasks_stops_planting_wheat_once_target_is_met():
    """Existing wheat tiles count toward the target, so a board already at
    target gets no new wheat -- the remaining tiles go to the ROI pick."""
    tiles = [[None] * 10 for _ in range(10)]
    for x in range(3):
        tiles[0][x] = {
            "kind": "PLANT", "crop": "WHEAT", "planted_day": 0,
            "watered_today": True, "consecutive_unwatered": 0, "yield_units": 0,
            "max_lifespan_step": -1, "fertilized_until_day": -1,
        }
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices={"WHEAT": 25.0, "CARROT": 35.0, "MELON": 250.0},
        candidate_crops=("WHEAT", "CARROT", "MELON"),
        wheat_target_tiles=3,
    )
    wheat_plants = [
        t for t in tasks
        if t.task_id.kind == TaskKind.PLANT and t.task_id.item == "WHEAT"
    ]
    assert wheat_plants == []


def test_generate_tasks_does_not_plant_wheat_that_cannot_mature_in_time():
    """The cash-crop rule respects the same season-horizon gate as every
    other planting decision -- a seed that can't mature is money burned."""
    tiles = [[None] * 10 for _ in range(10)]
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=28,  # WHEAT max_yield_day is 4; 28 + 4 > 29
        last_day=29,
        market_prices={"WHEAT": 25.0, "CARROT": 35.0, "MELON": 250.0},
        candidate_crops=("WHEAT", "CARROT", "MELON"),
        wheat_target_tiles=10,
    )
    wheat_plants = [
        t for t in tasks
        if t.task_id.kind == TaskKind.PLANT and t.task_id.item == "WHEAT"
    ]
    assert wheat_plants == []


def test_cash_crop_rule_does_not_break_the_feed_planting_path():
    """The feed rule runs first and must keep working with the cash-crop
    rule disabled -- animals starve if feed planting regresses."""
    tiles = [[None] * 10 for _ in range(10)]
    tasks = generate_tasks(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices={"WHEAT": 25.0, "CARROT": 35.0, "MELON": 250.0},
        candidate_crops=("WHEAT", "CARROT", "MELON"),
        wheat_needed_for_feed=True,
        wheat_target_tiles=0,
    )
    wheat_plants = [
        t for t in tasks
        if t.task_id.kind == TaskKind.PLANT and t.task_id.item == "WHEAT"
    ]
    assert len(wheat_plants) == 4  # the existing feed cap
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
.venv/bin/python -m pytest tests/test_tasking.py -k cash_crop_target -v
```

Expected: `TypeError: generate_tasks() got an unexpected keyword argument 'wheat_target_tiles'`.

- [ ] **Step 3: Add the parameter to the signature**

In `src/kaggriculture_lib/tasking.py`, add one line to `generate_tasks`'s signature, immediately after `sheep_in_any_inventory`:

```python
    sheep_in_any_inventory: bool = False,
    wheat_target_tiles: int = 0,
    max_feed_tasks: int | None = None,
```

Then extend the docstring's final paragraph (currently ending "...preserve the Goose path used by `task_teacher_v4`.") with:

```
    `wheat_target_tiles` defaults to 0, which disables the cash-crop wheat
    rule entirely and leaves task output byte-identical for every agent
    that does not pass it. That default is load-bearing: agent versions are
    immutable as files but read this shared module, so a behavioural change
    here rewrites frozen agents' evaluated behaviour retroactively (see
    docs/2_environment_notes.md's 2026-08-28 correction, where exactly that
    happened to task_teacher_v8).
```

- [ ] **Step 4: Add the planting rule**

In the crop-selection block (`src/kaggriculture_lib/tasking.py`, currently lines 305-322), insert an `elif` between the strawberry branch and the `else: crop = best` branch. The block becomes:

```python
                # Choose crop based on dynamic allocation rules
                crop = None
                if wheat_needed_for_feed and n_wheat < 4 and "WHEAT" in candidate_crops and economy.can_mature_in_time("WHEAT", day, last_day):
                    crop = "WHEAT"
                    n_wheat += 1
                else:
                    best = _best_feasible_crop(day, last_day, market_prices, candidate_crops)
                    if "STRAWBERRY" in candidate_crops and day >= 10 and n_strawberries < 12 and economy.can_ongoing_crop_reach_any_tick("STRAWBERRY", day, last_day):
                        crop = "STRAWBERRY"
                        n_strawberries += 1
                    elif (
                        n_wheat < wheat_target_tiles
                        and "WHEAT" in candidate_crops
                        and economy.can_mature_in_time("WHEAT", day, last_day)
                    ):
                        # Wheat as a cash crop, not just feed. Unlike MELON
                        # (~113 units of whole-game absorption, drained only
                        # ~1/day by the town centre), five town shops consume
                        # wheat, so its absorption is effectively unbounded and
                        # its price rises across the season.
                        crop = "WHEAT"
                        n_wheat += 1
                    else:
                        crop = best
                        if crop == "MELON":
                            n_melons += 1
                        elif crop == "STRAWBERRY":
                            n_strawberries += 1
                        elif crop == "WHEAT":
                            n_wheat += 1
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_tasking.py -k "cash_crop_target or mature_in_time" -v
```

Expected: all three PASS.

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: add wheat_target_tiles cash-crop planting rule to generate_tasks"
```

---

### Task 2: Frozen-agent regression guard

**Files:**
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: `generate_tasks(..., wheat_target_tiles: int = 0)` from Task 1.
- Produces: nothing consumed later. This task exists solely to prove Task 1 cannot alter frozen agents.

**Why this task is separate:** a reviewer could reasonably approve Task 1's new rule while rejecting an implementation that leaks into existing agents. This is the gate for that.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tasking.py`:

```python
def test_wheat_target_defaults_to_zero_leaving_existing_agents_unchanged():
    """The cash-crop rule must be inert unless explicitly requested.

    Agent versions are immutable as files but read this shared module, so a
    behavioural change here rewrites every frozen agent's evaluated
    behaviour retroactively. That is not hypothetical: on 2026-08-28,
    correcting economy.FARM_HAND_COST_MULT silently changed frozen
    task_teacher_v8 (docs/2_environment_notes.md). This asserts the default
    path is byte-identical, so v2..v18 keep the behaviour they were
    evaluated with.
    """
    tiles = [[None] * 10 for _ in range(10)]
    kwargs = dict(
        tiles=tiles,
        unlocked_quadrants=["NW"],
        day=0,
        last_day=29,
        market_prices={"WHEAT": 25.0, "CARROT": 35.0, "MELON": 250.0},
        candidate_crops=("WHEAT", "CARROT", "MELON"),
    )
    without_param = generate_tasks(**kwargs)
    explicit_zero = generate_tasks(**kwargs, wheat_target_tiles=0)

    assert [t.task_id for t in without_param] == [t.task_id for t in explicit_zero]
    # And the default plants no cash-crop wheat at all.
    assert not [
        t for t in without_param
        if t.task_id.kind == TaskKind.PLANT and t.task_id.item == "WHEAT"
    ]
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/test_tasking.py -k defaults_to_zero -v
```

Expected: PASS immediately (Task 1 already implemented the default correctly). This test is a guard, not a driver — if it FAILS, Task 1's default is wrong and must be fixed before continuing.

- [ ] **Step 3: Run the whole existing suite as the real regression check**

```bash
.venv/bin/python -m pytest -q
```

Expected: `592 passed` (the pre-existing baseline) plus 4 new tests from Task 1 and 1 from Task 2 = **597 passed**. Any pre-existing test that now fails means Task 1 leaked — fix Task 1, do not edit the failing test.

- [ ] **Step 4: Commit**

```bash
git add tests/test_tasking.py
git commit -m "test: guard that wheat_target_tiles default leaves frozen agents unchanged"
```

---

### Task 3: Create `task_teacher_v19` with the feed-reserved wheat sell

**Files:**
- Create: `agents/task_teacher_v19/main.py` (copied from `agents/task_teacher_v17/main.py`, then edited)
- Test: `tests/test_task_teacher_v19.py` (new)

**Interfaces:**
- Consumes: `generate_tasks(..., wheat_target_tiles=...)` from Task 1.
- Produces: module constants `WHEAT_TARGET_TILES = 20`, `FEED_DAYS_BUFFER = 2`, and `agent(obs, config)` — used by Tasks 4-6.

- [ ] **Step 1: Copy v17 forward**

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
mkdir -p agents/task_teacher_v19
cp agents/task_teacher_v17/main.py agents/task_teacher_v19/main.py
```

- [ ] **Step 2: Fix the header and constants**

In `agents/task_teacher_v19/main.py`, replace the module docstring (line 1-2, which wrongly says "v11" — a copy-forward artifact inherited from v17) with:

```python
"""Kaggriculture multi-tile task/route teacher agent, v19.

Extends `task_teacher_v17` with one variable: wheat becomes a cash crop
rather than animal feed only. Plants wheat to a total tile target and sells
the surplus above a feed reserve.

Measured motivation (docs/10_ladder_revenue_diagnosis.md, 78 real ladder
episodes): WHEAT is the opponents' single largest revenue line
($1,090,522) and this agent family earned $0 from it -- v17's wheat sell
branch is gated on owning zero animals, which never holds, and planting was
capped at 4 feed-only tiles. Unlike MELON (~113 units of whole-game
absorption, no town-shop demand), five shops consume wheat, so absorption
is effectively unbounded and its price rises across the season.

Design: docs/superpowers/specs/2026-08-28-task-teacher-v19-wheat-cash-crop-design.md
"""
```

Then update the constants block. `COW_COST`'s trailing comment currently reads `# 600`, which went stale when the library was corrected to the ladder's real `1.32.4` values on 2026-08-28:

```python
CANDIDATE_CROPS = ("WHEAT", "CARROT", "MELON", "STRAWBERRY")
DEFAULT_TURNS_PER_DAY = 24

MAX_GEESE = 4
MAX_COWS = 8
MAX_SHEEP = 4
MAX_FEED_ACTIONS_PER_DAY = 10

# Total wheat tiles on the board (inclusive of the up-to-4 feed tiles --
# one shared n_wheat counter). 20 tiles * ~0.8 units/tile/day ~= 16
# units/day ~= $640/day at the observed $41/unit ~= $16k/season, which
# brackets the opponents' measured ~$14k/game. This is the design's one
# tunable knob.
WHEAT_TARGET_TILES = 20
# Days of feed to keep unsold. Matches the existing buy-side target
# (max(2, total_owned_animals * 2)) so the reserve the agent buys up to and
# the reserve it refuses to sell below are the same number. Animals escape
# after two consecutive unfed days, so this is the smallest reserve that
# tolerates one missed delivery.
FEED_DAYS_BUFFER = 2

COW_COST = economy.ANIMALS["COW"]["cost"]      # 400 under 1.32.4
SHEEP_COST = economy.ANIMALS["SHEEP"]["cost"]  # 500
GOOSE_COST = economy.ANIMALS["GOOSE"]["cost"]  # 300
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_task_teacher_v19.py`:

```python
"""Tests for agents/task_teacher_v19 -- wheat as a cash crop."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

BOARD_SIZE = 10
V19_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "farmHandCostMult": 1}


def load_agent_module(name):
    spec = importlib.util.spec_from_file_location(
        f"agents_{name}_main", REPO_ROOT / "agents" / name / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_obs(*, day=0, hour=1, money=5000.0, farmer=(4, 4), tiles=None,
             shed=None, hands=None, hires_today=0, unlocked=None):
    tiles = tiles if tiles is not None else [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    return {
        "player": 0,
        "day": day,
        "hour": hour,
        "step": day * 24 + hour,
        "farms": [
            {
                "money": money,
                "tiles": tiles,
                "farmer": list(farmer),
                "hands": hands or [],
                "unlocked_quadrants": unlocked or ["NW"],
                "hires_today": hires_today,
            },
            {
                "money": money,
                "tiles": [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)],
                "farmer": [4, 4],
                "hands": [],
                "unlocked_quadrants": ["NW"],
                "hires_today": 0,
            },
        ],
        "market": {
            "inventory": {k: 10000 for k in
                          ("WHEAT", "CARROT", "MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "FERTILIZER")},
            "prices": {"WHEAT": 25, "CARROT": 35, "MELON": 250,
                       "STRAWBERRY": 120, "MILK": 160, "WOOL": 200,
                       "EGG": 50, "FERTILIZER": 100},
        },
        "town": {"unlocked_shops": []},
        "private": {
            "shed": shed or {},
            "seeds": {},
            "inventories": [{}],
        },
    }


def pasture_tile(animal="COW"):
    return {
        "kind": "PASTURE", "animal": animal, "placed_day": 0, "yield_units": 0,
        "fed_today": True, "consecutive_unfed": 0, "cared_today": True,
        "fertilizer_available": False, "pending_care_bonus": 0,
    }


def sell_orders(action, item):
    return [o for o in action["market"]
            if isinstance(o, (list, tuple)) and o and o[0] == "SELL" and o[1] == item]


def test_constants():
    module = load_agent_module("task_teacher_v19")
    assert module.WHEAT_TARGET_TILES == 20
    assert module.FEED_DAYS_BUFFER == 2


def test_sells_surplus_wheat_while_owning_animals():
    """The case v17 made unreachable: its wheat sell branch is gated on
    owning zero animals, and it always owns animals, so it sold $0 of wheat
    across 78 real ladder episodes."""
    module = load_agent_module("task_teacher_v19")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = pasture_tile("COW")  # 1 animal -> reserve = max(2, 1*2) = 2
    obs = make_obs(day=5, tiles=tiles, shed={"WHEAT": 30})
    action = module.agent(obs, V19_CONFIG)
    orders = sell_orders(action, "WHEAT")
    assert orders, "expected a wheat SELL order while owning animals"
    assert orders[0][2] == 28  # 30 held - 2 reserved


def test_never_sells_into_the_feed_reserve():
    """Animals escape after two consecutive unfed days; selling the buffer
    out from under them turns a revenue change into an animal-loss bug."""
    module = load_agent_module("task_teacher_v19")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = pasture_tile("COW")
    tiles[0][1] = pasture_tile("SHEEP")  # 2 animals -> reserve = 4
    obs = make_obs(day=5, tiles=tiles, shed={"WHEAT": 4})
    action = module.agent(obs, V19_CONFIG)
    assert sell_orders(action, "WHEAT") == []


def test_terminal_liquidation_still_sells_the_feed_reserve():
    """Unsold stock scores nothing, so the last-hours dump must ignore the
    reserve."""
    module = load_agent_module("task_teacher_v19")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = pasture_tile("COW")
    obs = make_obs(day=29, hour=22, tiles=tiles, shed={"WHEAT": 3})
    action = module.agent(obs, V19_CONFIG)
    orders = sell_orders(action, "WHEAT")
    assert orders and orders[0][2] == 3


def test_passes_wheat_target_to_generate_tasks():
    """Planting without selling only clogs the 100-item shed, and selling
    without planting has nothing to sell -- both halves must be wired."""
    module = load_agent_module("task_teacher_v19")
    obs = make_obs(day=0, money=5000.0)
    action = module.agent(obs, V19_CONFIG)
    assert action["farmer"], "agent returned no farmer action"
    # The planting rule is exercised end-to-end in the full-episode smoke
    # test (Task 5); here we assert the constant is actually consumed.
    src = (REPO_ROOT / "agents" / "task_teacher_v19" / "main.py").read_text()
    assert "wheat_target_tiles=WHEAT_TARGET_TILES" in src
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v19.py -v
```

Expected: `test_constants` FAILS with `AttributeError: module ... has no attribute 'WHEAT_TARGET_TILES'` if Step 2 was skipped; otherwise `test_sells_surplus_wheat_while_owning_animals` FAILS (`expected a wheat SELL order while owning animals`) because the copied v17 gate still requires zero animals.

- [ ] **Step 5: Replace the dead sell gate**

In `agents/task_teacher_v19/main.py`, replace the wheat sell block (copied from v17's lines 200-204):

```python
        # Sell wheat only if no animals need it for feed
        if (owned_cows == 0 and owned_sheep == 0 and owned_geese == 0):
            available = shed.get("WHEAT", 0)
            if available > 0:
                market_orders.append(["SELL", "WHEAT", available])
```

with:

```python
        # Sell wheat above a feed reserve. v17 gated this on owning zero
        # animals, which never holds, so it sold no wheat at all.
        feed_reserve = max(2, total_owned_animals * FEED_DAYS_BUFFER) if total_owned_animals else 0
        sellable = shed.get("WHEAT", 0) - feed_reserve
        if sellable > 0:
            market_orders.append(["SELL", "WHEAT", sellable])
```

- [ ] **Step 6: Wire the planting target**

In `agents/task_teacher_v19/main.py`, in the `generate_tasks(...)` call (copied from v17's line 158), add one keyword argument after `sheep_in_any_inventory=sheep_in_any_inventory,`:

```python
        sheep_in_any_inventory=sheep_in_any_inventory,
        wheat_target_tiles=WHEAT_TARGET_TILES,
        max_feed_tasks=MAX_FEED_ACTIONS_PER_DAY,
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v19.py -v
```

Expected: all 5 PASS.

- [ ] **Step 8: Commit**

```bash
git add agents/task_teacher_v19/main.py tests/test_task_teacher_v19.py
git commit -m "feat: add task_teacher_v19 -- wheat as a cash crop with feed reserve"
```

---

### Task 4: Packaging verification

**Files:**
- Modify: `tests/test_package_agent.py`

**Interfaces:**
- Consumes: `agents/task_teacher_v19/main.py` from Task 3.
- Produces: a verified `build/task_teacher_v19/main.py` suitable for submission.

**Why this matters:** the 2026-08-06 ladder submission errored at import because packaging bundled an unrelated module. Every agent gets a standalone check.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_package_agent.py`, next to the existing `test_packaged_task_teacher_v3_runs_standalone_without_pythonpath`:

```python
def test_packaged_task_teacher_v19_runs_standalone_without_pythonpath():
    """v19 adds the wheat cash-crop path on top of the same shared modules
    v17 already packages correctly."""
    out_path = REPO_ROOT / "build" / "task_teacher_v19" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v19", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/test_package_agent.py -k v19 -v
```

Expected: PASS. If it FAILS with an import error naming a `replay_*` module, packaging has regressed — see `docs/4_agent_version_log.md`'s 2026-08-06 incident.

- [ ] **Step 3: Confirm only the needed modules are bundled**

```bash
grep -oE "_register_shared_module\('kaggriculture_lib\.[a-z_]+'" build/task_teacher_v19/main.py
```

Expected exactly two lines: `kaggriculture_lib.economy` and `kaggriculture_lib.tasking`. Any `replay_*` module means the packaging scope fix regressed.

- [ ] **Step 4: Commit**

```bash
git add tests/test_package_agent.py
git commit -m "test: verify task_teacher_v19 packages and runs standalone"
```

---

### Task 5: Full-episode behavioural smoke test

**Files:**
- Modify: `tests/test_task_teacher_v19.py`

**Interfaces:**
- Consumes: `agents/task_teacher_v19/main.py` from Task 3.
- Produces: evidence the two halves work together in a real simulator run — the unit tests above cannot show that.

**Why this task is separate:** `docs/4_agent_version_log.md`'s recorded lesson from v2 is that synthetic unit tests validated every function correctly while a runaway-hiring bug and a performance bug were both invisible until a real full-length run. Full-episode smoke runs are not optional here.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_task_teacher_v19.py`:

```python
def test_full_episode_sells_wheat_and_completes():
    """End-to-end: v19 must actually realise wheat revenue in a real
    episode, not merely be capable of emitting the order.

    Guards the coupling: the planting rule (shared library) and the sell
    rule (agent) are in different files, and either alone produces zero
    wheat revenue.
    """
    from kaggle_environments import make

    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "startingMoney": 3000, "farmHandCostMult": 1},
        debug=True,
    )
    env.run(["agents/task_teacher_v19/main.py", "starter"])

    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final), [s.status for s in final]

    wheat_sold = 0
    wheat_bought = 0
    wheat_planted = 0
    for step in env.steps:
        action = step[0].action
        if not isinstance(action, dict):
            continue
        for order in action.get("market") or []:
            if not (isinstance(order, (list, tuple)) and len(order) > 2):
                continue
            if order[0] == "SELL" and order[1] == "WHEAT":
                wheat_sold += int(order[2])
            elif order[0] == "BUY_PRODUCT" and order[1] == "WHEAT":
                wheat_bought += int(order[2])
        farmer = action.get("farmer")
        if isinstance(farmer, list) and len(farmer) > 1 and farmer[0] == "PLANT" and farmer[1] == "WHEAT":
            wheat_planted += 1

    assert wheat_planted > 0, "v19 never planted wheat as a cash crop"
    assert wheat_sold > 0, "v19 never sold wheat -- the two halves are not wired together"
    print(f"v19 wheat planted={wheat_planted} sold={wheat_sold} bought={wheat_bought}")

    # Growing our own feed should reduce market purchases: the existing
    # BUY_PRODUCT top-up is gated on total_wheat < animals*2, so it stops
    # firing once the farm supplies itself. Same seed, same opponent.
    env17 = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "startingMoney": 3000, "farmHandCostMult": 1},
        debug=True,
    )
    env17.run(["agents/task_teacher_v17/main.py", "starter"])
    v17_bought = 0
    for step in env17.steps:
        action = step[0].action
        if not isinstance(action, dict):
            continue
        for order in action.get("market") or []:
            if (isinstance(order, (list, tuple)) and len(order) > 2
                    and order[0] == "BUY_PRODUCT" and order[1] == "WHEAT"):
                v17_bought += int(order[2])
    print(f"v17 wheat bought={v17_bought}")
    assert wheat_bought <= v17_bought, (
        f"v19 bought more feed wheat ({wheat_bought}) than v17 ({v17_bought}) "
        "despite growing its own"
    )
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v19.py -k full_episode -v -s
```

Expected: PASS, with the printed line showing `planted > 0` and `sold > 0`. This takes roughly 30-60s.

If `wheat_sold == 0` but `wheat_planted > 0`, the sell rule (Task 3 Step 5) is wrong. If both are 0, the planting wiring (Task 3 Step 6) is wrong.

- [ ] **Step 3: Run the whole suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: **604 passed** (592 baseline + 4 from Task 1 + 1 from Task 2 + 5 from Task 3 + 1 from Task 4 + 1 from this task). If the total differs but nothing fails, that is fine -- the binding requirement is **zero failures**.

- [ ] **Step 4: Commit**

```bash
git add tests/test_task_teacher_v19.py
git commit -m "test: full-episode smoke proving v19 plants and sells wheat"
```

---

### Task 6: Evaluation and promotion decision

**Files:**
- Modify: `docs/4_agent_version_log.md` (new `task_teacher_v19` entry)
- Modify: `docs/6_next_steps.md` (current recommendation)

**Interfaces:**
- Consumes: `agents/task_teacher_v19/main.py` from Task 3.
- Produces: a promote / do-not-promote decision. **No Kaggle submission happens in this plan.**

**Run every command sequentially, never concurrently.** `docs/4_agent_version_log.md` records a false timing-regression alarm caused by CPU contention from two simultaneous simulation jobs.

- [ ] **Step 1: 100-episode acceptance gate**

Write `/tmp/v19_acceptance.py`:

```python
"""100-episode acceptance gate for task_teacher_v19."""
import math, sys, time
from pathlib import Path

REPO_ROOT = Path("/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture")
sys.path.insert(0, str(REPO_ROOT / "src"))
from kaggle_environments import make  # noqa: E402

N, BASE_SEED, STEPS = 100, 130000, 720
CFG = {"episodeSteps": STEPS, "startingMoney": 3000, "farmHandCostMult": 1}

done = finite = 0
kinds = {"PLANT": 0, "WATER": 0, "HARVEST": 0, "DIG": 0}
wheat_sold = wheat_planted = melon_sold = 0
latencies = []

for i in range(N):
    env = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED + i}, debug=True)
    t0 = time.time()
    env.run(["agents/task_teacher_v19/main.py", "starter"])
    latencies.append((time.time() - t0) / STEPS * 1000)
    final = env.steps[-1]
    done += all(s.status == "DONE" for s in final)
    finite += all(s.reward is not None and math.isfinite(s.reward) for s in final)
    for step in env.steps:
        a = step[0].action
        if not isinstance(a, dict):
            continue
        f = a.get("farmer")
        if isinstance(f, list) and f:
            if f[0] in kinds:
                kinds[f[0]] += 1
            if f[0] == "PLANT" and len(f) > 1 and f[1] == "WHEAT":
                wheat_planted += 1
        for o in a.get("market") or []:
            if isinstance(o, (list, tuple)) and len(o) > 2 and o[0] == "SELL":
                if o[1] == "WHEAT":
                    wheat_sold += int(o[2])
                elif o[1] == "MELON":
                    melon_sold += int(o[2])

print(f"DONE: {done}/{N}   finite: {finite}/{N}")
print(f"action kinds: {kinds}")
print(f"wheat planted/ep: {wheat_planted/N:.1f}   wheat sold/ep: {wheat_sold/N:.1f}   melon sold/ep: {melon_sold/N:.1f}")
print(f"median latency ms/turn: {sorted(latencies)[len(latencies)//2]:.2f}")

a = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED}, debug=False)
a.run(["agents/task_teacher_v19/main.py", "starter"])
b = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED}, debug=False)
b.run(["agents/task_teacher_v19/main.py", "starter"])
ra = (a.steps[-1][0].reward, a.steps[-1][1].reward)
rb = (b.steps[-1][0].reward, b.steps[-1][1].reward)
print(f"determinism: {ra} vs {rb} -> {'IDENTICAL' if ra == rb else 'MISMATCH'}")
```

Run it:

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
.venv/bin/python /tmp/v19_acceptance.py
```

**Acceptance criteria — all must hold:**
- `DONE: 100/100` and `finite: 100/100`
- `determinism: ... -> IDENTICAL`
- `wheat sold/ep > 0` (the whole point of the version)
- median latency well under 1000 ms/turn (`actTimeout` is 1s)

If any fails, stop and fix before evaluating. Record the numbers — Step 5 needs them.

- [ ] **Step 2: 20-pair screen vs `task_teacher_v17`**

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v19/main.py agents/task_teacher_v17/main.py \
  --episodes 20 --episode-steps 720 --seed 131000
```

Read `hoeffding_95%_ci` from the output and apply the authoritative rule:
- CI wholly **above** 0.50 → go to Step 3.
- CI **straddles** 0.50 → go to Step 3 (escalate on ambiguity).
- CI wholly **below** 0.50 → **stop.** Not promoted. Skip to Step 5 and record the screen as the outcome. Do not re-run on a friendlier seed.

- [ ] **Step 3: 50-pair promotion gate (only if Step 2 said escalate)**

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v19/main.py agents/task_teacher_v17/main.py \
  --episodes 50 --episode-steps 720 --seed 132000
```

Promotion requires the CI **wholly above 0.50**. If it straddles, add 25-pair blocks at fresh seeds per the authoritative protocol. If it lands wholly below, v19 is not promoted.

- [ ] **Step 4: Regression screens (only if Step 3 promoted)**

Run these one at a time:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v19/main.py agents/task_teacher_v16/main.py \
  --episodes 20 --episode-steps 720 --seed 133000
```

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v19/main.py starter \
  --episodes 20 --episode-steps 720 --seed 133000
```

- [ ] **Step 5: Record the result honestly**

Append a `## task_teacher_v19` entry to `docs/4_agent_version_log.md` following the format of the existing `task_teacher_v5` entry: date, config diff from v17, the acceptance table from Step 1, a paired-evaluation table (matchup / pairs / win rate / mean margin / Hoeffding CI), outcome, and lesson.

Include this caveat verbatim — it is why v19's numbers are not comparable to older entries:

```
- **Evaluation caveat:** v19 is the first version evaluated under the
  corrected `1.32.4` simulator (validated against real ladder prices,
  299/299 exact matches). Every prior promotion number in this log was
  measured under the miscalibrated `1.29.3` constants, which under-punish
  premium-good glut ~4x. v19's figures are not directly comparable to them.
```

Then update `docs/6_next_steps.md`'s current recommendation with the outcome and the next priority.

- [ ] **Step 6: Commit**

```bash
git add docs/4_agent_version_log.md docs/6_next_steps.md
git commit -m "docs: record task_teacher_v19 evaluation result"
git push origin main
```

---

## Post-Plan Notes

**Not in scope, deliberately** (see design §6): melon over-production (~200 grown into a ~113-unit market), sale metering / the 100-unit day-13 dump, the 26-melon shed overflow, fertilizer collection (`COLLECT_FERTILIZER` is not a `TaskKind`; opponents earn $421k, we earn $0), and the feed-starvation defect that rejected v18.

**If v19 promotes,** the natural next version is fertilizer collection — it is unclaimed revenue like wheat, rather than a zero-sum melon race.

**If v19 does not promote,** check the acceptance telemetry first: if `wheat sold/ep` is high but the win rate dropped, `WHEAT_TARGET_TILES = 20` is displacing too much melon. Lower it to 12 (matching the strawberry target) and re-run Step 2 before abandoning the approach.
