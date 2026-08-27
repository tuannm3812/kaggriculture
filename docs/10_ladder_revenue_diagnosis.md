# 10. Ladder Revenue Diagnosis and Strategy — 2026-08-28

Evidence base: all 78 real ladder episodes for submission `55622884`
(the 3-quadrant HTDC build, `publicScore` 470.6), fetched with
`scripts/analyze_ladder_submission.py --submission-id 55622884 --label
v17_live` and analysed with `scripts/diagnose_ladder_gap.py`. Replays are
cached under `replays/ladder/v17_live/`.

## 0. Standing: we are in the bottom quartile

| | |
| --- | ---: |
| Public leaderboard rank | **4992 of 6650** |
| Our score | 470.6 |
| Field median | 764.8 |
| Percentile | 24.9 |
| Teams above 600 | 4138 |
| Top score (`Crop Dusta`) | 3114.0 |

The ~47% ladder win rate is not evidence of parity — Kaggle's matchmaking
pairs agents of similar rating, so a rating that has settled at 470 with a
47% win rate means the rating is *correct*, not that the field is even.
Every local promotion result this project has recorded (including the
2026-08-28 retroactive confirmations that v16 and v17 both beat v5 with
Hoeffding CI `[0.760, 1.000]`) is real but measured **against our own
lineage**. v5 was itself a weak baseline. Beating it decisively is
compatible with sitting in the bottom quartile of the real field, and
that is exactly what happened.

## 1. The headline: opponents earn 1.68x our revenue

Realized sale revenue across the same 78 episodes, ours vs. every
opponent we faced. `$/u` is the quoted market price at the selling turn,
so it is an approximation of realized price, but the volumes and the
zeroes are exact.

| Commodity | our units | our $/u | our total | opp units | opp $/u | opp total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **WHEAT** | **0** | — | **$0** | 26,436 | 41.3 | **$1,090,522** |
| MELON | 15,589 | **64.2** | $1,001,066 | 6,433 | **102.0** | $656,264 |
| MILK | 1,711 | 264.2 | $452,005 | 3,672 | 216.2 | $794,013 |
| STRAWBERRY | 2,701 | **260.6** | $703,852 | 2,044 | 232.7 | $475,697 |
| **FERTILIZER** | **0** | — | **$0** | 5,120 | 82.4 | **$421,761** |
| WOOL | 771 | 227.9 | $175,741 | 1,706 | 206.4 | $352,071 |
| CARROT | 838 | 53.2 | $44,585 | 2,658 | 40.4 | $107,436 |
| EGG | 324 | 59.5 | $19,291 | 1,375 | 51.7 | $71,041 |
| TOMATO | 0 | — | $0 | 625 | 87.2 | $54,506 |
| **Total** | | | **~$2.40M** | | | **~$4.02M** |

Two entries are zero for us, and one of them is the opponents' single
largest revenue line in the entire game.

Note what we do *well*: our realized unit prices on the premium goods —
strawberry ($260.6 vs 232.7), milk ($264.2 vs 216.2), wool ($227.9 vs
206.4) — are **better** than the field's. The multi-tile task/route
engine is not the problem. Portfolio and sale timing are.

## 2. Defect A — melon is dumped into a market we crash ourselves

Melon's price curve is the most glut-fragile in the game
(`above_func=sq`, `above_target=3.60`; the competition's own table gives
`P(I0+T) = $1` at `T=300`). It tolerates roughly 60–70 units before
collapsing.

Measured across all 78 episodes:

- our median melon sale day: **26**; opponents': **16**
- our largest single-turn melon order: **100 units**
- we sell **2.4x** the melon volume for **1.5x** the revenue, at **63%**
  of the opponents' unit price

Episode `98996520` is the clean illustration:

| | day 10 | day 12 | day 13 | day 14 | day 26 |
| --- | --- | --- | --- | --- | --- |
| **them** | 59u @ **$245** | 84u @ $81 | | | |
| **us** | | | 100u @ **$4** | 24u @ $4 | 46u @ $4 |

The market price ran 250 → 269 (day 8) → 228 (day 12) → **7** (day 16)
and never recovered. The opponent sold 59 units into the peak; we dumped
100 units in a single turn and realized $4 each. We sold 170 melons that
game for about $680 total. They sold 143 for about $21,000.

Root cause, confirmed in code — every sell in
`agents/task_teacher_v17/main.py` is an unmetered dump of the entire
shed:

```python
for crop in ["CARROT", "MELON", "STRAWBERRY"]:
    available = shed.get(crop, 0)
    if available > 0:
        market_orders.append(["SELL", crop, available])   # no cap, no price check
```

made worse by terminal liquidation (`day == last_day and hour >= 20`),
which sells everything remaining into the crater we already made. This is
also why `task_teacher_v14`'s "base-price ROI crop fix" backfired at
scale: ranking melon at its $250 base makes the agent plant melon
everywhere, and the agent then has no mechanism to notice the realized
price is $4.

## 3. Defect B — wheat is never sold, and barely planted

`WHEAT` is the opponents' largest revenue line ($1.09M across 78 games,
~$14k/game) and we earn **$0** from it. Two independent causes:

```python
# agents/task_teacher_v17/main.py — sell gate
if (owned_cows == 0 and owned_sheep == 0 and owned_geese == 0):
    available = shed.get("WHEAT", 0)
    ...
```

We always own animals, so this branch never fires. And in
`src/kaggriculture_lib/tasking.py`, wheat planting is capped at four
tiles and gated on feed need:

```python
if wheat_needed_for_feed and n_wheat < 4 and "WHEAT" in candidate_crops ...
```

so wheat is treated purely as animal feed, never as a cash crop.

This is backwards relative to the price curves. Wheat is the most
glut-*resistant* good in the game (`above_func=log`,
`above_target=0.20`; `P(I0+T)=$20`), town shops consume it constantly, and
its price *rose* from $25 to $45 over the season in our own replays. It
matures in 2 days (fastest crop), and it is dual-use — surplus feeds the
animals, which removes the `BUY_PRODUCT WHEAT` spend at the same time.

## 4. Defect C — fertilizer is never collected

Opponents earned $421,761 selling fertilizer. We earned $0.

`COLLECT_FERTILIZER` does not appear anywhere in the codebase — it is not
even a member of `tasking.TaskKind`. Per the competition rules every
surviving animal makes one fertilizer available at the end of each day
**whether or not it was fed or cared for**, so this is close to free
revenue on animals we already own and already pay to feed. (Uncollected
fertilizer does not accumulate, so it must be collected daily to be
worth anything.)

## 5. Defect D — animal starvation, live

The bug that got `task_teacher_v18` rejected is already present in the
shipped build: **16 animal escapes across 11 of 46 analysed games**
(opponents: 80 escapes, so the field is not immune either). Real, worth
fixing — but the revenue table puts it fourth. It costs us animals we
paid for; it is not what is keeping us at rank 4992.

## 6. Where the gap opens

In every one of the 24 analysed losses, the opponent opened a >$5,000
lead, at **median day 11** (range 8–22). Our cash sits at
$996 → $958 → $134 → $106 through day 20 in the losses, while the
opponent banks $18k by day 15. We convert to cash only at terminal
liquidation, into a market we have already crashed.

Median final money: **wins** $31,914 vs $13,072; **losses** $20,457 vs
$37,028. The loss gap is about **$16,500**.

## 7. Strategy — ordered by measured value, not by novelty

Rough per-game upside, taken as the opponents' measured revenue on each
line divided by 78 games. These are upper bounds: the market is
interactive (selling more wheat softens wheat, melon timing is a race
against the opponent's dump), so treat them as magnitude, not forecast.

| # | Change | Measured basis | Rough upside/game |
| --- | --- | --- | ---: |
| **P1** | **Meter every sale against the live price curve** — cap batch size, stop selling a good once its quoted price falls below a floor, spread across days | our melon $64.2/u vs their $102.0/u on 2.4x volume | **~+$7,600** |
| **P2** | **Wheat as a cash crop** — remove the animals-owned sell gate; lift the 4-tile feed-only planting cap | their $1.09M vs our $0 | **~+$7,000** (half capture) |
| **P3** | **Collect and sell fertilizer** — add `COLLECT_FERTILIZER` task kind + daily collection | their $421k vs our $0 | **~+$2,700** (half capture) |
| **P4** | **Fix feed starvation** (the v18 rejection bug) | 16 escapes / 11 of 46 games | animal preservation |

P1–P3 total roughly $17,300/game against a measured loss gap of
~$16,500. That is the right order of magnitude to close it, which is the
main reason to believe this is the real diagnosis rather than a
collection of small optimisations.

**This supersedes the 2026-08-28 recommendation** in
`docs/6_next_steps.md` to lead with the v18 feed-starvation fix. That
recommendation was made before this revenue audit existed and was
reasoning from the only evidence then available (v18's acceptance
report). The starvation bug is real and still worth fixing, but it is
fourth by measured value, not first.

Relationship to `docs/8_ladder_replay_analysis.md` (2026-08-06/07): that
analysis concluded land + animals was the gap, and it was right for the
agent of that era (`task_teacher_v2`, which had neither). v16/v17 acted
on it and the standing did not improve much — because acquiring capacity
without fixing the *conversion of output into banked cash* moves
production, not score. The win condition is money in the bank.

## 8. Caveats

- `$/u` is the quoted price at the selling turn, not a settled fill
  price; the simulator fills one unit at a time and moves the price
  mid-order. Volumes, zeroes, batch sizes and sale days are exact; unit
  prices are close approximations.
- 78 episodes against a matchmaking-selected opponent pool, all from one
  submission. The pool shifts as our rating moves.
- Upside figures are per-line upper bounds under the counterfactual that
  we capture what opponents captured. Market interaction means realised
  gains will be smaller.
- `scripts/diagnose_ladder_gap.py`'s escape counter infers starvation
  from a net drop in placed animals across a day boundary; it does not
  distinguish an escape from a deliberate animal sale. Opponents sell
  animals (221 COW, 334 SHEEP units), so their 80 "escapes" are an
  overcount. Ours is reliable — we never sell animals.
