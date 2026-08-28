"""Tests for agents/task_teacher_v20 -- fertilizer collection."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

BOARD_SIZE = 10
V20_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "farmHandCostMult": 1}


def load_agent_module(name):
    spec = importlib.util.spec_from_file_location(
        f"agents_{name}_main", REPO_ROOT / "agents" / name / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_enables_fertilizer_collection():
    """Planting the rule in the library does nothing unless the agent turns
    it on -- the parameter defaults to False."""
    src = (REPO_ROOT / "agents" / "task_teacher_v20" / "main.py").read_text()
    assert "collect_fertilizer=True" in src


def test_agent_dispatches_the_collect_action():
    """A generated task is inert unless the agent can turn it into the
    simulator action string."""
    src = (REPO_ROOT / "agents" / "task_teacher_v20" / "main.py").read_text()
    assert 'return ["COLLECT_FERTILIZER"]' in src


def test_full_episode_collects_and_sells_fertilizer():
    """End-to-end proof. v17 already sells FERTILIZER (main.py:206), so
    collection alone should produce sale revenue.

    If this fails with zero fertilizer, the ECONOMIC pricing and
    value-competition risk recorded in the design (Sec 5.3) has materialised
    -- units are labour-saturated and the task never gets assigned. Report
    that as a finding; do NOT raise the tier to force a pass.
    """
    from kaggle_environments import make

    env = make(
        "kaggriculture",
        configuration={
            "episodeSteps": 720, "startingMoney": 3000, "farmHandCostMult": 1,
            "seed": 140000,
        },
        debug=True,
    )
    env.run(["agents/task_teacher_v20/main.py", "starter"])

    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final), [s.status for s in final]

    collected = 0
    sold = 0
    for step in env.steps:
        action = step[0].action
        if not isinstance(action, dict):
            continue
        units = [action.get("farmer")] + list(action.get("hands") or [])
        for act in units:
            if isinstance(act, list) and act and act[0] == "COLLECT_FERTILIZER":
                collected += 1
        for order in action.get("market") or []:
            if (isinstance(order, (list, tuple)) and len(order) > 2
                    and order[0] == "SELL" and order[1] == "FERTILIZER"):
                sold += int(order[2])

    print(f"v20 fertilizer collected={collected} sold={sold}")
    assert collected > 0, (
        "v20 never collected fertilizer -- ECONOMIC tier saturated by higher-value tasks"
    )
    assert sold > 0, "v20 collected fertilizer but never sold any"


def test_collection_does_not_displace_higher_priority_work():
    """Fertilizer collection no longer guarantees non-displacement -- this
    paired measurement is the guard that replaces the removed OPTIONAL tier.

    Fertilizer is emitted at `PriorityTier.ECONOMIC`, the same tier as
    `PLANT`. Tier ordering means it still cannot preempt `WATER`/`FEED`/
    `CARE` (tiers `DAILY_CARE`/`EMERGENCY`) or `HARVEST`
    (`DECAYING_YIELD`) -- those all outrank `ECONOMIC` regardless. What it
    does compete with, at the same tier, is new-tile `PLANT`: taking a
    unit-turn for fertilizer instead of a `PLANT` is design doc Sec 5.3's
    accepted trade-off. Since `ECONOMIC` no longer guarantees blanket
    non-displacement the way `OPTIONAL` did, this paired FEED/WATER
    measurement against v17 is what actually stands guard.

    task_teacher_v19 sold wheat successfully and still lost 0/20 pairs,
    because the new work displaced Melon. Selling fertilizer is worthless if
    it costs us waterings (crops die) or feedings (animals escape). Same
    seed and opponent for both agents, so the comparison is paired.
    """
    from kaggle_environments import make

    def run(agent_path):
        env = make(
            "kaggriculture",
            configuration={
                "episodeSteps": 720, "startingMoney": 3000,
                "farmHandCostMult": 1, "seed": 140000,
            },
            debug=True,
        )
        env.run([agent_path, "starter"])
        counts = {"WATER": 0, "FEED": 0, "HARVEST": 0, "PLANT": 0}
        for step in env.steps:
            action = step[0].action
            if not isinstance(action, dict):
                continue
            for act in [action.get("farmer")] + list(action.get("hands") or []):
                if isinstance(act, list) and act and act[0] in counts:
                    counts[act[0]] += 1
        return counts, env.steps[-1][0].reward

    v20_counts, v20_reward = run("agents/task_teacher_v20/main.py")
    v17_counts, v17_reward = run("agents/task_teacher_v17/main.py")
    print(f"v20 {v20_counts} reward={v20_reward}")
    print(f"v17 {v17_counts} reward={v17_reward}")

    # Feeding is life-or-death: animals escape after two unfed days.
    assert v20_counts["FEED"] >= v17_counts["FEED"], (
        f"v20 fed less than v17 ({v20_counts['FEED']} vs {v17_counts['FEED']}) "
        "-- fertilizer collection is displacing feeding"
    )
    # Watering keeps crops alive; allow a small margin for routing noise.
    assert v20_counts["WATER"] >= v17_counts["WATER"] * 0.95, (
        f"v20 watered materially less than v17 "
        f"({v20_counts['WATER']} vs {v17_counts['WATER']}) "
        "-- fertilizer collection is displacing watering"
    )
