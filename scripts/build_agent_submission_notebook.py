#!/usr/bin/env python3
"""Build a Kaggle submission notebook that emits submission.tar.gz.

Kaggriculture accepts notebook submissions via:

    kaggle competitions submit kaggriculture \\
      -k USERNAME/kernel-slug -f submission.tar.gz -v VERSION -m "..."

The notebook must write `/kaggle/working/submission.tar.gz` with `main.py`
at the archive root (see competition AGENTS.md). This script embeds the
already-packaged `build/<agent>/main.py` into that notebook so the kernel
has no repo/dataset dependency.

Usage:
    python scripts/package_agent.py agents/task_teacher_v5
    python scripts/build_agent_submission_notebook.py agents/task_teacher_v5
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _notebook(agent_name: str, main_src: str, sha256: str) -> dict:
    """Return a minimal nbformat-v4 notebook dict."""
    # json.dumps so the Python string literal in the notebook is safe.
    main_literal = json.dumps(main_src)
    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                f"# Kaggriculture submission — `{agent_name}`\n",
                "\n",
                "Writes packaged `main.py` into `/kaggle/working/submission.tar.gz`\n",
                "(archive root = `main.py`) for notebook-based competition submit:\n",
                "\n",
                "```bash\n",
                "kaggle competitions submit kaggriculture \\\n",
                f"  -k USERNAME/kaggriculture-{agent_name.replace('_', '-')}-submission \\\n",
                "  -f submission.tar.gz -v VERSION -m \"...\"\n",
                "```\n",
                "\n",
                f"Embedded artifact SHA-256: `{sha256}`\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import hashlib\n",
                "import tarfile\n",
                "from pathlib import Path\n",
                "\n",
                f"AGENT_NAME = {json.dumps(agent_name)}\n",
                f"EXPECTED_SHA256 = {json.dumps(sha256)}\n",
                f"MAIN_PY = {main_literal}\n",
                "\n",
                "work = Path(\"/kaggle/working\")\n",
                "main_path = work / \"main.py\"\n",
                "main_path.write_text(MAIN_PY)\n",
                "sha = hashlib.sha256(MAIN_PY.encode()).hexdigest()\n",
                "print(f\"Wrote {main_path} ({len(MAIN_PY)} bytes)\")\n",
                "print(f\"SHA-256: {sha}\")\n",
                "assert sha == EXPECTED_SHA256, (sha, EXPECTED_SHA256)\n",
                "\n",
                "tar_path = work / \"submission.tar.gz\"\n",
                "with tarfile.open(tar_path, \"w:gz\") as tar:\n",
                "    tar.add(main_path, arcname=\"main.py\")\n",
                "print(f\"Wrote {tar_path} ({tar_path.stat().st_size} bytes)\")\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from kaggle_environments import make\n",
                "\n",
                "env = make(\n",
                "    \"kaggriculture\",\n",
                "    configuration={\"episodeSteps\": 96, \"seed\": 424242},\n",
                "    debug=True,\n",
                ")\n",
                "env.run([\"/kaggle/working/main.py\", \"starter\"])\n",
                "final = env.steps[-1]\n",
                "for i, s in enumerate(final):\n",
                "    print(f\"Player {i}: reward={s.reward}, status={s.status}\")\n",
                "    assert s.status == \"DONE\", s.status\n",
                "print(\"Smoke vs starter OK\")\n",
            ],
        },
    ]
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "cells": cells,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_dir", type=Path, help="e.g. agents/task_teacher_v5")
    parser.add_argument(
        "--packaged",
        type=Path,
        default=None,
        help="Path to packaged main.py (default: build/<agent>/main.py)",
    )
    args = parser.parse_args()

    agent_name = args.agent_dir.resolve().name
    packaged = (args.packaged or (REPO_ROOT / "build" / agent_name / "main.py")).resolve()
    if not packaged.is_file():
        raise SystemExit(
            f"Missing packaged agent at {packaged}. Run "
            f"`python scripts/package_agent.py agents/{agent_name}` first."
        )

    main_src = packaged.read_text()
    sha256 = hashlib.sha256(main_src.encode()).hexdigest()
    nb = _notebook(agent_name, main_src, sha256)

    out_nb = REPO_ROOT / "notebooks" / f"03_{agent_name}_submission.ipynb"
    out_nb.write_text(json.dumps(nb, indent=1) + "\n")
    print(f"Wrote {out_nb}")

    slug = f"kaggriculture-{agent_name.replace('_', '-')}-submission"
    kernel_dir = REPO_ROOT / "notebooks" / "kernels" / f"{agent_name}_submission"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": f"tuannm3812/{slug}",
        "title": f"Kaggriculture - {agent_name} Submission",
        "code_file": out_nb.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": False,
        "enable_tpu": False,
        "enable_internet": False,
        "dataset_sources": [],
        "competition_sources": ["kaggriculture"],
        "kernel_sources": [],
    }
    meta_path = kernel_dir / "kernel-metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"Wrote {meta_path}")
    print(f"Kernel id: tuannm3812/{slug}")
    print(f"SHA-256: {sha256}")


if __name__ == "__main__":
    main()
