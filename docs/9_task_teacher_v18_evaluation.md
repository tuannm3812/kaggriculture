# Task Teacher v18 Evaluation

Evaluation date: 2026-08-20

Current evaluated repository commit:
`a6f6444ebcd9abab5b34b62e26a749fc14cad1a5`

Decision: **`reject`**

## Decision rules

The approved v18 protocol classifies a candidate as:

- `reject` when acceptance fails, the 50-pair win rate is below `0.55`,
  mean margin is non-positive, or the compact regression is catastrophic;
- `experimental_submission` when acceptance and regression gates are clean,
  the 50-pair point estimate is at least `0.55` with positive mean margin,
  but the Hoeffding 95% interval crosses `0.50`; or
- `local_champion` only when the Hoeffding 95% lower bound exceeds `0.50`
  and every regression gate passes.

The point estimate and Hoeffding interval are separate from the safety gates.
A strong result against `starter` cannot override failed acceptance. No Kaggle
submission was made.

## Patched acceptance at `a6f6444`: failed

Evidence: [`task_teacher_v18_acceptance.json`](../replays/analysis/task_teacher_v18_acceptance.json)

The refresh evaluated `agents/task_teacher_v18/main.py` against built-in
`starter` using ladder-match configuration, 50 paired seeds
`110000`-`110049`, 720 steps, and both seats: 100 games total. The JSON embeds
the exact candidate path and evaluated commit.

The structural gates passed:

- all 200 terminal agent statuses were `DONE` and all rewards were finite;
- a second full 100-game replay exactly matched the stored rewards, actions,
  diagnostics, and aggregate;
- every action used exactly the `farmer`, `hands`, and `market` schema;
- returned actions contained at most 10 market orders, with zero
  planned/emitted/dropped cap-accounting mismatches;
- every turn contained at most one `BUY_LAND`, with zero order/authorization
  mismatches and zero invalid authorized post-land cash values; and
- all recorded cash values were finite and minimum cash was `$1,668`, so no
  bankruptcy signature was present.

Acceptance nevertheless failed the starvation gate. Direct simulator-state
inspection found 47 placed animals disappearing in 24/100 games: 24 Cows and
23 Sheep. The pinned simulator removes an animal at daily refresh after its
second consecutive unfed day, so the largest observable pre-removal
`consecutive_unfed` value is 1. These disappearances are animal escapes, not
normal aging or liquidation, and establish a repeated feed-starvation
signature. Example escape refreshes occurred at steps 624, 648, and 696.

The evaluator's feed-inventory forecast was positive on 26,587/71,900
candidate turns (36.98%). That forecast count is context; the direct escape
events are the acceptance-failing evidence.

The acceptance-opponent point estimate was win rate `1.000`, mean money margin
`+$43,962.03`, with Hoeffding 95% interval
`[0.7598267085, 1.0000000000]`. This is not promotion evidence and does not
override the failed safety gate.

Other patched acceptance telemetry:

| Metric | Measured value |
| --- | ---: |
| Threat-state turns | COMPACT 71,900; BUILDING 0; COMPOUNDING 0 |
| Threat transitions | 0 |
| Land orders / authorizations | 100 / 100 |
| Land activation | step 313 (day 13, hour 1) in all 100 games |
| Mean productive utilization | 0.55954 |
| Maximum hands | 8 in each seat |
| Total hire spend | $29,800 |
| Pass-action rate | 0.18250 |
| Crop sale value | Melon $4,431,282; Strawberry $672,308; Carrot $12,278 |
| Animal-product sale value | Milk $802,857; Wool $271,042; Egg $57,302 |

The opponent remained COMPACT throughout. This acceptance run exercised the
preserved first-land path, not threat-conditioned third or fourth land.

## Historical acceptance at `78e8e0a`

The replaced acceptance artifact previously described commit
`78e8e0aed39ae375c978a27c1642781da45ca33d`, before the final-review
correctness patches. Its result remains historical context, not current
evidence:

| Metric | Historical `78e8e0a` | Patched `a6f6444` |
| --- | ---: | ---: |
| Animal escapes | 15 (12 Cow, 3 Sheep) | 47 (24 Cow, 23 Sheep) |
| Games with escape | 13/100 | 24/100 |
| Feed-shortage forecast turns | 30,554 | 26,587 |
| Win-rate point estimate vs `starter` | 1.000 | 1.000 |
| Mean margin vs `starter` | +$37,867.07 | +$43,962.03 |
| Mean productive utilization | 0.51535 | 0.55954 |
| Total hire spend | $33,479 | $29,800 |

The patched run improved the margin point estimate, utilization, pass rate,
and feed-shortage forecast count, but actual escapes increased by 32 and
affected 11 more games. Those economic point estimates therefore do not
establish acceptance safety.

## Historical ablation and stopped later gates

[`task_teacher_v18_ablation.json`](../replays/analysis/task_teacher_v18_ablation.json)
remains the historical `78e8e0a` classifier-only run: 20 paired seeds
`110100`-`110119`, exact mirrored rewards, point estimate `0.500`, margin
`$0.00`, and Hoeffding interval `[0.1202526828, 0.8797473172]`. It was not
rerun for patched commit `a6f6444` and must not be represented as current
evaluation evidence.

The patched acceptance failure independently satisfies the `reject` rule.
The stop rule therefore prevented a patched ablation, v16 screen, 50-pair
promotion evaluation, comparator screens against v17/v10/v2/v12, and Kaggle
submission. No unrun result is inferred.

The measured decision for patched commit `a6f6444` is **`reject`**.
`task_teacher_v18` is neither an experimental-submission candidate nor a local
champion.
