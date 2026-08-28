# 0. Coding Standards

Project-specific layer on top of the master
`~/Documents/GitHub/coding-standards/coding_standards.md`. That doc's
notebook-first default does not apply here — see the design doc
(`docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md`,
§3) for why this is an agent-competition repo, not a tabular one.

## 1. Repository Scope

Code, not notebooks, is the executable artifact Kaggle runs. Structure:

- `src/kaggriculture_lib/` — shared, tested library (economy math, encoders,
  policies). See §2 for why this exists from day one, against the master
  doc's default of "only once reuse is proven."
- `agents/<version>/main.py` — one immutable folder per tried agent version,
  each a self-contained `agent(obs)` submission candidate.
- `scripts/` — local tournament runner (`run_tournament.py`), submission
  packaging (`package_agent.py`), Kaggle kernel push (`push_kaggle_kernel.sh`).
- `tests/` — unit tests for `src/kaggriculture_lib`, agent decision logic,
  the tournament harness, and packaging.
- `notebooks/` — narrow exceptions for platform verification and rendering
  tracked analysis tables, not agent development or metric computation. See
  §2.
- `docs/` — numbered, in the same spirit as the master doc's §2, adapted for
  this genre: `0_coding_standards.md` → `1_competition_instructions.md` →
  `2_environment_notes.md` → `3_agent_strategy.md` → `4_agent_version_log.md`
  → `5_replay_strategy.md` → `6_next_steps.md` → `7_elite_replay_eda.md`.
- `replays/` — gitignored raw episode JSON; `replays/analysis/` derived
  summaries are small enough to keep in git when they document a real
  finding (mirrors master doc §8's "lightweight artifacts only" rule).
- No `data/` — there is no train/test data for this competition.

## 2. Exceptions to the Master Standard

**`src/kaggriculture_lib` from day one.** The master standard says only add
`src/<package>` once shared logic is genuinely reused across multiple
notebooks/agents. This project adds it at v1 instead, because the
price-curve and yield formulas (9 resources × asymmetric shape functions,
one-time vs. ongoing yield math, `CARE` bonus banking) are complex enough
that every agent version — heuristic teacher, BC-cloned policy,
PPO-trained policy — must share exactly one correct implementation.
Reimplementing this per agent version risks silent divergence between what
an agent *thinks* is true and what the environment actually does.

**`notebooks/` platform-verification exception, added 2026-08-01.** This
repo is otherwise code-first (§1) — but Kaggle's execution environment
can't be verified without running actual code on Kaggle's own
infrastructure, and this project's local dev dependency (`kaggle-
environments`) is version-pinned rather than "latest" (§6,
`docs/2_environment_notes.md`), so whether Kaggle's kernel image runs a
compatible version was a genuine open question — one that turned out to
matter: the smoke test surfaced a real version gap (`1.29.3` on Kaggle's
kernel vs. `1.32.2` this project had been developing against, with actual
balance differences, not just a version-number bump). `notebooks/
00_platform_smoke_test.ipynb` + `notebooks/kernels/platform_smoke_test/`
exist solely for this kind of platform check — not to become the
executable source of truth for agent development.

**Analysis-only replay EDA notebook, added 2026-08-02.**
`notebooks/02_elite_replay_eda.ipynb` is a second narrow notebook exception:
it may import pandas/matplotlib/seaborn, read the tracked
`replays/analysis/elite_*.csv` tables, reshape them for plots, and render
figures. It must not retrieve artifacts, normalize or split trajectories,
evaluate compatibility, compute replay metrics, repair actions, or implement
policy logic. Tested library code and `scripts/build_elite_eda.py` remain the
source of truth; an empty plot is preferable to manufacturing a measurement
from notebook-authored prose.

See the design doc §6 for the original reasoning behind both exceptions.

## 3. Code Style

Same as the master doc §3 (PEP 8, type hints on reusable functions,
Google-style docstrings, snake_case/UPPER_SNAKE_CASE, grouped imports,
comments explain why not what). Additionally for this project:

- Every function in `economy.py` that reimplements a game formula must cite
  the exact source location it was derived from (line range in the locally
  installed `kaggriculture.py`, plus the installed package version) in its
  docstring, and have a unit test comparing its output against calling the
  real environment package's equivalent function directly — not just against
  the README's prose description, which can drift from the actual
  implementation.

## 4. Agent Versioning

- One folder per tried version: `agents/<family>_v<n>/main.py`. Folders are
  immutable once tried (matches `orbit-wars`/`pokemon-tcg-ai-battle`
  precedent) — never edit a version in place; create the next one.
- Every version gets an entry in `docs/4_agent_version_log.md`: config diff
  from the previous version, local-tournament result, ladder result once
  available, and outcome/lesson.
- One-variable-at-a-time changes wherever practical, so a score movement is
  interpretable (per `maze-crawler`'s lesson, recorded repeatedly in its own
  `docs/05_agent_version_log.md`).

## 5. Submission Discipline

- Confirm Kaggriculture's actual submission-slot/ladder-tracking rules early
  (open item in the design doc §8) before assuming any specific "don't push
  a known-good version out of tracked slots" constraint.
- Never submit a speculative variant without a local-tournament comparison
  against the current champion first.
- Every submission is logged immediately in `docs/4_agent_version_log.md`
  (or its RL-track equivalent once that exists) — notebook/version,
  local-tournament score, ladder score once available, decision.

## 6. Local Environment

Pinned to `kaggle-environments==1.32.4` in `requirements.txt` — installs
cleanly from PyPI, no GitHub source needed. Re-pinned 2026-08-28: `1.29.3`
matches Kaggle's *notebook-kernel* image but not the runtime that actually
grades ladder episodes, which real replays confirm is `1.32.4` — its
market constants reproduce 299 observed ladder prices 299/299, against
3/299 for `1.29.3`. See `docs/2_environment_notes.md`'s 2026-08-28
correction before ever bumping this pin again. Requires Python >= 3.11 —
use the project's `.venv` (created via `python3.11 -m venv .venv`) rather
than system Python.

## 7. Git Hygiene

Same as master doc §8, plus: never commit the vendored `kaggriculture.py`
env source itself (it's a dependency, reproducible via `requirements.txt`'s
pinned install source) — reference its line numbers in docstrings/docs
instead of copying it into this repo.
