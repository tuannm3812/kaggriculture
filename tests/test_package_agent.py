"""Tests for scripts/package_agent.py.

Added per Codex's 2026-08-01 code review: packaging correctness (import
removal, future-import hoisting, deterministic output, standalone import,
full-season smoke execution) previously had no automated coverage at all —
only manual verification during development.
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


@pytest.fixture
def stub_agent_dir(tmp_path):
    agent_dir = tmp_path / "stub_agent"
    agent_dir.mkdir()
    (agent_dir / "main.py").write_text(
        '"""Stub agent for packaging tests."""\n'
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
        "WHEAT_SEED_COST = economy.CROPS['WHEAT']['seed']\n"
    )
    return agent_dir


def test_package_removes_the_local_dev_import_line(stub_agent_dir, tmp_path):
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    generated = out_path.read_text()
    assert "from kaggriculture_lib import economy" not in generated


def test_package_hoists_future_import_to_top(stub_agent_dir, tmp_path):
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    generated = out_path.read_text()
    # Must compile at all — a from __future__ import that isn't the first
    # statement is a SyntaxError, which is exactly the bug this guards.
    compile(generated, str(out_path), "exec")
    future_line_idx = generated.index("from __future__ import annotations")
    types_import_idx = generated.index("import types as _types")
    assert future_line_idx < types_import_idx


def test_package_inlines_economy_source_so_module_is_usable(stub_agent_dir, tmp_path):
    out_path = tmp_path / "out" / "main.py"
    package_agent.package(stub_agent_dir, out_path)
    namespace: dict = {}
    exec(compile(out_path.read_text(), str(out_path), "exec"), namespace)
    assert namespace["WHEAT_SEED_COST"] == namespace["economy"].CROPS["WHEAT"]["seed"]
    assert callable(namespace["agent"])


def test_package_output_is_deterministic(stub_agent_dir, tmp_path):
    out_a = tmp_path / "a" / "main.py"
    out_b = tmp_path / "b" / "main.py"
    package_agent.package(stub_agent_dir, out_a)
    package_agent.package(stub_agent_dir, out_b)
    assert out_a.read_text() == out_b.read_text()


def test_package_rejects_agent_missing_expected_import_line(tmp_path):
    agent_dir = tmp_path / "no_import_agent"
    agent_dir.mkdir()
    (agent_dir / "main.py").write_text("def agent(obs):\n    return {'farmer': ['PASS'], 'hands': [], 'market': []}\n")
    with pytest.raises(SystemExit):
        package_agent.package(agent_dir, tmp_path / "out" / "main.py")


def test_packaged_roi_teacher_v3_runs_standalone_without_pythonpath():
    """Full-season smoke test: package the real v3 agent and run it in a
    subprocess with PYTHONPATH stripped — the actual condition Kaggle's
    execution environment imposes, not just an in-process import check."""
    out_path = REPO_ROOT / "build" / "roi_teacher_v3" / "main.py"
    package_agent.package(REPO_ROOT / "agents" / "roi_teacher_v3", out_path)

    script = f"""
from kaggle_environments import make
env = make("kaggriculture", configuration={{"episodeSteps": 96}}, debug=True)
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
