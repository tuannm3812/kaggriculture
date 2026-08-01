# 2. Environment Notes

## Local Installation

`kaggriculture` is not yet in a published `kaggle-environments` PyPI release
(checked 2026-08-01: `pip install kaggle-environments` resolves to `1.18.0`,
which only registers `halite`, `hungry_geese`, `kore_fleets`, `lux_ai_2021`,
`lux_ai_s2`, `mab`, `open_spiel`, `rps` — no `kaggriculture`). It exists on
the GitHub `master` branch. Also requires Python >= 3.11 (this machine's
system Python is 3.9), so:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt   # installs from GitHub source
```

Installed and verified 2026-08-01: `kaggle-environments==1.32.2` (from
GitHub `master`, commit as of that pip install). The env's own source ships
alongside the package at:

```
.venv/lib/python3.11/site-packages/kaggle_environments/envs/kaggriculture/kaggriculture.py
```

This is ground truth for every formula in `src/kaggriculture_lib/economy.py`
— more reliable than the README prose alone, which documents intent but can
drift from what's actually implemented. Per `docs/0_coding_standards.md` §2,
every reimplemented formula must cite the source line range it was derived
from and be unit-tested against calling the real function directly.

## Verified: Market Price Formula

`kaggriculture.py:177-191`'s `market_price(item, inventory, params=None)`
matches the documented formula exactly:

```text
price(inv) = base + sign * amp * f(|inv - I0|)
  sign = +1 if inv < I0 (scarcity), -1 if inv > I0 (glut)
  amp  = target * base / f(T)
  f in {linear, sq, sqrt, log}  (log uses ln(1+x))
floored at PRICE_FLOOR=1, rounded to nearest int
```

Confirmed 2026-08-01 by calling `market_price()` directly at `I0-T`, `I0+T`,
`I0+2T` for all 9 resources and comparing against the README's sample price
table — all 9 matched exactly (e.g. Wheat: `$45`/`$20`/`$19`; Strawberry:
`$204`/`$1`/`$1`). `MARKET_PARAMS` (base/I0/T/shape-function/target per
resource) at `kaggriculture.py:40-50` is the single source of truth for
these constants — `economy.py` mirrors this table verbatim rather than
retyping values from the README.

## Verified: Yield Formulas

- **One-time crops** (`kaggriculture.py:373-386`, the `WATER` handler): the
  watering bonus window starts at `(max_yield_day + 1) // 2` (integer
  division — equivalent to `ceil(max_yield_day / 2)`) through `max_yield_day`
  inclusive, adding `+1` per watering in that window (`+2` if
  `fertilized_until_day >= day`).
- **Ongoing crops** (`kaggriculture.py:738-771`, `_daily_refresh_plants`):
  production ticks when `(next_day - planted_day - first_yield_day) %
  interval == 0` and the running production count hasn't exceeded
  `max_yield`; yield is `+1`, or `+2` if fertilized **and** watered that same
  day (fertilizer bonus only applies on watered days — basic needs first,
  matching the README).
- **Animals** (`kaggriculture.py:774-802`, `_daily_refresh_animals`):
  production ticks on the same interval logic; `pending_care_bonus` (banked
  by `CARE` on days both fed and cared for) is added in full on a fed
  production day and reset to 0 whether or not it was consumed — matches the
  README's "care bonus banked, paid on next scheduled production" rule.
- **Fertilizer window**: `kaggriculture.py:417-424` sets
  `fertilized_until_day = max(current, day + 2)` — active for the day
  applied plus the following two days (3 days inclusive), matching the
  README.

## Quirk: The Built-in `"random"` Agent Is Not Seed-Reproducible

`kaggriculture.py:995-1019`'s `random_agent` creates `rng =
random.Random()` fresh and unseeded on every single call — the
environment's own `seed` config (which does deterministically control
weed spawning and episode generation) has no effect on it. Confirmed by
hand 2026-08-01: two `run_pair("starter", "random", ...)` calls at the same
seed produced different money margins (400.0 vs. 455.0). Consequence:
**any local-tournament or evaluation result measured against the `"random"`
built-in is not reproducible run-to-run**, even with `configuration["seed"]`
set. `tests/test_tournament.py` uses `"starter"`/`"pass"` (both
deterministic) for its seed-determinism test instead. Relevant to the
design doc §9's paired-seed evaluation protocol if `"random"` is ever used
as a league member for anything beyond a rough sanity check.

## Baseline Throughput (2026-08-01, this machine, env-only, CPU)

240-step episodes among the three built-in agents (`pass`, `random`,
`starter`), single-threaded, no policy inference overhead:

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
- **`kaggriculture_import_ok: true`, no explicit install needed** —
  confirms the hypothesis in §9: Kaggle's kernel image already has a
  `kaggle-environments` build with `kaggriculture` registered, distinct
  from (and older than, `1.29.3` vs. the `1.32.2` installed locally from
  GitHub `master`) the version this project develops against locally. The
  offline wheel-dataset fallback plan was not needed.
- Paired-seat match (seed `20260801`, 720 steps, packaged `roi_teacher_v3`
  vs. `starter`): both seat assignments finished `DONE`/`DONE` with finite
  rewards (`5319.0`/`2523.0` and `2523.0`/`5319.0` — consistent, agent won
  both seats).
- **Packaged-agent SHA-256 matches exactly** between the local build and
  the remote kernel: `dd47d40735d9370c2aa45f8e564ee5e6c4f0d462aeda75267fff165871031f42`
  — independently re-verified locally (`shasum -a 256`) against the
  downloaded kernel output file, not just the JSON result's self-reported
  hash.
- Result artifact: `/kaggle/working/smoke_result.json`, downloaded via
  `kaggle kernels output` to `/tmp/kaggriculture_smoke_output/`. Log
  inspected (`kaggle kernels output ... `'s `.log` file): clean run,
  "SMOKE TEST PASSED" printed; the only stderr output is Kaggle's own
  harmless `nbconvert`/`mistune` `SyntaxWarning`s during its own
  notebook-to-HTML rendering step, unrelated to this project's code.

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
- The remote kernel's pre-installed `kaggle-environments==1.29.3` is older
  than this project's local `1.32.2` (from GitHub `master`) — not yet
  confirmed whether this version gap matters (e.g. differing `kaggriculture`
  game-logic versions between local dev and Kaggle's actual ladder
  evaluator). Worth diffing if a future local-vs-ladder score discrepancy
  ever looks larger than expected.
