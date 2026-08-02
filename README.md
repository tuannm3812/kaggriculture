# Kaggriculture

Kaggle Featured competition ($50,000 prize pool) for a two-player farm-
economy simulation bot: https://www.kaggle.com/competitions/kaggriculture

## Status

Week 1-2 in progress (2026-08-02). Deadline: **2026-09-30 23:59 UTC**.
Local environment verified (including a passed Kaggle platform smoke
test), economy math tested against the real simulator, and a series of
agents have each beaten the last in local tournament play. Current local
champion: **`task_teacher_v2`** — adds daily hiring and bounded exhaustive
multi-unit assignment on top of `task_teacher_v1`'s multi-tile task
scheduler. Two rounds of Codex review (2026-08-02) each caught a real,
confirmed bug before promotion was legitimate: (1) a hiring-value fix that
was correct in the shared library but never actually passed to the running
agent's hiring call, and (2) an end-of-day hiring-timing bug (a hire queued
on the day's last hour is guaranteed zero future actions before hands
clear at the day boundary) plus a percentile-bootstrap confidence interval
that degenerated to false `[1.000, 1.000]` certainty on all-win samples.
After fixing both and re-running the full evidence gate with a corrected
Hoeffding confidence interval — 100-episode acceptance run, then paired
evaluation at 20 pairs (screen) and 50 pairs (promotion, 95% CI
`[0.730, 1.000]`, wholly above 0.50) — `task_teacher_v2` is legitimately
promoted. See `docs/4_agent_version_log.md` for full numbers and
`docs/superpowers/specs/2026-08-01-task-teacher-v2-design.md` §§10-13 for
Codex's review and the response. Packaging (`scripts/package_agent.py`)
is done and verified for every agent; not yet submitted to the ladder —
see `docs/6_next_steps.md` for the current recommendation.

Full design is split across
[`docs/superpowers/specs/`](docs/superpowers/specs/): the authoritative
project-level design
(`2026-08-01-kaggriculture-competition-plan-design.md`), the task-teacher
family's own design (`2026-08-01-task-teacher-design.md` and
`-v2-design.md`), and the full chronological Codex↔Claude discussion
history (`2026-08-01-kaggriculture-design-discussion-log.md`).

## Repository Structure

- `docs/`: numbered competition notes, environment verification, agent
  strategy, version log, next steps (see Documentation Map below).
- `src/kaggriculture_lib/`: shared, tested library — game economy math
  (price curve, yield formulas, season feasibility) in `economy.py`, and
  multi-tile task generation/ranking/routing in `tasking.py`. Single
  source of truth for every agent version.
- `agents/<family>_<version>/main.py`: one immutable folder per tried
  agent version. `roi_teacher_v*` (single-tile ROI heuristic) and
  `task_teacher_v*` (multi-tile task/route scheduler) are separate
  families — see `docs/3_agent_strategy.md`.
- `scripts/`: local tournament runner (`run_tournament.py`), submission
  packaging (`package_agent.py`).
- `tests/`: unit tests for `src/kaggriculture_lib`, agent decision logic,
  the tournament harness, and the packaging step.
- `replays/`: gitignored raw episode JSON; `replays/analysis/` keeps small
  derived summaries.

## Local Setup

Requires Python >= 3.11. Pinned to `kaggle-environments==1.29.3` (installs
cleanly from PyPI) — deliberately not "latest": `1.29.3` is confirmed
running on Kaggle's own kernel infrastructure and has real balance
differences from newer releases; see `docs/2_environment_notes.md`'s
version-gap comparison before bumping this pin:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run the local tournament harness:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_tournament.py \
    agents/task_teacher_v2/main.py pass random starter \
    --episodes 10 --episode-steps 720
```

Package an agent into a standalone submission artifact:

```bash
.venv/bin/python scripts/package_agent.py agents/task_teacher_v2
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
