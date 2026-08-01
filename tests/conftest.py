"""Shared test fixtures: repo-root sys.path setup and dynamic agent loading."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def load_agent_module(version: str):
    """Import `agents/<version>/main.py` as a fresh module object.

    Each version's `main.py` isn't part of a package (agents aren't meant
    to import from each other), so this loads it directly by file path —
    the same way `kaggle_environments` loads a file-path agent reference.
    """
    path = REPO_ROOT / "agents" / version / "main.py"
    spec = importlib.util.spec_from_file_location(f"agents_{version}_main", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
