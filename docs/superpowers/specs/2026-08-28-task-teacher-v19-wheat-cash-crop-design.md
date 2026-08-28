# Task Teacher v19 — Wheat as a Cash Crop — Design

Written 2026-08-28. Status: **approved**. Inherits every project and teacher
constraint from the authoritative competition and teacher specs, and
everything in `task_teacher_v17` unchanged except the one variable below.

## 1. Goal

Make wheat participate in the economy. Today it is feed-only: capped at four
tiles, planted solely when animals need feeding, and **never sold**. This is
the single largest measured revenue gap on the ladder.

## 2. Measured Motivation

From `docs/10_ladder_revenue_diagnosis.md` (all 78 real ladder episodes of
submission `55622884`):

| Commodity | our units | our total | opp units | opp total |
| --- | ---: | ---: | ---: | ---: |
| **WHEAT** | **0** | **$0** | 26,436 | **$1,090,522** |

$1.09M across 78 games (~$14k/game) is the opponents' single largest revenue
line, and we take none of it.

Wheat is uniquely suited to volume, which the corrected `1.32.4` market
constants make explicit (see `docs/2_environment_notes.md`'s 2026-08-28
correction). Absorption before the marginal price falls below half of base:

| Good | Base | Absorption |
| --- | ---: | ---: |
| **WHEAT** | $25 | **effectively unbounded** |
| MELON | $250 | ~113 units |
| STRAWBERRY | $120 | ~32 units |

Five town shops consume wheat (Bakery, Pizza Shop, Brunch Spot, Ice Cream
Shop, Farmers Market), draining it faster than players supply it — its price
*rose* $25 → $45 over the season in our own replays, and opponents realized
**$41.3/unit**, above base. No shop demands melon at all; its only drain is
the town centre at roughly 1 unit/day, so melon's ~113 units is a one-shot
whole-game budget shared with the opponent, not a rate that refills.

Wheat revenue is therefore *unclaimed*, not contested — unlike melon, where
further gains are a zero-sum race for a fixed pool.

## 3. Root Cause (confirmed in code, not inferred)

**Sell gate never fires** — `agents/task_teacher_v17/main.py`:

```python
# Sell wheat only if no animals need it for feed
if (owned_cows == 0 and owned_sheep == 0 and owned_geese == 0):
    available = shed.get("WHEAT", 0)
    if available > 0:
        market_orders.append(["SELL", "WHEAT", available])
```

v17 always owns animals, so this branch is dead code in every real episode.

**Planting is feed-only and capped at four tiles** —
`src/kaggriculture_lib/tasking.py`:

```python
if wheat_needed_for_feed and n_wheat < 4 and "WHEAT" in candidate_crops and economy.can_mature_in_time("WHEAT", day, last_day):
```

Both must change together: planting without selling only clogs the
100-item shed, and selling without planting has nothing to sell.

## 4. Change 1 — Sell Surplus Wheat

In the new `agents/task_teacher_v19/main.py`, replace the dead gate with a
feed-reserved surplus rule:

```python
feed_reserve = max(2, total_owned_animals * SELL_RESERVE_DAYS)
sellable = shed.get("WHEAT", 0) - feed_reserve
if sellable > 0:
    market_orders.append(["SELL", "WHEAT", sellable])
```

`SELL_RESERVE_DAYS = 5`, deliberately **larger** than the existing
buy-side target of two days (`target_wheat = max(2, total_owned_animals *
2)`).

### 4.1 Correction (2026-08-28): the two thresholds must not be equal

This section originally specified `FEED_DAYS_BUFFER = 2`, matching the
buy-side target exactly, and claimed that once the farm grew its own wheat
"that condition stops holding and the agent stops buying feed". **That was
wrong**, and the Task 5 full-episode smoke test caught it.

`BUY_PRODUCT WHEAT` is gated on `if hour == 1:` — it tops up to the
threshold once per day. The sell rule runs *every* turn, trimming surplus
down to the same threshold. With both numbers equal there is no buffer:
the agent sells its home-grown wheat down to the bare minimum, the animals
eat overnight, and the top-up fires again next morning. Measured over one
paired episode: v19 sold 153 wheat but **bought 71**, against v17's 47 —
fixing the revenue bug made buy-back churn *worse*, costing roughly
$2,000-3,000/episode to sell cheap and re-buy at market.

The fix is hysteresis. Sell only above five days of feed; keep buying at
two. With 13-20 wheat tiles harvesting on a ~5-day cycle, inventory should
sit well above the buy trigger and the top-up should essentially stop
firing — which is what the original claim assumed but did not achieve.

Animals eat one wheat per day and escape after two consecutive unfed days,
so five days is comfortably above the survival floor. This deliberately
does **not** attempt to fix the separate feed-starvation defect
(`docs/9_task_teacher_v18_evaluation.md`); it only avoids *making it worse*
by selling feed out from under the animals.

Terminal liquidation (`day == last_day and hour >= 20`) is unchanged and
still sells everything including the reserve — unsold stock scores nothing.

**Side effect, partial:** the existing `BUY_PRODUCT WHEAT` top-up is gated
on `total_wheat < animals * 2`, so growing our own wheat *reduces* feed
purchases — measured across four paired episodes after the §4.1 fix, v19
bought 33/40/47/40 units against v17's 59/44/51/48.

It does **not** eliminate them, and an earlier draft of this section
wrongly claimed it would ("the agent stops buying feed"). Buying continues
whenever a day's consumption outpaces that day's harvest, which happens
routinely. This is a step toward the circular feed economy
`task_teacher_v15` aimed at, not an achievement of it.

## 5. Change 2 — Plant Wheat to a Tile Target

`generate_tasks`'s empty-tile branch already expresses crop allocation as
ordered overrides on the ROI ranking, with strawberry as the precedent. Add
wheat as one more rule in the same shape:

```python
crop = None
if wheat_needed_for_feed and n_wheat < 4 and "WHEAT" in candidate_crops and economy.can_mature_in_time("WHEAT", day, last_day):
    crop = "WHEAT"                     # existing: feed
    n_wheat += 1
else:
    best = _best_feasible_crop(day, last_day, market_prices, candidate_crops)
    if "STRAWBERRY" in candidate_crops and day >= 10 and n_strawberries < 12 and economy.can_ongoing_crop_reach_any_tick("STRAWBERRY", day, last_day):
        crop = "STRAWBERRY"            # existing
        n_strawberries += 1
    elif (                             # NEW: wheat as a cash crop
        n_wheat < wheat_target_tiles
        and "WHEAT" in candidate_crops
        and economy.can_mature_in_time("WHEAT", day, last_day)
    ):
        crop = "WHEAT"
        n_wheat += 1
    else:
        crop = best                    # existing: ROI pick, usually MELON
        ...
```

The rule sits after strawberry and before the ROI pick, so melon receives
whatever remains. It cannot displace feed wheat, and it respects the same
`can_mature_in_time` horizon gate as every other planting decision.

`n_wheat` is the **single existing counter of all wheat tiles on the
board**, incremented by both the feed rule and the new cash-crop rule.
`wheat_target_tiles` is therefore a *total* wheat-tile target, not an
allowance on top of the four feed tiles: at `wheat_target_tiles=20` the
board converges to 20 wheat tiles in total, of which up to four may have
been placed by the feed rule. A target below 4 is meaningless rather than
harmful — the feed rule runs first and is unaffected.

### 5.1 Backwards compatibility is mandatory, not optional

`wheat_target_tiles` is a **new keyword parameter on `generate_tasks`
defaulting to `0`**, which disables the rule entirely. Every existing agent
therefore produces byte-identical task output.

This is deliberate. On 2026-08-28, correcting `economy.FARM_HAND_COST_MULT`
silently changed frozen `task_teacher_v8`'s evaluated behaviour, because
that agent derived a constant from the shared library. Agent versions are
immutable as *files* but read shared library code, so a shared-library
change rewrites their behaviour retroactively and invalidates their recorded
evaluations. A default of `0` is what keeps this change from repeating that.
A regression test asserts it directly.

### 5.2 Initial target: 20 tiles

`WHEAT_TARGET_TILES = 20` in v19.

A wheat tile yields ~0.8 units/tile/day (4 units unfertilized per ~5-day
plant→harvest cycle). Twenty tiles ≈ 16 units/day ≈ $640/day at the observed
$41/unit ≈ **$16k/season**, which brackets the opponents' measured
$14k/game. Twenty tiles also fits the labour budget: watering is one action
per tile per day against roughly 8 hands × 24 turns.

This is the design's one tunable knob. If the evaluation shows wheat
displacing too much melon, lower it before changing anything else.

## 6. Explicitly Out of Scope

- **Melon over-production.** We grow ~200 melons into a ~113-unit
  whole-game market. Real, and larger than it looks, but a separate
  variable.
- **Sale metering / the 100-unit dump.** Analysed in
  `docs/10_ladder_revenue_diagnosis.md` §2 and initially planned as this
  version's change; deferred after the replay trace showed melon's ceiling
  is production volume rather than sale scheduling (melon does not recover
  between sales, so spreading them gains little).
- **Shed overflow.** 26 melons are discarded at the day-13 cap. A symptom
  of melon over-production; fix it there.
- **Fertilizer collection** (`COLLECT_FERTILIZER` is not even a `TaskKind`;
  opponents earn $421k, we earn $0). Its own version.
- **The feed-starvation defect** that rejected v18. §4's reserve avoids
  aggravating it; it does not fix it.

## 7. Acceptance Tests

New, alongside every existing test, which must keep passing unmodified:

- Wheat `PLANT` task generated for an empty tile while `n_wheat` is below
  `wheat_target_tiles`.
- No wheat `PLANT` task once the target is reached.
- **`wheat_target_tiles=0` (the default) produces task output identical to
  the current behaviour** — the frozen-agent regression guard from §5.1.
- The cash-crop rule never pre-empts the feed rule.
- Late-season: no wheat planted once it cannot mature in time.
- Agent sells surplus wheat *while owning animals* — the case the v17 gate
  made unreachable.
- Agent never sells into the feed reserve.
- Terminal liquidation still sells the full shed including the reserve.
- Full-episode regression: a real run where v19 records wheat sale revenue
  greater than zero and `BUY_PRODUCT WHEAT` volume below v17's.

## 8. Evaluation

The protocol every version goes through, under the corrected `1.32.4`
simulator and ladder-match configuration:

1. 100-episode acceptance gate (both seats; validity; determinism;
   action-kind coverage; inference latency; wheat sale volume > 0).
2. Paired Hoeffding-CI screen: 20 pairs vs. **`task_teacher_v17`** — the
   strongest CI-verified version, not `task_teacher_v5`.
3. If the screen is positive or straddles 0.50, escalate to the 50-pair
   promotion gate; promotion requires the CI wholly above 0.50.
4. Regression screens vs. `task_teacher_v16` and `starter`.

**Evaluation caveat.** Every prior promotion result in this project was
measured under the miscalibrated `1.29.3` constants and is not evidence
about ladder performance for premium-good-heavy strategies. v19's
evaluation is the first run under a simulator validated against real ladder
prices (299/299 exact matches). Results are therefore not directly
comparable to historical numbers in `docs/4_agent_version_log.md`.
