# Task Teacher v6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `task_teacher_v6` — land-only NE `BUY_LAND` like v5, with `budget_reserve=2000` so land waits until the bank can absorb $1k without Melon cash starvation.

**Architecture:** Add optional `budget_reserve` kwarg to `should_buy_land` (default `LAND_BUDGET_RESERVE=400` so v4/v5 unchanged). Create immutable `agents/task_teacher_v6/main.py` from v5 that passes `LAND_BUDGET_RESERVE_V6=2000`. Promote only vs `task_teacher_v5` via Hoeffding.

**Tech Stack:** Python 3.11, pytest, `scripts/run_tournament.py`, `scripts/package_agent.py`.

## Global Constraints

- Never edit existing `agents/*/main.py` (v5 and earlier immutable).
- No animals / Goose path (`MAX_GEESE=0`).
- No earliest-day gate; no `NW_SATURATION_PLANTS` change in this version.
- If acceptance shows `BUY_LAND=0`, lower reserve toward 1500 and re-run — do not stack knobs.
- Promote only if 50-pair Hoeffding CI vs v5 is wholly above 0.50.
- Spec: `docs/superpowers/specs/2026-08-11-task-teacher-v6-design.md`.

---

### Task 1: Additive `budget_reserve` on `should_buy_land`

**Files:**
- Modify: `src/kaggriculture_lib/tasking.py` (`should_buy_land`)
- Test: `tests/test_tasking.py`

**Interfaces:**
- Consumes: existing `LAND_BUDGET_RESERVE = 400`, `economy.land_cost`
- Produces: `should_buy_land(..., budget_reserve: float = LAND_BUDGET_RESERVE) -> bool`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tasking.py` after `test_should_buy_land_false_when_cash_after_hire_reserve_too_low`:

```python
def test_should_buy_land_accepts_explicit_budget_reserve_kwarg():
    # Same fixture as the default-true case (money=2000, reserve hire=0):
    # default 400 passes (need 1400); explicit 2000 fails (need 3000).
    kwargs = dict(
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
    assert should_buy_land(**kwargs)  # default 400
    assert not should_buy_land(**kwargs, budget_reserve=2000)


def test_should_buy_land_true_when_cash_clears_high_budget_reserve():
    assert should_buy_land(
        unlocked_quadrants=["NW"],
        money=3500.0,
        projected_load=10,
        remaining_turns_today=20,
        existing_hands=3,
        day=5,
        last_day=29,
        reserved_for_hire=0.0,
        plant_tile_count=20,
        budget_reserve=2000,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && export PYTHONPATH=src && python -m pytest tests/test_tasking.py::test_should_buy_land_accepts_explicit_budget_reserve_kwarg tests/test_tasking.py::test_should_buy_land_true_when_cash_clears_high_budget_reserve -v`

Expected: FAIL — `budget_reserve` unexpected keyword argument (or second assert wrongly True if someone stubs).

- [ ] **Step 3: Minimal implementation**

In `src/kaggriculture_lib/tasking.py`, change `should_buy_land` signature and cash check:

```python
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
    budget_reserve: float = LAND_BUDGET_RESERVE,
) -> bool:
    """Whether to emit BUY_LAND for NE this turn (hard-cap: one extra quadrant)."""
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
    if money - reserved_for_hire < cost + budget_reserve:
        return False
    if estimate_hire_value(projected_load, remaining_turns_today, existing_hands) > 0:
        return False
    return True
```

Do not change `LAND_BUDGET_RESERVE = 400`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && export PYTHONPATH=src && python -m pytest tests/test_tasking.py -k should_buy_land -v`

Expected: all PASS (including existing default-reserve cases).

- [ ] **Step 5: Commit**

```bash
git add src/kaggriculture_lib/tasking.py tests/test_tasking.py
git commit -m "$(cat <<'EOF'
feat: add budget_reserve kwarg to should_buy_land

EOF
)"
```

---

### Task 2: `task_teacher_v6` agent + behavior tests

**Files:**
- Create: `agents/task_teacher_v6/main.py`
- Create: `tests/test_task_teacher_v6.py`

**Interfaces:**
- Consumes: `should_buy_land(..., budget_reserve=...)`
- Produces: `LAND_BUDGET_RESERVE_V6 = 2000`, `MAX_GEESE = 0`, `agent(obs, config=None)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_task_teacher_v6.py` (mirror `tests/test_task_teacher_v5.py` helpers `make_obs` / `make_plant_tile` / `BOARD_SIZE` / `V6_CONFIG`):

```python
"""Behavior tests for agents/task_teacher_v6/main.py.

Delayed-NE land teacher: v5 + LAND_BUDGET_RESERVE_V6=2000. Per
docs/superpowers/specs/2026-08-11-task-teacher-v6-design.md.
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
V6_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24}


# ... copy make_obs / make_plant_tile from test_task_teacher_v5.py verbatim ...


def test_candidate_crops_match_v2():
    module = load_agent_module("task_teacher_v6")
    assert module.CANDIDATE_CROPS == ("WHEAT", "CARROT", "MELON")


def test_max_geese_is_zero():
    module = load_agent_module("task_teacher_v6")
    assert module.MAX_GEESE == 0


def test_land_budget_reserve_v6_is_2000():
    module = load_agent_module("task_teacher_v6")
    assert module.LAND_BUDGET_RESERVE_V6 == 2000


def _saturated_nw_obs(*, money: float):
    day = 15
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    for y in range(5):
        for x in range(5):
            tiles[y][x] = make_plant_tile(
                "WHEAT", planted_day=day, watered_today=True, consecutive_unwatered=0
            )
    return make_obs(
        day=day,
        hour=0,
        money=money,
        farmer=(4, 4),
        hands=[(1, 1), (2, 2), (3, 3)],
        tiles=tiles,
    )


def test_emits_buy_land_when_cash_clears_v6_reserve():
    module = load_agent_module("task_teacher_v6")
    # need land 1000 + reserve 2000 = 3000; money 3500 clears it.
    action = module.agent(_saturated_nw_obs(money=3500.0), V6_CONFIG)
    assert ["BUY_LAND"] in action["market"]


def test_does_not_emit_buy_land_when_cash_only_clears_v5_reserve():
    module = load_agent_module("task_teacher_v6")
    # money 2000 clears v5 bar (1400) but not v6 bar (3000).
    action = module.agent(_saturated_nw_obs(money=2000.0), V6_CONFIG)
    assert ["BUY_LAND"] not in action["market"]


def test_never_buys_animal_even_with_empty_coop_and_cash():
    module = load_agent_module("task_teacher_v6")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[1][1] = {"kind": "COOP"}
    action = module.agent(make_obs(farmer=(4, 4), tiles=tiles, money=10_000.0), V6_CONFIG)
    assert not any(order[0] == "BUY_ANIMAL" for order in action["market"])
    assert action["farmer"] != ["BUILD_COOP"]


def test_simulator_full_episode_two_seats_done_and_finite():
    module = load_agent_module("task_teacher_v6")
    env = make("kaggriculture", configuration={"episodeSteps": 240}, debug=True)
    env.run([module.agent, "starter"])
    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final)
    assert all(s.reward is not None and math.isfinite(s.reward) for s in final)
```

Include the full `make_obs` / `make_plant_tile` bodies copied from `tests/test_task_teacher_v5.py` (do not import from that module).

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && export PYTHONPATH=src && python -m pytest tests/test_task_teacher_v6.py -v`

Expected: FAIL — cannot load `task_teacher_v6`.

- [ ] **Step 3: Create the agent**

```bash
mkdir -p agents/task_teacher_v6
cp agents/task_teacher_v5/main.py agents/task_teacher_v6/main.py
```

Then edit `agents/task_teacher_v6/main.py`:

1. Docstring → describe v6 delayed-NE cash floor; cite
   `docs/superpowers/specs/2026-08-11-task-teacher-v6-design.md`.
2. After `MAX_GEESE = 0` add:

```python
LAND_BUDGET_RESERVE_V6 = 2000
```

3. In the `should_buy_land(...)` call, add:

```python
        budget_reserve=LAND_BUDGET_RESERVE_V6,
```

Leave all other logic identical to v5.

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && export PYTHONPATH=src && python -m pytest tests/test_task_teacher_v6.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add agents/task_teacher_v6/main.py tests/test_task_teacher_v6.py
git commit -m "$(cat <<'EOF'
feat: add task_teacher_v6 delayed NE land (reserve 2000)

EOF
)"
```

---

### Task 3: Packaging smoke

**Files:**
- Modify: `tests/test_package_agent.py`

**Interfaces:**
- Consumes: `scripts/package_agent.py` auto-discovery
- Produces: `test_packaged_task_teacher_v6_runs_standalone_without_pythonpath`

- [ ] **Step 1: Write the failing test**

Immediately after `test_packaged_task_teacher_v5_runs_standalone_without_pythonpath`:

```python
def test_packaged_task_teacher_v6_runs_standalone_without_pythonpath():
    out_path = REPO_ROOT / "build" / "task_teacher_v6" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v6", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_package_agent.py::test_packaged_task_teacher_v6_runs_standalone_without_pythonpath -v`

Expected: FAIL only if packaging/agent broken; if Task 2 is done this may already PASS on first run — that is OK (package path already works). If it PASSes immediately, still commit the test.

- [ ] **Step 3: Fix packaging only if needed**

No packaging code changes expected. If FAIL for a reason other than missing agent, stop and diagnose `scripts/package_agent.py`.

- [ ] **Step 4: Confirm pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_package_agent.py -k task_teacher_v6 -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_package_agent.py
git commit -m "$(cat <<'EOF'
test: verify task_teacher_v6 packages and runs standalone

EOF
)"
```

---

### Task 4: Evaluation + docs (promote gate)

**Files:**
- Modify: `docs/4_agent_version_log.md`, `docs/6_next_steps.md`, `docs/3_agent_strategy.md`, `README.md` (as needed after results)
- Modify: `docs/superpowers/specs/2026-08-11-task-teacher-v6-design.md` status line
- Scratch logs under `.superpowers/sdd/` (gitignored OK)

**Interfaces:**
- Consumes: `scripts/run_tournament.py`
- Produces: promote / no-promote decision vs `task_teacher_v5`

- [ ] **Step 1: Acceptance vs starter**

```bash
source .venv/bin/activate && export PYTHONPATH=src
python scripts/run_tournament.py \
  agents/task_teacher_v6/main.py starter \
  --episodes 100 --episode-steps 720 --seed 86000 \
  > .superpowers/sdd/task-9-v6-acceptance.log 2>&1
```

Also collect action coverage (BUY_LAND / BUY_ANIMAL counts) the same way prior v5 Task 9 did (grep tournament JSON/telemetry or a small probe script). Required: 100/100 DONE/finite, `BUY_LAND>0`, `BUY_ANIMAL=0`. If `BUY_LAND=0`, lower `LAND_BUDGET_RESERVE_V6` to 1500, add a regression test for the new constant, re-run acceptance — do not add other knobs.

Optionally log first-buy-day histogram vs a short v5 reference (e.g. 10 seeds) for the version-log writeup.

- [ ] **Step 2: 20-pair screen vs v5**

```bash
python scripts/run_tournament.py \
  agents/task_teacher_v6/main.py agents/task_teacher_v5/main.py \
  --episodes 20 --episode-steps 720 --seed 87000 \
  > .superpowers/sdd/task-9-v6-screen-v5.log 2>&1
grep -E 'win_rate|Hoeffding|CI' .superpowers/sdd/task-9-v6-screen-v5.log
```

- If CI wholly below 0.50 → **stop, do not promote**.
- If wholly above 0.50 → may skip straight to docs as promoted (still run 50-pair for the log), or run Step 3 for the authoritative number.
- If straddles 0.50 → Step 3 required.

- [ ] **Step 3: 50-pair promotion vs v5 (if needed / for the log)**

```bash
python scripts/run_tournament.py \
  agents/task_teacher_v6/main.py agents/task_teacher_v5/main.py \
  --episodes 50 --episode-steps 720 --seed 88000 \
  > .superpowers/sdd/task-9-v6-promo-v5.log 2>&1
```

Promote only if CI wholly above 0.50.

- [ ] **Step 4: Regression screens**

```bash
python scripts/run_tournament.py \
  agents/task_teacher_v6/main.py agents/task_teacher_v2/main.py starter \
  --episodes 20 --episode-steps 720 --seed 89000 \
  > .superpowers/sdd/task-9-v6-regression.log 2>&1
```

- [ ] **Step 5: Docs + commit**

Update version log / next_steps / strategy / README with numbers and promote/no-promote. Mark design status **implemented** (and promoted or not).

```bash
git add docs/
git commit -m "$(cat <<'EOF'
docs: record task_teacher_v6 eval vs v5

EOF
)"
```

Do **not** ladder-submit unless the user explicitly asks after a promote.

---

## Spec coverage (self-review)

| Spec requirement | Task |
| --- | --- |
| Additive `budget_reserve` default 400 | Task 1 |
| v6 agent, `LAND_BUDGET_RESERVE_V6=2000`, `MAX_GEESE=0` | Task 2 |
| v5/earlier mains immutable | Task 2 (copy-only) |
| Unit/agent tests for 2000 vs 400 cash bars | Tasks 1–2 |
| Packaging smoke | Task 3 |
| Acceptance + Hoeffding vs v5 + regressions | Task 4 |
| No animals / no earliest-day / no sat bump | Global + Tasks 2–4 |
| If land never fires → lower to 1500 | Task 4 Step 1 |
| Ladder submit only post-promote + user ask | Task 4 note |

No TBD/TODO placeholders. Signature `budget_reserve: float = LAND_BUDGET_RESERVE` is consistent across Tasks 1–2.
