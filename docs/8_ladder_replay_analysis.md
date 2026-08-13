# 8. Ladder Replay Analysis — `task_teacher_v2`, 2026-08-06/07

## Methodology

The `kaggle` CLI (1.7.4.5, the latest release on PyPI as of this writing)
does not implement the `episodes`, `replay`, or `logs` subcommands that
Kaggriculture's own getting-started guide documents (`kaggle competitions
episodes <SUBMISSION_ID>`, `kaggle competitions replay <EPISODE_ID>`,
`kaggle competitions logs <EPISODE_ID> <agent_index>` all fail with
`invalid choice` against the installed CLI). The underlying API is
implemented — it's exposed one layer down, in the `kagglesdk` package
(`kagglesdk.competitions.services.competition_api_service
.CompetitionApiClient`), which the `kaggle` CLI itself depends on but
hasn't wired these three commands up to yet. Used `kagglesdk` directly:

```python
from kagglesdk import KaggleClient
from kagglesdk.competitions.types.competition_api_service import (
    ApiListSubmissionsRequest, ApiListSubmissionEpisodesRequest, ApiGetEpisodeReplayRequest,
)

client = KaggleClient()  # reuses the same ~/.kaggle credentials as the CLI
# ApiListSubmissionsRequest -> submission id
# ApiListSubmissionEpisodesRequest(submission_id=...) -> list of episodes, each with both
#   agents' team name + final reward
# ApiGetEpisodeReplayRequest(episode_id=...) -> requests.Response; .content is the same
#   env.toJSON() replay format used everywhere else in this project (steps/observation/
#   action/rewards/statuses), just pulled from Kaggle's live ladder instead of a local run
```

Submission analyzed: `task_teacher_v2`'s resubmission (id `55298958`,
2026-08-06 13:06:42 — the packaging-bug-fixed artifact from
`docs/4_agent_version_log.md`'s 2026-08-06 incident entry).

**Ladder record as of this analysis:** 20 episodes total (1 self-play
`EPISODE_TYPE_VALIDATION` + 19 real `EPISODE_TYPE_PUBLIC` games against
other teams' submissions). **8W-11L-0T (42.1% win rate)** over the 19 real
episodes. Live skill rating (`publicScore`) `488.9`, down from `537.6` at
the 12-episode mark checked earlier the same day — declining as sample
size grows, consistent with a real skill gap rather than early-sample
noise.

All 19 real-episode replay JSONs (`env.toJSON()` format, ~13-18 MB each)
were downloaded and parsed programmatically (final money, max hands
fielded, land-quadrant unlocks, `BUY_LAND`/`BUY_ANIMAL` order presence,
`HIRE` order counts, for both sides of every game). Three of the
nineteen — the clearest win, the closest loss, and the most lopsided loss
— were additionally parsed in full day-by-day detail (money trajectory,
animal `PLACE` actions, `FERTILIZE` counts, final tile snapshots).

## Headline Finding

**Win/loss splits almost entirely on whether the opponent expanded land
and/or added animals — not on tactical execution quality within
`task_teacher_v2`'s existing scope** (single quadrant, Wheat/Carrot/Melon,
hired-hand task routing):

| Opponent profile | Games | Record | Win rate |
| --- | ---: | --- | ---: |
| Opponent bought land and/or used animals | 16 | 5W-11L | 31% |
| Opponent did neither (still single-quadrant, no animals) | 3 | 3W-0L | **100%** |

16 of the 19 real opponents faced so far (84%) have already built land
and/or animal expansion — this is not an edge case in the ladder's
opponent pool, it is the norm. `task_teacher_v2` issued **zero**
`BUY_LAND` and **zero** `BUY_ANIMAL` orders across all 19 episodes — it
structurally cannot do either; that logic was never built (per the
v1/v2/v3 design docs' explicit scoping). Its own hand count topped out at
2-5 in most games regardless of opponent.

Full per-episode table:

| Episode | Opponent | Result | Money (us / opp) | Opp land? | Opp animals? | Opp max hands | Opp max quadrants |
| --- | --- | --- | ---: | :---: | :---: | ---: | ---: |
| 90553564 | Koba | LOSS | 35,111 / 46,596 | yes | yes | 13 | 3 |
| 90549011 | huangjunjia | **WIN** | 24,416 / 13,531 | no | no | 4 | 1 |
| 90518189 | Giordano Dolenz | LOSS | 28,247 / 45,478 | yes | yes | 14 | 3 |
| 90514445 | Agrippa Beaulieu | LOSS | 26,896 / 60,910 | yes | yes | 13 | 4 |
| 90484352 | TheSven | LOSS | 29,185 / 83,921 | yes | yes | 10 | 3 |
| 90467113 | Michał Łapiński | LOSS | 20,253 / 68,016 | yes | yes | 10 | 2 |
| 90455456 | Pratik Priyanshu | **WIN** | 42,029 / 33,649 | yes | yes | 11 | 2 |
| 90448684 | Nathan Thor | LOSS | 45,538 / 64,654 | yes | yes | 10 | 3 |
| 90447916 | David kinyanjui | **WIN** | 34,498 / 2,369 | yes | yes | 5 | 4 |
| 90447014 | BALLEN1337 | **WIN** | 25,700 / 17,216 | yes | yes | 9 | 4 |
| 90446358 | Tim Wong | LOSS | 35,983 / 63,742 | yes | yes | 12 | 3 |
| 90445580 | Daumas Benjamin | **WIN** | 20,628 / 17,058 | no | yes | 5 | 1 |
| 90444806 | Antonio Stanciu | **WIN** | 41,316 / 15,707 | no | no | 5 | 1 |
| 90444006 | Saugat Kannojia | LOSS | 28,903 / 38,097 | yes | yes | 10 | 2 |
| 90443219 | Tian_Wang1210 | LOSS | 15,061 / 23,542 | yes | no | 8 | 4 |
| 90443211 | qwertyDmitry | **WIN** | 34,233 / 18,138 | no | no | 2 | 1 |
| 90442431 | Greek olive oil | LOSS | 14,928 / 34,359 | no | yes | 9 | 1 |
| 90441655 | Dziriyin wa9il | LOSS | 13,699 / 85,245 | yes | yes | 12 | 4 |
| 90440902 | cheesama | **WIN** | 28,293 / 25,146 | yes | no | 10 | 3 |

The split isn't absolute — 5 of the 16 "expanded" opponents were still
beaten (one, David kinyanjui, appears to have bought land/animals but
executed so poorly they finished with only $2,369; the other four —
Pratik Priyanshu, BALLEN1337, Daumas Benjamin, cheesama — were closer
contests our task/route execution still won). But the *pass rate* is
stark: perfect within scope, roughly 1-in-3 outside it. This is not
evidence the core task/route logic is weak — it's evidence the logic
wins within its scope and mostly loses on scope.

In the most lopsided loss (vs. Dziriyin wa9il, full day-by-day trace),
the opponent's money trajectory shows the exact moment the gap opens:
both sides were within ~$300 of each other through day 9 (typical
early-game seed-buying drawdown), but the opponent had unlocked all 4
land quadrants by day 11 and their money jumped from $5,227 (day 12) to
$85,245 (day 30) as land and animal income compounded, while ours grew
from $380 to $13,699 over the same span — roughly 6x slower.

## Why This Matters

Every local evaluation this project has run to date — the 100-episode
acceptance gates, the paired Hoeffding-CI screens vs. `task_teacher_v1`/
`roi_teacher_v3`/`starter` — measures `task_teacher_v2` against opponents
from the *same scope-constrained family*: none of `starter`, `random`,
`pass`, `roi_teacher_v1-v3`, or `task_teacher_v1` ever buy land or use
animals either. Those evaluations correctly show `task_teacher_v2`
dominating that field (CI `[0.730, 1.000]` vs. `task_teacher_v1`) — but
they cannot and do not measure anything about land or animal strategy,
because nothing in that local field exercises it. The real ladder's
opponent pool is not scope-constrained the same way — 84% of real
opponents faced so far (16 of 19) have already built land and/or animal
expansion. `docs/3_agent_strategy.md` flagged "ongoing
crops / animals ROI ranking" as an open, unranked question back on
2026-08-01, and `docs/6_next_steps.md` item 9 explicitly deferred both
land purchases and animals out of `task_teacher_v3`'s scope. This replay
data is the first *measured* evidence — as opposed to a standing
hypothesis — that closing that gap is where the real ladder points are.

The bottleneck is land, not headcount: with only 25 tiles (1 quadrant)
and 3 one-time crop types, 4-5 hands may already be close to saturating
the available useful work. `docs/6_next_steps.md` item 14's 2026-08-02
finding that more aggressive hiring made things *worse* was measured
entirely within this same single-quadrant, animal-free world — it doesn't
generalize to "hiring more never helps," it's consistent with "hiring
more without more land/animals to work doesn't help." More hands only
pays off once there's more farm to run.

## Recommendation

Land purchase + animal husbandry looks like a materially higher-leverage
next version than finishing the ongoing-crops (`task_teacher_v3`) line
alone. `task_teacher_v3` only adds Tomato/Strawberry within the same
single-quadrant, animal-free world this data shows losing decisively — it
would not have changed the outcome of either loss analyzed here. This
doesn't invalidate `task_teacher_v3`'s in-flight fix (still worth landing,
since the ongoing-crop scoring bug is real and independent of this
finding), but it does argue land/animal expansion should be prioritized
as scope for whichever version comes after it, rather than treated as a
"someday" item behind further single-quadrant refinement.

## Caveats

- **Sample size:** all 19 real episodes played so far were summarized
  (land/animal presence, hands, quadrants, win/loss); 3 were additionally
  deep-analyzed day-by-day. 19 games is still a small sample of the full
  ladder field and will keep growing — the 100%-vs-31% split is stark but
  not yet a large-n statistical guarantee.
- **Opponent pool is not fixed:** Kaggle's skill-based matchmaking shifts
  who we're paired against as our own rating moves, and other teams are
  actively resubmitting too. This finding should be periodically
  re-checked as more episodes land, not treated as a permanent
  characterization of "the field."
- **Directional, not a full revenue attribution:** this analysis
  quantifies *that* land/animal opponents pull far ahead and *when*, not
  the exact dollar breakdown of how much of their income was land/animal-
  derived versus simply better crop execution on a larger board. Land and
  hand-count are entangled (more land enables more useful hands), so the
  finding should be read as "land+animals is the standout differentiator
  we can act on now," not as a precise causal decomposition.

## Refresh — 2026-08-10 (56 public episodes)

Same submission `55298958`. Live `publicScore` **504.2**. Full public
episode count grew from 19 → **56** (plus 1 validation). All 56 replays
re-downloaded via `kagglesdk` and re-parsed
(`.superpowers/sdd/ladder/fetch_and_analyze.py`).

| Cohort | Record | Win rate | vs expanded (land and/or animals) |
| --- | --- | ---: | ---: |
| First 19 (Aug 7 baseline) | 8W-11L | 42.1% | 31.2% |
| Next 37 | 20W-17L | 54.1% | 50.0% |
| **All 56** | **28W-28L** | **50.0%** | **43.5%** |

Finer profile split (all 56; our side still 0×`BUY_LAND`, 0×`BUY_ANIMAL`,
max 1 quadrant):

| Opponent profile | Games | Record | Win rate | Mean $ margin |
| --- | ---: | --- | ---: | ---: |
| Neither land nor animals | 10 | 8W-2L | **80.0%** | +9,581 |
| Land only | 8 | 5W-3L | **62.5%** | +8,609 |
| Land + animals | 31 | 13W-18L | 41.9% | −11,115 |
| Animals only | 7 | 2W-5L | **28.6%** | −7,211 |

**Updated nuance:** with 3× sample, land alone is no longer the whole
story — land-only opponents are still beatable. **Animals** (with or
without land) drive the deep negative margins. Clean counterexample:
MoongladeAI, animals-only on 1 quadrant, 10 hands, margin **−$49,866**.
Opponent peak hands also tracks losses (0–4 hands: 83% WR; 13+: 0W-3L).

Implication for `task_teacher_v4`: design land **and** the animal loop
together; do not ship land as a solitary feature.

## Refresh — 2026-08-11 (`task_teacher_v5`, submission `55425318`)

Land-only champion submitted via notebook (`submission.tar.gz`). Analyzed
with `scripts/analyze_ladder_submission.py` (same `kagglesdk` path as
above). Artifacts: `replays/ladder/task_teacher_v5/` +
`replays/analysis/ladder_v5_episode_summary.csv`.

**Live score at analysis:** `publicScore` **444.2** (was 423.9 at submit;
v2 still tracked at ~490). **17 public + 1 validation.** Record
**8W-9L (47.1%)**. Mean final money **$21,720 us / $19,982 opp** (we are
slightly ahead on mean dollars despite the losing record — asymmetric
margins).

### Land path is live

| Our behavior (17 public) | Result |
| --- | --- |
| `BUY_LAND` episodes | **17/17** (exactly 1 order/ep) |
| Final unlocked quadrants | **2.00** mean (NE only, as designed) |
| `BUY_ANIMAL` | **0/17** |

### Opponent-profile split

| Opponent profile | Games | Record | Win rate | Mean $ margin |
| --- | ---: | --- | ---: | ---: |
| Land and/or animals | 13 | 6W-7L | 46% | +1,587 |
| Land + animals | 6 | 2W-4L | **33%** | −6,741 |
| Land only | 6 | 3W-3L | 50% | +5,753 |
| Animals only | 1 | 1W-0L | 100% | +26,560 |
| Neither | 4 | 2W-2L | 50% | +2,226 |

vs v2's Aug-10 56-ep refresh: v2 was **50% overall**, **41.9%** vs
land+animals, **80%** vs neither. v5's early sample is roughly in line on
expanded opponents and **worse vs neither** — see cash-starvation note.

### Headline finding for v5

1. **NE land works on the ladder** — every episode unlocks exactly one
   extra quadrant. That closes the v2 "never buys land" structural gap.
2. **Full expansion + animals still dominate late.** Deep losses (Fanis
   Alexakis −$37.9k, YJ Wee 2807 −$14.6k, khanna.rohit5 −$14.5k) show
   opponents unlocking 3–4 quadrants and placing cows/sheep/geese; we stay
   at 2Q / 0 animals and get overtaken after day ~20 even when mid-game
   ahead (Fanis: we $20k vs $1.2k on day 15, then $19.6k vs $57.4k final).
3. **Early `BUY_LAND` can lose to strong NW-only crop bots.** Losses to
   TinkerBotics and Alex Kapend (neither land nor animals): we unlock NE
   on **day 1**, bank drops to ~$10–60 through day 13, while they stay
   NW-only, saturate ~22–25 plants, and cash a large harvest spike around
   day 12 (`$11k` / `$18k`). Our first meaningful sell lands ~day 14. Land
   opportunity cost is real when the opponent's Melon timing is clean.

### Per-episode table (17 public)

| Episode | Opponent | Result | Money (us / opp) | Our BL | Opp land? | Opp animals? | Opp max hands | Opp Q |
| --- | --- | --- | ---: | ---: | :---: | :---: | ---: | ---: |
| 91907290 | kuroneko | LOSS | 20,856 / 24,694 | 1 | yes | no | 8 | 2 |
| 91906359 | AgriBot | **WIN** | 27,017 / 18,297 | 1 | yes | yes | 10 | 3 |
| 91905416 | Charan Manthena | **WIN** | 18,953 / 3,426 | 1 | yes | no | 10 | 4 |
| 91904486 | Horizonx30 | **WIN** | 28,397 / 9,862 | 1 | yes | yes | 6 | 2 |
| 91903522 | TinkerBotics | LOSS | 9,157 / 25,181 | 1 | no | no | 2 | 1 |
| 91902554 | Ryan Triplett | LOSS | 22,394 / 23,143 | 1 | yes | yes | 15 | 4 |
| 91901556 | Amalio Gomez | **WIN** | 27,520 / 4,611 | 1 | yes | no | 2 | 2 |
| 91900645 | Kaggri Farmers | LOSS | 18,204 / 20,074 | 1 | yes | no | 9 | 3 |
| 91899701 | Francesco Benincasa | **WIN** | 23,352 / 6,019 | 1 | yes | no | 2 | 2 |
| 91898760 | JordanM10 | **WIN** | 24,778 / 14,603 | 1 | no | no | 10 | 1 |
| 91897820 | mayank | **WIN** | 27,859 / 1,299 | 1 | no | yes | 10 | 1 |
| 91896853 | khanna.rohit5 | LOSS | 27,631 / 42,118 | 1 | yes | yes | 12 | 4 |
| 91895978 | Hilarus | **WIN** | 28,981 / 3,000 | 1 | no | no | 0 | 1 |
| 91894934 | Blu cky | LOSS | 6,920 / 22,465 | 1 | yes | no | 6 | 2 |
| 91893999 | Alex Kapend | LOSS | 11,629 / 22,856 | 1 | no | no | 3 | 1 |
| 91893042 | Fanis Alexakis | LOSS | 19,563 / 57,413 | 1 | yes | yes | 8 | 4 |
| 91892084 | YJ Wee 2807 | LOSS | 26,023 / 40,636 | 1 | yes | yes | 10 | 3 |

### Recommendation (superseded by 2026-08-12 refresh + v6 findings)

Keep v5 on the ladder (land is validated). `task_teacher_v6`'s cash-floor
delay was **locally inert** vs v5 — see version log. Next: reconcile
ladder day-1 NE unlock vs local day-~15 buy, then a carefully capped
animal path. Re-run this script as n grows.

## Refresh — 2026-08-12 (`task_teacher_v5`, 29 public)

Same submission `55425318`. Live `publicScore` **448.8** (v2 ~477).
Artifacts refreshed via `scripts/analyze_ladder_submission.py` →
`replays/analysis/ladder_task_teacher_v5_episode_summary.csv`.

**Record: 14W–15L (48.3%)**. Mean money **$21,971 us / $24,359 opp**.
Cohorts: first 17 = 8W–9L (47.1%); next 12 = 6W–6L (50.0%).

### Our behavior (29 public)

| Metric | Result |
| --- | --- |
| `BUY_LAND` | **29/29** (exactly 1/ep) |
| Unlocked quadrants | **2.00** mean (NE only) |
| `BUY_ANIMAL` | **0/29** |

### Opponent-profile split (29)

| Opponent profile | Games | Record | Win rate | Mean $ margin |
| --- | ---: | --- | ---: | ---: |
| Land and/or animals | 24 | 11W–13L | 46% | −4,339 |
| Land + animals | 16 | 6W–10L | **38%** | **−11,219** |
| Land only | 7 | 4W–3L | 57% | +6,974 |
| Animals only | 1 | 1W–0L | 100% | +26,560 |
| Neither | 5 | 3W–2L | 60% | +6,979 |

**Updated headline:** land-only is roughly break-even / slightly positive.
**Land+animals remains the loss mode** (38% WR, −$11k mean margin). New
deep losses: Kers Aoyagi −$115k (3Q, 13 animals, 14 hands), Hamed
Seyed-allaei −$33k (4Q, 16 animals). Two neither-losses (TinkerBotics,
Alex Kapend) still in the sample — early-land opportunity cost unchanged
as a secondary issue.

### New episodes since Aug-11 table (12 public)

| Episode | Opponent | Result | Money (us / opp) | Our BL | Opp land? | Opp animals? | Opp max hands | Opp Q |
| --- | --- | --- | ---: | ---: | :---: | :---: | ---: | ---: |
| 92112231 | Simon Ziegs | LOSS | 29,446 / 32,518 | 1 | yes | yes | 8 | 4 |
| 92109442 | Hamed Seyed-allaei | LOSS | 17,491 / 50,302 | 1 | yes | yes | 8 | 4 |
| 92101932 | Kers Aoyagi | LOSS | 17,079 / 131,865 | 1 | yes | yes | 14 | 3 |
| 92100177 | Bum_Fy_Mz | LOSS | 24,483 / 29,741 | 1 | yes | yes | 5 | 3 |
| 92089986 | danielle Ange | **WIN** | 23,070 / 1,123 | 1 | yes | yes | 2 | 3 |
| 92038005 | SuroRitch | **WIN** | 29,133 / 14,834 | 1 | yes | no | 5 | 3 |
| 91997037 | detectivseb | **WIN** | 29,305 / 23,291 | 1 | yes | yes | 9 | 2 |
| 91995143 | Palak Choudhary | LOSS | 19,459 / 30,279 | 1 | yes | yes | 12 | 4 |
| 91995071 | Ashray Bagde | **WIN** | 17,644 / 17,605 | 1 | yes | yes | 12 | 3 |
| 91990479 | Fahim Montasir | LOSS | 16,734 / 17,543 | 1 | yes | yes | 11 | 2 |
| 91956815 | Yuvraj singh | **WIN** | 15,100 / 14,609 | 1 | yes | yes | 10 | 3 |
| 91929478 | guoqin gu | **WIN** | 28,989 / 3,000 | 1 | no | no | 0 | 1 |

## Correction — 2026-08-13: “day-1 land” vs local day-15 was a config mismatch

Reconciled `docs/6_next_steps.md` item 1 against cached
`task_teacher_v5` ladder replays (`55425318`, 29 public) and local
`kaggle-environments==1.29.3`.

### Replay attribution

Kaggriculture JSON labels `BUY_LAND` on the **post-unlock** step (typically
day N+1 hour 0, hands already cleared). The decision cleared on the prior
hour. Prefer **cause-day** = observation immediately before
`n_unlocked` increases. `scripts/analyze_ladder_submission.py` now emits
`our_land_cause_*` fields.

### Measured cause-day (29/29 public)

| Field at cause obs | Value |
| --- | --- |
| day / hour | **0 / 23** (all 29) |
| money / hands / plants | **$1873 / 4 / 13** (identical across all 29) |

So the Aug-11 “day 1” wording was the post-unlock label; the gate actually
fires at **end of day 0**, once NW saturation (12) + min hands (3) + cash
($1000+$400) all clear.

### Why local eval showed day ~15

Live ladder `configuration` (from replay JSON) ≠ bare `make()` defaults on
pinned 1.29.3:

| Key | Local 1.29.3 default | Live ladder |
| --- | ---: | ---: |
| `startingMoney` | 2000 | **3000** |
| `farmHandCostMult` | 10 | **1** |
| `townShopSellInterval` | 2 | **4** |
| `townCenterSellInterval` | 6 | **24** |

With ladder-match config locally, v5’s cause-day is **0** (money ~$1873,
matches ladder). With 1.29.3 defaults, cause-day stays **~14–15** because
day-0 cash is only ~$810 (< $1400 bar).

### Consequence for v6

Under ladder-match config, `LAND_BUDGET_RESERVE_V6=2000` **does bind**:
10-seed probe → v5 cause-day 0×10; v6 cause-day 13–14. The earlier “v6 ≡
v5 locally” result was an artifact of evaluating against the wrong
episode defaults. Harness fix:
`kaggriculture_lib.env_config.tournament_configuration` +
`scripts/run_tournament.py` (default ladder-match; `--legacy-1293-defaults`
to opt out).
