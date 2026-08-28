# Task Teacher v21 — Melon Planting Cutoff — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop planting melon after a cutoff day, eliminating a second growing cycle that is measured to sell for ~$7/unit into a market it cannot recover from.

**Architecture:** One new `melon_last_plant_day: int | None = None` parameter on `generate_tasks`. When set, `MELON` is filtered out of the candidate tuple handed to the single `_best_feasible_crop` call for any day past the cutoff. A new immutable agent `agents/task_teacher_v21/` (copy-forward of `task_teacher_v20`) passes `MELON_LAST_PLANT_DAY = 10`. Freed tiles are deliberately **not** reassigned to a hardcoded crop — they fall through to existing allocation logic.

**Tech Stack:** Python 3.11, `kaggle-environments==1.32.4`, pytest. Run everything through the repo venv: `.venv/bin/python`. Shared-library imports need `PYTHONPATH=src`.

## Global Constraints

- Design doc: `docs/superpowers/specs/2026-08-28-task-teacher-v21-melon-cutoff-design.md`. Read it before starting.
- **TDD is mandatory** (`superpowers:test-driven-development`): write the failing test, watch it fail for the right reason, then write the minimal code. No production code before a failing test.
- **`melon_last_plant_day` MUST default to `None`.** Every existing agent (`task_teacher_v2` … `v20`) must keep byte-identical task output. Task 2 is the regression guard and is not optional.
- **Agent versions are immutable.** Never edit `agents/task_teacher_v2` … `v20`. v21 is a new folder.
- `MELON_LAST_PLANT_DAY = 10` in v21.
- **The change is exactly one call site.** Melon can only ever be selected at `src/kaggriculture_lib/tasking.py:330`'s `_best_feasible_crop` call. Do not filter candidates anywhere else — the other branches name their crop literally.
- **Do not add a replacement-crop rule.** Freed tiles must fall through to existing logic. Hardcoding a replacement is exactly what lost `task_teacher_v19` 0 of 20 paired games.
- Simulator is `1.32.4`; `scripts/run_tournament.py` already applies ladder-match config by default.
- Full suite must be green before Task 4's evaluation. Baseline is **617 passing**.

---

### Task 1: Add `melon_last_plant_day` to `generate_tasks`

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py` — signature (~line 215-223), crop-selection block (~line 329-331)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `generate_tasks(..., melon_last_plant_day: int | None = None)`. Task 2 asserts the default is inert; Task 3 passes `melon_last_plant_day=MELON_LAST_PLANT_DAY` from the v21 agent.

#### Why one call site — read before writing code

The empty-tile crop-selection block chooses a crop through four paths:

```python
crop = None
if wheat_needed_for_feed and n_wheat < 4 ...:      # names "WHEAT" literally
    crop = "WHEAT"
else:
    best = _best_feasible_crop(day, last_day, market_prices, candidate_crops)   # <-- line 330
    if "STRAWBERRY" in candidate_crops and day >= 10 ...:                       # names "STRAWBERRY"
        crop = "STRAWBERRY"
    elif n_wheat < wheat_target_tiles ...:                                      # names "WHEAT"
        crop = "WHEAT"
    else:
        crop = best                                                             # only melon path
```

Only `best` can ever be `"MELON"`. Filtering that one call's candidate tuple is necessary and sufficient. The `MELON` reference further down (~line 348) only *increments a counter* for a crop already chosen — do not touch it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tasking.py`. Use the fixtures this file already establishes (`BOARD_SIZE`, `CANDIDATE_CROPS`, `BASE_PRICES`, `make_tiles`) rather than hand-rolling board data or repeating literals:

```python
MELON_CROPS = ("WHEAT", "CARROT", "MELON", "STRAWBERRY")
MELON_PRICES = {"WHEAT": 25, "CARROT": 35, "MELON": 250, "STRAWBERRY": 120}


def _planted_crops(tasks):
    return [t.task_id.item for t in tasks if t.task_id.kind == TaskKind.PLANT]


def _generate_on_empty_board(*, day, **kwargs):
    return generate_tasks(
        tiles=make_tiles(),
        unlocked_quadrants=["NW"],
        day=day,
        last_day=29,
        market_prices=MELON_PRICES,
        candidate_crops=MELON_CROPS,
        **kwargs,
    )


def test_melon_planted_on_the_cutoff_day():
    """The cutoff is inclusive: day == cutoff still plants melon. Cycle 1 is
    planted by day 2 and sells at $81/unit -- it must not be disturbed.
    """
    crops = _planted_crops(_generate_on_empty_board(day=10, melon_last_plant_day=10))
    assert "MELON" in crops


def test_melon_not_planted_after_the_cutoff_day():
    """Measured on 17 live ladder episodes: melon planted after ~day 13
    (cycle 2) is harvested ~day 25 and sells for $4-11/unit into a market
    that saturated on day 14 and never recovers -- melon is the one product
    no town shop demands. See docs/10_ladder_revenue_diagnosis.md and the
    v21 design doc Sec 3.
    """
    crops = _planted_crops(_generate_on_empty_board(day=11, melon_last_plant_day=10))
    assert "MELON" not in crops


def test_a_non_melon_crop_is_still_planted_after_the_cutoff():
    """The cutoff must free the tile for something else, not idle it."""
    crops = _planted_crops(_generate_on_empty_board(day=11, melon_last_plant_day=10))
    assert crops, "no crop planted at all after the melon cutoff"
    assert all(c != "MELON" for c in crops)


def test_cutoff_does_not_restrict_other_crops():
    """Only MELON is filtered. Every other candidate stays eligible; the
    cutoff must not become a general planting freeze.
    """
    crops = set(_planted_crops(_generate_on_empty_board(day=11, melon_last_plant_day=10)))
    assert crops - {"MELON"}, f"expected some non-melon crop, got {crops}"


def test_cutoff_does_not_affect_existing_melon_tiles():
    """Melon already in the ground before the cutoff must still be watered
    and harvested -- the cutoff governs planting only.
    """
    tile = make_plant_tile("MELON", planted_day=0, watered_today=False)
    tasks = generate_tasks(
        tiles=make_tiles({(1, 1): tile}),
        unlocked_quadrants=["NW"],
        day=11,
        last_day=29,
        market_prices=MELON_PRICES,
        candidate_crops=MELON_CROPS,
        melon_last_plant_day=10,
    )
    tile_tasks = {t.task_id.kind for t in tasks if t.target == (1, 1)}
    assert TaskKind.WATER in tile_tasks
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
.venv/bin/python -m pytest tests/test_tasking.py -k melon -v
```

Expected: `TypeError: generate_tasks() got an unexpected keyword argument 'melon_last_plant_day'`.

- [ ] **Step 3: Add the parameter**

In `src/kaggriculture_lib/tasking.py`, add one line to `generate_tasks`'s signature, immediately after `collect_fertilizer`:

```python
    collect_fertilizer: bool = False,
    melon_last_plant_day: int | None = None,
    max_feed_tasks: int | None = None,
```

Then extend the docstring with:

```
    `melon_last_plant_day` defaults to None, which disables the melon
    cutoff entirely and leaves task output byte-identical for every agent
    that does not pass it. That default is load-bearing: agent versions are
    immutable as files but read this shared module, so a behavioural change
    here rewrites frozen agents' evaluated behaviour retroactively (see
    docs/2_environment_notes.md's 2026-08-28 correction, where exactly that
    happened to task_teacher_v8).
```

- [ ] **Step 4: Filter the one call site**

Replace the single line at `src/kaggriculture_lib/tasking.py:330`:

```python
                    best = _best_feasible_crop(day, last_day, market_prices, candidate_crops)
```

with:

```python
                    # MELON's absorption is a ~113-unit whole-game stock, not a
                    # rate: no town shop demands it, so the town centre drains
                    # only ~1/day and dumped supply never clears. A second
                    # planting cycle therefore sells at $4-11/unit. Past the
                    # cutoff, drop MELON from the ranking and let the existing
                    # allocation choose. See the v21 design doc Sec 3-4.
                    melon_ok = melon_last_plant_day is None or day <= melon_last_plant_day
                    ranking_crops = (
                        candidate_crops
                        if melon_ok
                        else tuple(c for c in candidate_crops if c != "MELON")
                    )
                    best = _best_feasible_crop(day, last_day, market_prices, ranking_crops)
```

Change nothing else in the block.

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_tasking.py -k melon -v
```

Expected: all 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "feat: add melon_last_plant_day cutoff to generate_tasks"
```

---

### Task 2: Frozen-agent regression guard

**Files:**
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: `generate_tasks(..., melon_last_plant_day: int | None = None)` from Task 1.
- Produces: nothing consumed later. This task exists solely to prove Task 1 cannot alter frozen agents.

**Why this is a separate task:** a reviewer could reasonably approve Task 1's cutoff while rejecting an implementation that leaks into existing agents. This is the gate for that, and the leak is not hypothetical — correcting `economy.FARM_HAND_COST_MULT` on 2026-08-28 silently changed frozen `task_teacher_v8`.

- [ ] **Step 1: Write the guard test**

Append to `tests/test_tasking.py`:

```python
def test_melon_cutoff_defaults_to_none_leaving_existing_agents_unchanged():
    """The cutoff must be inert unless explicitly requested.

    Agent versions are immutable as files but read this shared module, so a
    behavioural change here rewrites every frozen agent's evaluated
    behaviour retroactively. That is not hypothetical: on 2026-08-28,
    correcting economy.FARM_HAND_COST_MULT silently changed frozen
    task_teacher_v8 (docs/2_environment_notes.md). This asserts the default
    path is unchanged, so v2..v20 keep the behaviour they were evaluated
    with.

    Day 11 is used because it is past the cutoff v21 will ship (10), so a
    leaked default would show up as MELON disappearing here.
    """
    kwargs = dict(
        tiles=make_tiles(),
        unlocked_quadrants=["NW"],
        day=11,
        last_day=29,
        market_prices=MELON_PRICES,
        candidate_crops=MELON_CROPS,
    )
    without_param = generate_tasks(**kwargs)
    explicit_none = generate_tasks(**kwargs, melon_last_plant_day=None)

    assert [t.task_id for t in without_param] == [t.task_id for t in explicit_none]
    # And the default still plants melon on a day a cutoff would have blocked.
    assert "MELON" in _planted_crops(without_param)
```

- [ ] **Step 2: Run the test**

```bash
.venv/bin/python -m pytest tests/test_tasking.py -k defaults_to_none -v
```

Expected: PASS immediately (Task 1 already implemented the default correctly). This is a guard, not a driver — if it FAILS, Task 1's default is wrong and must be fixed before continuing.

- [ ] **Step 3: Run the whole suite as the real regression check**

```bash
.venv/bin/python -m pytest -q
```

Expected: **623 passed** (617 baseline + 5 from Task 1 + 1 here), ZERO failures. Any pre-existing test that now fails means Task 1 leaked — fix Task 1, do not edit the failing test.

- [ ] **Step 4: Commit**

```bash
git add tests/test_tasking.py
git commit -m "test: guard that melon_last_plant_day default leaves frozen agents unchanged"
```

---

### Task 3: Create `task_teacher_v21`

**Files:**
- Create: `agents/task_teacher_v21/main.py` (copied from `agents/task_teacher_v20/main.py`, then edited)
- Create: `tests/test_task_teacher_v21.py`
- Modify: `tests/test_package_agent.py`

**Interfaces:**
- Consumes: `generate_tasks(..., melon_last_plant_day=...)` from Task 1.
- Produces: `agents/task_teacher_v21/main.py` with module constant `MELON_LAST_PLANT_DAY = 10` and `agent(obs, config)` — used by Task 4.

- [ ] **Step 1: Copy v20 forward**

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
mkdir -p agents/task_teacher_v21
cp agents/task_teacher_v20/main.py agents/task_teacher_v21/main.py
```

- [ ] **Step 2: Replace the module docstring**

In `agents/task_teacher_v21/main.py`, replace the whole module docstring (it currently describes v20's fertilizer change) with:

```python
"""Kaggriculture multi-tile task/route teacher agent, v21.

Extends `task_teacher_v20` with one variable: stop planting melon after
day `MELON_LAST_PLANT_DAY`.

Measured motivation (17 real ladder episodes of the live v20 submission):
we sold 192.9 melons/ep at $57.0/unit against opponents' 102.0 at $84.7.
The cause is over-production, not sale timing. Melon is planted in two
cycles; cycle 1 (planted ~day 0-2) sells day 13-14 at $81/$42 and works,
while cycle 2 (planted ~day 13-14) sells day 26-29 at $4-11. Cycle 1 alone
already saturates melon's ~113-unit whole-game absorption, and melon is
the one product no town shop demands, so its excess inventory sits at +157
from day 14 to day 29 and never clears.

The existing horizon gate does not catch this: `can_mature_in_time` allows
melon planting through day 17, because it only asks whether the crop can
mature -- never whether it can be sold for anything.

Freed tiles are deliberately NOT reassigned to a hardcoded crop. They fall
through to the existing allocation order (strawberry, already gated at
day >= 10, then the ROI ranking). Forcing a replacement is exactly what
lost `task_teacher_v19` 0 of 20 paired games.

Design: docs/superpowers/specs/2026-08-28-task-teacher-v21-melon-cutoff-design.md
"""
```

- [ ] **Step 3: Add the constant**

In the constants block, immediately after `MAX_FEED_ACTIONS_PER_DAY`:

```python
# Last day on which melon may be planted. Cycle 1 is planted by day 2, so a
# day-10 cutoff leaves the profitable cycle untouched while removing the
# cycle-2 plantings that begin ~day 13 and sell at $4-11/unit. Day 10 also
# coincides with the existing strawberry rule's `day >= 10` activation, so
# freed tiles have a reallocation path that already exists. This is the
# design's one tunable knob.
MELON_LAST_PLANT_DAY = 10
```

- [ ] **Step 4: Write the failing tests**

Create `tests/test_task_teacher_v21.py`:

```python
"""Tests for agents/task_teacher_v21 -- melon planting cutoff."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def load_agent_module(name):
    spec = importlib.util.spec_from_file_location(
        f"agents_{name}_main", REPO_ROOT / "agents" / name / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cutoff_constant():
    module = load_agent_module("task_teacher_v21")
    assert module.MELON_LAST_PLANT_DAY == 10


def test_agent_passes_the_cutoff_to_generate_tasks():
    """The constant is inert unless it is actually wired into the shared
    scheduler -- the parameter defaults to None."""
    src = (REPO_ROOT / "agents" / "task_teacher_v21" / "main.py").read_text()
    assert "melon_last_plant_day=MELON_LAST_PLANT_DAY" in src


def _melon_stats(agent_path, seed=150000):
    """Melon plantings, units sold, and revenue for one full episode."""
    from kaggle_environments import make

    env = make(
        "kaggriculture",
        configuration={
            "episodeSteps": 720, "startingMoney": 3000,
            "farmHandCostMult": 1, "seed": seed,
        },
        debug=True,
    )
    env.run([agent_path, "starter"])
    planted = units = 0
    revenue = 0.0
    for step in env.steps:
        obs = step[0].observation
        action = step[0].action
        if not isinstance(action, dict):
            continue
        for act in [action.get("farmer")] + list(action.get("hands") or []):
            if isinstance(act, list) and len(act) > 1 and act[0] == "PLANT" and act[1] == "MELON":
                planted += 1
        price = 0
        if isinstance(obs, dict):
            price = (obs.get("market") or {}).get("prices", {}).get("MELON", 0)
        for order in action.get("market") or []:
            if (isinstance(order, (list, tuple)) and len(order) > 2
                    and order[0] == "SELL" and order[1] == "MELON"):
                q = int(order[2])
                units += q
                revenue += q * price
    status_ok = all(s.status == "DONE" for s in env.steps[-1])
    return planted, units, revenue, env.steps[-1][0].reward, status_ok


def test_full_episode_plants_less_melon_at_a_better_unit_price():
    """End-to-end, paired against v20 on one seed.

    The cutoff's whole claim is that removing cycle-2 melon raises the
    realised price of the melon we do sell. If plantings fall but $/unit
    does not rise, the cutoff is removing volume without fixing the glut --
    report that rather than relaxing the assertion.
    """
    v21_planted, v21_units, v21_rev, v21_reward, v21_ok = _melon_stats(
        "agents/task_teacher_v21/main.py"
    )
    v20_planted, v20_units, v20_rev, v20_reward, v20_ok = _melon_stats(
        "agents/task_teacher_v20/main.py"
    )
    assert v21_ok and v20_ok

    v21_pu = v21_rev / max(1, v21_units)
    v20_pu = v20_rev / max(1, v20_units)
    print(f"v21 planted={v21_planted} units={v21_units} $/u={v21_pu:.1f} reward={v21_reward}")
    print(f"v20 planted={v20_planted} units={v20_units} $/u={v20_pu:.1f} reward={v20_reward}")

    assert v21_planted < v20_planted, "cutoff did not reduce melon plantings"
    assert v21_pu > v20_pu, "melon $/unit did not improve despite fewer plantings"
```

- [ ] **Step 5: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v21.py -v -s
```

Expected: `test_agent_passes_the_cutoff_to_generate_tasks` FAILS — the copied v20 does not pass the parameter.

- [ ] **Step 6: Wire the cutoff into the agent**

In `agents/task_teacher_v21/main.py`, in the `generate_tasks(...)` call, add one keyword argument after `collect_fertilizer=True,`:

```python
        collect_fertilizer=True,
        melon_last_plant_day=MELON_LAST_PLANT_DAY,
        max_feed_tasks=MAX_FEED_ACTIONS_PER_DAY,
```

- [ ] **Step 7: Add the packaging test**

Append to `tests/test_package_agent.py`, next to the sibling agent tests:

```python
def test_packaged_task_teacher_v21_runs_standalone_without_pythonpath():
    """v21 adds the melon cutoff on top of the same shared modules v20
    already packages correctly."""
    out_path = REPO_ROOT / "build" / "task_teacher_v21" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v21", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/test_task_teacher_v21.py tests/test_package_agent.py -v -s
```

Expected: all PASS, with the printed v21/v20 melon lines showing fewer plantings and a higher `$/u` for v21.

- [ ] **Step 9: Confirm packaging bundles only what it should**

```bash
grep -oE "_register_shared_module\('kaggriculture_lib\.[a-z_]+'" build/task_teacher_v21/main.py
```

Expected exactly two lines: `kaggriculture_lib.economy` and `kaggriculture_lib.tasking`. Any `replay_*` module means the packaging scope fix regressed — see `docs/4_agent_version_log.md`'s 2026-08-06 incident, where exactly that broke a live submission.

- [ ] **Step 10: Run the whole suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: **627 passed** (623 after Task 2, plus 3 agent tests and 1 packaging test), ZERO failures.

- [ ] **Step 11: Commit**

```bash
git add agents/task_teacher_v21/main.py tests/test_task_teacher_v21.py tests/test_package_agent.py
git commit -m "feat: add task_teacher_v21 -- melon planting cutoff at day 10"
```

---

### Task 4: Evaluation and promotion decision

**Files:**
- Modify: `docs/4_agent_version_log.md` (new `task_teacher_v21` entry)
- Modify: `docs/6_next_steps.md` (current recommendation)
- Create: `replays/analysis/task_teacher_v21_acceptance.txt`

**Interfaces:**
- Consumes: `agents/task_teacher_v21/main.py` from Task 3.
- Produces: a promote / do-not-promote decision. **No Kaggle submission happens in this plan.**

**Run every command strictly sequentially, never concurrently.** This project once chased a phantom timing regression that was CPU contention from two simultaneous simulation jobs.

- [ ] **Step 1: 100-episode acceptance gate**

Write `/tmp/v21_acceptance.py`:

```python
"""100-episode acceptance gate for task_teacher_v21."""
import math, sys, time
from pathlib import Path

REPO_ROOT = Path("/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture")
sys.path.insert(0, str(REPO_ROOT / "src"))
from kaggle_environments import make  # noqa: E402

N, BASE_SEED, STEPS = 100, 150000, 720
CFG = {"episodeSteps": STEPS, "startingMoney": 3000, "farmHandCostMult": 1}

done = finite = 0
melon_planted = melon_units = 0
melon_rev = 0.0
rewards = []
latencies = []

for i in range(N):
    env = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED + i}, debug=True)
    t0 = time.time()
    env.run(["agents/task_teacher_v21/main.py", "starter"])
    latencies.append((time.time() - t0) / STEPS * 1000)
    final = env.steps[-1]
    done += all(s.status == "DONE" for s in final)
    finite += all(s.reward is not None and math.isfinite(s.reward) for s in final)
    rewards.append(final[0].reward)
    for step in env.steps:
        obs, a = step[0].observation, step[0].action
        if not isinstance(a, dict):
            continue
        for act in [a.get("farmer")] + list(a.get("hands") or []):
            if isinstance(act, list) and len(act) > 1 and act[0] == "PLANT" and act[1] == "MELON":
                melon_planted += 1
        price = (obs.get("market") or {}).get("prices", {}).get("MELON", 0) if isinstance(obs, dict) else 0
        for o in a.get("market") or []:
            if (isinstance(o, (list, tuple)) and len(o) > 2
                    and o[0] == "SELL" and o[1] == "MELON"):
                q = int(o[2])
                melon_units += q
                melon_rev += q * price

print(f"DONE: {done}/{N}   finite: {finite}/{N}")
print(f"melon planted/ep: {melon_planted/N:.1f}   (v20 measured ~51)")
print(f"melon units sold/ep: {melon_units/N:.1f}  (v20 measured ~193)")
print(f"melon $/unit: {melon_rev/max(1,melon_units):.1f}  (v20 measured $57.0)")
print(f"mean reward/ep: {sum(rewards)/N:,.0f}")
print(f"median latency ms/turn: {sorted(latencies)[len(latencies)//2]:.2f}")

a = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED}, debug=False)
a.run(["agents/task_teacher_v21/main.py", "starter"])
b = make("kaggriculture", configuration={**CFG, "seed": BASE_SEED}, debug=False)
b.run(["agents/task_teacher_v21/main.py", "starter"])
ra = (a.steps[-1][0].reward, a.steps[-1][1].reward)
rb = (b.steps[-1][0].reward, b.steps[-1][1].reward)
print(f"determinism: {ra} vs {rb} -> {'IDENTICAL' if ra == rb else 'MISMATCH'}")
```

Run it:

```bash
cd "/Users/tuannm3812/Documents/GitHub/2. Kaggle/kaggriculture"
.venv/bin/python /tmp/v21_acceptance.py
```

**Acceptance criteria — all must hold:**
- `DONE: 100/100` and `finite: 100/100`
- `determinism: ... -> IDENTICAL`
- median latency well under 1000 ms/turn (`actTimeout` is 1s)
- `melon planted/ep` materially below v20's ~51 — otherwise the cutoff is not firing

Save the output verbatim to `replays/analysis/task_teacher_v21_acceptance.txt` with a header naming the script, base seed (150000), episode count (100), opponent (`starter`), and config.

- [ ] **Step 2: 20-pair screen vs `task_teacher_v20`**

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v21/main.py agents/task_teacher_v20/main.py \
  --episodes 20 --episode-steps 720 --seed 151000
```

Read `hoeffding_95%_ci` and apply the authoritative rule:
- CI wholly **above** 0.50 → Step 3.
- CI **straddles** 0.50 → Step 3 (escalate on ambiguity).
- CI wholly **below** 0.50 → **stop.** Not promoted. Record the screen as the outcome. **Do not re-run on a different seed.** Then do the Step 5 diagnostic before writing up.

- [ ] **Step 3: 50-pair promotion gate (only if Step 2 said escalate)**

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v21/main.py agents/task_teacher_v20/main.py \
  --episodes 50 --episode-steps 720 --seed 152000
```

Promotion requires the CI **wholly above 0.50**. If it straddles, add 25-pair blocks at fresh seeds per the authoritative protocol.

- [ ] **Step 4: Regression screens (only if Step 3 promoted)**

One at a time:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v21/main.py agents/task_teacher_v17/main.py \
  --episodes 20 --episode-steps 720 --seed 153000
```

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
  agents/task_teacher_v21/main.py starter \
  --episodes 20 --episode-steps 720 --seed 153000
```

- [ ] **Step 5: Diagnose a negative result before writing it up**

**Only if the screen or gate came back negative.** Compare Step 1's acceptance figures against v20's measured baseline (melon planted/ep ~51, units sold/ep ~193, $/unit $57.0):

- **`$/unit` rose but mean reward fell** → the cutoff worked and the *reallocation* did not: freed tiles are worth less than the melon they replaced. This is `task_teacher_v19`'s failure in mirror image. The next step is to tune `MELON_LAST_PLANT_DAY` upward (a smaller cut), not to abandon the approach.
- **`$/unit` did not rise despite fewer plantings** → the glut is not ours alone; the opponent's melon is saturating the market regardless. Cutting our own production then only forfeits revenue, and the melon line needs a different idea entirely.
- **`melon planted/ep` barely moved** → the cutoff is not firing; treat as an implementation bug, not an evaluation result.

Record whichever applies in the version-log entry. This diagnostic is the point of collecting those metrics.

- [ ] **Step 6: Record the result honestly**

Append a `## task_teacher_v21` entry to `docs/4_agent_version_log.md` following the format of the existing `task_teacher_v5` entry: date, config diff from v20, the acceptance table from Step 1, a paired-evaluation table (matchup / pairs / win rate / mean margin / Hoeffding CI), outcome, lesson.

Report figures at the scope you measured them — the acceptance script counts **all units** (farmer plus hands), so label them that way. A previous entry mixed farmer-only action counts with whole-farm sale totals and misled a later reader.

Include this caveat verbatim:

```
- **Evaluation caveat:** measured under the corrected `1.32.4` simulator
  (validated against real ladder prices, 299/299 exact matches). Version-log
  entries predating 2026-08-28 were measured under the miscalibrated
  `1.29.3` constants, which under-punish premium-good glut ~4x, and are not
  directly comparable.
```

Then update `docs/6_next_steps.md`'s current recommendation with the outcome and the next priority.

- [ ] **Step 7: Commit**

```bash
git add docs/4_agent_version_log.md docs/6_next_steps.md replays/analysis/task_teacher_v21_acceptance.txt
git commit -m "docs: record task_teacher_v21 evaluation result"
```

---

## Post-Plan Notes

**Not in scope, deliberately** (design §5): melon sale metering (the day-13 single-turn dump of 100 units — real, but melon does not recover between sales so spreading gains little); the 100-item shed cap that discards ~26 melons/ep; terminal liquidation (still correct for stock already grown); and the wheat ($0/ep vs opponents' $6,766) and wool ($2,329 vs $6,419) lines.

**If v21 promotes,** the remaining measured gaps in `docs/10_ladder_revenue_diagnosis.md` are carrot (opponents $6,999/ep vs our $661, with ~230 units of absorption) and wool. Carrot is the larger and has the most headroom.

**If v21 does not promote,** Step 5's diagnostic says which of three distinct things went wrong; do not re-run the screen on a new seed hoping for a better number.
