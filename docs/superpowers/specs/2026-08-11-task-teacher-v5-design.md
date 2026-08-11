# Task Teacher v5 — Design (land-only)

Written 2026-08-11. Status: **approved**.

Motivated by the 2026-08-10 Goose ablation: vs `task_teacher_v2` (10 pairs,
seeds 81000–81009), full v4 scored `0.050` WR; **v4 with Goose stripped and
NE land kept scored `0.750` WR (+2449 mean margin)**. Goose FEED/PICKUP/PLACE
labor (~259 actions/episode) crowds out Melon work. Land alone is the
ladder-motivated piece that still looks locally positive.

## 1. Goal

Ship `task_teacher_v5` — **`task_teacher_v2` + ROI-gated NE `BUY_LAND` only**.
No animals.

### Non-goals

- Goose / Cow / Sheep / coops / `PICKUP` animal path
- Fertilizer
- SW/SE land
- Changing `task_teacher_v4` (leave as the land+Goose experiment, not promoted)
- Editing any existing `agents/*/main.py`

### Success

- 100-ep acceptance clean; `BUY_LAND` > 0 across episodes
- **No** `BUY_ANIMAL` / `FEED` / `BUILD_COOP` / `PLACE` / animal `PICKUP`
- Hoeffding vs `task_teacher_v2`: CI wholly above 0.50 at 20-pair → 50-pair
  promotion protocol
- Existing tests keep passing

## 2. Architecture

- New immutable `agents/task_teacher_v5/main.py` copied from
  `task_teacher_v4/main.py`.
- `MAX_GEESE = 0` — buy/want_coop gates already key off this; no Goose market
  or structure loop fires.
- Keep `should_buy_land` wiring, hire→land→seed budget stack, wheat sell
  (reserve stays 0 with zero placed geese).
- Shared lib unchanged unless a tiny constant/doc comment is needed (prefer
  zero lib churn).

## 3. Tests

- `tests/test_task_teacher_v5.py`: crops match v2; `MAX_GEESE==0`; emits
  `BUY_LAND` under the existing gate fixture; never `BUY_ANIMAL` even with
  empty coop + cash; short episode DONE/finite.
- Packaging smoke in `tests/test_package_agent.py`.

## 4. Evaluation

Fresh seeds (not reused from v4 failures). Same protocol as v4 Task 9.
Honesty rule unchanged.

## 5. Approval checklist

1. Approve land-only scope (`MAX_GEESE=0`, no animal path)?
2. Approve new agent `task_teacher_v5` (leave v4 immutable)?
3. Approve promote-only-vs-v2 Hoeffding gate before any ladder submit?
