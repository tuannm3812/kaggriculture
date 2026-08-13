"""Episode configuration helpers for local vs ladder-parity evaluation.

Pinned `kaggle-environments==1.29.3` ships schema defaults that do **not**
match live Kaggriculture ladder episodes (measured 2026-08-13 from
`task_teacher_v5` submission `55425318` replays, e.g. episode 91903522):

| Key | 1.29.3 make() default | Live ladder replay |
| --- | ---: | ---: |
| `startingMoney` | 2000 | **3000** |
| `farmHandCostMult` | 10 | **1** |
| `townShopSellInterval` | 2 | **4** |
| `townCenterSellInterval` | 6 | **24** |

Under 1.29.3 defaults, v5's land gate only clears around day 14–15 (cash).
Under ladder-match config, the same gate clears on **day 0 hour 23** —
matching every public ladder replay for `55425318`. This is why v6's
`budget_reserve=2000` looked inert locally but is the right lever for the
ladder.
"""

from __future__ import annotations

# Measured from live ladder replay `configuration` blocks (2026-08-13).
LADDER_MATCH_CONFIGURATION: dict = {
    "startingMoney": 3000,
    "farmHandCostMult": 1,
    "townShopSellInterval": 4,
    "townCenterSellInterval": 24,
    "turnsPerDay": 24,
}


def tournament_configuration(episode_steps: int = 720, seed: int | None = None) -> dict:
    """Configuration for local tournaments that should mirror the ladder."""
    cfg = {**LADDER_MATCH_CONFIGURATION, "episodeSteps": episode_steps}
    if seed is not None:
        cfg["seed"] = seed
    return cfg
