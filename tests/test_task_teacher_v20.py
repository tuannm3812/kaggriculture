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
