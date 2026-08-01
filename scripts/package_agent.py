#!/usr/bin/env python3
"""Package an agents/<version>/main.py into a self-contained submission file.

Local dev agents do `from kaggriculture_lib import economy` (and, for
task_teacher_v*, `from kaggriculture_lib.tasking import ...`), which only
resolves because scripts/run_tournament.py puts `src/` on sys.path. Kaggle
runs a submitted main.py with no knowledge of this repo's layout, so it
must not depend on that.

Per Codex's review of the task_teacher_v1 design: this registers real
modules in `sys.modules` under their true dotted names
(`kaggriculture_lib`, `kaggriculture_lib.economy`, `kaggriculture_lib.tasking`,
...) rather than bare namespace-object aliases. That means: (a) dataclass
`__module__` introspection resolves correctly (a dataclass's `__module__`
must point to a real, importable module for tooling that consults
`sys.modules[cls.__module__]`), and (b) every shared module's own
`from kaggriculture_lib import X` line — and the agent's own import lines —
stay completely unmodified. No per-module import-line stripping, and no
hardcoded module list: shared modules under `src/kaggriculture_lib/` are
discovered automatically and topologically sorted by their internal
`kaggriculture_lib` imports, so adding a new shared module needs no changes
here.

Usage:
    python scripts/package_agent.py agents/task_teacher_v1
    # writes build/task_teacher_v1/main.py, then verifies it runs standalone
    # (no PYTHONPATH) against an opponent before printing success.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = REPO_ROOT / "src" / "kaggriculture_lib"

FUTURE_IMPORT_RE = re.compile(r"^from __future__ import .+\n", re.MULTILINE)

DOCSTRING_TEMPLATE = (
    '"""Auto-generated self-contained submission artifact. Do not edit by '
    "hand — edit {agent_dir}/main.py and/or src/kaggriculture_lib, then rerun "
    'scripts/package_agent.py to regenerate."""\n\n'
)

REGISTER_HELPER = """\
import sys as _sys
import types as _types


def _register_shared_module(name, source, path):
    module = _types.ModuleType(name)
    module.__file__ = path
    _sys.modules[name] = module
    exec(compile(source, path, "exec"), module.__dict__)
    return module


_kaggriculture_lib = _types.ModuleType("kaggriculture_lib")
_kaggriculture_lib.__path__ = []
_sys.modules["kaggriculture_lib"] = _kaggriculture_lib
"""


def _referenced_shared_modules(source: str, known_names: set[str]) -> set[str]:
    """Which `known_names` modules `source` imports via `kaggriculture_lib`."""
    referenced: set[str] = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module == "kaggriculture_lib":
            referenced.update(alias.name for alias in node.names)
        elif node.module.startswith("kaggriculture_lib."):
            referenced.add(node.module.split(".", 1)[1])
    return referenced & known_names


def _discover_shared_modules(lib_dir: Path) -> list[str]:
    """Shared module names under `lib_dir`, topologically sorted so a
    module that imports another comes after it (Kahn's algorithm)."""
    names = sorted(p.stem for p in lib_dir.glob("*.py") if p.stem != "__init__")
    deps = {name: _referenced_shared_modules((lib_dir / f"{name}.py").read_text(), set(names)) for name in names}

    ordered: list[str] = []
    remaining = set(names)
    while remaining:
        ready = sorted(name for name in remaining if deps[name] <= set(ordered))
        if not ready:
            raise SystemExit(f"Circular dependency among shared modules: {sorted(remaining)}")
        ordered.extend(ready)
        remaining -= set(ready)
    return ordered


def package(agent_dir: Path, out_path: Path) -> None:
    module_order = _discover_shared_modules(LIB_DIR)

    agent_src = (agent_dir / "main.py").read_text()
    future_imports = "".join(FUTURE_IMPORT_RE.findall(agent_src))
    agent_src = FUTURE_IMPORT_RE.sub("", agent_src)
    if future_imports:
        future_imports += "\n"

    registration_blocks = []
    for name in module_order:
        source = (LIB_DIR / f"{name}.py").read_text()
        dotted = f"kaggriculture_lib.{name}"
        registration_blocks.append(
            f"_{name}_source = {source!r}\n"
            f"{name} = _register_shared_module({dotted!r}, _{name}_source, {dotted.replace('.', '/') + '.py'!r})\n"
            f"_kaggriculture_lib.{name} = {name}\n"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        DOCSTRING_TEMPLATE.format(agent_dir=agent_dir.name)
        + future_imports
        + REGISTER_HELPER
        + "\n"
        + "\n".join(registration_blocks)
        + "\n\n"
        + agent_src
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
    parser.add_argument("agent_dir", type=Path, help="e.g. agents/task_teacher_v1")
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
