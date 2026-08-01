#!/usr/bin/env python3
"""Local batch tournament runner for Kaggriculture agents.

Runs an agent (by file path, e.g. `agents/roi_teacher_v1/main.py`) against
one or more opponents (built-in names `pass`/`random`/`starter`, or another
agent file path) across paired seat assignments and seeds, and reports win
rate / final-money margin. This is the "local tournament gate" every
`docs/0_coding_standards.md` §5 submission-discipline check runs before a
candidate is submitted, and the harness the design doc's weekly checkpoints
compare against.

Usage:
    PYTHONPATH=src python scripts/run_tournament.py \\
        agents/roi_teacher_v1/main.py pass random starter \\
        --episodes 10 --episode-steps 720

Each seed is played with both seat assignments (agent as player 0 and as
player 1) — one seed pair counts as two games, matching the design doc §9's
paired-seat/seed evaluation protocol.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from kaggle_environments import make  # noqa: E402


class GameFailure(RuntimeError):
    """Raised when a played episode did not complete cleanly.

    A broken candidate (crashes, times out, produces an invalid final
    state) must fail the gate loudly here, not silently corrupt downstream
    win-rate/margin arithmetic with a None or non-finite reward.
    """


def final_rewards(env) -> tuple[float, float]:
    """Validated (player_0_reward, player_1_reward) from a finished env."""
    final = env.steps[-1]
    rewards = []
    for i, s in enumerate(final):
        if s.status != "DONE":
            raise GameFailure(f"player {i} finished with status={s.status!r}, not DONE")
        reward = s.reward
        if reward is None or not math.isfinite(reward):
            raise GameFailure(f"player {i} reward is invalid: {reward!r}")
        rewards.append(float(reward))
    return rewards[0], rewards[1]


def pairwise_score(a: float, b: float) -> float:
    """1.0 if a beat b, 0.5 if tied, 0.0 if a lost."""
    if a > b:
        return 1.0
    if a == b:
        return 0.5
    return 0.0


def run_pair(agent_ref: str, opponent_ref: str, episode_steps: int, seed: int) -> tuple[float, float, float]:
    """Play one seed with both seat assignments.

    Returns `(agent_score, mean_money_margin, wall_time_seconds)`:
    `agent_score` is the paired win-rate contribution (1.0 win / 0.5 draw /
    0.0 loss per seat, averaged over both seats — so a fully-swept pair
    scores 1.0, a fully-lost pair scores 0.0); `mean_money_margin` is the
    agent's mean final money minus the opponent's, averaged over both seats.
    """
    t0 = time.time()

    env_a = make("kaggriculture", configuration={"episodeSteps": episode_steps, "seed": seed}, debug=False)
    env_a.run([agent_ref, opponent_ref])
    agent_money_a, opp_money_a = final_rewards(env_a)

    env_b = make("kaggriculture", configuration={"episodeSteps": episode_steps, "seed": seed}, debug=False)
    env_b.run([opponent_ref, agent_ref])
    opp_money_b, agent_money_b = final_rewards(env_b)

    dt = time.time() - t0
    agent_score = 0.5 * (
        pairwise_score(agent_money_a, opp_money_a) + pairwise_score(agent_money_b, opp_money_b)
    )
    mean_margin = (agent_money_a + agent_money_b) / 2 - (opp_money_a + opp_money_b) / 2
    return agent_score, mean_margin, dt


def bootstrap_ci(
    pair_scores: list[float], n_resamples: int = 10000, ci: float = 0.95, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of paired seed/seat scores.

    Per the authoritative design doc §6: promotion/rejection is decided by
    whether this interval is wholly above/below 0.50, not by a point
    estimate alone. Resamples whole pairs (each already averages both seat
    assignments of one seed), not individual games, to respect the paired
    design.
    """
    n = len(pair_scores)
    rng = random.Random(seed)
    means = []
    for _ in range(n_resamples):
        resample = [pair_scores[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    lower_tail = (1.0 - ci) / 2
    lo_idx = int(lower_tail * n_resamples)
    hi_idx = int((1.0 - lower_tail) * n_resamples) - 1
    return means[lo_idx], means[max(lo_idx, hi_idx)]


def tournament(agent_ref: str, opponent_ref: str, episodes: int, episode_steps: int, base_seed: int) -> None:
    total_margin = 0.0
    total_wall = 0.0
    pair_scores = []
    for i in range(episodes):
        seed = base_seed + i
        score, margin, wall = run_pair(agent_ref, opponent_ref, episode_steps, seed)
        pair_scores.append(score)
        total_margin += margin
        total_wall += wall
    n_games = episodes * 2
    win_rate = sum(pair_scores) / episodes
    mean_margin = total_margin / episodes
    steps_per_sec = (n_games * episode_steps) / total_wall if total_wall > 0 else float("nan")
    ci_msg = ""
    if episodes >= 2:
        lo, hi = bootstrap_ci(pair_scores)
        ci_msg = f", bootstrap_95%_ci=[{lo:.3f}, {hi:.3f}]"
    print(
        f"{agent_ref!r} vs {opponent_ref!r}: "
        f"win_rate={win_rate:.3f} ({episodes} seed pairs / {n_games} games), "
        f"mean_money_margin={mean_margin:+.1f}{ci_msg}, "
        f"wall_time={total_wall:.1f}s ({steps_per_sec:.0f} steps/sec)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent", help="Agent under test: file path or built-in name")
    parser.add_argument("opponents", nargs="+", help="One or more opponents: file paths or built-in names")
    parser.add_argument("--episodes", type=int, default=10, help="Seed pairs per opponent (default 10)")
    parser.add_argument("--episode-steps", type=int, default=720, help="Turns per episode (default 720)")
    parser.add_argument("--seed", type=int, default=0, help="Base seed; seed pair i uses base_seed+i")
    args = parser.parse_args()

    for opponent in args.opponents:
        tournament(args.agent, opponent, args.episodes, args.episode_steps, args.seed)


if __name__ == "__main__":
    main()
