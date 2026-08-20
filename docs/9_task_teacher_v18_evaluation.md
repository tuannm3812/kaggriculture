# Task Teacher v18 Evaluation

Evaluation date: 2026-08-20

Evaluated repository commit: `78e8e0aed39ae375c978a27c1642781da45ca33d`

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

The point estimate and Hoeffding evidence are separate claims. A high point
estimate does not override a failed acceptance gate. No Kaggle submission was
made.

## Acceptance: failed

Evidence: [`task_teacher_v18_acceptance.json`](../replays/analysis/task_teacher_v18_acceptance.json)

The acceptance run used candidate
`agents/task_teacher_v18/main.py`, built-in opponent `starter`, ladder-match
configuration, 50 paired seeds `110000`-`110049`, 720 steps, and both seats:
100 games total.

Every game ended `DONE`; all 200 terminal agent statuses were `DONE`; every
terminal reward was finite. A second full replay of all 100 games was exactly
identical to the stored rewards, actions, diagnostics, and aggregates. Every
candidate action had exactly the competition keys `farmer`, `hands`, and
`market`. There was at most one `BUY_LAND` order per turn, and all 100 land
orders matched an affirmative land authorization. Minimum observed cash was
`$1,668`, so the run showed no bankruptcy signature.

Acceptance nevertheless failed the starvation gate. Direct replay inspection
found 13 placed-animal decrease events in 13/100 games, losing 15 animals in
total: 12 Cows and 3 Sheep. The pinned simulator removes a placed animal only
after two consecutive unfed days, so these decreases are animal escapes rather
than liquidation or normal aging. They occurred at daily-refresh steps 432,
480, 576, 600, or 672. The evaluator also recorded a positive feed-inventory
shortage forecast on 30,554/71,900 candidate turns (42.50%). The direct escape
events, rather than that forecast count alone, establish the repeated
feed-starvation signature.

The acceptance point estimate against `starter` was win rate `1.000`, mean
money margin `+$37,867.07`, with Hoeffding 95% interval
`[0.7598267085, 1.0000000000]`. These are acceptance-opponent measurements,
not promotion evidence, and cannot override the failed safety gate.

Other acceptance telemetry:

| Metric | Measured value |
| --- | ---: |
| Threat-state turns | COMPACT 71,900; BUILDING 0; COMPOUNDING 0 |
| Threat transitions | 0 |
| Land orders / authorizations | 100 / 100 |
| Land activation | step 313 (day 13, hour 1) in all 100 games |
| Mean productive utilization | 0.51535 |
| Maximum hands | 8 in each seat |
| Total hire spend | $33,479 |
| Pass-action rate | 0.20868 |
| Crop sale value | Melon $3,748,262; Strawberry $404,604; Carrot $48,056 |
| Animal-product sale value | Milk $932,195; Wool $361,304; Egg $75,238 |

The opponent remained COMPACT throughout, so the acceptance run exercised
v18's preserved first-land path but did not activate threat-conditioned third
or fourth land.

## Classifier-only ablation: identity retained

Evidence: [`task_teacher_v18_ablation.json`](../replays/analysis/task_teacher_v18_ablation.json)

The ablation used candidate `agents/task_teacher_v18/main.py`, opponent
`agents/task_teacher_v16/main.py`, `enableThreatExpansion=False`, ladder-match
configuration, 20 paired seeds `110100`-`110119`, 720 steps, and both seats:
40 games total. Mirrored paired rewards were exactly identical. Its point
estimate was win rate `0.500`, mean margin `$0.00`, with Hoeffding 95% interval
`[0.1202526828, 0.8797473172]`. This wide interval describes sampling
uncertainty; exact reward identity is the relevant ablation result.

Task 4's full simulator action-stream comparison also passed: v18 with threat
expansion disabled matched v16 exactly for seeds `18000`-`18009` in both
seats (`tests/test_task_teacher_v18.py::test_classifier_only_ablation_is_action_identical_to_v16_for_ten_seed_pairs`).

Ablation telemetry was COMPACT for all 28,760 candidate turns, with zero threat
transitions, 40 first-land orders at step 313, minimum cash `$954`, maximum 8
hands, mean productive utilization `0.69355`, total hire spend `$12,904`, and
pass-action rate `0.12366`.

## Promotion and comparator disposition

The acceptance failure independently satisfies the `reject` rule. Evaluation
therefore stopped before the 20-pair v16 screen, 50-pair promotion evaluation,
and comparator screens against v17, v10, v2, and v12. No comparator result is
reported or inferred, and no promotion JSON was created.

The measured decision is **`reject`**. `task_teacher_v18` is neither an
experimental-submission candidate nor a local champion, and it was not
submitted to Kaggle.
