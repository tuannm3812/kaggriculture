# Task Teacher v8 — Design (hire parity + gated SW)

Written 2026-08-13. Status: **implemented, not promoted**. Ladder-match
20-pair vs v5: `WR=0.300`, CI `[0.000, 0.680]` (seed 97400). SW fires
(~day 15) but loses head-to-head; S3 hire-mult=1 hire-runaways (reverted
to decision mult=10). Shared lib helpers remain useful for later versions.

## 1. Goal

Ship `task_teacher_v8` = `task_teacher_v5` (Melon/hire + early NE) plus:

1. **S3 — Hire cost parity + hand cap:** use `config["farmHandCostMult"]`
   (ladder = 1) for `should_hire` / hire reservation, plus hard
   `MAX_HANDS = 8` (mult=1 without a cap hire-runaways — first screen
   ~169 HIRE/ep, WR 0.000).
2. **S1 — Gated SW:** keep early NE; allow a second `BUY_LAND` (SW @ $2000)
   only after Melon cash clears a high reserve. Never SE.

### Non-goals

- Animals / Goose / Cow / Sheep (S2 is a later version)
- Delaying NE (v6 lost under ladder-match)
- Editing existing `agents/*/main.py`
- Changing default `should_buy_land` / `should_hire` behavior for v4–v7

### Success

- Acceptance (ladder-match): DONE; `BUY_LAND` count often 2; never SE;
  no `BUY_ANIMAL`
- Telemetry: NE cause-day still ~0; SW cause-day clearly later with high cash
- Promote: Hoeffding vs **`task_teacher_v5`**, CI wholly above 0.50
  (ladder-match tournament config)
- Notebook submit only after promote

## 2. Architecture

### Shared library (additive)

**Hire mult from config** (`economy.py` or thin helper):

```python
def hire_cost_mult(config) -> int:
    if not config:
        return FARM_HAND_COST_MULT  # 10
    return int(config.get("farmHandCostMult", FARM_HAND_COST_MULT))
```

`should_hire(..., hire_cost_mult: int = FARM_HAND_COST_MULT)` uses
`economy.hire_cost(hires_today, mult=hire_cost_mult)`.

**Land gate** — extend `should_buy_land` with:

| Kwarg | Default | v8 |
| --- | ---: | ---: |
| `max_extra_quadrants` | `1` | `2` |
| `sw_budget_reserve` | `3000` | `3000` (need ~$5000 for SW) |
| `sw_min_plants` | `20` | `20` |

- `n_extra == 0` → existing NE gates (`budget_reserve`, sat=12, hands≥3, …)
- `n_extra == 1` and `max_extra_quadrants >= 2` → SW gates: plants ≥
  `sw_min_plants`, hands ≥ 3, days remaining, hire_value==0,
  `money - reserved >= land_cost(1) + sw_budget_reserve`
- `n_extra >= max_extra_quadrants` → False

### Agent

`agents/task_teacher_v8/main.py` — forward-copy of v5:

- `MAX_GEESE = 0`
- `MAX_EXTRA_QUADRANTS = 2`
- `SW_BUDGET_RESERVE_V8 = 3000`
- Resolve `hire_mult = economy.hire_cost_mult(config)` each turn; pass into
  `should_hire` and `economy.hire_cost(..., mult=hire_mult)`
- `should_buy_land(..., max_extra_quadrants=2, sw_budget_reserve=SW_BUDGET_RESERVE_V8)`

## 3. Evaluation

Ladder-match config only (`tournament_configuration`).

1. Acceptance vs starter + land coverage (NE and SW both fire across run)
2. 20-pair vs v5 → 50-pair if warranted
3. Package + notebook submit only on promote

## 4. Approval

Strategy sequence S3→S1 and this design — **approved** (“approve keep going”).
