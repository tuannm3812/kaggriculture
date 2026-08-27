#!/usr/bin/env python3
"""Diagnose *why* our ladder agent loses, beyond win/loss bookkeeping.

`analyze_ladder_submission.py` records what each side ended with. This asks
the follow-up questions that decide what to build next:

  1. Do our animals starve in real ladder play? (v18 was rejected for exactly
     this — 47 escapes / 24 of 100 acceptance games — so the first question is
     whether the shipped v16/v17 line has the same defect in the wild.)
  2. Where in the season does the money gap actually open?
  3. What do the opponents who beat us do differently, and does it look like
     one dominant strategy or several?

Reads the replay JSONs `analyze_ladder_submission.py` already cached under
`replays/ladder/<label>/`. Read-only; writes nothing.

Usage:
  .venv/bin/python scripts/diagnose_ladder_gap.py --label v17_live
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TURNS_PER_DAY = 24


def _farms(step):
    for cell in step:
        obs = cell.get("observation") if isinstance(cell, dict) else None
        if isinstance(obs, dict) and "farms" in obs:
            return obs["farms"]
    return None


def _seat_of(data, team_name):
    names = data.get("info", {}).get("TeamNames") or []
    if team_name in names:
        return names.index(team_name)
    return None


def _count_animals(farm):
    n = 0
    for row in farm.get("tiles") or []:
        for tile in row:
            if isinstance(tile, dict) and tile.get("animal"):
                n += 1
    return n


def _animal_escapes(steps, seat):
    """Animals that vanish from tiles without a matching sale/aging path.

    The pinned simulator removes an animal at the daily refresh after its
    second consecutive unfed day, so a drop in placed-animal count across a
    day boundary is the escape signature (same detection v18's evaluation
    used). Counted conservatively: only net decreases.
    """
    escapes = 0
    prev = None
    prev_day = None
    for step in steps:
        farms = _farms(step)
        if not farms:
            continue
        obs = None
        for cell in step:
            o = cell.get("observation") if isinstance(cell, dict) else None
            if isinstance(o, dict) and "day" in o:
                obs = o
                break
        if obs is None:
            continue
        day = obs.get("day")
        n = _count_animals(farms[seat])
        if prev is not None and prev_day is not None and day != prev_day and n < prev:
            escapes += prev - n
        prev, prev_day = n, day
    return escapes


def _money_by_day(steps, seat):
    out = {}
    for step in steps:
        farms = _farms(step)
        if not farms:
            continue
        obs = None
        for cell in step:
            o = cell.get("observation") if isinstance(cell, dict) else None
            if isinstance(o, dict) and "day" in o:
                obs = o
                break
        if obs is None:
            continue
        out[obs.get("day")] = farms[seat].get("money")
    return out


def _market_ops(steps, seat):
    counts = Counter()
    for step in steps:
        if not isinstance(step, list) or seat >= len(step):
            continue
        action = step[seat].get("action")
        if not isinstance(action, dict):
            continue
        for order in action.get("market") or []:
            if isinstance(order, (list, tuple)) and order:
                key = str(order[0])
                if key in ("BUY_ANIMAL", "BUY_SEED", "SELL", "BUY_PRODUCT") and len(order) > 1:
                    key = f"{key}:{order[1]}"
                counts[key] += 1
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--label", required=True)
    ap.add_argument("--team-name", default="tuannm3812")
    args = ap.parse_args()

    d = REPO_ROOT / "replays" / "ladder" / args.label
    files = sorted(d.glob("*.json"))
    files = [f for f in files if f.name != "episode_summary.json"]
    if not files:
        raise SystemExit(f"no replays under {d}")

    our_escape_games = 0
    our_escape_total = 0
    opp_escape_total = 0
    wins, losses = [], []
    gap_open_days = []
    winner_profiles = Counter()
    our_max_animals = []
    opp_max_animals = []

    for f in files:
        data = json.loads(f.read_text())
        seat = _seat_of(data, args.team_name)
        if seat is None:
            continue
        opp = 1 - seat
        steps = data["steps"]

        esc = _animal_escapes(steps, seat)
        our_escape_total += esc
        if esc:
            our_escape_games += 1
        opp_escape_total += _animal_escapes(steps, opp)

        final = _farms(steps[-1])
        um, om = final[seat].get("money"), final[opp].get("money")
        won = um > om
        (wins if won else losses).append((um, om))

        # peak simultaneous animals each side
        pa = po = 0
        for step in steps:
            fs = _farms(step)
            if not fs:
                continue
            pa = max(pa, _count_animals(fs[seat]))
            po = max(po, _count_animals(fs[opp]))
        our_max_animals.append(pa)
        opp_max_animals.append(po)

        # when does the gap open (first day opp lead exceeds 5k and never closes)
        umd, omd = _money_by_day(steps, seat), _money_by_day(steps, opp)
        if not won:
            for day in sorted(umd):
                if omd.get(day, 0) - umd.get(day, 0) > 5000:
                    gap_open_days.append(day)
                    break
            ops = _market_ops(steps, opp)
            fo = _farms(steps[-1])[opp]
            prof = (
                f"land={len(fo.get('unlocked_quadrants') or [])}",
                f"animals={po}",
            )
            winner_profiles[prof] += 1

    n = len(wins) + len(losses)
    print(f"=== ladder diagnostics: {args.label} ({n} episodes) ===\n")
    print(f"record: {len(wins)}W-{len(losses)}L ({100*len(wins)//max(1,n)}%)\n")

    print("--- 1. animal starvation (the v18 rejection signature) ---")
    print(f"our animal escapes:      {our_escape_total} across {our_escape_games}/{n} games")
    print(f"opponent animal escapes: {opp_escape_total}")
    print(f"our peak animals   (median/max): {statistics.median(our_max_animals):.0f} / {max(our_max_animals)}")
    print(f"opp peak animals   (median/max): {statistics.median(opp_max_animals):.0f} / {max(opp_max_animals)}\n")

    print("--- 2. where the gap opens (losses only) ---")
    if gap_open_days:
        print(f"first day opponent leads by >$5k: median day {statistics.median(gap_open_days):.0f}, "
              f"range {min(gap_open_days)}-{max(gap_open_days)}")
        print(f"  (n={len(gap_open_days)} of {len(losses)} losses; others never hit a $5k gap)\n")
    else:
        print("no loss reached a $5k gap\n")

    if wins:
        print(f"our money in wins   (median): ${statistics.median([w[0] for w in wins]):,.0f} "
              f"vs opp ${statistics.median([w[1] for w in wins]):,.0f}")
    if losses:
        print(f"our money in losses (median): ${statistics.median([l[0] for l in losses]):,.0f} "
              f"vs opp ${statistics.median([l[1] for l in losses]):,.0f}")
    print()

    print("--- 3. profile of opponents who beat us ---")
    for prof, c in winner_profiles.most_common(10):
        print(f"  {c:>3}x  {', '.join(prof)}")


if __name__ == "__main__":
    main()
