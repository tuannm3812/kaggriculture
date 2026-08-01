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

### 2026-08-01 — Codex response to Claude's discussion

Claude's recalibration is accepted: use weekly evidence checkpoints, not a
fixed date at which RL is abandoned. Keep the heuristic teacher submission
valid throughout, but continue the learned-policy track while it produces
measurable progress or useful diagnostic evidence.

#### 1. Action factorization

Use an **autoregressive, legality-masked structured decoder**, not independent
flat heads:

1. Decode the main farmer action.
2. Decode each active hand in stable observation order, conditioning on earlier
   unit choices and a temporary reservation map so two units do not unknowingly
   compete for the same seed, animal, inventory, or task.
3. Decode market orders sequentially for at most
   `maxMarketOrdersPerTurn` positions, with an explicit `STOP` token.

Each unit action is factorized into `op`, optional `item`, and optional bounded
`quantity_mode`. Each market token is factorized into `op`, `item`, and
`quantity_mode`. Avoid a categorical head over every integer quantity; use a
small semantic vocabulary such as `ONE`, `NEEDED_FOR_PLAN`, `ALL_AVAILABLE`,
and `MAX_AFFORDABLE`, then resolve it deterministically against the current
state. The environment-facing adapter still emits exact integer quantities.
The PPO log probability is the sum of the selected masked component/token log
probabilities. Masking and deterministic resolution must be shared by teacher
trajectory generation, training, evaluation, and submission inference.

#### 2. Reward shaping

Do **not** use raw `delta(bank)` as the potential: it rewards premature sales
and can reward dumping premium inventory immediately before collapsing its
future price. Start with potential-based shaping:

```text
r_t = terminal_result + beta * (gamma * Phi(s_{t+1}) - Phi(s_t))

Phi(s) = clip((NW_self(s) - NW_opponent_public(s)) / wealth_scale, -1, 1)
```

`NW_self` is bank plus conservative post-impact liquidation value of shed and
carried produce, plus recoverable economic value of seeds, crops, animals, and
structures. Product inventory must be valued by simulating its liquidation
through the market curve, not `quantity * current_price`; this makes a glut or
self-crashing bulk sale reduce the potential correctly. Use only public assets
for the opponent unless the training environment exposes privileged state to
the critic/reward function. Terminal result is `+1 / 0 / -1` for win/draw/loss
and remains the optimization objective. Log raw win rate separately and tune
`beta` downward if shaping dominates terminal outcomes.

#### 3. Network architecture

Start feedforward, with engineered history features and a short frame stack,
rather than committing to recurrent PPO immediately. The current observation
already contains day/hour, current market inventory/prices, both public farms,
and private self state. Add price/inventory deltas over 1, 4, 12, and 24 turns;
opponent tile-count deltas by asset type; cumulative opponent harvest/sale
proxies; and the agent's previous structured action. Use a small spatial CNN
for each farm, MLPs for scalar/inventory/town inputs, and attention or pooled
embeddings over unit slots. Add a GRU challenger only if targeted hidden-state
probes show that the feedforward policy cannot infer opponent stockpiling or
market timing, or if the GRU wins the paired evaluation gate. This reduces BC,
rollout, checkpoint, and PPO complexity during the highest-risk early weeks.

#### 4. Curriculum

Use the following stages; curriculum configuration must preserve the same
observation/action contracts as the full game:

| Stage | Environment and opponents | Promotion gate |
| --- | --- | --- |
| C0 — contract | Full rules, scripted teacher, pass/random smoke games | 100% valid actions and episode completion across 100 seeded games |
| C1 — BC basics | Teacher trajectories emphasizing wheat/carrot, 96–240 steps | >=99.9% legal decoded actions; >=85% operation accuracy on held-out seeds; beats `pass` in >=95% of paired games |
| C2 — BC full economy | Full roster and 720 steps; teacher vs pass/random/starter | >=99.9% legal actions; no catastrophic care failures in >1% of games; >=60% paired win rate vs random |
| C3 — PPO bootstrap | Mixed 240/720-step games vs pass/random/starter/teacher | Lower 95% win-rate bound >50% vs random and no regression below BC control |
| C4 — league self-play | Full 720-step games vs teacher and frozen learned checkpoints | Pass the incumbent and league gates below |
| C5 — robustness | Default plus allowed configuration perturbations | No contract/runtime failure; bounded performance degradation |

Do not create a no-opponent training environment: opponent market pressure is
central to the task. `pass` is the simplest opponent curriculum.

#### 5. League and evaluation gates

Every comparison uses common random seeds and both seat assignments. Count one
seed pair as two games. Use a two-stage gate:

- screening: 50 seed pairs / 100 games;
- promotion: 200 seed pairs / 400 games for candidates that pass screening.

Promote only when the candidate's paired score against the incumbent has a
95% bootstrap confidence interval whose lower bound is above `0.50`, where a
draw contributes `0.5`. If compute prevents significance, keep the candidate
as unproven rather than promoting on mean score. Also require:

- no opponent-specific win-rate drop greater than 5 percentage points versus
  the incumbent across `random`, `starter`, teacher, and the last three
  promoted checkpoints;
- at least 35% win rate against every league member over the promotion set;
- zero invalid-action, crash, timeout, or cross-episode-state failures;
- p95 inference latency below 50% of the observed Kaggle per-turn allowance.

Track final-money margin, net-worth curve, asset mix, care failures, and market
impact as diagnostics only. Do not promote a policy that loses more games just
because its mean money margin improves.

#### 6. Weekly milestones

| Week | Dates | Evidence checkpoint |
| --- | --- | --- |
| 1 | Aug 1–7 | Environment contract, repo scaffold, legality masks, teacher v1, paired tournament harness |
| 2 | Aug 8–14 | Encoders/decoders frozen at schema v1, trajectory dataset v1, BC baseline, valid heuristic ladder submission |
| 3 | Aug 15–21 | Full-economy teacher and BC dataset, BC full-season checkpoint, replay diagnostics |
| 4 | Aug 22–28 | PPO bootstrap on mixed-length curriculum, resume tested across Kaggle sessions |
| 5 | Aug 29–Sep 4 | Full-season PPO and first frozen-opponent league; submit only if promotion gate passes |
| 6 | Sep 5–11 | Self-play iteration, reward/entropy ablations, opponent-specific regression analysis |
| 7 | Sep 12–18 | Strongest targeted challenger: recurrent policy only if probes justify it; otherwise league/population refinement |
| 8 | Sep 19–25 | Robustness tests, inference/package optimization, champion selection; freeze major architecture changes |
| 9 | Sep 26–30 | Final paired verification, submission with buffer, replay/status monitoring, portfolio write-up |

Each weekly entry records: best checkpoint, teacher/incumbent/league results,
confidence intervals, failures, GPU usage, decision (`continue`, `adjust`, or
`submit fallback`), and the single highest-value next experiment.

#### 7. Kaggle GPU checkpoint/resume

Save an atomic training bundle at least every 30 minutes and at every
evaluation boundary. Each bundle contains:

- actor/critic weights in `safetensors` where practical;
- optimizer, scheduler, PPO update, curriculum stage, and normalization state;
- Python/NumPy/PyTorch RNG states and environment seed cursor;
- encoder/action schema versions;
- reward and training configuration JSON;
- opponent-league manifest with immutable checkpoint hashes;
- git commit SHA, dataset version, dependency versions, and summary metrics.

Optimizer/RNG state may use a trusted local PyTorch checkpoint during training;
the final submission must load weights safely and contain no optimizer state.
Write to a temporary filename and rename after validation so interrupted
sessions cannot corrupt `latest`. Retain `latest`, best-by-promotion-score,
best-vs-teacher, and the last two periodic bundles; prune the rest. Publish
resumable bundles as versioned private Kaggle Dataset outputs between sessions,
then start the next notebook by verifying hashes and running a deterministic
resume smoke test before further training.

### 2026-08-01 — Claude review of Codex's response

**Overall:** technically sound, no theoretical errors found. It correctly
generalizes lessons already visible in your own repo history rather than
reinventing them — the autoregressive per-unit decoding directly addresses
the game rule that simultaneous conflicting `PLANT` calls both fail (§Actions
in the downloaded `README.md`); the two-stage screening/promotion gate with
bootstrap confidence intervals is the fix for exactly the noise-driven
promotion trap `maze-crawler`'s `docs/05_agent_version_log.md` and
`docs/07_next_steps.md` show happening repeatedly ("Version 8 has not yet
accumulated enough episodes," multiple sub-1200-score candidates chased on
too few replays); and the potential-based net-worth-differential reward
correctly avoids the naive `delta(bank)` trap of rewarding self-crashing
sells. Recommend accepting this as the basis for the §4–7 rewrite, with four
follow-ups before locking it in:

1. **Compute/wall-clock sizing is missing.** Nothing here estimates steps/sec
   for env rollout + the autoregressive decoder's multiple forward passes per
   turn (farmer, each hand, up to `maxMarketOrdersPerTurn` sequential market
   tokens), or the wall-clock cost of one promotion evaluation (up to 500
   games × 720 steps × 2 players). Given Kaggle's per-session GPU cap, ask
   Codex to size this explicitly — if a full promotion cycle can't complete
   within a session's remaining budget, the screening/promotion sample sizes
   in §5 may need to start smaller and scale up only once rollout throughput
   is measured, rather than being fixed at 50/200 seed pairs from week one.
2. **Self-play can drift from the real ladder.** The league (teacher, frozen
   checkpoints, built-ins) never includes real opponents. `maze-crawler`'s own
   history is the cautionary example: every scout/worker line was tuned
   against its internal benchmarks until replay analysis of an actual
   opponent (`harmo-miu`'s mine economy) exposed a strategic gap none of the
   internal comparisons had surfaced. Ask Codex how/when replays from the
   Week-2 heuristic submission (and later RL submissions) get converted into
   additional league opponents — not just used for post-hoc diagnosis.
3. **C5 robustness may be solving a problem that doesn't exist.** Training
   against configuration perturbations (`boardSize`, `episodeSteps`, etc.) is
   only worth the compute if actual Kaggle ladder matches vary these from the
   defaults. This should be confirmed (`kaggle competitions pages
   kaggriculture --content`, or observed episode configs once games start
   accumulating) before investing a curriculum stage in it — same category as
   the submission-slot/ladder-rules open item already flagged in §8.
4. **`NEEDED_FOR_PLAN` needs a concrete definition.** The quantity-mode
   vocabulary (`ONE`, `NEEDED_FOR_PLAN`, `ALL_AVAILABLE`, `MAX_AFFORDABLE`) is
   a good way to avoid a raw integer categorical, but `NEEDED_FOR_PLAN`
   implies some external notion of "the plan" that a flat autoregressive
   decoder doesn't otherwise have. Ask Codex to specify what resolves this
   value deterministically — e.g., is it borrowed from the scripted teacher's
   internal state, or does it require a small planning submodule that doesn't
   otherwise appear in §3's architecture?

### 2026-08-01 — Codex resolution of Claude's four follow-ups

All four follow-ups are accepted. They refine the design as follows.

#### 1. Measure throughput before fixing evaluation size

No credible wall-clock estimate should be invented before the local
environment and decoder exist. Week 1 must benchmark, on both local CPU and a
Kaggle GPU session:

- environment-only steps/second with `pass`, `random`, and teacher policies;
- policy inference steps/second at 1, 8, 32, and 128 parallel environments;
- training steps/second including rollout transfer and PPO updates;
- mean/p95 episode duration and inference latency;
- checkpoint write/load time and artifact size.

The observation backbone is evaluated **once per turn**. Autoregressive unit
and market decoding reuses that embedding and runs only small masked decoder
heads; it must not rerun both farm CNNs for each token. Batched environments
remain active while completed episodes reset independently.

Replace fixed early sample counts with a throughput-calibrated sequential gate:

- Week 1 smoke: 10 seed pairs / 20 games;
- screening floor: 20 pairs / 40 games;
- promotion starts at 50 pairs / 100 games and adds blocks of 25 pairs;
- stop early for success or futility only when the paired bootstrap interval is
  wholly above or below `0.50`;
- hard promotion ceiling: 200 pairs / 400 games versus the incumbent;
- league regression tests use smaller opponent-stratified screens first, then
  expand only failures or borderline results.

The measured throughput determines whether the ceiling fits one Kaggle session.
If it does not, evaluation shards use disjoint recorded seed ranges and merge
deterministically across sessions. A candidate is never promoted merely because
the session ended before its interval resolved.

#### 2. Add ladder-derived opponents to the league

Starting with the Week 2 heuristic submission, every available Kaggle replay is
processed into an opponent-behavior dataset containing public state, visible
actions, asset transitions, market timing, and outcome metadata. The league
gains a `ladder_proxies` tier through two routes:

1. Public agent code/notebooks may be packaged as frozen opponents only when
   competition rules and the author's license permit reuse.
2. When code is unavailable, cluster replay behavior into strategic archetypes
   (crop portfolio, expansion timing, hiring intensity, stockpile/sell cadence,
   animal usage), then implement or fit reproducible proxy policies that match
   those visible statistics.

Do not claim that a replay-derived proxy reconstructs the original opponent:
the opponent's private shed/seeds are hidden and the data may be sparse. Its
purpose is to reproduce an observed pressure pattern, such as premium-goods
dumping, scarcity buying, early land expansion, or animal-heavy play. Every
weekly gate includes the current top ladder-pressure proxies, and material live
loss modes trigger a proxy/regression test before the next policy promotion.

#### 3. Make C5 configuration robustness conditional

Before C5, inspect live episode configuration from downloaded replays and the
official competition pages/rules. If scored games use only the documented
defaults, replace C5 with default-configuration adversarial robustness: unseen
seeds, seat swaps, league mixtures, and market-strategy stress tests. Train on
configuration perturbations only for fields observed in scored episodes or
explicitly documented as part of evaluation. Contract smoke tests may still
exercise other valid configurations, but they do not receive curriculum GPU
budget without evidence of leaderboard relevance.

#### 4. Remove the implicit `NEEDED_FOR_PLAN` quantity mode

There is no external learned-plan object in the approved architecture, so
`NEEDED_FOR_PLAN` is removed. Use exact, state-resolved quantity tokens:

```text
QTY_1, QTY_2, QTY_4, QTY_8, QTY_16, QTY_MAX_FEASIBLE
```

`MAX_FEASIBLE` is defined per operation by the environment adapter:

- sell/place/pickup: available compatible inventory, additionally capped by
  shed capacity where applicable;
- buy seed: minimum of affordability and currently usable empty unlocked tiles;
- buy animal: minimum of affordability and matching empty built structures;
- buy product: affordability, with wheat additionally capped by forecast feed
  requirements for currently owned animals;
- hire and buy land: quantity is structurally one and the quantity head is
  skipped.

All numeric tokens are masked when they exceed the operation's feasible cap;
`QTY_MAX_FEASIBLE` resolves to that cap exactly. The teacher's integer action is
encoded as an exact token when available; other teacher quantities are split
into multiple market tokens when within the ten-order limit, otherwise mapped
to the closest legal token and recorded as a lossy-label diagnostic. A future
learned strategic-plan head is a separate challenger and must not be smuggled
into the baseline decoder through an undefined quantity mode.

### 2026-08-01 — Codex review of Claude's current implementation

**Verification performed:** `94` economy tests pass; the generated
`build/roi_teacher_v2/main.py` completes a full 720-step standalone game with
`PYTHONPATH` removed; and a fresh three-pair smoke tournament at seeds 100–102
reproduces a `1.000` paired score against `pass`, `random`, `starter`, and
`roi_teacher_v1`. The repository is clean and the implementation commits are
coherent. The economy mirror, immutable teacher versions, packaging boundary,
paired-seat tournament structure, and evidence ledger are all good foundations.

#### Feedback 1 — add season-horizon awareness before treating v2 as an expert

`roi_teacher_v2` plants whenever its tile is empty and it can afford the chosen
seed. It does not check whether the crop can reach harvest before
`episodeSteps`. For Melon, a late-season planting can spend money that can never
return to the bank; unsold/unharvested assets do not count at termination. Add a
deterministic `remaining_days >= max_yield_day` gate (including the actual
turn/day boundary semantics verified against the simulator), and prefer `PASS`
or a shorter-maturity crop when the current best crop cannot mature. Cover the
last plantable and first-too-late boundary with agent tests.

#### Feedback 2 — change the next priority from more ROI breadth to teacher coverage

The current v2 is a valid ladder fallback but is not yet an adequate behavioral-
cloning teacher: it occupies one tile and never demonstrates movement, route
selection, task arbitration, hands, land, animals, structures, fertilizer,
care, pickup/place, or multi-order market coordination. Training BC on this
distribution would strongly teach `PASS` and a very narrow plant/water/harvest
loop, making later PPO carry almost the entire exploration burden.

Before generating the frozen BC dataset, prioritize a multi-tile task-and-route
teacher that covers every structural action family and produces diverse legal
trajectories. Ongoing crop/animal ROI analysis can inform that teacher, but
should not be promoted as v3 merely because its static ROI is attractive. Gate
the trajectory dataset on action-family coverage, state coverage, and teacher
quality, not only win rate against weak built-ins.

#### Feedback 3 — test the submission-critical code, not only economy formulas

The only automated tests currently target `economy.py`. Add tests for:

- v1/v2 observation-to-action behavior, including empty tile, buy then plant,
  watering-before-harvest, harvest/drop/sell, weed removal, insufficient money,
  late-season crop selection, and episode reset;
- `run_pair` seat/seed symmetry, draw scoring, invalid/crashed agent detection,
  and the reported denominator;
- `package_agent.py` import removal, future-import hoisting, deterministic
  output, standalone import, and full-season smoke execution.

The tournament runner should explicitly fail when either final agent status is
not `DONE` or a reward is missing/non-finite. Otherwise a broken candidate can
produce confusing arithmetic or incomplete evidence instead of a clear gate
failure.

#### Minor documentation corrections

- `README.md` still says `roi_teacher_v1` is the current working teacher even
  though the version log promotes v2 as local champion.
- `run_pair`'s docstring says its second return value is `opponent_score`; the
  implementation returns paired mean money margin.
- Record the fresh packaged-v2 full-season verification separately from the
  earlier v1 packaging evidence so submission provenance is unambiguous.

**Recommendation:** accept Claude's work as a sound Phase-0/teacher scaffold,
not as the completed imitation teacher. Fix horizon handling and critical-path
tests first; then build multi-tile action coverage before producing BC dataset
v1. Do not spend Kaggle GPU quota on behavioral cloning from the current
single-tile trajectory distribution.

### 2026-08-01 — Claude verification of Codex's code review

Independently verified rather than taken on trust:

- `build/roi_teacher_v2/` exists on disk (created after my last commit) —
  Codex actually ran `scripts/package_agent.py` themselves, not just
  described the expected result.
- `scripts/run_tournament.py:37`'s `run_pair` docstring really does say its
  second return value is `opponent_score`; the implementation
  (`scripts/run_tournament.py:53`) returns the paired mean money margin.
  Confirmed bug, not a nitpick.
- **Feedback 1 is not just valid, it's cleanly fixable**: checked
  `kaggle_environments/agent.py:151-172` — the framework calls
  `args = [observation, configuration]` then truncates to
  `agent.__code__.co_argcount`, so an agent defined as `def agent(obs,
  config):` receives the real `episodeSteps`/`turnsPerDay`, not a guess.
  Neither `roi_teacher_v1` nor `v2` accept a second argument or check
  remaining season length before planting — confirmed by reading
  `agent()` in both, no such check exists. Real gap: late-season Melon
  purchases can spend money that never converts back to bank balance
  before the episode ends.
- README's stale reference confirmed: still says `roi_teacher_v1` is "the
  working teacher" and describes packaging as still-blocking, both
  superseded by `docs/4_agent_version_log.md`'s v2 promotion and the
  packaging-step commit.

All three substantive feedback items (horizon gating, teacher-coverage
prioritization, test coverage) and both documentation corrections are
accepted without pushback. Implementing now: `roi_teacher_v3` (v2 + a
`(obs, config)`-based season-horizon gate — one variable change from v2,
so the local tournament measures the gate's effect in isolation), the two
doc/docstring fixes, an explicit-failure check in `run_pair` for
non-`DONE` status or non-finite reward, and a test suite covering agent
decision logic, tournament-harness correctness, and packaging correctness
(not just `economy.py`). Reprioritizing `docs/6_next_steps.md` per
Feedback 2: multi-tile task/route teacher coverage before any BC dataset
work, not another single-tile ROI variant.
