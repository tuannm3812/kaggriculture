# 1. Competition Instructions

## Competition

- Name: Kaggriculture
- URL: https://www.kaggle.com/competitions/kaggriculture
- Category: **Featured**, reward **$50,000 USD**
- Deadline: **2026-09-30 23:59:00 UTC** (via `kaggle competitions list -s
  kaggriculture`, confirmed 2026-08-01)
- 312 teams entered as of 2026-08-01

## Format

Two-player, bot-vs-bot farm-economy simulation run via `kaggle_environments`.
There is no train/test data; the competition's downloadable bundle
(`kaggle competitions download -c kaggriculture`) contains only:

- `AGENTS.md` — getting-started guide (submission mechanics, CLI workflow)
- `README.md` — full game rules (object types, actions, market mechanics,
  turn processing, observation format, configuration defaults)

Both are also present locally once `kaggle-environments` is installed, at
`kaggle_environments/envs/kaggriculture/{AGENTS,README}.md` — see
`docs/2_environment_notes.md` for the exact path and version.

## Submission

A `main.py` (or `main.py` + helpers bundled in a `.tar.gz`) exposing an
`agent(obs)` function.

```bash
kaggle competitions submit kaggriculture -f main.py -m "<message>"
# or, multi-file:
tar -czf submission.tar.gz main.py helper.py
kaggle competitions submit kaggriculture -f submission.tar.gz -m "<message>"
```

Kaggle runs episodes against other submitted agents.

**Open item — not stated in Kaggriculture's own docs:** submission-slot /
ladder-tracking rules (e.g. whether only the latest N submissions are
tracked for ranking, as `maze-crawler` documented for its own competition).
Confirm via `kaggle competitions submissions kaggriculture` behavior and the
competition's Rules page once submissions exist, rather than assuming it
matches `maze-crawler`.

**Open item:** exact opponent pool for ladder games (other public
submissions? seeded built-ins?) — unclear from `AGENTS.md`/`README.md`
alone; affects how much weight to put on local built-in-agent tournament
results vs. real ladder score.

## Game Summary

Full rules in the downloaded `README.md`; key facts:

- 30-day season, 24 turns/day (720 turns total), `startingMoney = $3000`.
- Each player's farm: 10×10 grid, four 5×5 quadrants; only NW starts
  unlocked. `BUY_LAND` unlocks the rest at $1k / $2k / $4k.
- Object types: Wheat, Carrot, Melon (one-time yield); Tomato, Strawberry
  (ongoing yield); Goose/Egg, Cow/Milk, Sheep/Wool (animals, need
  coop/pasture). Each has its own seed/animal cost, yield curve, base price.
- Watering/feeding required daily; 2 consecutive misses → weed / animal
  escapes (unrecoverable).
- Market: per-resource dynamic sell price, asymmetric shape functions on
  scarcity vs. glut sides — see `docs/2_environment_notes.md` for the exact
  formula and its ground-truth source.
- Town buildings (center + unlockable shops) add a growing, player-action-
  independent demand sink.
- Win condition: most money in the bank at season end; ties possible.

## Built-in Agents

Three ship with the environment: `"pass"` (no-op), `"random"`, `"starter"`
(deterministic wheat-loop baseline). Available via
`kaggle_environments.make("kaggriculture").run([agent_a, agent_b])`.

## Configuration Defaults

| Parameter | Default |
| --- | --- |
| `episodeSteps` | 720 |
| `boardSize` | 10 |
| `startingMoney` | 3000 |
| `maxMarketOrdersPerTurn` | 10 |
| `turnsPerDay` | 24 |
| `shedCapacity` | 100 |
| `weedSpawnChance` | 0.005 |
| `townShopUnlockInterval` | 3 |
| `townShopSellInterval` | 4 |
| `townCenterSellInterval` | 12 |
| `seed` | null (deterministic episode generation when set) |

Per-resource market-param overrides are possible via
`env.configuration["marketParams"]` without code changes — relevant to the
design doc's conditional C5 robustness stage (only worth training against if
scored ladder episodes actually vary these from defaults).
