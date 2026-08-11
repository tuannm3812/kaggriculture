# Task Teacher v5 Implementation Plan

> **For agentic workers:** Execute task-by-task with TDD. Stop only if BLOCKED.

**Goal:** Ship `task_teacher_v5` — v2 + NE `BUY_LAND`, `MAX_GEESE=0` (no Goose).

**Architecture:** Copy `agents/task_teacher_v4/main.py` → `v5`; set `MAX_GEESE=0`; update docstring. Leave v4 untouched.

**Tech Stack:** Python 3.11, pytest, existing packaging/tournament scripts.

## Task 1: Agent + unit tests

- Create `agents/task_teacher_v5/main.py` from v4 with `MAX_GEESE = 0` and land-only docstring.
- Create `tests/test_task_teacher_v5.py` (mirror v4 helpers): crops match v2; `MAX_GEESE==0`; `BUY_LAND` under gate fixture; never `BUY_ANIMAL` with empty coop + cash; short episode DONE/finite.
- Commit: `feat: add task_teacher_v5 land-only (MAX_GEESE=0)`

## Task 2: Packaging

- Add `test_packaged_task_teacher_v5_runs_standalone_without_pythonpath` to `tests/test_package_agent.py`.
- Commit: `test: verify task_teacher_v5 packages and runs standalone`

## Task 3: Evaluation + docs

- 100-ep acceptance vs starter (fresh seeds 82000–82099); assert `BUY_LAND>0`, no `BUY_ANIMAL`.
- 20-pair screen vs `task_teacher_v2` seed 83000; escalate to 50-pair seed 84000 only if CI not wholly below 0.50.
- Regression vs `roi_teacher_v3` + `starter` seed 85000 if screen positive/ambiguous.
- Record in version log / next_steps / README; promote only if CI wholly above 0.50.
- Push to main when user-requested (this session: yes after eval).
