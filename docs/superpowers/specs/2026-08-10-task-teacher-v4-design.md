# Task Teacher v4 — Design

Written 2026-08-10. Status: **implemented; land gate retuned (sat=12); still not promoted**
(Task 9c vs v2 still 0.000 — see `docs/4_agent_version_log.md`).
Implementation plan: `docs/superpowers/plans/2026-08-10-task-teacher-v4-implementation.md`.

Inherits project constraints from the authoritative competition and teacher
specs. Extends the `task_teacher_v2` line (current `competitive_champion` /
ladder submission). `task_teacher_v3` (ongoing crops) was built and
evaluated but **not promoted**; its shared-library scoring helpers remain
available. Ladder evidence in `docs/8_ladder_replay_analysis.md` (56-episode
refresh) motivates this version: animals (with or without land) drive the
deep losses; land-only opponents remain beatable.

## 1. Goal

Ship `task_teacher_v4` that adds two capabilities on top of the v2
task/hire teacher:

1. **ROI-gated purchase of at most one extra quadrant** (NE at $1000).
2. **Goose loop** — build coop → buy/place goose → daily feed/care →
   harvest/sell eggs.

So we can compete with the ladder’s animal-using field without boiling the
ocean (no Cow/Sheep, no fertilizer apply, no 3rd/4th quadrant).

### Non-goals

- Cow / Sheep / `BUILD_PASTURE`
- `COLLECT_FERTILIZER` / `FERTILIZE`
- Quadrants SW / SE (hard-cap: NW + NE only)
- Forcing Tomato/Strawberry into the agent’s default candidate list
  (shared day-aware scorer may still select them if they win)
- Learned policy / BC / PPO
- Recalibrating hire constants unless a v4 evaluation gate forces it
- Promoting on ladder metrics alone (see §6)

### Success

- **Promotion:** paired Hoeffding vs `task_teacher_v2` — CI wholly above
  0.50 at the usual 20-pair screen → 50-pair promotion protocol; 100-episode
  acceptance gate clean.
- **Post-submit (not a promote blocker):** refresh ladder win rate vs
  animal-using opponents after submit.
- **Structural:** existing v1/v2/v3 tests keep passing; existing
  `agents/*/main.py` files remain immutable.

### Architecture choice

**Extend the task graph** (Approach 1): animal/structure work as
first-class tasks in `tasking.py`; `BUY_LAND` / `BUY_ANIMAL` as market
orders with reservation discipline like `HIRE`. Rejected alternatives: a
separate expansion planner outside tasks (two brains fighting for budget),
and a fixed day-calendar script (too brittle vs ROI-gated land).

### Base agent

New immutable `agents/task_teacher_v4/main.py` copied forward from
`task_teacher_v2`. Shared `economy` / `tasking` carry the new logic.
Ongoing-crop dispatch already in the library stays available; v4 need not
identity itself as “v3 + land.”

## 2. Verified Mechanics

Verified against
`kaggle_environments/envs/kaggriculture/kaggriculture.py` (pinned
`1.29.3`), not assumed from tables alone.

### Land

- `BUY_LAND` unlocks `LAND_ORDER = ["NE", "SW", "SE"]` at
  `LAND_PRICES = [1000, 2000, 4000]` (`_do_buy_land`).
- v4 only ever buys the first extra → **NE @ $1000**.

### Goose / coop

- `BUILD_COOP` on an empty tile → `{"kind": "COOP"}`.
- `BUY_ANIMAL` Goose costs 300 and deposits into **`private["shed"]`**, not
  unit inventory (`_commit_buy`, `BUY_ANIMAL` branch) — same pattern as
  `BUY_PRODUCT`, **not** like `BUY_SEED`.
- `PLACE` Goose succeeds only when standing on a matching empty structure
  (`kind == "COOP"`) and the unit’s inventory holds the animal
  (`_inv_take(inv, item, 1)`). Therefore **`PICKUP` from the shed is
  required** before `PLACE` (see below).
- Animal tile shape (`_new_animal`): `placed_day`, `yield_units`,
  `consecutive_unfed`, `fed_today`, `cared_today`,
  `fertilizer_available`, `pending_care_bonus`.
- Production ticks in `_daily_refresh_animals`: first yield at
  `first_yield_day=4`, then every `interval=1` day; care bonus only
  consumed on a **fed** production day.
- **2 consecutive unfed days → animal escapes**; empty `COOP` remains.
- Egg collection uses the same **`HARVEST`** op as plants: if the tile has
  an `animal` key and `yield_units > 0`, product goes to unit inventory
  (`EGG`). Tile is **not** cleared.
- End-of-day dumps unit inventories into the shed (`_drop_inventories_to_shed`);
  sell `EGG` from the shed on later turns.

### Feed / inventory (scope-critical)

- `FEED` consumes **1 WHEAT from the acting unit’s inventory**, not from
  the shed directly.
- Therefore v4 **must** implement shed→inventory **`PICKUP`** for at least
  `WHEAT` (feed) and `GOOSE` (place). This is the same `PICKUP` action
  type v3 deferred for fertilizer — but here it is **not optional**:
  without it, `PLACE`/`FEED` cannot run after market buys or after EOD
  shed dump. Fertilizer pickup/apply remain out of scope.
- `CARE` is free (no inventory); banks `pending_care_bonus` when both fed
  and cared the same day.
- `COLLECT_FERTILIZER` / `FERTILIZE` exist in the env; **v4 ignores them**.

## 3. Land Gate (`should_buy_land`)

Hard-cap: only NE. At most one `BUY_LAND` order per turn.

```text
should_buy_land(
  unlocked_quadrants,
  money,
  projected_load,
  remaining_turns_today,
  existing_hands,
  day, last_day,
  reserved_for_hire,
) -> bool
```

Approve only if all hold:

1. **Cap:** currently exactly one unlocked quadrant (NW); refuse if NE owned.
2. **Afford:** `money - reserved_for_hire >= 1000` after a small
   seed/feed safety reserve (constant fixed in the implementation plan).
3. **Season horizon:** enough days left for new tiles to matter — default
   proposal `last_day - day >= 12` (Melon-length cycle); tune only with
   evidence, not mid-eval.
4. **Demand:** current 25 tiles are saturated — e.g. hire value is already
   zero at a useful hand floor while pending crop load remains high — so
   land means “more tiles,” not “buy because rich.”
5. **Ordering:** evaluate `should_hire` first and reserve; then
   `should_buy_land` on remaining money (hire is the cheaper overload fix).

Agent emits `["BUY_LAND"]` in `market` when true (market-only, like
`HIRE`).

## 4. Goose Loop (Tasks + Market)

### Setup sequence

1. Dig/clear a tile if needed (existing `DIG`).
2. `BUILD_COOP` on empty tile.
3. `BUY_ANIMAL` Goose (market) → shed.
4. `PICKUP` Goose at shed-adjacent tile → unit inventory.
5. `PLACE` Goose on coop.

Cap geese in v4 at a small constant (**propose 2**, ≤ `max_held=4`) so
wheat/feed and land/hire budgets stay solvable. Exact cap in the plan.

### Task generation extensions

| Task | When | Priority sketch |
| --- | --- | --- |
| `BUILD_COOP` | Goose path approved, no coop, free tile | ECONOMIC |
| `PICKUP` (GOOSE / WHEAT) | Shed has item; unit needs it for PLACE/FEED | ECONOMIC / DAILY_CARE |
| `PLACE` (GOOSE) | On empty coop; goose in inventory | ECONOMIC |
| `FEED` | Animal present, not `fed_today` | DAILY_CARE; EMERGENCY if `consecutive_unfed >= 1` |
| `CARE` | Animal present, fed (or same-day care still valuable), not `cared_today` | DAILY_CARE (below FEED) |
| `HARVEST` (eggs) | Animal tile with `yield_units > 0` | DECAYING_YIELD-class |

`joint_assign` routes units to these like WATER/HARVEST. No fertilizer
tasks.

### Feed economy

- `wheat_reserved_for_feed(geese_count, days_horizon)` — do not SELL wheat
  below reserve; top up via existing wheat plant/buy path when reserve
  would go negative.
- Prefer `PICKUP` wheat near shed before FEED when inventory empty.

### Egg income

- Sell `EGG` from shed every turn (extend sell list beyond crop
  candidates).

### Same-turn budget stack

1. Assign emergency FEED (and WATER) tasks.
2. `should_hire` → reserve.
3. `should_buy_land` → reserve.
4. Goose setup market (`BUY_ANIMAL`) if path approved and affordable.
5. Seed buys + wheat top-up.

## 5. File Layout

| Path | Change |
| --- | --- |
| `agents/task_teacher_v4/main.py` | **Create** — v2 forward-copy; wire land/goose/PICKUP |
| `agents/task_teacher_v2/main.py`, `v3/main.py` | **Immutable** |
| `src/kaggriculture_lib/tasking.py` | TaskKinds, `generate_tasks` branches, `should_buy_land`, feed reserve, PICKUP tasks |
| `src/kaggriculture_lib/economy.py` | Goose/feed helpers only as needed; mirror env + tests |
| `tests/test_tasking.py`, `tests/test_economy.py` | TDD unit coverage |
| `tests/test_task_teacher_v4.py` | Agent behavior + short simulator episode |
| `tests/test_package_agent.py` | Standalone package smoke for v4 |

## 6. Evaluation Protocol

Same gates as v2/v3:

1. **Acceptance:** 100×720 vs `starter` — DONE/finite; assert we actually
   emit `BUY_LAND` / goose / `PICKUP`/`FEED` when affordable (local
   opponents still won’t use animals).
2. **Screen:** 20-pair vs `task_teacher_v2` (Hoeffding).
3. **Promote:** 50-pair if screen positive or ambiguous; CI wholly above
   0.50 required.
4. **Regression:** 20-pair vs `roi_teacher_v3` + `starter`.
5. **Post-submit:** ladder refresh vs animal-using opponents — validation,
   not a promote blocker.

**Honesty rule (v3 lesson):** if local vs-v2 is ~identity because Melon
still dominates single-quadrant play and land/goose never pay locally,
do **not** force-promote. Document the result. Ladder lift may still
justify a later submit experiment, but champion status follows the
protocol.

Packaging: reuse `scripts/package_agent.py` auto-discovery; add
`test_packaged_task_teacher_v4_runs_standalone_without_pythonpath`.

## 7. Open Items for the Implementation Plan

Resolve with env-backed tests, not guesswork, before coding agents:

1. Exact goose cap (2 vs 3–4) and seed/feed safety reserve dollars.
2. Exact `should_buy_land` saturation predicate (load/hire-floor formula).
3. Whether CARE is worth emitting every day or only when a production tick
   is imminent (bonus only pays on fed production days).
4. Interaction of NE unlock with `unlocked_quadrants` task generation
   (already iterates unlocked quads — verify 50-tile coverage).
   **Resolved 2026-08-10:** `test_generate_tasks_emits_plant_on_ne_when_ne_unlocked`
   (25 NW + 25 NE) and `test_acts_on_ne_tile_when_ne_unlocked`.
5. Branch base: merge/close v3 PR first vs branch v4 from `main` after
   packaging fix. **Resolved:** `feat/task-teacher-v4` from merged v3 tip.

## 8. Approval Checklist

1. Approve goal / non-goals / Approach 1 / v2-forward base?
2. Approve land gate (NE only, hire-then-land, ROI/saturation)?
3. Approve Goose loop including **required minimal `PICKUP`** for WHEAT +
   GOOSE (fertilizer still out)?
4. Approve evaluation protocol and honesty rule?

## 9. Decisions Log (brainstorm 2026-08-10)

| Topic | Decision |
| --- | --- |
| Scope | Land + animals together |
| Promotion bar | Local Hoeffding vs v2; ladder post-submit only |
| Animals | Goose only |
| Land policy | ROI/backlog-gated; hard-cap 2 quadrants (NW+NE) |
| Base agent | v2 forward-copy; shared-lib ongoing helpers available |
| Fertilizer | Out of scope |
| Architecture | Extend task graph (Approach 1) |
| PICKUP | **In scope** for WHEAT + GOOSE only (env-required) |
