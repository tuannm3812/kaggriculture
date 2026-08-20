"""Standalone packaging characterization for task_teacher_v18."""

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

spec = importlib.util.spec_from_file_location(
    "package_agent", REPO_ROOT / "scripts" / "package_agent.py"
)
package_agent = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(package_agent)


def test_packaged_task_teacher_v18_runs_standalone_without_pythonpath(tmp_path):
    """v18 packages its adaptive strategy dependency and runs without repo imports."""
    out_path = tmp_path / "task_teacher_v18" / "main.py"

    package_agent.package(REPO_ROOT / "agents" / "task_teacher_v18", out_path)

    generated = out_path.read_text()
    assert "kaggriculture_lib.adaptive_strategy" in generated
    package_agent.verify(out_path, opponent="starter", episode_steps=96)
