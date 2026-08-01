# Kaggriculture Competition Plan — Design

Written 2026-08-01. Discuss/revise with Codex or others before moving to a
detailed implementation plan — nothing in `src/`, `agents/`, or `scripts/`
should be built until this design is settled.

## 1. Competition Facts

- Name: Kaggriculture — https://www.kaggle.com/competitions/kaggriculture
- Category: **Featured** (not Playground Series), reward **$50,000 USD**
- Deadline: **2026-09-30 23:59:00 UTC** (confirmed via `kaggle competitions
  list -s kaggriculture`, checked 2026-08-01) — roughly 60 days from today
- 312 teams entered as of 2026-08-01
- Format: two-player, bot-vs-bot farm economy simulation run via
  `kaggle_environments`. Not a tabular ML task — no train/test CSVs. The
  competition data bundle only contains `AGENTS.md` (getting-started guide)
  and `README.md` (full game rules), both fetched via `kaggle competitions
  download -c kaggriculture`.
- Submission: a `main.py` (or `main.py` + helpers in a `.tar.gz`) exposing an
  `agent(obs)` function, submitted via `kaggle competitions submit
  kaggriculture -f main.py -m "<message>"`. Kaggle runs episodes against
  other submitted agents; **submission-slot / ladder-tracking rules are not
  stated in Kaggriculture's own docs** and must be confirmed early (see Phase
  0) rather than assumed to mirror `maze-crawler`'s "only latest N tracked"
  behavior.

## 2. Game Summary (see full rules in the downloaded `README.md`)

- 30-day season, 24 turns/day (720 turns total), `startingMoney = $3000`.
- Each player's farm is a 10×10 grid split into four 5×5 quadrants; only NW
  starts unlocked, others bought via `BUY_LAND` ($1k/$2k/$4k).
- Object types: Wheat, Carrot, Melon (one-time yield crops), Tomato,
  Strawberry (ongoing yield crops), Goose/Egg, Cow/Milk, Sheep/Wool
  (animals, need coop/pasture). Each has its own seed/animal cost, yield
  curve, and base market price.
- Plants must be watered, animals fed, every day (2 consecutive misses →
  weed / escaped animal, unrecoverable). `FERTILIZE` and `CARE` bank yield
  bonuses under specific timing rules.
- Market: per-resource dynamic sell price, `price(inv) = base ± amp·f(|inv −
  I0|)`, asymmetric shape functions (`linear`/`sq`/`sqrt`/`log`) on the
  scarcity vs. glut side — meaning big sells of premium goods (strawberry,
  melon, milk, wool) crash their own price hard, while staples (wheat) absorb
  gluts more gently. Town buildings (center + unlockable shops) add a second,
  growing demand sink independent of player action.
- Win condition: most money in the bank at season end; ties possible.

This is meaningfully more complex than any prior agent-competition repo
(`orbit-wars`, `maze-crawler`, `pokemon-tcg-ai-battle`) because of the
compounding economy layer — ROI isn't static, it depends on your own and the
opponent's trading behavior.

## 3. Why This Isn't a Tabular-Playground Project

Your master `coding_standards.md` defaults to a notebook-first structure
(`notebooks/` as source of truth, `docs/` for reasoning). That fits the
Playground Series repos (`s6e4`–`s6e8`) but not this competition: there's no
train/test data, the executable artifact Kaggle actually runs is a Python
agent, and iteration happens via versioned agent code + replay analysis, not
notebook cells. `orbit-wars`, `maze-crawler`, and `pokemon-tcg-ai-battle` are
the right precedent instead — they already establish: numbered `docs/`
(coding standards → competition instructions → environment/EDA →
strategy → version log → next steps → replay findings), versioned
`agents/`/`candidates/` folders (one immutable folder per tried version), a
local tournament/replay-analysis script pair, and a strict "don't submit
speculative variants that push a known-good version out of tracked slots"
submission discipline.

## 4. Strategy Approach — Recommendation

**Start heuristic, layer in search later.** Ship a hand-tuned ROI-heuristic
agent first (fast to build, easy to debug, gets on the ladder quickly so
rating has time to converge on real game volume — the same lesson
`maze-crawler`'s docs recorded repeatedly). Only add a short-horizon
lookahead/planning layer once replay evidence identifies a *specific* tempo
or timing failure the heuristic can't fix — not preemptively.

Rejected alternatives:
- **Full lookahead/simulation agent from day one** — more adaptive to market
  state, but much more code to get right before any submission exists, and
  the added complexity may not target this game's actual failure modes
  (unknown until replay data exists).
- **Heuristic only, no planning layer ever** — likely leaves value on the
  table once the market-timing and quadrant/hand-investment tradeoffs get
  sophisticated in later-game states; deferred, not discarded.

## 5. Repo Structure

```
kaggriculture/
├── README.md                       # overview + current champion result
├── requirements.txt
├── .gitignore
├── docs/
│   ├── 0_coding_standards.md       # project-specific layer on the master doc;
│   │                               # documents the src/-from-day-one exception (§6)
│   ├── 1_competition_instructions.md  # game rules, deadline, submission mechanics
│   ├── 2_environment_notes.md     # price-curve/yield-formula verification,
│   │                               # kaggle_environments quirks found locally
│   ├── 3_agent_strategy.md        # ROI tables, market-timing hypotheses
│   ├── 4_agent_version_log.md     # per-version config diff + score/outcome
│   ├── 5_replay_strategy.md       # aggregate replay findings, loss-mode taxonomy
│   ├── 6_next_steps.md            # rolling submit/wait recommendation
│   └── assets/
├── src/kaggriculture_lib/
│   ├── economy.py                 # replicated price curve + yield formulas
│   └── planner.py                 # decision logic (heuristic first, lookahead later)
├── agents/
│   ├── roi_baseline_v1/main.py
│   └── ...                        # one folder per tried version, immutable once tried
├── scripts/
│   ├── run_tournament.py          # local batch runner: agent vs pass/random/starter/champion
│   ├── analyze_replay.py          # action counts, money-over-time, loss-mode tagging
│   └── submit.sh                  # wraps `kaggle competitions submit`
├── tests/                          # unit tests for economy.py math
└── replays/                        # gitignored raw JSON; replays/analysis/ summaries kept in git
```

## 6. Deliberate Exception to the Master Coding Standard

The master standard says: "only add `src/<package>` once shared logic is
genuinely reused across multiple notebooks." This project adds
`src/kaggriculture_lib/` starting at v1, not after proving reuse, because the
price-curve and yield formulas (9 resources × asymmetric shape functions,
one-time vs. ongoing yield math, `CARE` bonus banking) are complex enough
that every agent version must share exactly one correct implementation —
reimplementing per version risks silent divergence and an agent that's
"wrong" in an untestable way. `docs/0_coding_standards.md` will record this
exception explicitly, per the master doc's own convention for project-level
deviations.

## 7. Phased Timeline

Today: 2026-08-01. Deadline: 2026-09-30 23:59 UTC (~60 days). Pace: **heavy
push now, taper later** (front-load Phases 0–3, then steady iteration,
freeze before the deadline).

| Phase | Window | Deliverable |
| --- | --- | --- |
| 0 — Setup | Day 0–1 | Repo scaffold; `docs/0_coding_standards.md`, `docs/1_competition_instructions.md`; confirm `kaggle_environments.make("kaggriculture")` runs locally; baseline matchups among the three built-in agents (`pass`, `random`, `starter`); **confirm submission-slot/ladder-tracking rules** (open item, not stated in Kaggriculture's own docs) |
| 1 — Economics modeling | Day 1–4 | `src/kaggriculture_lib/economy.py` + `tests/`, validated against the README's sample price points (e.g. wheat `$45`/`$20`/`$19` at `I0−T`/`I0+T`/`I0+2T`); static $/tile/day and $/action tables per crop/animal → `docs/2_environment_notes.md`, `docs/3_agent_strategy.md` (v0 hypotheses) |
| 2 — ROI baseline agent | Day 4–8 | `agents/roi_baseline_v1`: greedy highest-current-ROI planting/selling, never miss watering/feeding, hire hands / buy land only when marginal ROI clears cost; `scripts/run_tournament.py` built and used locally before any submission |
| 3 — First submission + diagnostics | Day 8–14 | Submit v1 early to start accumulating ladder games (rating needs volume to converge); build `scripts/analyze_replay.py` (money-over-time, weed/escape counts, self-crash-on-sell detection); scaffold `docs/4_agent_version_log.md`, `docs/5_replay_strategy.md` |
| 4 — Iterate (heavy-push window) | Day 14–30 | One-variable-at-a-time versions v2–v6+: sell pacing (avoid self-crashing premium goods), hire cadence, land-buy timing, crop-mix sequencing over the season, fertilizer/care gating. Local tournament gate before every submission; update `docs/4` + `docs/6_next_steps.md` after every result |
| 5 — Lookahead layer (conditional) | Day 30–45 | Only if replay evidence shows a specific tempo/timing failure a greedy heuristic can't fix. Short-horizon (1–3 day) simulate-and-score used only at high-value decision points: `BUY_LAND` timing, crop-mix switch timing, bulk-sell timing — not a full replan every turn |
| 6 — Stabilize & final | Day 45–60 | Freeze new mechanics ~1 week before deadline; re-verify champion via local tournament; submit with buffer before 2026-09-30 23:59 UTC; close out `README.md` with a results summary |

## 8. Open Items to Resolve Early (Phase 0)

1. Submission-slot / ladder-tracking behavior for Kaggriculture specifically
   — do not assume it matches `maze-crawler`'s "only latest N submissions
   tracked" rule until confirmed via `kaggle competitions submissions
   kaggriculture` behavior or competition rules page.
2. Whether team play is relevant (solo assumed unless stated otherwise).
3. Exact opponent pool for ladder games (random public submissions? seeded
   built-ins? unclear from `AGENTS.md`/`README.md` alone) — affects how much
   weight to put on built-in-agent tournament results vs. real ladder score.

## 9. Design Review Log

### 2026-08-01 — Codex review after user strategy change

**Decision from the user:** compete solo, budget roughly 10 hours per week,
optimize for both leaderboard performance and portfolio quality, use Kaggle
GPUs, and replace the heuristic-first strategy with a reinforcement-learning /
imitation-learning strategy. The user approved **scripted expert imitation
followed by PPO self-play**.

**Agreement with the original design:** retain the authoritative competition
facts, early environment verification, reusable tested Python package,
deterministic tournament harness, replay diagnostics, immutable promoted
checkpoints/agent versions, submission ledger, and pre-deadline stabilization
window. A scripted heuristic is still required, but its role changes from the
champion architecture to teacher, benchmark opponent, curriculum aid, and
fallback submission.

**Required redesign:** Sections 4, 5, 6, and 7 currently describe a heuristic
ROI agent with optional short-horizon search. They must be replaced after the
learning-system design is approved. The revised design needs explicit modules
and gates for:

- observation encoding and normalization;
- factorized, legality-masked actions for the farmer, hands, and market;
- scripted-expert trajectory generation and behavioral cloning;
- curriculum environments with progressively longer seasons and fuller game
  mechanics;
- PPO fine-tuning against a league containing built-ins, the teacher, frozen
  historical checkpoints, and self-play policies;
- checkpoint evaluation using paired seats/seeds, win rate with uncertainty,
  final-money margin as a diagnostic only, and exploitability/regression
  screens against the full opponent league;
- compact deterministic inference and offline-safe weight packaging in the
  Kaggle submission artifact;
- GPU-budget controls, resumable training artifacts, and promotion thresholds
  suitable for a solo 10-hour/week schedule.

**Risks to resolve before implementation:** the multi-unit plus ordered-market
action space may be too large for one flat categorical head; terminal-only win
reward is too sparse for efficient PPO; recurrent state may be necessary for
opponent and market-history inference; and Kaggle GPU session/runtime/storage
constraints must shape checkpoint cadence. The next design sections will lock
down the action factorization, reward shaping, network architecture, curriculum,
and evaluation gates before this document is rewritten into the approved RL
specification.

### 2026-08-01 — Claude discussion notes for Codex (time-budget recalibration)

**Budget update from the user:** the ~10hr/week figure is not a hard cap —
they can invest more time as needed. The constraint they actually want is a
**weekly progress/checkpoint cadence**, not a fixed total-hour ceiling. This
changes the framing of my earlier risk note (which was sized against ~80
total hours); it does not remove the underlying engineering risks, which are
independent of how much time is available.

**Proposal: replace the single hard 2-week fallback ripcord with a rolling
weekly checkpoint.** Each week, compare the current best learned policy
against the scripted-heuristic teacher (and, once available, the prior
week's checkpoint and the built-ins) via the local tournament harness, and
log a continue / adjust / fall-back-to-heuristic-submission decision in
`docs/4_agent_version_log.md` — the same discipline `maze-crawler` already
uses for its submit/wait rule, just applied weekly to the RL track instead
of per-agent-version. This keeps a working ladder submission available at
every checkpoint without committing to one fixed abandon-RL date up front.

**What does NOT change because the budget relaxed** (these are engineering
constraints, not time-budget artifacts, so more hours doesn't dissolve
them):
- Kaggle GPU sessions are still capped per-session (~9–12h) with a weekly
  quota — checkpoint/resume infrastructure is still a Phase-1 requirement.
- Terminal-only win reward is still too sparse regardless of wall-clock
  budget; still recommend potential-based shaping on bank-balance delta per
  step as the first fix, before reaching for recurrence.
- Action-space factorization (farmer / hands / market as separate masked
  heads, vs. one flat categorical) is a correctness/tractability question,
  not a time-budget question — needs to be settled before any BC data
  generation starts, since the observation → action encoding is shared by
  every downstream stage.

**Discussion asks for Codex**, to unblock the sections-4–7 rewrite:

1. Action factorization: confirm (or propose an alternative to) per-role
   masked action heads — farmer op, per-hand op, ordered market-order list
   (up to `maxMarketOrdersPerTurn`) — and how the market order *list* (a
   variable-length sequence, not a single categorical) gets encoded/decoded.
2. Reward shaping formula: proposed starting point is potential-based
   shaping on Δbank-balance per step, plus a terminal win/loss/draw bonus;
   confirm or counter-propose, and specify how to avoid the shaped reward
   rewarding self-crashing sells (dumping inventory to realize short-term
   Δbank at the cost of price crashing future turns).
3. Network architecture: feedforward-with-engineered-history-features vs.
   recurrent — specifically, is partial observability (hidden opponent
   shed/seeds, price-curve inference) severe enough to need recurrence, or
   can a rolling window of recent market/opponent-tile observations as
   input features substitute?
4. Curriculum stages: propose the specific progression (e.g., short season
   → full season, single-crop-only → full object roster, no-opponent →
   built-in opponents → self-play), with promotion criteria between stages.
5. League/eval gates: define the paired-seat/seed evaluation protocol,
   minimum sample size for a win-rate-with-uncertainty verdict, and the
   exploitability/regression screen against the full opponent league
   mentioned in the risks section above.
6. Weekly milestone breakdown: a week-by-week table from 2026-08-01 through
   2026-09-30 that Phase timeline in §7 can be rewritten against, sized for
   a flexible-but-tracked weekly cadence rather than a fixed hour budget.
7. Kaggle GPU checkpoint/resume plan: concrete artifact format and cadence
   given session/runtime/storage limits, independent of how many hours/week
   are available.
