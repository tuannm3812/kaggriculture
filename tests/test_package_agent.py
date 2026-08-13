"""Tests for scripts/package_agent.py.

Per Codex's review of the task_teacher_v1 design: packaging must register
real modules in sys.modules (not bare namespace-object aliases), so
dataclass __module__ introspection works correctly and a shared module's
own `from kaggriculture_lib import X` import line can stay completely
unmodified as more shared modules are added — no per-module import-line
stripping needed, and no hardcoded module list to update by hand.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location("package_agent", REPO_ROOT / "scripts" / "package_agent.py")
package_agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_agent)


@pytest.fixture(autouse=True)
def _isolate_sys_modules():
    """Packaged code registers real modules into sys.modules by design (the
    whole point of this packaging approach) -- but that means exec()'ing a
    packaged artifact in-process has global side effects. Snapshot and
    restore sys.modules around every test here so a stub/fake
    "kaggriculture_lib" registered by one test can't leak into a later
    test that imports the real package (e.g. tests/test_task_teacher_v1.py)."""
    before = dict(sys.modules)
    yield
    for name in list(sys.modules):
        if name not in before:
            del sys.modules[name]
    sys.modules.update(before)


@pytest.fixture
def stub_lib_dir(tmp_path, monkeypatch):
    """A fake src/kaggriculture_lib/ with two modules: `economy` (no
    internal deps) and `tasking` (imports `economy`) -- mirrors the real
    dependency shape so discovery/ordering is tested against something
    representative, not just a single trivial module."""
    lib_dir = tmp_path / "src" / "kaggriculture_lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "economy.py").write_text(
        '"""Stub economy module."""\n\nSEED_COST = {"WHEAT": 10}\n'
    )
    (lib_dir / "tasking.py").write_text(
        '"""Stub tasking module."""\n\nfrom __future__ import annotations\n\n'
        "from dataclasses import dataclass\n\n"
        "from kaggriculture_lib import economy\n\n\n"
        "@dataclass(frozen=True)\n"
        "class StubTask:\n"
        "    item: str\n\n\n"
        "WHEAT_TASK = StubTask(item=economy.SEED_COST['WHEAT'])\n"
    )
    monkeypatch.setattr(package_agent, "LIB_DIR", lib_dir)
    return lib_dir


@pytest.fixture
def stub_agent_dir(tmp_path, stub_lib_dir):
    agent_dir = tmp_path / "stub_agent"
    agent_dir.mkdir()
    (agent_dir / "main.py").write_text(
        '"""Stub agent for packaging tests."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "from kaggriculture_lib import economy\n"
        "from kaggriculture_lib.tasking import StubTask, WHEAT_TASK\n"
        "\n"
        "\n"
        "def agent(obs):\n"
        "    return {\n"
        '        "farmer": ["PASS"],\n'
        '        "hands": [],\n'
        '        "market": [],\n'
        "    }\n"
        "\n"
        "\n"
        "WHEAT_SEED_COST = economy.SEED_COST['WHEAT']\n"
        "ANOTHER_TASK = StubTask(item='CARROT')\n"
    )
    return agent_dir


def test_package_preserves_agent_import_lines_unmodified(stub_agent_dir, tmp_path):
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    generated = out_path.read_text()
    assert "from kaggriculture_lib import economy" in generated
    assert "from kaggriculture_lib.tasking import StubTask, WHEAT_TASK" in generated


def test_package_hoists_agent_future_import_to_top(stub_agent_dir, tmp_path):
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    generated = out_path.read_text()
    # Must compile at all -- a from __future__ import that isn't the first
    # statement is a SyntaxError, which is exactly the bug this guards.
    compile(generated, str(out_path), "exec")
    assert generated.index("from __future__ import annotations") < generated.index("import sys")


def test_package_registers_modules_in_dependency_order(stub_agent_dir, tmp_path):
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    generated = out_path.read_text()
    # economy has no internal deps and must be registered before tasking,
    # which imports it.
    assert generated.index("'kaggriculture_lib.economy'") < generated.index("'kaggriculture_lib.tasking'")


def test_package_only_bundles_modules_the_agent_transitively_imports(stub_lib_dir, tmp_path):
    """Regression test for the 2026-08-06 production incident: `main.py`
    unconditionally bundled every module under `src/kaggriculture_lib/`,
    not just what the agent actually imports. That was harmless while the
    directory only held `economy`/`tasking`, but once an unrelated module
    with an import-time side effect (`replay_compat.py`'s hard version
    guard) was added to the same directory, every already-packaged agent
    silently started bundling it too -- and it crashed the live Kaggle
    submission on import, before the agent ever took a turn, because
    Kaggle's runtime wasn't the exact pinned version that guard demands.
    Packaging must only bundle the transitive closure of what the agent's
    own `main.py` references, never "everything in the directory"."""
    (stub_lib_dir / "unrelated_with_side_effect.py").write_text(
        '"""Stub module the agent never imports, with an import-time crash '
        'standing in for replay_compat.py\'s real version guard."""\n\n'
        "raise RuntimeError('must never be imported by an agent that does not need it')\n"
    )

    agent_dir = tmp_path / "stub_agent"
    agent_dir.mkdir()
    (agent_dir / "main.py").write_text(
        '"""Stub agent that only needs economy, not tasking or the unrelated module."""\n'
        "\n"
        "from __future__ import annotations\n"
        "\n"
        "from kaggriculture_lib import economy\n"
        "\n"
        "\n"
        "def agent(obs):\n"
        "    return {\n"
        '        "farmer": ["PASS"],\n'
        '        "hands": [],\n'
        '        "market": [],\n'
        "    }\n"
        "\n"
        "\n"
        "WHEAT_SEED_COST = economy.SEED_COST['WHEAT']\n"
    )

    out_path = tmp_path / "out" / "main.py"
    package_agent.package(agent_dir, out_path)
    generated = out_path.read_text()

    assert "'kaggriculture_lib.economy'" in generated
    assert "unrelated_with_side_effect" not in generated
    assert "'kaggriculture_lib.tasking'" not in generated

    namespace: dict = {}
    exec(compile(generated, str(out_path), "exec"), namespace)  # must not raise
    assert namespace["WHEAT_SEED_COST"] == 10


def test_package_output_runs_and_resolves_unmodified_imports(stub_agent_dir, tmp_path):
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    namespace: dict = {}
    exec(compile(out_path.read_text(), str(out_path), "exec"), namespace)
    assert namespace["WHEAT_SEED_COST"] == 10
    assert callable(namespace["agent"])


def test_package_dataclass_module_attribute_resolves_via_sys_modules(stub_agent_dir, tmp_path):
    """The concrete concern Codex raised: a dataclass's __module__ must
    point to a real, registered sys.modules entry, not a bare alias."""
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    namespace: dict = {}
    exec(compile(out_path.read_text(), str(out_path), "exec"), namespace)
    task = namespace["ANOTHER_TASK"]
    assert task.__class__.__module__ == "kaggriculture_lib.tasking"
    # The module registered under that name is importable and is the same
    # module object the class was actually defined in.
    assert sys.modules["kaggriculture_lib.tasking"].StubTask is task.__class__


def test_package_output_is_deterministic(stub_agent_dir, tmp_path):
    out_a = tmp_path / "a" / "main.py"
    out_b = tmp_path / "b" / "main.py"
    package_agent.package(stub_agent_dir, out_a)
    package_agent.package(stub_agent_dir, out_b)
    assert out_a.read_text() == out_b.read_text()


def test_package_raises_on_circular_shared_module_dependency(tmp_path, monkeypatch):
    lib_dir = tmp_path / "src" / "kaggriculture_lib"
    lib_dir.mkdir(parents=True)
    (lib_dir / "a.py").write_text("from kaggriculture_lib import b\n")
    (lib_dir / "b.py").write_text("from kaggriculture_lib import a\n")
    monkeypatch.setattr(package_agent, "LIB_DIR", lib_dir)

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "main.py").write_text("def agent(obs):\n    return {'farmer': ['PASS'], 'hands': [], 'market': []}\n")

    with pytest.raises(SystemExit):
        package_agent.package(agent_dir, tmp_path / "out" / "main.py")


def test_packaged_roi_teacher_v3_runs_standalone_without_pythonpath():
    """Full-season smoke test against the real repo's shared modules (not
    the stub fixture above): package the real v3 agent and run it in a
    subprocess with PYTHONPATH stripped — the actual condition Kaggle's
    execution environment imposes, not just an in-process import check."""
    out_path = REPO_ROOT / "build" / "roi_teacher_v3" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "roi_teacher_v3", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def test_packaged_task_teacher_v1_runs_standalone_without_pythonpath():
    """Same check for task_teacher_v1, which uses both shared modules
    (economy and tasking), not just economy."""
    out_path = REPO_ROOT / "build" / "task_teacher_v1" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v1", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def test_packaged_task_teacher_v3_runs_standalone_without_pythonpath():
    """Same check for task_teacher_v3, which adds ongoing-crop dispatch to
    the same shared modules task_teacher_v1/v2 already package correctly."""
    out_path = REPO_ROOT / "build" / "task_teacher_v3" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v3", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def test_packaged_task_teacher_v4_runs_standalone_without_pythonpath():
    out_path = REPO_ROOT / "build" / "task_teacher_v4" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v4", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def test_packaged_task_teacher_v5_runs_standalone_without_pythonpath():
    out_path = REPO_ROOT / "build" / "task_teacher_v5" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v5", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def test_packaged_task_teacher_v6_runs_standalone_without_pythonpath():
    out_path = REPO_ROOT / "build" / "task_teacher_v6" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v6", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def test_packaged_task_teacher_v7_runs_standalone_without_pythonpath():
    out_path = REPO_ROOT / "build" / "task_teacher_v7" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v7", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def test_packaged_task_teacher_v8_runs_standalone_without_pythonpath():
    out_path = REPO_ROOT / "build" / "task_teacher_v8" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v8", out_path)
    _assert_runs_standalone(out_path, episode_steps=96)


def _assert_runs_standalone(out_path: Path, episode_steps: int) -> None:
    script = f"""
from kaggle_environments import make
env = make("kaggriculture", configuration={{"episodeSteps": {episode_steps}}}, debug=True)
env.run([{str(out_path)!r}, "starter"])
final = env.steps[-1]
assert all(s.status == "DONE" for s in final), [s.status for s in final]
print("OK")
"""
    import os

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=str(REPO_ROOT), env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
