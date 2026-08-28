# Task Teacher v21 — Melon Planting Cutoff — Design

Written 2026-08-28. Status: **approved**. Inherits every project and teacher
constraint from the authoritative competition and teacher specs, and
everything in `task_teacher_v20` unchanged except the one variable below.

## 1. Goal

Stop growing melon that the market will never pay for. One variable: a
cutoff day after which melon is no longer planted.

## 2. Measured Motivation

From 17 real ladder episodes of the live `task_teacher_v20` submission
(`55838476`), replays under `replays/ladder/v20_live/`:

| | melons/ep | $/ep | $/unit | median sale day |
| --- | ---: | ---: | ---: | ---: |
| **us** | 192.9 | $10,998 | **$57.0** | 26 |
| **opponents** | 102.0 | $8,642 | **$84.7** | 21 |

We sell 1.9x their volume for 1.3x their revenue, at 67% of their unit
price. Broken down by day (8-episode sample, 1,543 units):

| day | units | **$/unit** | market excess inventory at sale |
| ---: | ---: | ---: | --- |
| 13 | 800 | $81.1 | +86 .. +158 |
| 14 | 192 | $42.5 | +109 .. +157 |
| **26** | **398** | **$10.8** | +145 .. +157 |
| 27 | 63 | $4.0 | +157 |
| 28 | 60 | $4.0 | +157 |
| 29 | 30 | $3.4 | +157 .. +158 |

**36% of our melon volume (~69 units/episode) sells for ~$7/unit.** Those
melons consumed tiles, $80-per-tile seed money, daily watering actions,
harvest actions and shed space, and returned about $483/episode.

The market never recovers: excess inventory sits at +157 from day 14 to
day 29. Melon is the only product **no town shop demands** — its sole
drain is the town centre at roughly 1 unit/day — so unlike wheat or
strawberry, supply dumped into it is gone for the rest of the season.
Absorption is a whole-game *stock* of ~113 units at >=50% of base
(`above_func=sq`, `above_target=3.60`), shared with the opponent, not a
rate that refills.

## 3. Root Cause: a second planting cycle that cannot pay

Measured planting behaviour (same 8 episodes):

- **51 melon plantings per episode**, at a **peak of 25 concurrent tiles**
  (exactly one quadrant, in every sampled episode).
- That is two cycles. Melon's `max_yield_day` is 12, so:
  - **Cycle 1** — planted ~day 0-2, harvested ~day 12, sold day 13-14 at
    **$81 / $42.5**. This cycle works.
  - **Cycle 2** — planted ~day 13-14, harvested ~day 25, sold day 26-29 at
    **$4-11**. This cycle is the waste.

Cycle 1 alone produces ~150 units (25 tiles x 6), of which ~124 sold and
~26 were lost to shed overflow. That single cycle already saturates
melon's whole-game absorption. **Cycle 2 is planted into a market that our
own cycle-1 sale has already crashed.**

The existing season-horizon gate does not prevent this:
`economy.can_mature_in_time("MELON", day, 29)` permits planting through
day 17, because it only asks whether the crop can *mature*, never whether
it can be *sold for anything*.

## 4. The Change

One new keyword parameter on `generate_tasks`:

```python
    melon_last_plant_day: int | None = None,
```

When set, melon is excluded from the candidate crops for any planting
decision on a day after it.

**The change is a single call site.** Melon can only ever be chosen at
`src/kaggriculture_lib/tasking.py:330`, the sole `_best_feasible_crop`
call — the feed-wheat, strawberry and cash-crop-wheat branches name their
crop literally, and line 348 merely *counts* a melon already chosen. So
filtering that one call's candidate tuple is both necessary and
sufficient:

```python
                    melon_ok = (
                        melon_last_plant_day is None
                        or day <= melon_last_plant_day
                    )
                    ranking_crops = (
                        candidate_crops
                        if melon_ok
                        else tuple(c for c in candidate_crops if c != "MELON")
                    )
                    best = _best_feasible_crop(day, last_day, market_prices, ranking_crops)
```

Nothing else changes. `None` disables the rule entirely, leaving task
output byte-identical for every agent that does not pass it.

### 4.1 Backwards compatibility is mandatory

`melon_last_plant_day` defaults to `None`. Every frozen agent
(`task_teacher_v2` … `v20`) must produce byte-identical task output, and a
regression test asserts it.

This is not routine caution. On 2026-08-28, correcting
`economy.FARM_HAND_COST_MULT` silently changed frozen `task_teacher_v8`'s
evaluated behaviour, because that agent derived a constant from the shared
library. Agent versions are immutable as *files* but read shared code, so a
behavioural change here rewrites their recorded evaluations retroactively.

### 4.2 Cutoff value: day 10

`MELON_LAST_PLANT_DAY = 10` in `agents/task_teacher_v21/main.py`.

Cycle 1 is planted by day 2, so a day-10 cutoff leaves the profitable
cycle completely untouched while eliminating the cycle-2 plantings that
begin around day 13.

Day 10 also lines up with an existing rule rather than fighting it: the
strawberry allocation in `generate_tasks` already activates at
`day >= 10`. Tiles freed by the melon cutoff therefore become eligible for
strawberry in the same turn the cutoff starts biting — the reallocation
path already exists and needs no new code.

This is the design's one tunable knob.

### 4.3 Freed capacity is reallocated by existing logic, deliberately

Roughly 25 tiles per season stop growing melon. They are **not** assigned
to a hardcoded replacement. They fall through to the existing allocation
order — strawberry (already gated at `day >= 10`, capped at 12), then
`_best_feasible_crop`'s ROI ranking.

This is the explicit lesson of `task_teacher_v19`, which lost **0 of 20
paired games** by forcing freed tiles into wheat on the strength of a
revenue comparison that ignored the tile's opportunity cost. Here the
change is subtractive: stop doing something measured to be worthless, and
let the ranking that already exists decide what replaces it.

The measured headroom is real — opponents earn $6,999/ep from carrot
against our $661, and carrot absorbs ~230 units at >=50% of base — but
this design makes **no** commitment to capturing it, and asserts nothing
about which crop fills the gap. That is for the evaluation to reveal.

## 5. Out of Scope

- **Melon sale metering.** The day-13 dump of 100 units in a single turn
  is real, but the data shows melon does not recover between sales
  (~1 unit/day drain), so spreading that sale gains little. Production
  volume is the binding constraint, not sale scheduling.
- **Shed overflow.** ~26 melons/ep are discarded when the shed caps at 100.
  This design reduces it as a side effect; it does not address the cap.
- **Terminal liquidation.** Still correct for whatever remains — $4 beats
  $0 for stock already grown. The fix is to not grow it.
- **Wheat ($0/ep vs opponents' $6,766) and wool ($2,329 vs $6,419).**
  Separate variables, and wheat specifically failed as `task_teacher_v19`.

## 6. Acceptance Tests

New, alongside every existing test, which must keep passing unmodified:

- Melon is planted on a day at or before the cutoff.
- Melon is **not** planted on a day after the cutoff; a non-melon crop is
  chosen for that tile instead.
- **`melon_last_plant_day=None` (the default) produces task output
  identical to current behaviour** — the frozen-agent guard from §4.1.
- The cutoff does not affect any non-melon crop's eligibility.
- The cutoff does not interfere with harvesting, watering, or clearing
  existing melon tiles planted before it.
- Full-episode regression: a real run in which v21 plants materially fewer
  melons than v20 and sells a materially higher melon $/unit.

## 7. Evaluation

The protocol every version goes through, under the corrected `1.32.4`
simulator and ladder-match configuration:

1. 100-episode acceptance gate (both seats; validity; determinism;
   action-kind coverage; inference latency). **Record melon plantings,
   melon units sold, melon $/unit, and total reward per episode** — the
   first three are how we tell whether the cutoff did what it claims.
2. Paired Hoeffding-CI screen: 20 pairs vs. **`task_teacher_v20`**, the
   current champion.
3. If the screen is positive or straddles 0.50, escalate to the 50-pair
   promotion gate; promotion requires the CI wholly above 0.50.
4. Regression screens vs. `task_teacher_v17` and `starter`.

**Stop rule, stated explicitly because this project has a documented
history of promotion claims outrunning evidence:** if the 20-pair CI falls
wholly below 0.50, stop and record the screen as the outcome. Do not
escalate, do not re-run on a different seed, do not average across seeds.

**Anticipated failure mode.** If v21 loses, the most likely cause is that
the freed tiles are worth less than the melon they replaced — the mirror
of `task_teacher_v19`. The acceptance telemetry distinguishes the cases: if
melon $/unit rises sharply but total reward falls, the cutoff worked and
the reallocation did not, and the next step is the cutoff day rather than
abandoning the idea.
