# Task Teacher v3 — Design

Written 2026-08-02. Status: **pending approval**. This file is intentionally
focused. It inherits the project and teacher constraints from the
authoritative competition and teacher specs, and everything in
`task_teacher_v2`'s design and implementation unchanged.

## 1. Goal

Extend `task_teacher_v2` (current `competitive_champion`) with ongoing crops
(Tomato, Strawberry) as the one variable changed, per the project's
established immutable-version, one-variable-at-a-time construction sequence.

No animals, no fertilizer, no `PICKUP`/`PLACE`, and no learned policy are
added in v3. Fertilizer requires an entirely new action type (`PICKUP`,
moving items from the farm-level shed into a specific unit's inventory —
verified against the real environment source: `BUY_PRODUCT("FERTILIZER")`
deposits into the shed, not any unit's inventory, and `FERTILIZE` consumes
from a unit's own inventory) that no prior version has built or tested.
Bundling it with ongoing crops would break the "one variable changed"
discipline that has kept every prior version's regressions cheap to
isolate. It is deferred to its own version (tentatively v4) once ongoing
crops are proven out.

## 2. Verified Mechanics

Verified directly against
`kaggle_environments/envs/kaggriculture/kaggriculture.py` (the pinned
`1.29.3` source), not assumed from the `CROPS` table alone:

- Ongoing crops (`CROPS[crop]["ongoing"] is True`) start at `yield_units=0`
  on planting (`_new_plant`), unlike one-time crops' guaranteed base 1 unit.
- Yield accumulates via scheduled ticks at day-offsets from planting
  (`economy.ongoing_crop_production_days`, already implemented and tested —
  e.g. Tomato ticks at offsets `[8, 9, 10, 11]`), adding 1 unit per tick
  (2 if fertilized *and* watered that day — not reachable in v3, no
  fertilizer), capped at `max_yield`.
- **Watering is still required daily**, even though it has no direct yield
  effect for ongoing crops (that code path is gated on `not
  crop_data["ongoing"]`): the universal "2 consecutive unwatered days →
  tile becomes a `WEED`" rule (`_daily_refresh_plants`) applies to every
  `PLANT` tile regardless of crop type.
- **Harvest never clears an ongoing-crop tile** (`_apply_unit_action`'s
  `HARVEST` handler only sets `tiles[fy][fx] = None` `if not
  crop_data["ongoing"]`). The same tile keeps producing and can be
  harvested repeatedly across the season.
- Once an ongoing crop reaches its final tick (`production_count ==
  max_yield`), `max_lifespan_step` is set and the tile begins the same
  decay-to-weed countdown one-time crops enter after their harvest window
  (`_decay_plants`): `yield_units` drains by 1 every 2 steps until it hits
  0, at which point the tile becomes a `WEED`. This is deterministic and
  needs no special handling beyond harvesting before it happens, same
  incentive one-time crops already create.

## 3. Task Generation Extension

`tasking.generate_tasks`'s `PLANT`-tile branch gets one new fork, verified
against the exact mechanics above — HARVEST eligibility differs by crop
type, everything else is unchanged:

```python
elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
    cd = economy.CROPS[tile["crop"]]
    if not tile["watered_today"]:
        ...  # unchanged: WATER task, same tier logic for both crop types
    elif cd["ongoing"]:
        if tile["yield_units"] > 0:
            ...  # HARVEST task
    elif day - tile["planted_day"] >= cd["max_yield_day"]:
        ...  # HARVEST task, unchanged one-time-crop day-based gate
```

The one-time-crop day-based gate is *not* replaced with a uniform
`yield_units > 0` check: one-time crops start with 1 base unit immediately
on planting and deliberately wait out the full watering-bonus window
before harvesting (already covered by
`test_plant_not_watered_waters_before_harvesting` and
`test_plant_watered_but_not_yet_mature_passes`) — switching to a uniform
check would cause premature harvesting and lose bonus yield. Ongoing crops
have no such window; `yield_units > 0` is the correct and only signal that
there's something to collect.

## 4. Crop Scoring (Day-Aware)

`tasking._best_feasible_crop` currently does two things for every
candidate, both one-time-crop-specific: filters via
`economy.can_mature_in_time` (a single maturity-day check), then scores
via `tasking._score_crop` (`(revenue - seed_cost) / (max_yield_day + 1)`,
a $/day figure). Both need an ongoing-crop counterpart, and
`_best_feasible_crop` dispatches on `economy.CROPS[crop]["ongoing"]` to
pick the right pair for each candidate — one-time crops keep their
existing path unchanged.

New `economy.can_ongoing_crop_reach_any_tick(crop, current_day, last_day)`
(the feasibility filter, replacing `can_mature_in_time` for ongoing
candidates): `True` iff at least one entry in
`ongoing_crop_production_days(crop)` satisfies `current_day + offset <=
last_day`. A crop with zero reachable ticks is excluded from that day's
candidates entirely — the same treatment `can_mature_in_time` already
gives infeasible one-time crops, not a negative score that still enters
the comparison.

New `tasking._score_ongoing_crop(crop, price, current_day, last_day)` (the
scoring function, used only once feasibility is confirmed): count
`reachable_ticks` — entries in `ongoing_crop_production_days(crop)` with
`current_day + offset <= last_day`; `revenue = reachable_ticks * price`;
`cost = CROPS[crop]["seed"]`; normalize by `(last reachable offset -
first reachable offset + 1)` days (the ongoing-crop analog of one-time
crops' `max_yield_day + 1` lifespan denominator, i.e. the actual span this
planting decision commits the tile for) to get a $/day figure directly
comparable to `_score_crop`'s output, so `_best_feasible_crop` can pick
whichever candidate scores highest across both crop types with no
separate ranking pass.

## 5. Acceptance Tests

New, alongside every existing test in `task_teacher_v1`/`v2`'s suites,
which must keep passing unmodified:

- Ongoing-crop `PLANT` task generated for an empty tile when an ongoing
  crop scores highest that day.
- Ongoing-crop `WATER` task still generated despite no direct yield bonus
  (weed-prevention only).
- Ongoing-crop `HARVEST` task generated only when `yield_units > 0`, and
  generated *again* on a later turn once yield reaccumulates — proving the
  tile isn't cleared, the core behavioral difference from one-time crops.
- Day-aware scoring: an ongoing crop with zero reachable ticks late in the
  season is excluded from that day's candidates.
- Crop selection: at least one scenario where an ongoing crop wins over a
  one-time crop, and one where a one-time crop wins over an ongoing crop,
  on the same day-aware scale.
- Full-episode regression: a real run where an ongoing-crop tile survives
  multiple harvest cycles across the season without ever being cleared.

## 6. Evaluation

Same protocol every version has gone through:

1. 100-episode acceptance gate (both seats; validity; action-kind coverage
   including the new ongoing-crop harvest-without-clearing pattern;
   inference latency).
2. Paired Hoeffding-CI screen: 20 pairs vs. `task_teacher_v2` (current
   champion) first.
3. If the screen is positive, escalate to the 50-pair promotion gate
   (adding 25-pair blocks per the authoritative protocol if the interval
   remains ambiguous) — promotion requires the CI wholly above 0.50 vs. v2.
4. Regression screens vs. `roi_teacher_v3` and `starter`.

## 7. Approval Questions

1. Approve scoping v3 to ongoing crops only, deferring fertilizer/`PICKUP`
   to a later version?
2. Approve the day-aware ongoing-crop scoring model (only reachable ticks
   count, excluded entirely if zero reachable)?
3. Approve the task-generation extension (ongoing-crop HARVEST gated on
   `yield_units > 0`, one-time crops' existing day-based gate unchanged)?
4. Approve the acceptance and evaluation gates above?

## 8. Correction — §4 Lifespan Denominator Bug — 2026-08-06

**This is my own design error**, not an implementation deviation — Cursor
built `_score_ongoing_crop` exactly as §4 specified, and the bug is in
that specification.

§4's `(last reachable offset - first reachable offset + 1)` lifespan
denominator is **not** analogous to one-time crops' `max_yield_day + 1` —
I claimed it was, and that claim was wrong. `max_yield_day + 1` counts
days from *planting* (offset 0) through the harvest event, inclusive.
`(last - first + 1)` only counts the span *between* the first and last
reachable tick, silently dropping the days from planting to the first
tick entirely. The correct, actually-analogous denominator is
`reachable[-1] + 1` — mirroring `max_yield_day + 1` exactly, using the
last reachable tick's day-offset from planting.

**Measured impact:** at `current_day=0` (full season ahead), Strawberry's
buggy score is `54.29` vs. the corrected `22.35` — already a ~2.4x
inflation, and Strawberry's corrected score (`22.35`) sits *below* Melon's
`109.23`, not above it. The bug gets worse late-season: at `current_day=17`
(2 of 4 ticks reachable), the buggy score is `46.67` vs. the corrected
`10.77` — a ~4.3x inflation. This directly explains the Task 9 evaluation
failure below: `_best_feasible_crop` was picking Strawberry over Melon in
scenarios where Melon should have won.

**Required fix**, test-first: change
`tasking._score_ongoing_crop`'s `lifespan_days` from
`reachable[-1] - reachable[0] + 1` to `reachable[-1] + 1`. Add a
regression test asserting Melon beats Strawberry at `current_day=0` under
base prices (the case that should have been caught before Task 9, and
wasn't, because no existing test compared an ongoing crop's score against
a *correctly*-scored one-time crop at realistic relative prices — the
existing `_best_feasible_crop` tests only ever compared Strawberry/Tomato
against Wheat/Carrot, both of which the buggy formula still beat). Re-run
Task 9's full evaluation (100-episode acceptance gate, 20-pair screen,
promotion gate if positive) after the fix — the current result
(`win_rate=0.025`, Hoeffding CI `[0.000, 0.405]` vs. `task_teacher_v2`, 20
pairs) does not promote and should be treated as superseded once the fix
lands, not as v3's final evaluation.
