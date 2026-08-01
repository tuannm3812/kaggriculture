# Kaggriculture Competition Plan — Authoritative Design

Written 2026-08-01. This is the current source of truth. The chronological
discussion that produced it is preserved in
`2026-08-01-kaggriculture-design-discussion-log.md` and is non-authoritative.
Teacher-specific decisions live in `2026-08-01-task-teacher-design.md`.

## 1. Goal and Constraints

- Compete solo for both leaderboard performance and portfolio quality.
- Deadline: **2026-09-30 23:59 UTC**.
- Featured competition with a **$50,000** prize pool.
- Use Kaggle GPU sessions for learned-policy training.
- Track progress weekly; the original 10-hour/week estimate is not a hard cap.
- Maintain a valid deterministic heuristic fallback throughout development.
- Do not submit to the competition without explicit user authorization.

## 2. Verified Platform Contract

- Two-player `kaggle_environments` farming/economy simulation.
- Default season: 720 turns, 24 turns/day, 30 days.
- Submission artifact exposes `agent(obs[, config])` from root `main.py`.
- The Kaggle smoke kernel
  `tuannm3812/kaggriculture-platform-smoke-test`, version 1, completed
  successfully on 2026-08-01.
- Remote runtime used `kaggle-environments==1.29.3`; local development is pinned
  to that version because later `1.32.2` mechanics differ materially.
- Smoke validation confirmed offline import, two full seat assignments, finite
  rewards, `DONE` statuses, and matching local/remote agent hashes.
- No competition submission has been made as of this revision.

## 3. Approved Strategy

Use **scripted-expert imitation followed by PPO league self-play**:

1. Build a deterministic, economically competent task-based teacher.
2. Generate separate competitive and action-coverage trajectory corpora.
3. Train a legality-masked policy by behavioral cloning.
4. Fine-tune with PPO against built-ins, the teacher, frozen checkpoints, and
   ladder-derived strategic proxies.
5. Promote learned checkpoints only through paired-seat/seed evaluation with
   uncertainty and regression gates.

The heuristic teacher is simultaneously:

- a behavioral-cloning expert;
- a benchmark opponent;
- a curriculum aid;
- a portfolio-quality interpretable baseline;
- the safe ladder fallback.

Do not train BC/PPO from the single-tile `roi_teacher_v1`–`v3` trajectories.

## 4. Learning Architecture

### 4.1 Observation encoding

- Spatial tensors for both farms.
- Scalar features for time, money, configuration, inventory, seeds, town, and
  current market state.
- Engineered history: price/inventory deltas over 1, 4, 12, and 24 turns;
  opponent public asset deltas; prior structured action.
- Start with a small CNN plus MLP encoders and pooled unit embeddings.
- Add a recurrent challenger only if hidden-state probes and paired evaluation
  justify the added complexity.

### 4.2 Structured action decoding

- Encode the observation backbone once per turn.
- Autoregressively decode farmer, active hands, then up to ten market tokens.
- Every component uses legality masks shared by teacher data, BC, PPO,
  evaluation, and submission inference.
- Market sequences use an explicit `STOP` token.
- Quantities use `1`, `2`, `4`, `8`, `16`, or operation-specific
  `MAX_FEASIBLE`; no undefined plan-dependent quantity token.
- Deterministic resolver converts tokens into exact environment actions.

### 4.3 Reward

Use terminal win/draw/loss as the objective plus potential-based shaping:

```text
r_t = terminal_result + beta * (gamma * Phi(s_{t+1}) - Phi(s_t))
Phi(s) = clip((NW_self - NW_opponent_public) / wealth_scale, -1, 1)
```

Own net worth includes conservative post-impact liquidation value rather than
`quantity * current_price`, preventing premature sales and self-crashing market
exploits. Final win rate remains the promotion metric; money margin is a
diagnostic only.

### 4.4 State and reproducibility

- Core policies accept explicit per-environment state.
- Submission wrappers reset state at step zero or when step moves backward.
- Parallel rollouts use one state instance per environment.
- Training bundles store weights, optimizer/scheduler, normalization, RNG
  states, seed cursor, schema versions, league manifest, configuration, git SHA,
  dependencies, and metrics.
- Save atomically every 30 minutes and at evaluation boundaries.

## 5. Curriculum

| Stage | Scope | Promotion evidence |
| --- | --- | --- |
| C0 | Contract and teacher smoke games | 100% completion and valid actions |
| C1 | BC basics on teacher trajectories | >=99.9% legal decoding, held-out action accuracy, beats `pass` |
| C2 | Full-economy BC | Full-season stability and useful win rate against controls |
| C3 | PPO bootstrap | No regression from BC; confident win over weak controls |
| C4 | Full league self-play | Pass incumbent and league regression gates |
| C5 | Relevant robustness only | Perturb only configurations observed or officially scored |

The teacher construction sequence and BC corpus gate are defined in the teacher
spec. Do not create a no-opponent curriculum; `pass` is the simplest opponent.

## 6. Evaluation and Promotion

- Use common seeds and both seat assignments.
- Start screening at 20 seed pairs / 40 games.
- Promotion begins at 50 pairs / 100 games and adds 25-pair blocks.
- Stop for success/futility only when the paired bootstrap interval is wholly
  above/below 0.50.
- Maximum incumbent comparison: 200 pairs / 400 games, sharded deterministically
  across sessions if necessary.
- Require zero crashes, invalid actions, timeouts, or cross-episode leakage.
- Require no opponent-specific drop greater than five percentage points and at
  least 35% win rate against every retained league member.
- Keep teacher, built-ins, last three promoted checkpoints, licensed public
  agents, and replay-derived pressure proxies in the league.
- Treat replay-derived proxies as archetypes, not exact opponent clones.

## 7. Repository Boundaries

```text
agents/                         immutable teacher/submission versions
src/kaggriculture_lib/         tested economy, tasking, encoding, policy logic
tests/                          unit, invariant, integration, packaging tests
notebooks/                     analysis and Kaggle platform/training notebooks
notebooks/kernels/             kernel metadata only; copied notebooks ignored
scripts/                       packaging, tournament, replay, push/status tools
docs/                          instructions, results, version ledger, next steps
docs/superpowers/specs/        authoritative and component designs
replays/                       raw JSON ignored; small summaries may be tracked
```

The executable agent/package is the source of truth. Notebooks orchestrate
analysis, remote verification, and training; they must not duplicate policy
logic. Raw data, replays, checkpoints, generated submissions, and credentials
remain outside git.

## 8. Weekly Milestones

| Week | Dates | Evidence checkpoint |
| --- | --- | --- |
| 1 | Aug 1–7 | Platform contract, economy alignment, ROI controls, task teacher foundation |
| 2 | Aug 8–14 | Multi-action teacher coverage, schema v1, trajectory dataset v1 |
| 3 | Aug 15–21 | Full-economy teacher, BC full-season checkpoint, replay diagnostics |
| 4 | Aug 22–28 | PPO bootstrap and verified Kaggle checkpoint/resume |
| 5 | Aug 29–Sep 4 | Full-season PPO and first frozen-opponent league |
| 6 | Sep 5–11 | Self-play, shaping/entropy ablations, regression analysis |
| 7 | Sep 12–18 | Evidence-selected recurrent or population challenger |
| 8 | Sep 19–25 | Robustness, packaging, champion selection, architecture freeze |
| 9 | Sep 26–30 | Final verification, authorized submission, monitoring, write-up |

Every weekly record includes champion/checkpoint, paired confidence intervals,
failures, GPU usage, decision, and one highest-value next experiment.

## 9. Operational Status Vocabulary

Use these states literally:

1. `local_verified`
2. `packaged`
3. `kernel_pushed`
4. `kernel_running`
5. `kernel_complete`
6. `submitted`
7. `scored`
8. `failed`

Creating files or attempting a push is not remote execution. A kernel push is
not a competition submission.

## 10. Current Status and Gates

- `roi_teacher_v3`: local deterministic fallback, packaged and tested.
- Platform smoke kernel: `kernel_complete`.
- `task_teacher_v1`: implemented and locally verified; see version ledger.
- `task_teacher_v2`: implemented, locally verified, and **legitimately
  promoted to competitive_champion** (2026-08-02) after fixing a confirmed
  hiring-wiring bug and completing the full evaluation protocol in §6:
  100-episode acceptance gate, 20-pair screen and 50-pair promotion gate
  vs. `task_teacher_v1` (paired bootstrap 95% CI `[0.930, 1.000]`, wholly
  above 0.50), plus regression screens vs. `roi_teacher_v3` and `starter`.
  An earlier "provisional champion" claim in this line was self-identified
  as premature (margin-based, incomplete evidence, and built on a bug where
  a correct library-level fix was never wired into the agent's call site);
  see version ledger and `2026-08-01-task-teacher-v2-design.md` §10 for the
  full account.
- BC dataset v1: blocked on teacher action/state coverage.
- PPO: blocked on BC and checkpoint/resume verification.
- Competition submission: blocked on explicit user authorization.

## 11. Open Items

- Confirm whether ladder evaluation uses the same mechanics as kernel runtime
  `1.29.3`; treat it as the best current evidence.
- Confirm submission-slot and ladder-tracking behavior after an authorized first
  submission.
- Confirm whether scored episode configuration varies from defaults.
- Measure policy and training throughput before fixing large evaluation budgets.
- Decide when to submit the deterministic fallback versus waiting for the task
  teacher or learned policy.

