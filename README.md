# Kaggriculture

Kaggle Featured competition ($50,000 prize pool) for a two-player farm-
economy simulation bot: https://www.kaggle.com/competitions/kaggriculture

## Status

Week 1 in progress (2026-08-01). Deadline: **2026-09-30 23:59 UTC**. Local
environment verified, economy math tested against the real simulator, and
a series of ROI-heuristic teacher agents beat all three built-in agents in
local tournament play. Current local champion: **`roi_teacher_v3`** (see
`docs/4_agent_version_log.md` for the full v1→v3 progression). Packaging
(`scripts/package_agent.py`) is done and verified; not yet submitted to the
ladder — see `docs/6_next_steps.md` for the current recommendation.

Full design (why this repo is structured this way, strategy approach, and
the converged RL-pipeline discussion with Codex) is in
[`docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md`](docs/superpowers/specs/2026-08-01-kaggriculture-competition-plan-design.md).

## Repository Structure

- `docs/`: numbered competition notes, environment verification, agent
  strategy, version log, next steps (see Documentation Map below).
- `src/kaggriculture_lib/`: shared, tested library — game economy math
  (price curve, yield formulas) mirrored from and validated against the
  real environment. Single source of truth for every agent version.
- `agents/<version>/main.py`: one immutable folder per tried agent version.
- `scripts/`: local tournament runner (`run_tournament.py`), submission
  packaging (`package_agent.py`).
- `tests/`: unit tests for `src/kaggriculture_lib`, agent decision logic,
  the tournament harness, and the packaging step.
- `replays/`: gitignored raw episode JSON; `replays/analysis/` keeps small
  derived summaries.

## Local Setup

Requires Python >= 3.11 (`kaggriculture` isn't yet in a published
`kaggle-environments` PyPI release as of 2026-08-01 — installed from GitHub
source; see `docs/2_environment_notes.md`):

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run the local tournament harness:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
    agents/roi_teacher_v3/main.py pass random starter \
    --episodes 10 --episode-steps 720
```

Package an agent into a standalone submission artifact:

```bash
.venv/bin/python scripts/package_agent.py agents/roi_teacher_v3
```

Run tests:

```bash
.venv/bin/python -m pytest tests/ -q
```

## Documentation Map

- [`docs/0_coding_standards.md`](docs/0_coding_standards.md): project-specific
  standards layered on the shared master coding-standards doc.
- [`docs/1_competition_instructions.md`](docs/1_competition_instructions.md):
  official facts — task, format, deadline, submission mechanics.
- [`docs/2_environment_notes.md`](docs/2_environment_notes.md): local
  environment setup, formulas verified against the real simulator,
  baseline throughput.
- [`docs/3_agent_strategy.md`](docs/3_agent_strategy.md): static ROI tables
  and the current agent's strategy scope.
- [`docs/4_agent_version_log.md`](docs/4_agent_version_log.md): every tried
  version's config, local-tournament result, and lesson.
- [`docs/6_next_steps.md`](docs/6_next_steps.md): rolling submit/wait
  recommendation.
