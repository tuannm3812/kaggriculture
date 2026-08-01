# 2. Environment Notes

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
