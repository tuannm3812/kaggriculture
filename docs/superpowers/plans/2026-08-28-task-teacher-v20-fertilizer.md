# Task Teacher v20 — Fertilizer Collection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect and sell the fertilizer our animals already produce, closing a measured $421,761-across-78-episodes revenue line we currently score zero on.

**Architecture:** Three small pieces. `COLLECT_FERTILIZER` joins `tasking.TaskKind`; a new `collect_fertilizer: bool = False` parameter on `generate_tasks` emits that task at `PriorityTier.OPTIONAL` for animal tiles holding uncollected fertilizer; a new immutable agent `agents/task_teacher_v20/` (copy-forward of `task_teacher_v17`) enables it and dispatches the action. **No sell logic changes** — `task_teacher_v17/main.py:206` already sells `FERTILIZER`; it has simply never had any.

**Tech Stack:** Python 3.11, `kaggle-environments==1.32.4`, pytest. Run everything through the repo venv: `.venv/bin/python`. Shared-library imports need `PYTHONPATH=src`.

## Global Constraints

- Design doc: `docs/superpowers/specs/2026-08-28-task-teacher-v20-fertilizer-design.md`. Read it before starting.
- **TDD is mandatory** (`superpowers:test-driven-development`): write the failing test, watch it fail for the right reason, then write the minimal code. No production code before a failing test.
- **`collect_fertilizer` MUST default to `False`.** Every existing agent (`task_teacher_v2` … `v19`) must keep byte-identical task output. Task 2 is the regression guard and is not optional.
- **The task MUST be emitted at `PriorityTier.OPTIONAL`.** This is the design's load-bearing property — it is what stops fertilizer displacing watering, feeding, harvesting or planting, which is exactly how `task_teacher_v19` failed. Assert it explicitly.
- **Agent versions are immutable.** Never edit `agents/task_teacher_v2` … `v19`. v20 is a new folder.
- Simulator is `1.32.4`; `scripts/run_tournament.py` already applies ladder-match config by default.
- Full suite must be green before Task 5's evaluation. Baseline is **605 passing**.

---

### Task 1: Emit `COLLECT_FERTILIZER` tasks from `generate_tasks`

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py` — `TaskKind` enum (~line 20-30), `generate_tasks` signature (~line 215-222), animal-tile branch (~line 458-497)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `TaskKind.COLLECT_FERTILIZER`, and `generate_tasks(..., collect_fertilizer: bool = False)`. Task 2 asserts the default is inert; Task 3 passes `collect_fertilizer=True` from the v20 agent.

#### Structural note — read before writing code

The animal-tile branch is an **`if / elif / elif` chain**:

```python
elif isinstance(tile, dict) and "animal" in tile:
    if not tile["fed_today"]:              # FEED
    elif tile.get("yield_units", 0) > 0:   # HARVEST
    elif not tile["cared_today"]:          # CARE
```

so at most **one** task is generated per animal tile per turn. The new
fertilizer block must be a **separate `if`, not another `elif`** — appended
after that chain, still inside the animal branch.

If it were an `elif`, generation would be gated on the animal being fed
**and** having no harvestable yield **and** already cared for, which would
suppress it on most turns and could make the whole version inert. The
design's intent is that the task is always *generated* when fertilizer is
available, and `PriorityTier.OPTIONAL` decides whether it gets *assigned*.
Multiple tasks may share a target tile — `TaskId` differs by `kind`, so
`joint_assign` handles them independently.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tasking.py`. Use the fixtures this file already
establishes (`BOARD_SIZE`, `CANDIDATE_CROPS`, `BASE_PRICES`, `make_tiles`)
rather than hand-rolling board data or repeating literals:

```python
def make_animal_tile(
    animal="COW",
    *,
    fed_today=True,
    cared_today=True,
    yield_units=0,
    fertilizer_available=True,
    consecutive_unfed=0,
):
    """An occupied animal structure. Defaults are a fully-tended animal with
    nothing to harvest, so only the fertilizer rule can fire."""
    return {
        "kind": "PASTURE",
        "animal": animal,
        "placed_day": 0,
        "yield_units": yield_units,
        "fed_today": fed_today,
        "consecutive_unfed": consecutive_unfed,
        "cared_today": cared_today,
        "fertilizer_available": fertilizer_available,
        "pending_care_bonus": 0,
    }


def _collect_tasks(tasks):
    return [t for t in tasks if t.task_id.kind == TaskKind.COLLECT_FERTILIZER]


def _generate_with_animal(tile, **kwargs):
    return generate_tasks(
        tiles=make_tiles({(1, 1): tile}),
        unlocked_quadrants=["NW"],
        day=5,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
        **kwargs,
    )


def test_generate_tasks_collects_available_fertilizer():
    """Every surviving animal makes 1 fertilizer available each end-of-day,
    fed or not. Opponents earned $421,761 across 78 ladder episodes selling
    it; this agent family earns $0 because COLLECT_FERTILIZER was never
    implemented. See docs/10_ladder_revenue_diagnosis.md.
    """
    tasks = _generate_with_animal(make_animal_tile(), collect_fertilizer=True)
    collect = _collect_tasks(tasks)
    assert len(collect) == 1
    assert collect[0].target == (1, 1)


def test_collect_fertilizer_task_is_optional_tier():
    """Load-bearing: OPTIONAL (tier 4) is what stops fertilizer displacing
    watering, feeding, harvesting or planting. task_teacher_v19 lost 0/20
    pairs by displacing higher-value work; this tier is the fix.
    """
    tasks = _generate_with_animal(make_animal_tile(), collect_fertilizer=True)
    assert _collect_tasks(tasks)[0].priority_tier == PriorityTier.OPTIONAL


def test_no_collect_task_when_fertilizer_not_available():
    """fertilizer_available is a boolean, not a counter -- once collected it
    stays false until the next end-of-day refresh."""
    tasks = _generate_with_animal(
        make_animal_tile(fertilizer_available=False), collect_fertilizer=True
    )
    assert _collect_tasks(tasks) == []


def test_collect_task_generated_even_when_animal_also_needs_feeding():
    """The fertilizer rule is a separate `if`, not another `elif` in the
    FEED/HARVEST/CARE chain. If it were chained it would only fire on a
    fed, fully-cared, nothing-to-harvest animal -- suppressing it on most
    turns. Generation is unconditional; PriorityTier.OPTIONAL decides
    whether it actually gets assigned.
    """
    tasks = _generate_with_animal(
        make_animal_tile(fed_today=False), collect_fertilizer=True
    )
    kinds = {t.task_id.kind for t in tasks}
    assert TaskKind.FEED in kinds
    assert TaskKind.COLLECT_FERTILIZER in kinds


def test_no_collect_task_for_empty_structure():
    """BUILD_COOP/BUILD_PASTURE create {"kind": ...} with no "animal" key,
    and an escaped animal's tile is reset the same way, so an unoccupied
    structure must never generate a collection task."""
    tasks = _generate_with_animal({"kind": "PASTURE"}, collect_fertilizer=True)
    assert _collect_tasks(tasks) == []


def test_no_collect_task_for_a_plant_tile():
    """Crops never produce fertilizer. This is currently guaranteed by the
    branch ordering (a PLANT tile is handled earlier in the if/elif chain
    and never reaches the animal branch), so the test guards against a
    future restructure quietly breaking that.
    """
    plant = make_plant_tile("MELON", planted_day=0, watered_today=True)
    plant["fertilizer_available"] = True  # nonsense state, must still be ignored
    tasks = _generate_with_animal(plant, collect_fertilizer=True)
    assert _collect_tasks(tasks) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
.venv/bin/python -m pytest tests/test_tasking.py -k fertilizer -v
```

Expected: FAIL with `AttributeError: COLLECT_FERTILIZER` (the enum member
does not exist yet) or `TypeError: generate_tasks() got an unexpected
keyword argument 'collect_fertilizer'`.

- [ ] **Step 3: Add the enum member**

In `src/kaggriculture_lib/tasking.py`, add one line to `TaskKind`:

```python
    PICKUP = "PICKUP"
    COLLECT_FERTILIZER = "COLLECT_FERTILIZER"
```

- [ ] **Step 4: Add the parameter**

Add one line to `generate_tasks`'s signature, immediately after
`wheat_target_tiles`:

```python
    wheat_target_tiles: int = 0,
    collect_fertilizer: bool = False,
    max_feed_tasks: int | None = None,
```

Then extend the docstring with:

```
    `collect_fertilizer` defaults to False, which suppresses the
    COLLECT_FERTILIZER rule entirely and leaves task output byte-identical
    for every agent that does not pass it. That default is load-bearing:
    agent versions are immutable as files but read this shared module, so a
    behavioural change here rewrites frozen agents' evaluated behaviour
    retroactively (see docs/2_environment_notes.md's 2026-08-28 correction,
    where exactly that happened to task_teacher_v8).
```

- [ ] **Step 5: Add the generation rule**

Append this **as a separate `if`** at the end of the animal-tile branch —
after the `elif not tile["cared_today"]:` block closes, at the same
indentation as that chain's opening `if not tile["fed_today"]:`:

```python
                if collect_fertilizer and tile.get("fertilizer_available"):
                    # Separate `if`, not another `elif`: the FEED/HARVEST/CARE
                    # chain emits at most one task per tile per turn, and
                    # chaining this would suppress it on most turns. Generation
                    # is unconditional; OPTIONAL tier decides assignment.
                    tasks.append(
                        Task(
                            task_id=TaskId(kind=TaskKind.COLLECT_FERTILIZER, x=x, y=y),
                            target=(x, y),
                            priority_tier=PriorityTier.OPTIONAL,
                            deadline_step=None,
                            expected_value=0.0,
                            action_cost=1,
                        )
                    )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_tasking.py -k fertilizer -v
```

Expected: all 6 PASS.

- [ ] **Step 7: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: emit COLLECT_FERTILIZER tasks at OPTIONAL tier"
```

---

### Task 2: Frozen-agent regression guard

**Files:**
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: `generate_tasks(..., collect_fertilizer: bool = False)` from Task 1.
- Produces: nothing consumed later. This task exists solely to prove Task 1 cannot alter frozen agents.

**Why this is a separate task:** a reviewer could reasonably approve Task 1's new rule while rejecting an implementation that leaks into existing agents. This is the gate for that, and the leak is not hypothetical — correcting `economy.FARM_HAND_COST_MULT` on 2026-08-28 silently changed frozen `task_teacher_v8`.

- [ ] **Step 1: Write the guard test**

Append to `tests/test_tasking.py`:

```python
def test_collect_fertilizer_defaults_to_off_leaving_existing_agents_unchanged():
    """The fertilizer rule must be inert unless explicitly requested.

    Agent versions are immutable as files but read this shared module, so a
    behavioural change here rewrites every frozen agent's evaluated
    behaviour retroactively. On 2026-08-28 correcting
    economy.FARM_HAND_COST_MULT silently changed frozen task_teacher_v8
    (docs/2_environment_notes.md). This asserts the default path is
    unchanged, so v2..v19 keep the behaviour they were evaluated with.
    """
    tile = make_animal_tile(fertilizer_available=True)
    kwargs = dict(
        tiles=make_tiles({(1, 1): tile}),
        unlocked_quadrants=["NW"],
        day=5,
        last_day=29,
        market_prices=BASE_PRICES,
        candidate_crops=CANDIDATE_CROPS,
    )
    without_param = generate_tasks(**kwargs)
    explicit_false = generate_tasks(**kwargs, collect_fertilizer=False)

    assert [t.task_id for t in without_param] == [t.task_id for t in explicit_false]
    assert _collect_tasks(without_param) == []
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/test_tasking.py -k defaults_to_off -v
```

Expected: PASS immediately (Task 1 already implemented the default
correctly). This is a guard, not a driver — if it FAILS, Task 1's default is
wrong and must be fixed before continuing.

- [ ] **Step 3: Run the whole suite as the real regression check**

```bash
.venv/bin/python -m pytest -q
```

Expected: **612 passed** (605 baseline + 6 from Task 1 + 1 here), ZERO
failures. Any pre-existing test that now fails means Task 1 leaked — fix
Task 1, do not edit the failing test.

- [ ] **Step 4: Commit**

```bash
git add tests/test_tasking.py
git commit -m "test: guard that collect_fertilizer default leaves frozen agents unchanged"
```

---

### Task 3: Create `task_teacher_v20`

**Files:**
- Create: `agents/task_teacher_v20/main.py` (copied from `agents/task_teacher_v17/main.py`, then edited)
- Create: `tests/test_task_teacher_v20.py`
- Modify: `tests/test_package_agent.py`

**Interfaces:**
- Consumes: `TaskKind.COLLECT_FERTILIZER` and `generate_tasks(..., collect_fertilizer=...)` from Task 1.
- Produces: `agents/task_teacher_v20/main.py` with `agent(obs, config)` — used by Tasks 4-5.

- [ ] **Step 1: Copy v17 forward**

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
mkdir -p agents/task_teacher_v20
cp agents/task_teacher_v17/main.py agents/task_teacher_v20/main.py
```

- [ ] **Step 2: Fix the header and the stale COW_COST comment**

Replace the module docstring (line 1-2, which wrongly says "v11" — a
copy-forward artifact inherited from v17) with:

```python
"""Kaggriculture multi-tile task/route teacher agent, v20.

Extends `task_teacher_v17` with one variable: collect the fertilizer our
animals already produce, and sell it.

Measured motivation (docs/10_ladder_revenue_diagnosis.md, 78 real ladder
episodes): opponents earned $421,761 selling FERTILIZER (~$5.4k/game) and
this agent family earned $0 -- COLLECT_FERTILIZER was never implemented,
not even as a TaskKind. v17 already sells FERTILIZER, so only collection
was missing.

Collection is emitted at PriorityTier.OPTIONAL so it can never displace
watering, feeding, harvesting or planting. That is deliberate:
`task_teacher_v19` lost 0/20 pairs by displacing Melon on tiles still in
their high-value range. Fertilizer costs no tiles at all -- only spare
unit-actions.

Design: docs/superpowers/specs/2026-08-28-task-teacher-v20-fertilizer-design.md
"""
```

`COW_COST`'s trailing comment reads `# 600`, which went stale when the
library was corrected to the ladder's real `1.32.4` values on 2026-08-28.
Fix it in this copy:

```python
COW_COST = economy.ANIMALS["COW"]["cost"]      # 400 under 1.32.4
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_task_teacher_v20.py`:

```python
"""Tests for agents/task_teacher_v20 -- fertilizer collection."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

BOARD_SIZE = 10
V20_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "farmHandCostMult": 1}


def load_agent_module(name):
    spec = importlib.util.spec_from_file_location(
        f"agents_{name}_main", REPO_ROOT / "agents" / name / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_enables_fertilizer_collection():
    """Planting the rule in the library does nothing unless the agent turns
    it on -- the parameter defaults to False."""
    src = (REPO_ROOT / "agents" / "task_teacher_v20" / "main.py").read_text()
    assert "collect_fertilizer=True" in src


def test_agent_dispatches_the_collect_action():
    """A generated task is inert unless the agent can turn it into the
    simulator action string."""
    src = (REPO_ROOT / "agents" / "task_teacher_v20" / "main.py").read_text()
    assert 'return ["COLLECT_FERTILIZER"]' in src


def test_full_episode_collects_and_sells_fertilizer():
    """End-to-end proof. v17 already sells FERTILIZER (main.py:206), so
    collection alone should produce sale revenue.

    If this fails with zero fertilizer, the OPTIONAL-tier risk recorded in
    the design (Sec 5) has materialised -- units are labour-saturated and the
    task never gets assigned. Report that as a finding; do NOT raise the
    tier to force a pass.
    """
    from kaggle_environments import make

    env = make(
        "kaggriculture",
        configuration={
            "episodeSteps": 720, "startingMoney": 3000, "farmHandCostMult": 1,
            "seed": 140000,
        },
        debug=True,
    )
    env.run(["agents/task_teacher_v20/main.py", "starter"])

    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final), [s.status for s in final]

    collected = 0
    sold = 0
    for step in env.steps:
        action = step[0].action
        if not isinstance(action, dict):
            continue
        units = [action.get("farmer")] + list(action.get("hands") or [])
        for act in units:
            if isinstance(act, list) and act and act[0] == "COLLECT_FERTILIZER":
                collected += 1
        for order in action.get("market") or []:
            if (isinstance(order, (list, tuple)) and len(order) > 2
                    and order[0] == "SELL" and order[1] == "FERTILIZER"):
                sold += int(order[2])

    print(f"v20 fertilizer collected={collected} sold={sold}")
    assert collected > 0, (
        "v20 never collected fertilizer -- OPTIONAL tier may never be reached"
    )
    assert sold > 0, "v20 collected fertilizer but never sold any"
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v20.py -v -s
```

Expected: `test_agent_enables_fertilizer_collection` FAILS (the copied v17
does not pass `collect_fertilizer=True`).

- [ ] **Step 5: Enable collection in the agent**

In `agents/task_teacher_v20/main.py`, in the `generate_tasks(...)` call, add
one keyword argument after `sheep_in_any_inventory=sheep_in_any_inventory,`:

```python
        sheep_in_any_inventory=sheep_in_any_inventory,
        collect_fertilizer=True,
        max_feed_tasks=MAX_FEED_ACTIONS_PER_DAY,
```

- [ ] **Step 6: Dispatch the action**

In the same file's `resolve_unit_action`, add a branch alongside the
existing `TaskKind.CARE` one:

```python
        if task_id.kind == TaskKind.CARE:
            return ["CARE"]
        if task_id.kind == TaskKind.COLLECT_FERTILIZER:
            return ["COLLECT_FERTILIZER"]
```

- [ ] **Step 7: Add the packaging test**

Append to `tests/test_package_agent.py`, next to the sibling agent tests:

```python
def test_packaged_task_teacher_v20_runs_standalone_without_pythonpath():
    """v20 adds fertilizer collection on top of the same shared modules
    v17 already packages correctly."""
    out_path = REPO_ROOT / "build" / "task_teacher_v20" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v20", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v20.py tests/test_package_agent.py -v -s
```

Expected: all PASS, with the printed line showing `collected > 0` and
`sold > 0`.

- [ ] **Step 9: Confirm packaging bundles only what it should**

```bash
grep -oE "_register_shared_module\('kaggriculture_lib\.[a-z_]+'" build/task_teacher_v20/main.py
```

Expected exactly two lines: `kaggriculture_lib.economy` and
`kaggriculture_lib.tasking`. Any `replay_*` module means the packaging
scope fix regressed — see `docs/4_agent_version_log.md`'s 2026-08-06
incident, where exactly that broke a live submission.

- [ ] **Step 10: Run the whole suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: **616 passed** (612 after Task 2, plus 3 from this task's agent
tests and 1 packaging test), ZERO failures.

- [ ] **Step 11: Commit**

```bash
git add agents/task_teacher_v20/main.py tests/test_task_teacher_v20.py tests/test_package_agent.py
git commit -m "feat: add task_teacher_v20 -- collect and sell animal fertilizer"
```

---

### Task 4: Measure the labour cost

**Files:**
- Test: `tests/test_task_teacher_v20.py`

**Interfaces:**
- Consumes: `agents/task_teacher_v20/main.py` from Task 3.
- Produces: evidence that collection did not displace higher-priority work — the specific risk this design exists to avoid.

**Why this is a separate task:** Task 3 proves fertilizer is collected. It does not prove collection was *free*. `task_teacher_v19` was rejected for exactly this blind spot: it demonstrably sold wheat, and still lost every pair, because nobody measured what the new work displaced. A reviewer could approve Task 3 and reject this.

- [ ] **Step 1: Write the test**

Append to `tests/test_task_teacher_v20.py`:

```python
def test_collection_does_not_displace_higher_priority_work():
    """OPTIONAL tier must mean 'spare labour only'.

    task_teacher_v19 sold wheat successfully and still lost 0/20 pairs,
    because the new work displaced Melon. Selling fertilizer is worthless if
    it costs us waterings (crops die) or feedings (animals escape). Same
    seed and opponent for both agents, so the comparison is paired.
    """
    from kaggle_environments import make

    def run(agent_path):
        env = make(
            "kaggriculture",
            configuration={
                "episodeSteps": 720, "startingMoney": 3000,
                "farmHandCostMult": 1, "seed": 140000,
            },
            debug=True,
        )
        env.run([agent_path, "starter"])
        counts = {"WATER": 0, "FEED": 0, "HARVEST": 0, "PLANT": 0}
        for step in env.steps:
            action = step[0].action
            if not isinstance(action, dict):
                continue
            for act in [action.get("farmer")] + list(action.get("hands") or []):
                if isinstance(act, list) and act and act[0] in counts:
                    counts[act[0]] += 1
        return counts, env.steps[-1][0].reward

    v20_counts, v20_reward = run("agents/task_teacher_v20/main.py")
    v17_counts, v17_reward = run("agents/task_teacher_v17/main.py")
    print(f"v20 {v20_counts} reward={v20_reward}")
    print(f"v17 {v17_counts} reward={v17_reward}")

    # Feeding is life-or-death: animals escape after two unfed days.
    assert v20_counts["FEED"] >= v17_counts["FEED"], (
        f"v20 fed less than v17 ({v20_counts['FEED']} vs {v17_counts['FEED']}) "
        "-- fertilizer collection is displacing feeding"
    )
    # Watering keeps crops alive; allow a small margin for routing noise.
    assert v20_counts["WATER"] >= v17_counts["WATER"] * 0.95, (
        f"v20 watered materially less than v17 "
        f"({v20_counts['WATER']} vs {v17_counts['WATER']}) "
        "-- fertilizer collection is displacing watering"
    )
```

- [ ] **Step 2: Run it**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v20.py -k displace -v -s
```

Expected: PASS, with both agents' action counts printed. This takes ~1-2
minutes (two full 720-step episodes).

**If it FAILS**, that is a real finding, not a test to relax: `OPTIONAL`
tier is not behaving as spare-labour-only. Report it and stop — do not
loosen the thresholds.

- [ ] **Step 3: Run the whole suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: **617 passed**, ZERO failures.

- [ ] **Step 4: Commit**

```bash
git add tests/test_task_teacher_v20.py
git commit -m "test: verify fertilizer collection does not displace watering or feeding"
```

---

### Task 5: Evaluation and promotion decision

**Files:**
- Modify: `docs/4_agent_version_log.md` (new `task_teacher_v20` entry)
- Modify: `docs/6_next_steps.md` (current recommendation)
- Create: `replays/analysis/task_teacher_v20_acceptance.txt`

**Interfaces:**
- Consumes: `agents/task_teacher_v20/main.py` from Task 3.
- Produces: a promote / do-not-promote decision. **No Kaggle submission happens in this plan.**

**Run every command strictly sequentially, never concurrently.** This project once chased a phantom timing regression that was CPU contention from two simultaneous simulation jobs.

- [ ] **Step 1: 100-episode acceptance gate**

Write `/tmp/v20_acceptance.py`:

```python
"""100-episode acceptance gate for task_teacher_v20."""
import math, sys, time
from pathlib import Path

REPO_ROOT = Path("/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture")
sys.path.insert(0, str(REPO_ROOT / "src"))
from kaggle_environments import make  # noqa: E402

N, BASE_SEED, STEPS = 100, 140000, 720
CFG = {"episodeSteps": STEPS, "startingMoney": 3000, "farmHandCostMult": 1}

done = finite = 0
kinds = {"PLANT": 0, "WATER": 0, "HARVEST": 0, "DIG": 0, "FEED": 0, "COLLECT_FERTILIZER": 0}
fert_sold = 0
latencies = []

for i in range(N):
    env = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED + i}, debug=True)
    t0 = time.time()
    env.run(["agents/task_teacher_v20/main.py", "starter"])
    latencies.append((time.time() - t0) / STEPS * 1000)
    final = env.steps[-1]
    done += all(s.status == "DONE" for s in final)
    finite += all(s.reward is not None and math.isfinite(s.reward) for s in final)
    for step in env.steps:
        a = step[0].action
        if not isinstance(a, dict):
            continue
        for act in [a.get("farmer")] + list(a.get("hands") or []):
            if isinstance(act, list) and act and act[0] in kinds:
                kinds[act[0]] += 1
        for o in a.get("market") or []:
            if (isinstance(o, (list, tuple)) and len(o) > 2
                    and o[0] == "SELL" and o[1] == "FERTILIZER"):
                fert_sold += int(o[2])

print(f"DONE: {done}/{N}   finite: {finite}/{N}")
print(f"action kinds (all units): {kinds}")
print(f"fertilizer collected/ep: {kinds['COLLECT_FERTILIZER']/N:.1f}")
print(f"fertilizer sold/ep: {fert_sold/N:.1f}")
print(f"median latency ms/turn: {sorted(latencies)[len(latencies)//2]:.2f}")

a = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED}, debug=False)
a.run(["agents/task_teacher_v20/main.py", "starter"])
b = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED}, debug=False)
b.run(["agents/task_teacher_v20/main.py", "starter"])
ra = (a.steps[-1][0].reward, a.steps[-1][1].reward)
rb = (b.steps[-1][0].reward, b.steps[-1][1].reward)
print(f"determinism: {ra} vs {rb} -> {'IDENTICAL' if ra == rb else 'MISMATCH'}")
```

Run it:

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
.venv/bin/python /tmp/v20_acceptance.py
```

**Acceptance criteria — all must hold:**
- `DONE: 100/100` and `finite: 100/100`
- `determinism: ... -> IDENTICAL`
- median latency well under 1000 ms/turn (`actTimeout` is 1s)
- **`fertilizer sold/ep` materially greater than 0**

**If `fertilizer sold/ep` is ~0, STOP.** The change is inert: `OPTIONAL`
tier is never reached because units are labour-saturated. Record that as the
outcome, skip Steps 2-4 entirely, and write it up. Do not raise the priority
tier to force collection — that would reintroduce v19's displacement failure
and must be a new version with its own evaluation.

Save the output verbatim to `replays/analysis/task_teacher_v20_acceptance.txt`
with a header naming the script, base seed (140000), episode count (100),
opponent (`starter`), and config.

- [ ] **Step 2: 20-pair screen vs `task_teacher_v17`**

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v20/main.py agents/task_teacher_v17/main.py \
  --episodes 20 --episode-steps 720 --seed 141000
```

Read `hoeffding_95%_ci` and apply the authoritative rule:
- CI wholly **above** 0.50 → Step 3.
- CI **straddles** 0.50 → Step 3 (escalate on ambiguity).
- CI wholly **below** 0.50 → **stop.** Not promoted. Record the screen as
  the outcome. **Do not re-run on a different seed.**

- [ ] **Step 3: 50-pair promotion gate (only if Step 2 said escalate)**

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v20/main.py agents/task_teacher_v17/main.py \
  --episodes 50 --episode-steps 720 --seed 142000
```

Promotion requires the CI **wholly above 0.50**. If it straddles, add
25-pair blocks at fresh seeds per the authoritative protocol.

- [ ] **Step 4: Regression screens (only if Step 3 promoted)**

One at a time:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v20/main.py agents/task_teacher_v16/main.py \
  --episodes 20 --episode-steps 720 --seed 143000
```

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v20/main.py starter \
  --episodes 20 --episode-steps 720 --seed 143000
```

- [ ] **Step 5: Record the result honestly**

Append a `## task_teacher_v20` entry to `docs/4_agent_version_log.md`
following the format of the existing `task_teacher_v5` entry: date, config
diff from v17, the acceptance table from Step 1, a paired-evaluation table
(matchup / pairs / win rate / mean margin / Hoeffding CI), outcome, lesson.

Report figures at the scope you measured them — the acceptance script above
counts **all units** (farmer plus hands), so label them that way. A previous
entry mixed farmer-only action counts with whole-farm sale totals and
misled a later reader.

Include this caveat verbatim:

```
- **Evaluation caveat:** measured under the corrected `1.32.4` simulator
  (validated against real ladder prices, 299/299 exact matches). Version-log
  entries predating 2026-08-28 were measured under the miscalibrated
  `1.29.3` constants, which under-punish premium-good glut ~4x, and are not
  directly comparable.
```

Then update `docs/6_next_steps.md`'s current recommendation with the
outcome and the next priority.

- [ ] **Step 6: Commit**

```bash
git add docs/4_agent_version_log.md docs/6_next_steps.md replays/analysis/task_teacher_v20_acceptance.txt
git commit -m "docs: record task_teacher_v20 evaluation result"
```

---

## Post-Plan Notes

**Not in scope, deliberately** (design §6): using fertilizer on crops via
`FERTILIZE` rather than selling it (it doubles a one-time crop's watering
bonus and may well beat selling — but it is a different variable with its
own tile and labour interactions); buying fertilizer; melon
over-production and sale metering; the v18 feed-starvation defect.

**If v20 promotes,** the next candidate is melon sale metering / production
capping — the largest remaining line in
`docs/10_ladder_revenue_diagnosis.md`, and now the only one of the original
four left unaddressed.

**If v20 is inert** (fertilizer sold/ep ~0), the finding is that units are
labour-saturated. That is itself valuable: it would mean *any* change adding
unit-actions is doomed, and the next version should reduce labour demand or
add hands rather than add work.

**If v20 collects but loses the screen,** compare its acceptance action
counts against v17's from Task 4's printed output — that isolates whether
collection displaced work despite the OPTIONAL tier.
