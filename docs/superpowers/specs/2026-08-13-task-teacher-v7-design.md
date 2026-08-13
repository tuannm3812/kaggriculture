# Task Teacher v7 — Design (Cow / pasture / milk on v5)

Written 2026-08-13. Status: **implemented, not promoted** (20-pair vs v5
`win_rate=0.000`, Hoeffding CI `[0.000, 0.380]`, mean margin `-$17k`).
Cow loop places animals but does not beat land-only Melon locally; no
notebook submit. Implementation plan:
`docs/superpowers/plans/2026-08-13-task-teacher-v7-implementation.md`.

Motivated by ladder replay on `task_teacher_v5` (`docs/8_ladder_replay_analysis.md`
refresh): land-only holds vs shallow opponents, but **land+animals** is the
deep loss mode. v4 Goose failed locally from FEED/PICKUP labor tax on Melon;
v6 cash-floor land delay was locally inert. v7 keeps v5 Melon + NE land and
adds a **bounded Cow loop**.

## 1. Goal

Ship `task_teacher_v7` = `task_teacher_v5` (Wheat/Carrot/Melon + hire + NE
`BUY_LAND`) + a **Cow / pasture / milk** loop capped at **`MAX_COWS = 6`**,
with labor rules so FEED does not recreate v4’s Goose Melon-tax.

### Non-goals

- Goose / Sheep / `BUILD_COOP` path (keep `MAX_GEESE = 0`)
- SW / SE land
- Fertilizer collect/apply
- Editing any existing `agents/*/main.py` (v5/v6 stay immutable)
- Learned policy / BC / PPO
- Recalibrating hire constants unless eval forces it
- Promoting on ladder metrics alone

### Hard constraint (physics)

Verified against pinned env `kaggle-environments` Kaggriculture:

- `BUILD_PASTURE` → `{"kind": "PASTURE"}`; `BUY_ANIMAL` COW ($600 in 1.29.3)
  deposits into **shed**; `PLACE` needs inventory + empty PASTURE → needs
  `PICKUP`.
- `FEED` consumes **1 WHEAT from unit inventory**; 2 consecutive unfed days
  → animal escapes (structure remains).
- Milk via `HARVEST` on animal tile; sell `MILK` from shed.
- Cow `first_yield_day=8`, `interval=2`, `max_held=6` (yield storage, not
  ownership cap). Soft ownership cap is ours: `MAX_COWS`.

Real lever: **don’t own more cows than spare labor + hire can support**,
with priority:

1. Melon emergency `WATER` (`consecutive_unwatered >= 1`)
2. FEED when `consecutive_unfed >= 1` (escape prevention)
3. Economic Melon / plant / land work
4. Non-emergency FEED (budget-capped) and CARE (optional)

### Success

- Acceptance (100×720 vs `starter`): all DONE/finite; `BUY_LAND > 0`;
  `BUY_ANIMAL` COW `> 0`; `FEED` bounded; Melon `HARVEST` still fires; no
  Goose orders
- Animal screen: mean FEED actions/day ≤ `MAX_FEED_ACTIONS_PER_DAY`; Melon
  harvest count not collapsed vs a short v5 reference
- Promotion: paired Hoeffding vs **`task_teacher_v5`** — CI wholly above
  0.50 (20→50 pair protocol)
- Notebook submit only after promote (same path as v5)

## 2. Architecture

### Approach (locked)

**Task-graph cows with a daily FEED budget** — extend `tasking.py` like v4’s
Goose path, but for Cow/Pasture, and demote/cap FEED so Melon stays first.

Rejected: market-first cows (escape risk); fixed NE pasture corridor
(brittle).

### Shared library (additive)

In `src/kaggriculture_lib/tasking.py`:

- `TaskKind.BUILD_PASTURE`
- `generate_tasks(..., want_pasture=False, cow_in_any_inventory=False,
  max_feed_tasks=None, non_emergency_feed_tier=DAILY_CARE,
  care_tier=DAILY_CARE)`
  - Defaults preserve v4 Goose behavior
  - v7 passes `non_emergency_feed_tier=OPTIONAL`, `care_tier=OPTIONAL`,
    `max_feed_tasks=MAX_FEED_ACTIONS_PER_DAY`
  - Empty PASTURE + cow in inventory → `PLACE` COW
  - Shed COW + empty PASTURE → `PICKUP` COW
  - `want_pasture` emits one `BUILD_PASTURE` on first empty unlocked
    shed-access tile (same target picker as coop)
  - After generation, if `max_feed_tasks` is set, keep at most that many
    `FEED` tasks (emergency tier first)

### New agent

`agents/task_teacher_v7/main.py` — forward-copy of v5 with:

| Constant | Value |
| --- | ---: |
| `MAX_GEESE` | `0` |
| `MAX_COWS` | `6` |
| `MAX_FEED_ACTIONS_PER_DAY` | `6` |
| `COW_COST` | `economy.ANIMALS["COW"]["cost"]` (600) |

Turn order (same budget stack spirit as v4/v5):

1. Generate tasks (pasture/cow flags + FEED budget kwargs)
2. `joint_assign`
3. Sell crops (wheat reserved via `wheat_reserved_for_feed(placed_cows, …)`)
   + sell `MILK`
4. Hire → land (v5 `should_buy_land` defaults) → at most one
   `BUY_ANIMAL COW` if `owned_cows < MAX_COWS` and (empty pasture or
   `want_pasture`) and cash clears cost after reserves
5. Resolve unit actions including `BUILD_PASTURE`

`owned_cows` = placed + shed + inventory (same buy-cap lesson as v4 Goose).

### Why `MAX_COWS = 6` (not 8)

Locked band was ~6–8. Start at **6** (= one FEED per cow within the daily
FEED budget, and aligned with cow `max_held`). If acceptance shows clean
labor and Hoeffding is close, raising to 8 is a one-constant follow-up —
do not stack knobs in the same version.

## 3. Tests

| File | Coverage |
| --- | --- |
| `tests/test_tasking.py` | `want_pasture` → `BUILD_PASTURE`; PICKUP/PLACE COW; `max_feed_tasks` caps FEED; default Goose path unchanged |
| `tests/test_task_teacher_v7.py` | crops; `MAX_COWS==6`; `MAX_GEESE==0`; emits `BUY_LAND`; emits `BUY_ANIMAL COW` under fixture; never Goose; short episode DONE/finite |
| `tests/test_package_agent.py` | standalone package smoke for v7 |

## 4. Evaluation

Fresh seeds (do not reuse v5/v6 ranges).

1. Acceptance vs `starter` (100×720) + action coverage
2. Animal-aware screen (FEED/day bound; Melon harvest vs v5 reference)
3. 20-pair screen vs `task_teacher_v5`
4. 50-pair promotion if screen clears/straddles
5. Package + notebook submit **only if** promote clears

## 5. Approval checklist (locked in brainstorming)

1. Cow only — **approved**
2. Medium cap (~6–8) + hard daily FEED budget / Melon-first — **approved**
   (implement as `MAX_COWS=6`, `MAX_FEED_ACTIONS_PER_DAY=6`, optional FEED/CARE tiers)
3. NE land only — **approved**
4. Promote vs v5 Hoeffding **and** animal-aware local screen — **approved**
5. Approach 1 (task-graph + FEED budget) — **approved** via “finish it”
6. Design §1 — **approved** via “finish it”
