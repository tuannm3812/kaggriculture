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
