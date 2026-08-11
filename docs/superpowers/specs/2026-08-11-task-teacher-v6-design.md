# Task Teacher v6 — Design (delayed NE land via cash floor)

Written 2026-08-11. Status: **approved** (spec reviewed 2026-08-11).

Motivated by the 2026-08-11 ladder replay check on submitted
`task_teacher_v5` (`docs/8_ladder_replay_analysis.md`): `BUY_LAND` fired in
17/17 public games (always NE), but **day-1 land** left the bank at
~$10–60 through day 13 while strong NW-only Melon bots cashed a day-12
spike and won without land. Deep losses to 3–4Q + animals remain a later
problem; this version only fixes the cash-starvation timing of NE buy.

## 1. Goal

Ship `task_teacher_v6` — same land-only teacher as v5 (`MAX_GEESE = 0`, NE
only), with a **higher land budget reserve** so `BUY_LAND` waits until the
bank can absorb $1k without starving Melon cashflow.

### Non-goals

- Animals / Goose / Cow / Sheep / coops / pastures
- SW / SE land
- Earliest-day hard gate (`day >= N`)
- Raising `NW_SATURATION_PLANTS` (unless acceptance shows land never fires
  under the new reserve — then lower the reserve first, do not stack knobs)
- Editing any existing `agents/*/main.py` (v5 and earlier stay immutable)
- Changing default `should_buy_land` behavior for v4/v5 callers

### Success

- Acceptance: 100×720 vs `starter` all DONE/finite; `BUY_LAND > 0` across
  the run; **no** `BUY_ANIMAL` / animal structure loop
- Telemetry: typical first `BUY_LAND` day clearly later than v5’s day-0/1
  pattern (logged; not a brittle unit assert)
- Promotion: paired Hoeffding vs **`task_teacher_v5`** — CI wholly above
  0.50 at the usual 20-pair screen → 50-pair gate
- Regression: stay strong vs `task_teacher_v2` and `starter` (20-pair
  screens)
- Existing v4/v5 / default-`should_buy_land` tests keep passing

Ladder submit and replay refresh are **post-promote** validation, not a
promotion blocker.

## 2. Architecture

### New agent

`agents/task_teacher_v6/main.py` — forward-copy of
`agents/task_teacher_v5/main.py` (`MAX_GEESE = 0`, land-only docstring
updated). Pass an explicit higher reserve into `should_buy_land`:

```python
LAND_BUDGET_RESERVE_V6 = 2000  # need cost+$2000 post-hire (~$3000) before NE buy

should_buy_land(..., budget_reserve=LAND_BUDGET_RESERVE_V6)
```

### Shared library (additive)

In `src/kaggriculture_lib/tasking.py`, extend `should_buy_land` with an
optional keyword (default preserves today’s gate):

```python
def should_buy_land(
    ...,
    budget_reserve: float = LAND_BUDGET_RESERVE,  # still 400
) -> bool:
    ...
    if money - reserved_for_hire < cost + budget_reserve:
        return False
```

All other gates unchanged: exactly one unlocked quadrant (NW),
`plant_tile_count >= NW_SATURATION_PLANTS` (12),
`existing_hands >= MIN_HANDS_BEFORE_LAND` (3),
`last_day - day >= LAND_MIN_DAYS_REMAINING` (12),
`estimate_hire_value(...) == 0` (hire-before-land).

### Why `budget_reserve=2000`

Ladder day-1 buys cleared the current bar (`cost + 400 = $1400`) with
roughly ~$1.8k bank. Requiring `cost + 2000 = $3000` after hire reserve is
incompatible with early seed+hire drawdown and compatible with post–Melon
sell cash. If acceptance ever shows `BUY_LAND = 0` for the whole 100-ep
gate, **lower toward 1500** and re-run — do not add earliest-day or
saturation knobs in the same version.

## 3. Tests

| File | Coverage |
| --- | --- |
| `tests/test_tasking.py` | Default `budget_reserve` behavior unchanged; new case: identical fixture that passes at 400 fails at 2000 |
| `tests/test_task_teacher_v6.py` | `MAX_GEESE == 0`; `LAND_BUDGET_RESERVE_V6 == 2000`; emits `BUY_LAND` when cash clears the v6 bar; does not emit when cash only clears the v5 (400) bar; never `BUY_ANIMAL`; short episode DONE/finite |
| `tests/test_package_agent.py` | Standalone package smoke for v6 |

## 4. Evaluation

Fresh seeds (do not reuse v4/v5 eval seed ranges). Same tournament harness
and honesty rule as prior teacher versions.

1. Acceptance vs `starter` (100×720) + action coverage (`BUY_LAND>0`,
   `BUY_ANIMAL=0`) + first-buy-day histogram vs a short v5 reference run
2. 20-pair screen vs `task_teacher_v5`
3. 50-pair promotion vs `task_teacher_v5` if the screen straddles or clears
4. 20-pair regression vs `task_teacher_v2` and `starter`
5. Package via `scripts/package_agent.py`; notebook submit only after
   promote (`scripts/submit_agent_notebook.sh`)

## 5. Approval checklist (locked in brainstorming)

1. New immutable `task_teacher_v6`; additive `budget_reserve` param so
   v4/v5 defaults stay 400 — **approved**
2. Delay via higher cash floor only (not earliest-day / not saturation
   bump as the primary lever) — **approved**
3. Promote vs `task_teacher_v5` Hoeffding; ladder post-submit — **approved**
4. Approach: raise reserve for v6 only; starting value **2000** — **approved**
5. Design §§1–3 — **approved**
