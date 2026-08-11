#!/usr/bin/env python3
"""Fetch and summarize Kaggriculture ladder episodes for a submission.

Uses kagglesdk (CLI lacks competitions episodes/replay). Writes:
  replays/ladder/<label>/{episode_id}.json
  replays/ladder/<label>/episode_summary.json
  replays/analysis/ladder_<label>_episode_summary.csv

Example:
  .venv/bin/python scripts/analyze_ladder_submission.py \\
      --submission-id 55425318 --label task_teacher_v5
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path

from kagglesdk import KaggleClient
from kagglesdk.competitions.types.competition_api_service import (
    ApiGetEpisodeReplayRequest,
    ApiListSubmissionEpisodesRequest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _normalize_agents(ep):
    agents = list(ep.agents)
    for j, a in enumerate(agents):
        if a.index is None:
            a.index = j
    return agents


def _farms_from_step(step):
    for s in step:
        obs = s.get("observation", {})
        if isinstance(obs, dict) and "farms" in obs:
            return obs["farms"]
    return None


def _market_ops(steps, seat: int) -> Counter:
    counts: Counter = Counter()
    for step in steps:
        if not isinstance(step, list) or seat >= len(step):
            continue
        action = step[seat].get("action")
        if not isinstance(action, dict):
            continue
        for order in action.get("market") or []:
            if isinstance(order, (list, tuple)) and order:
                counts[str(order[0])] += 1
    return counts


def _final_farm_stats(steps, seat: int) -> dict:
    farms = _farms_from_step(steps[-1])
    farm = farms[seat]
    unlocked = farm.get("unlocked_quadrants") or []
    animals = 0
    for row in farm.get("tiles") or []:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal"):
                animals += 1
    return {
        "n_unlocked": len(unlocked),
        "animals_placed": animals,
    }


def _max_hands(steps, seat: int) -> int:
    mx = 0
    for step in steps:
        if not isinstance(step, list):
            continue
        farms = _farms_from_step(step)
        if not farms:
            continue
        mx = max(mx, len(farms[seat].get("hands") or []))
    return mx


def analyze(submission_id: int, label: str, team_name: str) -> list[dict]:
    out_dir = REPO_ROOT / "replays" / "ladder" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    client = KaggleClient()
    req = ApiListSubmissionEpisodesRequest()
    req.submission_id = submission_id
    episodes = client.competitions.competition_api_client.list_submission_episodes(req).episodes

    rows: list[dict] = []
    for i, ep in enumerate(episodes):
        agents = _normalize_agents(ep)
        is_validation = "VALIDATION" in str(ep.type)
        if is_validation:
            our_agent, opp = agents[0], agents[1]
        else:
            our_agent = next(a for a in agents if a.submission_id == submission_id)
            opp = next(a for a in agents if a.submission_id != submission_id)
        our_idx, opp_idx = our_agent.index, opp.index

        path = out_dir / f"{ep.id}.json"
        if not path.exists():
            rreq = ApiGetEpisodeReplayRequest()
            rreq.episode_id = ep.id
            resp = client.competitions.competition_api_client.get_episode_replay(rreq)
            content = resp.content if hasattr(resp, "content") else resp
            if hasattr(content, "read"):
                content = content.read()
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(json.dumps(content) if isinstance(content, (dict, list)) else str(content))
            print(f"[{i + 1}/{len(episodes)}] downloaded {ep.id}")
            time.sleep(0.25)
        else:
            print(f"[{i + 1}/{len(episodes)}] cached {ep.id}")

        steps = json.loads(path.read_text())["steps"]
        our_ops = _market_ops(steps, our_idx)
        opp_ops = _market_ops(steps, opp_idx)
        our_farm = _final_farm_stats(steps, our_idx)
        opp_farm = _final_farm_stats(steps, opp_idx)
        our_r, opp_r = our_agent.reward, opp.reward
        if our_r > opp_r:
            result = "WIN"
        elif our_r < opp_r:
            result = "LOSS"
        else:
            result = "TIE"
        rows.append(
            {
                "episode_id": ep.id,
                "type": str(ep.type).split(".")[-1],
                "our_seat": our_idx,
                "our_reward": our_r,
                "opp_team": "(self-play validation)" if is_validation else opp.team_name,
                "opp_submission_id": opp.submission_id,
                "opp_reward": opp_r,
                "result": result,
                "our_buy_land": int(our_ops.get("BUY_LAND", 0)),
                "our_buy_animal": int(our_ops.get("BUY_ANIMAL", 0)),
                "our_hire": int(our_ops.get("HIRE", 0)),
                "our_n_unlocked": our_farm["n_unlocked"],
                "our_max_hands": _max_hands(steps, our_idx),
                "our_animals_placed": our_farm["animals_placed"],
                "opp_buy_land": int(opp_ops.get("BUY_LAND", 0)),
                "opp_buy_animal": int(opp_ops.get("BUY_ANIMAL", 0)),
                "opp_hire": int(opp_ops.get("HIRE", 0)),
                "opp_n_unlocked": opp_farm["n_unlocked"],
                "opp_max_hands": _max_hands(steps, opp_idx),
                "opp_animals_placed": opp_farm["animals_placed"],
                "opp_land": bool(opp_ops.get("BUY_LAND", 0) > 0 or opp_farm["n_unlocked"] > 1),
                "opp_animals": bool(opp_ops.get("BUY_ANIMAL", 0) > 0 or opp_farm["animals_placed"] > 0),
            }
        )

    (out_dir / "episode_summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    csv_path = REPO_ROOT / "replays" / "analysis" / f"ladder_{label}_episode_summary.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    public = [r for r in rows if r["type"] == "EPISODE_TYPE_PUBLIC"]
    wins = sum(1 for r in public if r["result"] == "WIN")
    losses = sum(1 for r in public if r["result"] == "LOSS")
    print(f"\n{team_name} / {label} submission {submission_id}")
    print(f"Public {len(public)}: {wins}W-{losses}L WR={wins / len(public):.3f}" if public else "no public")
    print(f"Wrote {out_dir / 'episode_summary.json'} and {csv_path}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-id", type=int, required=True)
    parser.add_argument("--label", required=True, help="e.g. task_teacher_v5")
    parser.add_argument("--team-name", default="tuannm3812")
    args = parser.parse_args()
    analyze(args.submission_id, args.label, args.team_name)


if __name__ == "__main__":
    main()
