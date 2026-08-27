# 2. Environment Notes

## Ladder-match configuration (2026-08-13)

Live Kaggriculture ladder episode `configuration` blocks (measured from
`task_teacher_v5` submission `55425318` replays) do **not** match bare
`make()` defaults on pinned `kaggle-environments==1.29.3`:

| Key | 1.29.3 default | Live ladder |
| --- | ---: | ---: |
| `startingMoney` | 2000 | **3000** |
| `farmHandCostMult` | 10 | **1** |
| `townShopSellInterval` | 2 | **4** |
| `townCenterSellInterval` | 6 | **24** |

Use `kaggriculture_lib.env_config.tournament_configuration` (wired into
`scripts/run_tournament.py` by default) for any local eval that should
predict ladder land timing. See `docs/8_ladder_replay_analysis.md`
(2026-08-13 correction).

## Local Installation

`kaggle-environments==1.29.3` from PyPI, pinned in `requirements.txt` — no
GitHub source install needed. Requires Python >= 3.11:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**Correction (2026-08-01):** earlier notes here said `kaggriculture` "isn't
yet in a published PyPI release" and installed from GitHub `master`
(`1.32.2`) instead. That was wrong — the actual problem was running `pip
install kaggle-environments` under this machine's *system* Python 3.9,
which is incompatible with `kaggle-environments`' own `requires-python =
">=3.11"`, so pip silently fell back to the newest Python-3.9-compatible
release (`1.18.0`, which predates `kaggriculture`). Under Python 3.11,
`pip install kaggle-environments==1.29.3` installs cleanly straight from
PyPI. See the version-gap section below for why `1.29.3` specifically,
not `1.32.2` or "latest".

> **Superseded 2026-08-28 — the pin is now `1.32.4`.** The reasoning below
> (that `1.29.3` is what the ladder runs) was correct about Kaggle's
> *notebook-kernel* image but wrong about the runtime that grades ladder
> episodes. See
> [§ Correction (2026-08-28)](#correction-2026-08-28-the-ladder-runs-1324-not-1293)
> at the end of this section. Everything between here and that correction is
> retained as the historical record of the 2026-08-01 decision, not as
> current guidance.

The env's own source ships alongside the package at:

```
.venv/lib/python3.11/site-packages/kaggle_environments/envs/kaggriculture/kaggriculture.py
```

This is ground truth for every formula in `src/kaggriculture_lib/economy.py`
— more reliable than the README prose alone, which documents intent but can
drift from what's actually implemented. Per `docs/0_coding_standards.md` §2,
every reimplemented formula must cite the source line range it was derived
from and be unit-tested against calling the real function directly.

## Version-Gap Finding: `1.29.3` vs. `1.32.2` Have Real Mechanics Differences

Found 2026-08-01 via Codex's code review (design doc §9): the Kaggle
platform smoke test's kernel had `kaggle-environments==1.29.3`
pre-installed — different from the `1.32.2` (GitHub `master`) this project
had been developing against. Diffed both versions' `kaggriculture.py`
directly (not just READMEs). **These are real balance/mechanics
differences, not a trivial version bump:**

| Constant | `1.32.2` | `1.29.3` (pinned, matches Kaggle's kernel) |
| --- | ---: | ---: |
| `COW` cost | 400 | **600** |
| `FARM_HAND_COST_MULT` | 1 | **10** |
| `startingMoney` (schema default) | 3000 | **2000** |
| `townShopSellInterval` (schema default) | 4 | **2** |
| `townCenterSellInterval` (schema default) | 12 | **6** |
| Strawberry/Melon/Milk/Wool `above_target` | 1.60 / 3.60 / 1.60 / 3.20 | **0.40 / 0.90 / 0.40 / 0.80** |

Also: `DROP` doesn't exist as an action in `1.29.3`'s `_apply_unit_action`
(silently a no-op there — but the automatic end-of-day shed-drop,
`_drop_inventories_to_shed`/`_end_of_day`, is present and identical in both
versions, so agents relying on `DROP` aren't broken, just up to a day
slower to reach the shed); `BUY_PRODUCT` is restricted to `("WHEAT",
"FERTILIZER")` in `1.32.2` but allows any `PRODUCTS` member in `1.29.3`;
`SELL` excludes `FERTILIZER` in `1.29.3` but not `1.32.2`; episode-seed
resolution differs (a `resolve_episode_seed()` utility in `1.32.2` vs. an
inline info/configuration/random fallback chain in `1.29.3`).

**What did NOT change:** every crop/animal's `base` price and
`below_func`/`below_target` are identical between versions — so this
project's static "$/day @ base price" ROI ranking (Melon >> Carrot >
Wheat, `docs/3_agent_strategy.md`) is unaffected, and `roi_teacher_v1→v3`'s
*relative* tournament rankings hold under either version (re-verified
after the fix below). What was wrong: Melon's oversupply risk was modeled
~4x too punishing, hand-hiring was modeled 10x too cheap, and
`economy.py`/its tests were validated against the wrong constants.

**Resolution (2026-08-01):** re-pinned `requirements.txt` to
`kaggle-environments==1.29.3` (confirmed running on Kaggle's own kernel
infrastructure — the best available evidence for what the ladder uses,
per the design doc §9), rebuilt `.venv` against it, corrected
`economy.py`'s `MARKET_PARAMS`/`ANIMALS`/`FARM_HAND_COST_MULT` and every
docstring's source line-range citations (which had also shifted — `1.29.3`
lacks the `DROP` block, changing line numbers throughout), corrected
`tests/test_economy.py`'s expected sample-price table, re-ran the full
suite (129 passing) and the `v1→v3` local tournaments (rankings unchanged:
`v3 > v2 > v1 > starter > random > pass`), and re-packaged all three
agents. Full before/after tournament numbers in
`docs/4_agent_version_log.md`.

**Still open:** whether Kaggle's kernel image version is necessarily what
the ladder's actual agent-evaluation backend runs (vs. pinned separately)
— treated as ladder-representative until contradicted, per the design
doc §9.

### Correction (2026-08-28): the ladder runs `1.32.4`, not `1.29.3`

**That "still open" question above resolved the wrong way, and it cost us
four weeks of miscalibrated evaluation.** The kernel image is *not* what
grades ladder episodes. `requirements.txt` is now pinned to `1.32.4`.

Two independent confirmations:

1. A submission's own error traceback reported the runtime as **`1.32.4`**
   (2026-08-06, the `replay_compat` packaging incident — the version string
   was right there in the crash and nobody connected it back to these
   constants).
2. Across **299 glut-side price observations** taken from real ladder
   replays, `1.32.4`'s `MARKET_PARAMS` reproduce the observed price
   **299/299**; `1.29.3`'s match **3/299**. Melon was exact at eight
   consecutive sampled inventories.

**Constants corrected in `economy.py`:**

| Constant | was (`1.29.3`) | now (`1.32.4`) |
| --- | ---: | ---: |
| `COW` cost | 600 | **400** |
| `FARM_HAND_COST_MULT` | 10 | **1** |
| `STRAWBERRY` `above_target` | 0.40 | **1.60** |
| `MELON` `above_target` | 0.90 | **3.60** |
| `MILK` `above_target` | 0.40 | **1.60** |
| `WOOL` `above_target` | 0.80 | **3.20** |

**Mechanics differences** (not just constants): `1.29.3` *forbids*
`SELL FERTILIZER` and blocks movement onto `LOCKED` tiles; `1.32.4` permits
both. `1.32.4` restricts `BUY_PRODUCT` to `WHEAT`/`FERTILIZER` (`1.29.3`
allowed any product) and implements `DROP` (a no-op in `1.29.3`).
`startingMoney` schema default is 3000 (was 150 in `1.29.3`'s schema).

**Why this matters more than a version bump.** All four *premium* goods —
exactly the ones our strategy leans on — collapse under glut **~4x harder**
on the real ladder than our simulator modelled. At the inventory where the
ladder charged us $4/melon, the old local model said $188. Consequences:

- Every local promotion result for a premium-good-heavy strategy (v14's
  melon-heavy base-price ROI fix, v15's strawberry engine, the v16/v17
  Hoeffding CI `[0.760, 1.000]` confirmations) was measured in a market that
  under-punishes the exact failure mode those strategies suffer on the
  ladder. Those results are not *wrong*, but they are **not evidence about
  ladder performance** and should not be cited as such.
- The fertilizer revenue gap (opponents $421k, us $0 — see
  `docs/10_ladder_revenue_diagnosis.md`) had a mechanical cause: selling
  fertilizer was *impossible* in our simulator.
- True market absorption, at ≥50% of base price: MELON ~113 units,
  STRAWBERRY ~32, MILK ~39, WOOL ~42, CARROT ~230, while WHEAT and EGG are
  effectively unbounded (town demand drains them faster than players
  supply). We were producing ~200 melons/game; the last ~80 are worth
  roughly $3 each.

**Test fallout and how it was handled.** 26 tests failed. Each was
classified as a stale expectation or a real regression rather than
re-baselined wholesale:

- `test_economy.py`'s sample price table encoded the `1.29.3` premium-good
  values; the corrected values `(204,1,1)`/`(300,1,1)`/`(256,1,1)`/
  `(240,1,1)` now match the competition's *own published table* exactly.
- Several agent and `should_hire` tests silently inherited
  `economy.FARM_HAND_COST_MULT` through configs that omitted
  `farmHandCostMult`. Those configs now pin the multiplier explicitly, so
  the tests state which hiring regime they exercise instead of drifting with
  a library default. Note they largely exercise mult=10, which the ladder
  does **not** use.
- `agents/task_teacher_v8/main.py` read `HIRE_DECISION_MULT =
  economy.FARM_HAND_COST_MULT` with a comment stating the intent was 10.
  Changing the library constant silently altered a frozen agent's evaluated
  behaviour, so the literal is now pinned. **This is a general hazard: agent
  versions are immutable as files, but they read shared-library constants,
  so a library change retroactively alters their behaviour.** Any future
  constant change must audit `agents/*/main.py` for derived values.

## Verified: Market Price Formula

`kaggriculture.py:175-191`'s `market_price(item, inventory, params=None)`
(line numbers per the pinned `1.29.3`) matches the documented formula
exactly:

```text
price(inv) = base + sign * amp * f(|inv - I0|)
  sign = +1 if inv < I0 (scarcity), -1 if inv > I0 (glut)
  amp  = target * base / f(T)
  f in {linear, sq, sqrt, log}  (log uses ln(1+x))
floored at PRICE_FLOOR=1, rounded to nearest int
```

Confirmed 2026-08-01 by calling `market_price()` directly at `I0-T`, `I0+T`,
`I0+2T` for all 9 resources and comparing against `1.29.3`'s own README
sample price table — all 9 matched exactly (e.g. Wheat: `$45`/`$20`/`$19`;
Strawberry: `$204`/`$72`/`$24`). `MARKET_PARAMS` (base/I0/T/shape-function/
target per resource) at `kaggriculture.py:38-50` is the single source of
truth for these constants — `economy.py` mirrors this table verbatim
rather than retyping values from the README.

## Verified: Yield Formulas

- **One-time crops** (`kaggriculture.py:368-382`, the `WATER` handler): the
  watering bonus window starts at `(max_yield_day + 1) // 2` (integer
  division — equivalent to `ceil(max_yield_day / 2)`) through `max_yield_day`
  inclusive, adding `+1` per watering in that window (`+2` if
  `fertilized_until_day >= day`).
- **Ongoing crops** (`kaggriculture.py:731-766`, `_daily_refresh_plants`):
  production ticks when `(next_day - planted_day - first_yield_day) %
  interval == 0` and the running production count hasn't exceeded
  `max_yield`; yield is `+1`, or `+2` if fertilized **and** watered that same
  day (fertilizer bonus only applies on watered days — basic needs first,
  matching the README).
- **Animals** (`kaggriculture.py:767-797`, `_daily_refresh_animals`):
  production ticks on the same interval logic; `pending_care_bonus` (banked
  by `CARE` on days both fed and cared for) is added in full on a fed
  production day and reset to 0 whether or not it was consumed — matches the
  README's "care bonus banked, paid on next scheduled production" rule.
- **Fertilizer window**: `kaggriculture.py:412-419` (the `FERTILIZE`
  handler) sets `fertilized_until_day = max(current, day + 2)` — active
  for the day applied plus the following two days (3 days inclusive),
  matching the README.

(Line numbers above are for the pinned `1.29.3`; the formulas themselves —
confirmed by direct diff — are identical to `1.32.2`, only their line
positions shifted.)

## Quirk: The Built-in `"random"` Agent Is Not Seed-Reproducible

`kaggriculture.py:988-1014`'s `random_agent` creates `rng =
random.Random()` fresh and unseeded on every single call — the
environment's own `seed` config (which does deterministically control
weed spawning and episode generation) has no effect on it. Confirmed by
hand 2026-08-01: two `run_pair("starter", "random", ...)` calls at the same
seed produced different money margins. Consequence: **any local-tournament
or evaluation result measured against the `"random"` built-in is not
reproducible run-to-run**, even with `configuration["seed"]` set.
`tests/test_tournament.py` uses `"starter"`/`"pass"` (both deterministic)
for its seed-determinism test instead. Relevant to the design doc §9's
paired-seed evaluation protocol if `"random"` is ever used as a league
member for anything beyond a rough sanity check.

## Baseline Throughput (2026-08-01, this machine, env-only, CPU)

240-step episodes among the three built-in agents (`pass`, `random`,
`starter`), single-threaded, no policy inference overhead — measured
before the version re-pin; order-of-magnitude only, not re-measured after
(the pin doesn't change env-only step cost meaningfully):

| Matchup | Rewards | Steps/sec |
| --- | --- | --- |
| pass vs. random | 3000.0 / 1650.0 | 1103.5 |
| random vs. starter | 1530.0 / 3053.0 | 1013.5 |
| starter vs. starter | 3051.0 / 3051.0 | 1138.1 |

~1000–1100 env-only steps/sec on this machine — a full 720-step episode
costs well under a second with trivial agents. This is a floor, not the
number that matters for RL rollout throughput once a real policy's
inference cost is added; see the design doc §9's Week-1 throughput-benchmark
plan (env-only, policy-inference at multiple parallel-env counts, full
training steps/sec, all still to be measured).

## Kaggle Platform Smoke Test — Passed (2026-08-01)

Per the design doc §9's execution-status audit: verified `kaggriculture`
actually runs on Kaggle's own infrastructure, not just this repo's local
`.venv`. State reached: `kernel_pushed` (10:0x UTC) → `kernel_complete`
(confirmed via `kaggle kernels status`, ~65s runtime).

- Kernel: `tuannm3812/kaggriculture-platform-smoke-test`, version 1,
  private. Source: `notebooks/00_platform_smoke_test.ipynb`.
- Remote environment: Python `3.12.13`, `Linux-6.12.90+-x86_64`,
  `kaggle-environments==1.29.3`, `torch==2.10.0+cpu`, no GPU (none
  requested — `enable_gpu: false`, this check didn't need one).
- **`kaggriculture_import_ok: true`, no explicit install needed** — this
  is what surfaced the `1.29.3` vs. `1.32.2` version gap above.
- Paired-seat match (seed `20260801`, 720 steps, packaged `roi_teacher_v3`
  vs. `starter`): both seat assignments finished `DONE`/`DONE` with finite
  rewards.
- Packaged-agent SHA-256 matched exactly between the local build and the
  remote kernel at the time — **now historical**: that hash was for the
  pre-version-fix build (`economy.py` has since been corrected, so
  `build/roi_teacher_v3/main.py`'s hash has changed). The platform-
  compatibility conclusion itself is unaffected by that; re-running the
  smoke kernel wasn't judged necessary just to refresh a hash for an
  already-confirmed compatibility check.
- Result artifact: `/kaggle/working/smoke_result.json`, downloaded via
  `kaggle kernels output` to `/tmp/kaggriculture_smoke_output/`. Log
  inspected: clean run, "SMOKE TEST PASSED" printed; the only stderr
  output was Kaggle's own harmless `nbconvert`/`mistune` `SyntaxWarning`s
  from its post-run notebook-to-HTML rendering, unrelated to this
  project's code.

**Conclusion:** platform compatibility confirmed. Per the audit's scope
decision, this validates execution only — it does not make the single-tile
`roi_teacher_v3` an adequate behavioral-cloning teacher (see
`docs/6_next_steps.md`), and it is not a competition submission.

## Open Items

- Confirm actual Kaggle ladder episode configuration (fixed defaults, or do
  scored games vary `boardSize`/`episodeSteps`/etc.?) — relevant to whether
  the design doc's conditional C5 robustness curriculum stage is worth its
  GPU budget. Not yet confirmed as of 2026-08-01.
- `kaggriculture_beginner` also exists alongside `kaggriculture` in the
  installed package — not yet investigated; may be a simplified variant
  worth using for early curriculum stages (C0/C1) instead of hand-rolling a
  reduced-rules training environment. Follow up before curriculum work
  starts.
- Whether Kaggle's kernel image version (`1.29.3`) is necessarily what the
  ladder's own agent-evaluation backend runs, vs. pinned separately — no
  way to confirm this without an actual submission; treated as
  ladder-representative until contradicted.
