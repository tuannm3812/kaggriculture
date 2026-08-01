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
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from kaggle_environments import make  # noqa: E402


def run_pair(agent_ref: str, opponent_ref: str, episode_steps: int, seed: int) -> tuple[float, float, float]:
    """Play one seed with both seat assignments. Returns (agent_score, opponent_score, wall_time)."""
    t0 = time.time()

    env_a = make("kaggriculture", configuration={"episodeSteps": episode_steps, "seed": seed}, debug=False)
    env_a.run([agent_ref, opponent_ref])
    final_a = env_a.steps[-1]
    agent_money_a, opp_money_a = final_a[0].reward, final_a[1].reward

    env_b = make("kaggriculture", configuration={"episodeSteps": episode_steps, "seed": seed}, debug=False)
    env_b.run([opponent_ref, agent_ref])
    final_b = env_b.steps[-1]
    opp_money_b, agent_money_b = final_b[0].reward, final_b[1].reward

    dt = time.time() - t0
    agent_score = 0.5 * ((1 if agent_money_a > opp_money_a else 0.5 if agent_money_a == opp_money_a else 0)
                          + (1 if agent_money_b > opp_money_b else 0.5 if agent_money_b == opp_money_b else 0))
    return agent_score, (agent_money_a + agent_money_b) / 2 - (opp_money_a + opp_money_b) / 2, dt


def tournament(agent_ref: str, opponent_ref: str, episodes: int, episode_steps: int, base_seed: int) -> None:
    total_score = 0.0
    total_margin = 0.0
    total_wall = 0.0
    for i in range(episodes):
        seed = base_seed + i
        score, margin, wall = run_pair(agent_ref, opponent_ref, episode_steps, seed)
        total_score += score
        total_margin += margin
        total_wall += wall
    n_games = episodes * 2
    win_rate = total_score / episodes
    mean_margin = total_margin / episodes
    steps_per_sec = (n_games * episode_steps) / total_wall if total_wall > 0 else float("nan")
    print(
        f"{agent_ref!r} vs {opponent_ref!r}: "
        f"win_rate={win_rate:.3f} ({episodes} seed pairs / {n_games} games), "
        f"mean_money_margin={mean_margin:+.1f}, "
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
