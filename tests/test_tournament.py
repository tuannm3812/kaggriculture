"""Tests for scripts/run_tournament.py.

Added per Codex's 2026-08-01 code review: the harness that gates every
submission decision had no tests of its own — a bug here (e.g. scoring a
draw as a win, or silently swallowing a crashed agent) could corrupt every
downstream comparison without ever showing up as a visible crash.
"""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("run_tournament", REPO_ROOT / "scripts" / "run_tournament.py")
run_tournament = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_tournament)


def fake_env(rewards, statuses=("DONE", "DONE")):
    state = [SimpleNamespace(reward=r, status=s) for r, s in zip(rewards, statuses)]
    return SimpleNamespace(steps=[state])


@pytest.mark.parametrize(
    "a, b, expected",
    [(100.0, 50.0, 1.0), (50.0, 100.0, 0.0), (75.0, 75.0, 0.5)],
)
def test_pairwise_score(a, b, expected):
    assert run_tournament.pairwise_score(a, b) == expected


def test_final_rewards_extracts_both_players():
    env = fake_env([3200.0, 2800.0])
    assert run_tournament.final_rewards(env) == (3200.0, 2800.0)


@pytest.mark.parametrize("statuses", [("DONE", "ACTIVE"), ("INVALID", "DONE"), ("ERROR", "ERROR")])
def test_final_rewards_raises_on_non_done_status(statuses):
    env = fake_env([3200.0, 2800.0], statuses=statuses)
    with pytest.raises(run_tournament.GameFailure):
        run_tournament.final_rewards(env)


@pytest.mark.parametrize("bad_reward", [None, float("nan"), float("inf")])
def test_final_rewards_raises_on_invalid_reward(bad_reward):
    env = fake_env([bad_reward, 2800.0])
    with pytest.raises(run_tournament.GameFailure):
        run_tournament.final_rewards(env)


# --- integration tests against the real environment ----------------------

def test_run_pair_pass_vs_pass_is_a_draw_with_zero_margin():
    score, margin, _ = run_tournament.run_pair("pass", "pass", episode_steps=48, seed=1)
    assert score == 0.5
    assert margin == 0.0


EPISODE_STEPS = 240  # >= ~6 in-game days: enough for starter's wheat loop to
# turn a profit over "pass". At very short episodes (e.g. 96 steps / 4 days)
# starter can legitimately still be behind "pass" -- confirmed by hand: it's
# the same season-horizon issue Codex's review flagged for roi_teacher_v1/v2,
# just showing up in the *official* starter baseline instead. Not this
# harness's bug; just needs a long-enough episode for the assumption to hold.


def test_run_pair_starter_beats_pass():
    score, margin, _ = run_tournament.run_pair("starter", "pass", episode_steps=EPISODE_STEPS, seed=1)
    assert score == 1.0
    assert margin > 0


def test_run_pair_is_seed_deterministic():
    # Deliberately not "random": kaggriculture.py's built-in random_agent
    # creates `random.Random()` fresh and unseeded on every call, so it is
    # NOT reproducible via the env's `seed` config -- confirmed by hand
    # (two runs of "starter" vs "random" at the same seed gave different
    # margins). Use two deterministic built-ins instead.
    result_1 = run_tournament.run_pair("starter", "pass", episode_steps=EPISODE_STEPS, seed=7)
    result_2 = run_tournament.run_pair("starter", "pass", episode_steps=EPISODE_STEPS, seed=7)
    assert result_1[0] == result_2[0]
    assert result_1[1] == result_2[1]


def test_run_pair_is_seat_symmetric_in_scoring():
    """Swapping which function plays agent-vs-opponent shouldn't change the
    *reported* pairwise score convention: run_pair always reports the score
    from the perspective of its first argument."""
    forward_score, forward_margin, _ = run_tournament.run_pair("starter", "pass", episode_steps=EPISODE_STEPS, seed=3)
    reverse_score, reverse_margin, _ = run_tournament.run_pair("pass", "starter", episode_steps=EPISODE_STEPS, seed=3)
    assert forward_score == 1.0
    assert reverse_score == 0.0
    assert math.isclose(forward_margin, -reverse_margin)


# --- bounded-mean confidence interval for paired scores -------------------
# Per the authoritative design doc §6: "Stop for success/futility only when
# the paired bootstrap interval is wholly above/below 0.50" -- this is
# permanent evaluation infrastructure every promotion decision needs, not a
# one-off for task_teacher_v2.
#
# An earlier version of this used a percentile bootstrap, which Codex's
# 2026-08-02 follow-up review (§12.2) correctly flagged: resampling only the
# observed pair scores means an all-identical sample (e.g. every pair a win)
# produces a zero-width interval regardless of sample size -- that describes
# resampling variation of the empirical sample, not uncertainty about the
# true population win rate, and a handful of pairs cannot establish a true
# rate of exactly 1.0. `hoeffding_ci` replaces it with a Hoeffding
# concentration bound for a bounded-in-[0,1] mean, which stays nonzero even
# on degenerate all-win/all-loss samples, and Bonferroni-corrects alpha
# across a fixed number of pre-registered sequential looks (matching the
# authoritative protocol's checkpoints: 20/50/75/.../200 pairs) so a chain
# of looks stays simultaneously valid at the stated confidence level.


def test_hoeffding_ci_four_all_win_pairs_lower_bound_strictly_below_one():
    lo, hi = run_tournament.hoeffding_ci([1.0, 1.0, 1.0, 1.0])
    assert lo < 1.0


def test_hoeffding_ci_twenty_all_win_pairs_lower_bound_strictly_below_one():
    lo, hi = run_tournament.hoeffding_ci([1.0] * 20)
    assert lo < 1.0


def test_hoeffding_ci_all_loss_upper_bound_strictly_above_zero():
    lo, hi = run_tournament.hoeffding_ci([0.0, 0.0, 0.0])
    assert hi > 0.0


def test_hoeffding_ci_brackets_the_sample_mean():
    scores = [1.0, 0.0, 1.0, 1.0, 0.5, 1.0, 0.0, 1.0, 1.0, 1.0]
    lo, hi = run_tournament.hoeffding_ci(scores)
    mean = sum(scores) / len(scores)
    assert lo <= mean <= hi


def test_hoeffding_ci_width_decreases_with_sample_size():
    """A 90%-win-rate sample repeated 10x (100 pairs) should give a tighter
    interval than the original 10 pairs -- more evidence at the same
    empirical rate should narrow the interval, not just recenter it."""
    small = [1.0] * 9 + [0.0]
    large = small * 10
    lo_small, hi_small = run_tournament.hoeffding_ci(small)
    lo_large, hi_large = run_tournament.hoeffding_ci(large)
    assert (hi_large - lo_large) < (hi_small - lo_small)


def test_hoeffding_ci_is_deterministic_given_the_same_inputs():
    """The alpha allocation across sequential looks is a fixed, documented
    split (Bonferroni over `max_looks`), not randomized -- same inputs must
    always give the same interval."""
    scores = [1.0, 0.0, 1.0, 0.5, 1.0, 0.0, 1.0, 1.0]
    assert run_tournament.hoeffding_ci(scores) == run_tournament.hoeffding_ci(scores)


def test_hoeffding_ci_rejects_empty_input():
    with pytest.raises(ValueError):
        run_tournament.hoeffding_ci([])


@pytest.mark.parametrize("bad_confidence", [0.0, 1.0, -0.1, 1.5])
def test_hoeffding_ci_rejects_invalid_confidence(bad_confidence):
    with pytest.raises(ValueError):
        run_tournament.hoeffding_ci([1.0, 0.5], confidence=bad_confidence)


@pytest.mark.parametrize("bad_max_looks", [0, -1])
def test_hoeffding_ci_rejects_invalid_max_looks(bad_max_looks):
    with pytest.raises(ValueError):
        run_tournament.hoeffding_ci([1.0, 0.5], max_looks=bad_max_looks)
