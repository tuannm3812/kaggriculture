# Task Teacher v20 — Fertilizer Collection — Design

Written 2026-08-28. Status: **approved**. Inherits every project and teacher
constraint from the authoritative competition and teacher specs, and
everything in `task_teacher_v17` unchanged except the one variable below.

## 1. Goal

Collect and sell the fertilizer our animals already produce. Today
`COLLECT_FERTILIZER` is not implemented at all — it is not even a member of
`tasking.TaskKind` — so this revenue line is exactly zero.

## 2. Measured Motivation

From `docs/10_ladder_revenue_diagnosis.md` (all 78 real ladder episodes of
submission `55622884`):

| Commodity | our units | our total | opp units | opp total |
| --- | ---: | ---: | ---: | ---: |
| **FERTILIZER** | **0** | **$0** | 5,120 | **$421,761** |

That is ~$5,407/game we never contest, against a measured median loss gap
of ~$16,500.

Part of why this was never built: `kaggle-environments==1.29.3` — which this
project was pinned to until 2026-08-28 — **excludes `FERTILIZER` from
`SELL` entirely**. Selling it was impossible in our own simulator, so the
opportunity was invisible locally. The ladder's real `1.32.4` permits it
(`op == "SELL" and item in PRODUCTS`). See
`docs/2_environment_notes.md`'s 2026-08-28 correction.

## 3. Verified Mechanics

Read directly from the pinned `1.32.4`
`kaggle_environments/envs/kaggriculture/kaggriculture.py`, not assumed:

- **Production** (line 809): `tile["fertilizer_available"] = True` is set in
  the end-of-day refresh for every animal tile, placed *after* the
  `consecutive_unfed >= 2` escape check. So every animal that survives the
  day produces one, **regardless of whether it was fed or cared for**.
- **It does not accumulate.** `fertilizer_available` is a boolean, not a
  counter. Uncollected fertilizer is lost at the next refresh: the ceiling
  is strictly **one per animal per day, use it or lose it**.
- **Collection** (lines 492-499): `COLLECT_FERTILIZER` requires the acting
  unit to be standing on a tile with an `animal` key and
  `fertilizer_available` true. It clears the flag and adds 1 `FERTILIZER`
  to that unit's own inventory (`_inv_add(inv, ...)`), not to the shed.
- **Delivery to the shed** happens through the existing end-of-day
  inventory drop — no new plumbing.
- **Selling already works.** `agents/task_teacher_v17/main.py:206` already
  reads `for prod in ["MILK", "WOOL", "EGG", "FERTILIZER"]`, and line 189
  includes it in terminal liquidation. The sell path has been wired the
  whole time; it has simply never had anything to sell.

## 4. The Change

Three small pieces. **No change to any sell logic.**

### 4.1 `TaskKind` gains a member

In `src/kaggriculture_lib/tasking.py`:

```python
class TaskKind(str, Enum):
    ...
    PICKUP = "PICKUP"
    COLLECT_FERTILIZER = "COLLECT_FERTILIZER"
```

### 4.2 `generate_tasks` emits the task

Inside the **existing** animal-tile branch — `elif isinstance(tile, dict)
and "animal" in tile:` — alongside the `FEED` and `CARE` blocks, mirroring
the `CARE` block's shape exactly.

That branch guard is already sufficient to mean "occupied by an animal", so
no further tile check is needed. Verified: `BUILD_COOP`/`BUILD_PASTURE`
create `{"kind": "COOP"}` with **no** `"animal"` key (line 440), only
`PLACE` adds one (line 219), and an escaped animal's tile is reset to
`{"kind": <structure>}` (line 807), again without it. So an empty or
vacated structure never enters this branch and can never generate a
collection task.

```python
                if tile.get("fertilizer_available") and collect_fertilizer:
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

### 4.3 The agent dispatches the action

In the new `agents/task_teacher_v20/main.py`, alongside the existing
`TaskKind.CARE` branch:

```python
        if task_id.kind == TaskKind.COLLECT_FERTILIZER:
            return ["COLLECT_FERTILIZER"]
```

## 5. Priority: `OPTIONAL`, and why that is the whole design

The task is emitted at `PriorityTier.OPTIONAL` (tier 4, the lowest —
below `ECONOMIC`). No task in this codebase currently uses that tier; this
is the first, and it is what the tier was defined for.

**This is the central design decision, and it is a direct response to
`task_teacher_v19`'s failure.** v19 lost 0/20 pairs because it made wheat
displace melon on tiles that were still in their high-value range — a tile
opportunity cost the design never priced. Fertilizer costs **no tiles at
all**; the animals already exist and are already fed. Its only cost is
**labour**: one unit-action per animal per day.

Placing it at `OPTIONAL` means it is assigned only to units with nothing
better to do. It can never pre-empt watering (crops die), harvesting
(yield decays), feeding (animals escape), or planting. If labour is the
binding constraint, the task simply does not fire and costs nothing.

**Honest risk:** the same property that makes this safe could make it
inert. If v17's units are labour-saturated, `OPTIONAL` may almost never be
reached and v20 collects nothing — a null result rather than a loss. This
is cheap to detect and is an explicit acceptance-gate metric (§7).

### 5.2 Correction (2026-08-28): `OPTIONAL` was unreachable, for a
different reason than §5 anticipated

The first implementation collected **7 fertilizer in a whole 720-step
episode**, against this design's ~200 estimate. §5 predicted the inert case
and blamed labour saturation. **That diagnosis was wrong.** Measured on the
same episode:

| | |
| --- | ---: |
| Peak animals | 8 |
| Tile-turns with fertilizer available | 2,379 |
| `COLLECT_FERTILIZER` actions taken | 7 |
| Idle (`PASS`) unit-actions | 342 of 4,473 (7%) |

Units were **not** saturated — they idled through 342 actions while 2,379
tile-turns of fertilizer went uncollected.

The real cause is in the assignment algorithm. `rank_tasks` sorts by
`priority_tier` **first**, and `joint_assign` then truncates each unit's
candidate set to its top `MAX_CANDIDATES_PER_UNIT = 8`. On a busy farm
there are far more than eight higher-tier tasks (WATER, HARVEST, PLANT,
FEED), so `OPTIONAL` tasks never enter any unit's shortlist. The
truncation happens *before* "does this unit have anything better to do?"
is ever evaluated.

**`PriorityTier.OPTIONAL` is therefore dead on any busy farm** — a finding
that reaches beyond this version, since it was the tier's first use.

**Fix: reserve a candidate slot.** Candidate-set construction reserves one
slot for the nearest `OPTIONAL`-tier task when one exists, so the tier
becomes reachable without changing its priority. The no-displacement
guarantee is preserved: an `OPTIONAL` task is still ranked below every
other tier and is only *taken* when the unit's higher-tier candidates are
infeasible or claimed. What changes is that it is now *visible* to the
scorer at all.

This is gated behind a new `reserve_optional_slot: bool = False` parameter
so every frozen agent (`task_teacher_v2` … `v19`) keeps byte-identical
behaviour, for the same reason §5.1 gives.

### 5.1 Backwards compatibility is mandatory

`collect_fertilizer` is a **new keyword parameter on `generate_tasks`
defaulting to `False`**, so every existing agent (`task_teacher_v2` …
`v19`) produces byte-identical task output.

This is not optional caution. On 2026-08-28, correcting
`economy.FARM_HAND_COST_MULT` silently changed frozen `task_teacher_v8`'s
evaluated behaviour, because that agent derived a constant from the shared
library. Agent versions are immutable as *files* but read shared code, so a
behavioural change here rewrites their recorded evaluations retroactively.
A regression test asserts the default is inert.

Note this differs from `task_teacher_v19`'s `wheat_target_tiles`, which
used `0` as its disabling value; a boolean is the natural equivalent here.

## 6. Expected Value and Scope

Roughly 10 animals × ~20 productive days ≈ 200 units. Fertilizer's curve
(`base 100`, `T 200`, `above_func linear`, `above_target 0.40`) absorbs
~253 units before the marginal price falls below half of base, so that
volume clears around $75-85/unit — up to ~$15k/season at the optimistic
end. The measured opponent benchmark is more conservative at ~$5,407/game,
likely reflecting fewer animals or less consistent collection. Both figures
are material against the ~$16,500 median loss gap.

**Explicitly out of scope:**

- Using fertilizer on crops (`FERTILIZE`) rather than selling it. Fertilizer
  doubles a one-time crop's per-day watering bonus, which may well beat
  selling it — but that is a different variable with its own tile and
  labour interactions, and it needs its own version.
- Buying fertilizer from the market (`BUY_PRODUCT FERTILIZER`).
- Melon over-production and sale metering
  (`docs/10_ladder_revenue_diagnosis.md` §2), still unaddressed.
- The feed-starvation defect that rejected `task_teacher_v18`. Note this
  design is neutral to it: fertilizer is produced whether or not an animal
  was fed, so collection neither helps nor worsens starvation.

## 7. Acceptance Tests

New, alongside every existing test, which must keep passing unmodified:

- `COLLECT_FERTILIZER` task generated for an animal tile with
  `fertilizer_available` true, when `collect_fertilizer=True`.
- No such task when `fertilizer_available` is false.
- No such task for a plant tile or an empty animal structure (no `animal`).
- The task is emitted at `PriorityTier.OPTIONAL`, asserted explicitly —
  this is the design's load-bearing property, not an incidental detail.
- **`collect_fertilizer=False` (the default) produces task output identical
  to current behaviour** — the frozen-agent regression guard from §5.1.
- The agent returns `["COLLECT_FERTILIZER"]` when assigned that task.
- Full-episode regression: a real run in which v20 records fertilizer sale
  revenue greater than zero. **If this assertion fails, the `OPTIONAL`-tier
  risk in §5 has materialised** — report it as a finding rather than
  lowering the tier to force a pass.

## 8. Evaluation

The protocol every version goes through, under the corrected `1.32.4`
simulator and ladder-match configuration:

1. 100-episode acceptance gate (both seats; validity; determinism;
   action-kind coverage; inference latency). **Record fertilizer collected
   and sold per episode** — if it is ~0, stop and report; the change is
   inert and no screen is warranted.
2. Paired Hoeffding-CI screen: 20 pairs vs. **`task_teacher_v17`** — the
   strongest CI-verified version.
3. If the screen is positive or straddles 0.50, escalate to the 50-pair
   promotion gate; promotion requires the CI wholly above 0.50.
4. Regression screens vs. `task_teacher_v16` and `starter`.

**Stop rule, stated explicitly because this project has a documented
history of promotion claims outrunning evidence:** if the 20-pair CI falls
wholly below 0.50, stop and record the screen as the outcome. Do not
escalate, do not re-run on a different seed, do not average across seeds.

**Evaluation caveat.** Results are not comparable to any version-log entry
predating 2026-08-28, which were measured under the miscalibrated `1.29.3`
constants.
