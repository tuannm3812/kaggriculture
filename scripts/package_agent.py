#!/usr/bin/env python3
"""Package an agents/<version>/main.py into a self-contained submission file.

Local dev agents do `from kaggriculture_lib import economy`, which only
resolves because scripts/run_tournament.py puts `src/` on sys.path. Kaggle
runs a submitted main.py with no knowledge of this repo's layout, so it
must not depend on that. This script inlines `src/kaggriculture_lib/economy.py`
as an in-memory module object at the top of the generated file, so the
agent's `economy.<name>` calls keep working with zero import-path tricks —
see docs/6_next_steps.md's packaging-step open item.

Usage:
    python scripts/package_agent.py agents/roi_teacher_v1
    # writes build/roi_teacher_v1/main.py, then verifies it runs standalone
    # (no PYTHONPATH) against an opponent before printing success.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TEMPLATE = '''"""Auto-generated self-contained submission artifact. Do not edit by
hand — edit {agent_dir}/main.py and/or src/kaggriculture_lib, then rerun
scripts/package_agent.py to regenerate."""

{future_imports}import types as _types

_economy_src = {economy_src!r}
economy = _types.ModuleType("economy")
exec(compile(_economy_src, "kaggriculture_lib/economy.py", "exec"), economy.__dict__)


{agent_src}
'''

IMPORT_LINE_RE = re.compile(r"^from kaggriculture_lib import economy\n", re.MULTILINE)
FUTURE_IMPORT_RE = re.compile(r"^from __future__ import .+\n", re.MULTILINE)


def package(agent_dir: Path, out_path: Path) -> None:
    economy_src = (REPO_ROOT / "src" / "kaggriculture_lib" / "economy.py").read_text()
    agent_src = (agent_dir / "main.py").read_text()

    if not IMPORT_LINE_RE.search(agent_src):
        raise SystemExit(
            f"{agent_dir / 'main.py'} doesn't have the expected "
            "'from kaggriculture_lib import economy' import line — packaging "
            "template needs updating if the agent's dependency shape changed."
        )
    agent_src = IMPORT_LINE_RE.sub("", agent_src)

    # `from __future__ import ...` must be the first statement in the file
    # (only a docstring may precede it) — hoist any such lines from the
    # agent source up to just under this template's own docstring.
    future_imports = "".join(FUTURE_IMPORT_RE.findall(agent_src))
    agent_src = FUTURE_IMPORT_RE.sub("", agent_src)
    if future_imports:
        future_imports += "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        TEMPLATE.format(
            agent_dir=agent_dir.name,
            future_imports=future_imports,
            economy_src=economy_src,
            agent_src=agent_src,
        )
    )
    print(f"Wrote {out_path}")


def verify(out_path: Path, opponent: str, episode_steps: int) -> None:
    """Run the packaged artifact in a subprocess with PYTHONPATH stripped,
    to confirm it doesn't secretly still depend on this repo's src/ layout
    (the actual condition Kaggle's execution environment will impose)."""
    script = f"""
from kaggle_environments import make
env = make("kaggriculture", configuration={{"episodeSteps": {episode_steps}}}, debug=True)
env.run([{str(out_path)!r}, {opponent!r}])
final = env.steps[-1]
for i, s in enumerate(final):
    print(f"Player {{i}}: reward={{s.reward}}, status={{s.status}}")
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
    print(result.stdout)
    if result.returncode != 0 or "status=DONE" not in result.stdout:
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"Standalone verification failed (exit {result.returncode})")
    print("Verified: runs standalone with no PYTHONPATH dependency on this repo.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_dir", type=Path, help="e.g. agents/roi_teacher_v1")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--verify-against", default="starter")
    parser.add_argument("--verify-steps", type=int, default=96)
    args = parser.parse_args()

    agent_dir = args.agent_dir.resolve()
    out_path = (args.out or (REPO_ROOT / "build" / agent_dir.name / "main.py")).resolve()
    package(agent_dir, out_path)
    verify(out_path, args.verify_against, args.verify_steps)


if __name__ == "__main__":
    main()
