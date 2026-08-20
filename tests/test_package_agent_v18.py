"""Standalone packaging characterization for task_teacher_v18."""

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "package_agent", REPO_ROOT / "scripts" / "package_agent.py"
)
package_agent = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(package_agent)


def _assert_both_players_finish_standalone(out_path: Path) -> None:
    """Run the generated artifact directly and inspect both final statuses."""
    script = f"""
from kaggle_environments import make
env = make("kaggriculture", configuration={{"episodeSteps": 96}}, debug=True)
env.run([{str(out_path)!r}, "starter"])
print("FINAL_STATUSES=" + ",".join(state.status for state in env.steps[-1]))
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tempfile.gettempdir(),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    status_line = next(
        (line for line in result.stdout.splitlines() if line.startswith("FINAL_STATUSES=")),
        None,
    )
    assert status_line is not None, result.stdout
    assert status_line.removeprefix("FINAL_STATUSES=").split(",") == ["DONE", "DONE"]


def test_packaged_task_teacher_v18_runs_standalone_without_pythonpath(tmp_path):
    """v18 packages its adaptive strategy dependency and runs without repo imports."""
    out_path = tmp_path / "task_teacher_v18" / "main.py"

    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v18", out_path)

    generated = out_path.read_text()
    assert "kaggriculture_lib.adaptive_strategy" in generated
    _assert_both_players_finish_standalone(out_path)
    package_agent.verify(out_path, opponent="starter", episode_steps=96)
