"""Tests for agents/task_teacher_v19 -- wheat as a cash crop."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

BOARD_SIZE = 10
V19_CONFIG = {"episodeSteps": 720, "turnsPerDay": 24, "farmHandCostMult": 1}


def load_agent_module(name):
    spec = importlib.util.spec_from_file_location(
        f"agents_{name}_main", REPO_ROOT / "agents" / name / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_obs(*, day=0, hour=1, money=5000.0, farmer=(4, 4), tiles=None,
             shed=None, hands=None, hires_today=0, unlocked=None):
    tiles = tiles if tiles is not None else [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    return {
        "player": 0,
        "day": day,
        "hour": hour,
        "step": day * 24 + hour,
        "farms": [
            {
                "money": money,
                "tiles": tiles,
                "farmer": list(farmer),
                "hands": hands or [],
                "unlocked_quadrants": unlocked or ["NW"],
                "hires_today": hires_today,
            },
            {
                "money": money,
                "tiles": [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)],
                "farmer": [4, 4],
                "hands": [],
                "unlocked_quadrants": ["NW"],
                "hires_today": 0,
            },
        ],
        "market": {
            "inventory": {k: 10000 for k in
                          ("WHEAT", "CARROT", "MELON", "STRAWBERRY", "MILK", "WOOL", "EGG", "FERTILIZER")},
            "prices": {"WHEAT": 25, "CARROT": 35, "MELON": 250,
                       "STRAWBERRY": 120, "MILK": 160, "WOOL": 200,
                       "EGG": 50, "FERTILIZER": 100},
        },
        "town": {"unlocked_shops": []},
        "private": {
            "shed": shed or {},
            "seeds": {},
            "inventories": [{}],
        },
    }


def pasture_tile(animal="COW"):
    return {
        "kind": "PASTURE", "animal": animal, "placed_day": 0, "yield_units": 0,
        "fed_today": True, "consecutive_unfed": 0, "cared_today": True,
        "fertilizer_available": False, "pending_care_bonus": 0,
    }


def sell_orders(action, item):
    return [o for o in action["market"]
            if isinstance(o, (list, tuple)) and o and o[0] == "SELL" and o[1] == item]


def test_constants():
    module = load_agent_module("task_teacher_v19")
    assert module.WHEAT_TARGET_TILES == 20
    assert module.SELL_RESERVE_DAYS == 5


def test_sells_surplus_wheat_while_owning_animals():
    """The case v17 made unreachable: its wheat sell branch is gated on
    owning zero animals, and it always owns animals, so it sold $0 of wheat
    across 78 real ladder episodes."""
    module = load_agent_module("task_teacher_v19")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = pasture_tile("COW")  # 1 animal -> reserve = max(2, 1*5) = 5
    obs = make_obs(day=5, tiles=tiles, shed={"WHEAT": 30})
    action = module.agent(obs, V19_CONFIG)
    orders = sell_orders(action, "WHEAT")
    assert orders, "expected a wheat SELL order while owning animals"
    assert orders[0][2] == 25  # 30 held - 5 reserved


def test_never_sells_into_the_feed_reserve():
    """Animals escape after two consecutive unfed days; selling the buffer
    out from under them turns a revenue change into an animal-loss bug."""
    module = load_agent_module("task_teacher_v19")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = pasture_tile("COW")
    tiles[0][1] = pasture_tile("SHEEP")  # 2 animals -> reserve = max(2, 2*5) = 10
    obs = make_obs(day=5, tiles=tiles, shed={"WHEAT": 4})
    action = module.agent(obs, V19_CONFIG)
    assert sell_orders(action, "WHEAT") == []


def test_sell_reserve_exceeds_buy_target():
    """The sell reserve must strictly exceed the buy top-up target at every
    animal count, or the every-turn sell rule and the once-daily buy top-up
    collide on the same number again -- exactly the bug this fix closes.
    When both were `max(2, n*2)`, the sell rule trimmed inventory down to
    the same threshold the buy rule topped it back up to, so the agent sold
    its own wheat cheap and re-bought it at market every morning."""
    module = load_agent_module("task_teacher_v19")
    for n_animals in (1, 2, 5, 12):
        sell_reserve = max(2, n_animals * module.SELL_RESERVE_DAYS)
        buy_target = max(2, n_animals * 2)
        assert sell_reserve > buy_target, (
            f"sell_reserve ({sell_reserve}) must exceed buy_target "
            f"({buy_target}) for n_animals={n_animals}, or daily buy-back "
            "churn returns"
        )


def test_terminal_liquidation_still_sells_the_feed_reserve():
    """Unsold stock scores nothing, so the last-hours dump must ignore the
    reserve."""
    module = load_agent_module("task_teacher_v19")
    tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    tiles[0][0] = pasture_tile("COW")
    obs = make_obs(day=29, hour=22, tiles=tiles, shed={"WHEAT": 3})
    action = module.agent(obs, V19_CONFIG)
    orders = sell_orders(action, "WHEAT")
    assert orders and orders[0][2] == 3


def test_passes_wheat_target_to_generate_tasks():
    """Planting without selling only clogs the 100-item shed, and selling
    without planting has nothing to sell -- both halves must be wired."""
    module = load_agent_module("task_teacher_v19")
    obs = make_obs(day=0, money=5000.0)
    action = module.agent(obs, V19_CONFIG)
    assert action["farmer"], "agent returned no farmer action"
    # The planting rule is exercised end-to-end in the full-episode smoke
    # test (Task 5); here we assert the constant is actually consumed.
    src = (REPO_ROOT / "agents" / "task_teacher_v19" / "main.py").read_text()
    assert "wheat_target_tiles=WHEAT_TARGET_TILES" in src


def test_full_episode_sells_wheat_and_completes():
    """End-to-end: v19 must actually realise wheat revenue in a real
    episode, not merely be capable of emitting the order.

    Guards the coupling: the planting rule (shared library) and the sell
    rule (agent) are in different files, and either alone produces zero
    wheat revenue.
    """
    from kaggle_environments import make

    env = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "startingMoney": 3000, "farmHandCostMult": 1},
        debug=True,
    )
    env.run(["agents/task_teacher_v19/main.py", "starter"])

    final = env.steps[-1]
    assert all(s.status == "DONE" for s in final), [s.status for s in final]

    wheat_sold = 0
    wheat_bought = 0
    wheat_planted = 0
    for step in env.steps:
        action = step[0].action
        if not isinstance(action, dict):
            continue
        for order in action.get("market") or []:
            if not (isinstance(order, (list, tuple)) and len(order) > 2):
                continue
            if order[0] == "SELL" and order[1] == "WHEAT":
                wheat_sold += int(order[2])
            elif order[0] == "BUY_PRODUCT" and order[1] == "WHEAT":
                wheat_bought += int(order[2])
        farmer = action.get("farmer")
        if isinstance(farmer, list) and len(farmer) > 1 and farmer[0] == "PLANT" and farmer[1] == "WHEAT":
            wheat_planted += 1

    assert wheat_planted > 0, "v19 never planted wheat as a cash crop"
    assert wheat_sold > 0, "v19 never sold wheat -- the two halves are not wired together"
    print(f"v19 wheat planted={wheat_planted} sold={wheat_sold} bought={wheat_bought}")

    # Growing our own feed should reduce market purchases: the existing
    # BUY_PRODUCT top-up is gated on total_wheat < animals*2, so it stops
    # firing once the farm supplies itself. Same seed, same opponent.
    env17 = make(
        "kaggriculture",
        configuration={"episodeSteps": 720, "startingMoney": 3000, "farmHandCostMult": 1},
        debug=True,
    )
    env17.run(["agents/task_teacher_v17/main.py", "starter"])
    v17_bought = 0
    for step in env17.steps:
        action = step[0].action
        if not isinstance(action, dict):
            continue
        for order in action.get("market") or []:
            if (isinstance(order, (list, tuple)) and len(order) > 2
                    and order[0] == "BUY_PRODUCT" and order[1] == "WHEAT"):
                v17_bought += int(order[2])
    print(f"v17 wheat bought={v17_bought}")
    assert wheat_bought <= v17_bought, (
        f"v19 bought more feed wheat ({wheat_bought}) than v17 ({v17_bought}) "
        "despite growing its own"
    )
