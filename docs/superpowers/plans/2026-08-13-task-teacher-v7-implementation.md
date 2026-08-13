# Task Teacher v7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `task_teacher_v7` — v5 Melon/hire/NE land + bounded Cow/pasture/milk loop (`MAX_COWS=6`, FEED budget) without Goose Melon-tax.

**Architecture:** Additive pasture/cow task generation in `tasking.py` (defaults preserve Goose). New immutable `agents/task_teacher_v7/main.py` from v5. Promote only vs `task_teacher_v5` Hoeffding + animal screen.

**Tech Stack:** Python 3.11, pytest, `scripts/run_tournament.py`, `scripts/package_agent.py`.

**Spec:** `docs/superpowers/specs/2026-08-13-task-teacher-v7-design.md`.

## Global Constraints

- Never edit existing `agents/*/main.py`.
- No Goose/Sheep; no SW/SE; no fertilizer.
- Defaults on `generate_tasks` must keep v4 Goose tests green.
- Promote only if Hoeffding CI vs v5 wholly above 0.50 **and** animal screen passes.
- Do not notebook-submit on a vs-v5 tie.

## File map

| File | Role |
| --- | --- |
| `src/kaggriculture_lib/tasking.py` | `BUILD_PASTURE`, cow PLACE/PICKUP, FEED cap/tier kwargs |
| `agents/task_teacher_v7/main.py` | New agent |
| `tests/test_tasking.py` | Library coverage |
| `tests/test_task_teacher_v7.py` | Agent coverage |
| `tests/test_package_agent.py` | Packaging smoke |

---

### Task 1: Pasture / cow task generation + FEED budget

**Files:** `src/kaggriculture_lib/tasking.py`, `tests/test_tasking.py`

- [ ] Add failing tests: `want_pasture` → `BUILD_PASTURE`; shed COW + empty PASTURE → PICKUP COW; inventory COW → PLACE; `max_feed_tasks=1` keeps only emergency FEED when two unfed animals exist; Goose defaults still pass existing tests
- [ ] Implement `TaskKind.BUILD_PASTURE`, helpers, kwargs, FEED filter
- [ ] `pytest tests/test_tasking.py -k "pasture or cow or max_feed or want_coop or pickup_goose or place_goose" -v`

### Task 2: `task_teacher_v7` agent + tests

**Files:** `agents/task_teacher_v7/main.py`, `tests/test_task_teacher_v7.py`

- [ ] Copy v5 → v7; wire cow counts, `want_pasture`, FEED kwargs, sell MILK, `BUY_ANIMAL COW`, `BUILD_PASTURE` resolve
- [ ] Tests: crops; caps; BUY_LAND; BUY_ANIMAL COW; never Goose; short episode DONE
- [ ] `pytest tests/test_task_teacher_v7.py -v`

### Task 3: Packaging smoke

**Files:** `tests/test_package_agent.py`

- [ ] Add `test_packaged_task_teacher_v7_runs_standalone_without_pythonpath`
- [ ] `pytest tests/test_package_agent.py::test_packaged_task_teacher_v7_runs_standalone_without_pythonpath -v`

### Task 4: Evaluation (stop before submit unless promote)

- [ ] Acceptance 100×720 vs starter + action coverage
- [ ] Animal screen (FEED/day, Melon harvest vs v5)
- [ ] 20-pair vs v5; 50-pair if warranted
- [ ] Package + notebook submit **only if** promote clears

## Checkpoint

After Task 3: suite green for new tests + no regressions on v4/v5/tasking.
After Task 4: write results into `docs/4_agent_version_log.md` only if promoting or explicitly documenting a no-promote.
