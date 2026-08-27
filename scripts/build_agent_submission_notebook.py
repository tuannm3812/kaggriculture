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


def _notebook(agent_name: str, main_src: str, sha256: str, public: bool = False) -> dict:
    """Return a nbformat-v4 notebook dict."""
    main_literal = json.dumps(main_src)
    
    if public:
        markdown_lines = [
            f"# 🌾 Kaggriculture: Hierarchical Task-Driven Coordinator (HTDC)\n",
            "\n",
            "Welcome to the public walkthrough and implementation of our high-performing agent for the **Kaggriculture** simulation challenge! \n",
            "\n",
            f"This notebook compiles and packages the self-contained production code of our top-tier agent, the **Hierarchical Task-Driven Coordinator (HTDC)**, which implements state-of-the-art multi-unit coordination algorithms and resource optimization loops.\n",
            "\n",
            "---\n",
            "\n",
            "## 🚀 Architectural Design & Core Paradigms\n",
            "\n",
            "Our agent relies on a hierarchical, task-driven joint coordinator rather than simple greedy agents or rule-based checklists. The core engine is built on three pillars:\n",
            "\n",
            "### 1. Multi-Unit Joint Task Assignment\n",
            "* **Greedy Joint-Optimal Search & Exhaustive Fallback:** For up to 4 units, the scheduler runs a bounded exhaustive search evaluating all possible assignments. Each combo is scored based on lexicographical priority tier coverage, total travel distance (Manhattan metric), and expected crop value, preventing two units from greedily racing toward the same tile.\n",
            "* When unit counts exceed safety thresholds, the engine dynamically falls back to a deterministic greedy sequence to guarantee sub-millisecond execution times.\n",
            "\n",
            "### 2. Lexicographical Priority-Safety Queue\n",
            "Tasks are ranked according to a deterministic safety hierarchy:\n",
            "* **EMERGENCY (0):** Starvation rescue (feeding animals) and dehydration rescue (watering dry crops).\n",
            "* **DECAYING_YIELD (1):** Harvesting ripe crops before they rot.\n",
            "* **DAILY_CARE (2):** General livestock grooming and crop watering.\n",
            "* **ECONOMIC (3):** Planting new seeds based on ROI and land-expansion projects.\n",
            "* **OPTIONAL (4):** Non-essential maintenance.\n",
            "\n",
            "### 3. Inventory-Aware Routing & Sourcing\n",
            "* **Prerequisite Sourcing:** Units only schedule `PLACE` or `FEED` tasks if they currently hold the required animal or feed in their inventory.\n",
            "* **Multi-Item Pickup Optimization:** Units assigned to fetch feed grab up to **6 wheat at once** from the shed rather than making separate single-item trips, boosting labor efficiency by up to 500% during feed cycles!\n",
            "\n",
            "---\n",
            "\n",
            "## 📈 Chronological Evolutionary Timeline\n",
            "\n",
            "| Version | Core Upgrades | Performance Impact / Champion Status |\n",
            "| :--- | :--- | :--- |\n",
            "| **v1** | Basic Heuristic Scheduler | Foundation established. |\n",
            "| **v2** | Joint-optimal Multi-Unit Assignment | Prevented hands from duplicating effort. |\n",
            "| **v3** | Multi-Quadrant Mapping | Expanded spatial reasoning to multiple sub-fields. |\n",
            "| **v4-v5** | Land Buying & Budget Reserves | ROI-gated NE land expansion; hit **467.7** on the leaderboard. |\n",
            "| **v6-v7** | Unified Task Model & Ongoing Crops | Support for Tomatoes and Strawberries. |\n",
            "| **v8** | Poultry Loop | Geese and egg collection mechanics. |\n",
            "| **v9** | Cow Loop & Direct Feed Buying | Gated cow schedules and wheat replenishment; hit **486.8** on the leaderboard. |\n",
            "| **v10** | Livestock & Logistics Optimization | Resolved placement deadlocks, added 6x feed pickup; hit **502.8** on the leaderboard. |\n",
            "| **v11** | Consolidated Market Gating & Maturity Look-Ahead | Fixed daily delivery seed buying traps, added can_mature_tomorrow safety. |\n",
            "| **v12 (Current)** | Elite Multi-Agent Scaling & Terminal Liquidation | Unlocked all 4 lands, expanded animals (Cows/Sheep/Geese), cost-sensitive hands cap, Day 29 liquidation. **93% win rate vs v11** locally. |\n",
            "\n",
            "---\n",
            "\n",
            "## 🛠️ Verification & Smoke Test\n",
            "Running this notebook writes the compiled self-contained agent to `/kaggle/working/main.py` and creates a packaged `/kaggle/working/submission.tar.gz` archive. The smoke test cell verifies the standalone module against the environment baseline.\n",
            "\n",
            f"Embedded artifact SHA-256: `{sha256}`\n",
        ]
    else:
        markdown_lines = [
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
        ]

    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": markdown_lines,
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
    parser.add_argument(
        "--public",
        action="store_true",
        help="Whether to publish the Kaggle notebook publicly",
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
    nb = _notebook(agent_name, main_src, sha256, public=args.public)

    out_nb = REPO_ROOT / "notebooks" / f"03_{agent_name}_submission.ipynb"
    out_nb.write_text(json.dumps(nb, indent=1) + "\n")
    print(f"Wrote {out_nb}")

    slug = "kaggriculture-htdc" if args.public else "kaggriculture-htdc-submission"
    kernel_dir = REPO_ROOT / "notebooks" / "kernels" / f"{agent_name}_submission"
    kernel_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": f"tuannm3812/{slug}",
        "title": "Kaggriculture HTDC" if args.public else "Kaggriculture HTDC Submission",
        "code_file": out_nb.name,
        "language": "python",
        "kernel_type": "notebook",
        "is_private": not args.public,
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
