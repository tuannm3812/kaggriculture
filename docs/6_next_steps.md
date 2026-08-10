# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-10)

**Stay on `task_teacher_v2` for the ladder.** Do **not** submit `task_teacher_v4`.

After buy-cap fix + `NW_SATURATION_PLANTS` 18→12: acceptance shows
`BUY_LAND=100/100` episodes and ~28k mean vs starter, but the 20-pair
screen vs `task_teacher_v2` is still `win_rate=0.000`, Hoeffding CI
`[0.000, 0.380]` — **not promoted**. Land works; Goose+NE still lose to
v2's NW Melon/hire play. See `docs/4_agent_version_log.md`.

**Next engineering priority:** diagnose opportunity cost of the Goose loop
(FEED labor, egg ROI vs Melon tiles, near-absent CARE) — not further land
threshold chasing.

## Prior Recommendation (2026-08-02)

`task_teacher_v2` is the new local champion — adds daily hiring and
bounded exhaustive multi-unit assignment on top of `task_teacher_v1`. This
supersedes an earlier, self-identified process error: the first pass
declared v2 "provisionally" champion from an 8-pair local tournament
(0.875 win rate, positive margin) without a confidence interval, which
Codex's 2026-08-02 review correctly flagged as both short of the
authoritative promotion gate (design doc §6) and built on top of a real
bug — a hiring-value fix that was correct in `tasking.py` but never
actually wired into `agents/task_teacher_v2/main.py`'s call site.

After fixing the wiring bug (test-first regression test, then the one-line
call-site fix) and re-running the acceptance gate (100 episodes, 100%
`DONE`/finite, all 25 tiles worked every episode), a second Codex review
round caught two more issues: an end-of-day hiring-timing bug (a hire
queued on the day's last hour is guaranteed zero future actions before
hands clear at the day boundary) and a percentile-bootstrap confidence
interval that gave false `[1.000, 1.000]` certainty on all-win samples.
Both fixed test-first (`agents/task_teacher_v2/main.py`'s
`_count_immediately_completing_tasks` and `future_action_turns`;
`scripts/run_tournament.py::hoeffding_ci` replacing `bootstrap_ci`). The
full paired evaluation, re-run with the corrected interval: 20-pair screen
vs. `task_teacher_v1` (1.000 win rate, CI `[0.620, 1.000]`), then the
50-pair promotion gate (0.970 win rate, CI `[0.730, 1.000]` — wholly above
0.50), plus 20-pair regression screens vs. `roi_teacher_v3` and `starter`
(both 1.000, CI `[0.620, 1.000]`). A third Codex review round then found
one further narrow defect in the same helper (a seedless `PLANT` assignment
was counted as completing this turn when it wouldn't actually resolve
without a held seed); fixed test-first, and refreshed acceptance/screen
telemetry showed no material change, so the 50-pair promotion evidence
above stands unchanged. A fourth Codex verification round then confirmed
no further correctness blocker and closed the v2 correctness review,
while flagging five documentation-precision and pre-BC measurement items
(addressed below, items 8-9 and 14-15) — none reopen promotion. See
`docs/4_agent_version_log.md` for full numbers.

**Submitted to the ladder 2026-08-06** — explicitly authorized by the user,
whose stated goal is to keep working while an agent is actively competing
rather than wait for a "final" one. The submission then showed
`SubmissionStatus.ERROR`; root-caused to a real packaging bug (an
unrelated Elite Replay EDA module was being silently bundled into every
agent's submission artifact and hard-failing on Kaggle's actual runtime
version) — see `docs/4_agent_version_log.md`'s 2026-08-06 incident entry
for the full diagnosis and fix (`fix/package-agent-scope-shared-modules`).
Fixed test-first, full suite clean (297 passed), re-packaged and
resubmitted. `task_teacher_v3` and the elite-replay EDA/BC/PPO work
continue in parallel and may produce later resubmissions.

**Ladder replay analysis (2026-08-06/07)** — see
[`docs/8_ladder_replay_analysis.md`](8_ladder_replay_analysis.md) for full
detail. Record as of writing: 8W-11L (19 real episodes), `publicScore`
488.9 and declining. Three deep-analyzed replays show win/loss splitting
almost entirely on whether the opponent bought land and used animals —
`task_teacher_v2` has never issued a `BUY_LAND` or `BUY_ANIMAL` order and
caps out at 4-5 hired hands regardless of opponent, while ladder opponents
who expand to the full board and add animals pull decisively ahead
starting around day 10-13. Against similarly land/animal-less opponents,
`task_teacher_v2` still wins convincingly, so this is a scope gap, not a
tactical-execution regression. **Recommendation: prioritize land
purchase + animal husbandry (deferred out of both v2 and v3) as the next
version's scope**, ahead of further single-quadrant refinement — see the
analysis doc for the full reasoning and caveats.

## Elite Replay EDA Gate (2026-08-02)

The decision report is [`docs/7_elite_replay_eda.md`](7_elite_replay_eda.md).
All five attributed notebook sources are currently quarantined: no normalized
public trajectory JSONL is available, three sources also declare an incompatible
`1.32.2` runtime, and no pinned-runtime `task_teacher_v2` comparison trajectory
was supplied. The report therefore records
`REJECT: insufficient compatible evidence` for all six strategy questions and
the EDA/data gate does not pass.

Only these replay/teacher follow-ups are supported by the measured result:

1. Obtain or reproduce normalized public episode decisions with their existing
   manifest attribution, then run the `1.29.3` compatibility gate; keep every
   unavailable or incompatible source quarantined with its reason codes.
2. Generate attributed `task_teacher_v2` comparison trajectories under pinned
   `1.29.3`, both seats and multiple opponent families, then rebuild the
   coverage table. This is an evidence task, not authorization to change the
   teacher.
3. Package a public policy as a frozen benchmark only after its normalized tape
   passes compatibility; none is approved from the present notebook-authored
   descriptions alone.

Do not begin BC collection or infer land, portfolio, labor, terminal, or
opponent-policy changes until the report's compatible-evidence decisions are
reviewed and the EDA/data gate explicitly passes.

## Immediate Next Tasks

1. ~~Packaging step~~ — done 2026-08-01.
2. ~~v2 (roi) — add Melon~~ — done 2026-08-01.
3. ~~v3 (roi) — season-horizon gate~~ — done 2026-08-01.
4. ~~Kaggle platform smoke test~~ — done 2026-08-01.
5. ~~Version-gap check (`1.29.3` vs `1.32.2`)~~ — done 2026-08-01.
6. ~~Multi-tile task/route teacher (`task_teacher_v1`)~~ — done 2026-08-01.
7. ~~`task_teacher_v2` (hiring + multi-unit assignment)~~ — done 2026-08-02.
   See `docs/4_agent_version_log.md`.
8. ~~Investigate `task_teacher_v2`'s occasional losses to `task_teacher_v1`~~
   — done 2026-08-02: the confirmed hiring-wiring bug (existing hands'
   capacity never reached `should_hire`) explains a real, confirmed portion
   of the originally-observed losses, though Codex's 2026-08-02 verification
   correctly noted the remaining ~5% (20-pair) and ~3% (50-pair) loss rates
   *after* all three fix rounds aren't fully attributable to that bug alone
   — some may be ordinary variance or a separate, unmeasured inefficiency.
   Fixed; the 50-pair promotion gate gave a (corrected, Hoeffding) CI
   `[0.730, 1.000]`, still not a perfect sweep but decisively above 0.50.
   The remaining loss rate could still be profiled further (same
   hiring-risk-vs-fallback-inefficiency question, item 15 below) if it
   matters before BC teacher selection, but is no longer a promotion
   blocker.
9. **`task_teacher_v3`** (ongoing crops — Tomato/Strawberry; no animals).
   **Built and §8-fixed by Cursor; evaluated twice; not promoted.**
   2026-08-06 buggy formula lost the vs-v2 screen (`win_rate=0.025`);
   2026-08-07 corrected `lifespan_days = reachable[-1] + 1` and re-ran
   Task 9: acceptance clean, but vs-v2 is exact identity
   (`win_rate=0.500`, margin `+0.0` at 20 and 50 pairs — Melon still
   outranks corrected Tomato/Strawberry whenever feasible), so the
   promotion CI never clears above 0.50. Regression vs. `roi_teacher_v3`
   / `starter` remains 1.000. `task_teacher_v2` remains
   `competitive_champion` and the submitted ladder agent. See
   `docs/4_agent_version_log.md`. Fertilizer / animals remain out of
   scope until a later version (handoff: land/animals need a v4 design
   doc first — `docs/8_ladder_replay_analysis.md`).
10. **Critical-path test coverage** — done for economy math, agent decision
    logic (`roi_teacher_*`, `task_teacher_v1`, `task_teacher_v2`), the
    tournament harness, and packaging. Extend to `task_teacher_v3`'s
    ongoing-crop/fertilizer logic once it exists.
11. **Confirm submission-slot / ladder-tracking rules** (open item since
    `docs/1_competition_instructions.md`): check `kaggle competitions
    submissions kaggriculture` behavior and the Rules page once a submission
    exists.
12. **Confirm actual ladder episode configuration** (open item since
    `docs/2_environment_notes.md`): whether scored games vary `boardSize`/
    `episodeSteps`/etc. from defaults — relevant to whether the design doc's
    conditional C5 robustness stage is worth its GPU budget later.
13. **Week-1 throughput benchmarking** (per the design doc's Codex
    resolution): env-only steps/sec is measured (~1000–1100/sec, see
    `docs/2_environment_notes.md`); policy-inference and training steps/sec
    at multiple parallel-env counts, and checkpoint write/load time, are not
    yet measured — needed before any BC/PPO evaluation-size commitment.
14. ~~Measurement gate before selecting v2 as the BC teacher: calibrate
    `tasking.py`'s hiring constants from real data~~ (Codex's 2026-08-02
    §16 item 4) — **measured 2026-08-02** (20 episodes, seeds 21000–21019,
    `task_teacher_v2` vs. `starter`):

    | Constant | Assumed | Measured | |
    | --- | ---: | --- | --- |
    | `TRAVEL_ALLOWANCE` | 4 | mean 7.51/unit/day, max 19 | ~1.9x higher |
    | `END_OF_DAY_RESERVE` | 2 | mean 1.23/unit/day, max 21 | roughly in range on average, high variance |
    | `AVERAGE_VALUE_PER_RECOVERED_ACTION` | 15.0 | mean $65.26/action, range [$57.86, $72.17] | ~4.3x higher |

    `TRAVEL_ALLOWANCE` and `AVERAGE_VALUE_PER_RECOVERED_ACTION` are both
    substantially underestimated versus real play. `TRAVEL_ALLOWANCE`'s gap
    is corroborated independently by item 15's measurement below (greedy
    fallback travels ~3 extra tiles/turn versus optimal — travel really
    is a bigger real cost than assumed).

    **Attempted and reverted, 2026-08-02:** recalibrated to `8` and `65.0`
    respectively, ran the required full fix-test-reevaluate cycle, and it
    made things measurably worse — win rate vs. `task_teacher_v1` dropped
    from 0.970/CI `[0.730, 1.000]` to 0.750/CI `[0.510, 0.990]` over 50
    pairs (declining monotonically as sample size grew: 1.000 → 0.850 →
    0.750, the signature of a real effect). The higher $/action drove much
    more aggressive hiring (flat 7 hands, ~111 orders/episode vs. the
    original ~71), whose real costs (fibonacci hire-cost escalation, more
    greedy-fallback travel inefficiency at higher unit counts) weren't
    reflected in a $/action figure measured under the calmer, original
    hiring regime. Reverted both constants; confirmed the revert restores
    the original, already-verified promotion evidence. See
    `docs/4_agent_version_log.md` for the full account. **Naive
    single-shot recalibration of a constant that feeds back into the
    behavior it was measured from doesn't work — any future attempt needs
    to validate at the new operating point the recalibration itself
    induces, not just the point it was measured at.**
15. ~~Measurement gate before selecting v2 as the BC teacher: quantify the
    exhaustive-vs-greedy assignment-quality gap~~ (Codex's 2026-08-02 §16
    item 5) — **measured 2026-08-02** (30 episodes, seeds 20000–20029,
    1086 real states with >4 units captured, each compared against the
    true exhaustive optimum via the newly-factored-out
    `tasking._exhaustive_assign`):

    | Metric | Result |
    | --- | --- |
    | Exact match with exhaustive optimum | 74/1086 (6.8%) |
    | Tier-coverage loss vs. optimum | mean 0.000, max 0 |
    | Expected-value loss vs. optimum | mean $0.000, max $0.0 |
    | Extra travel distance vs. optimum | mean 3.089 tiles/turn, max 17 |

    The greedy fallback almost never picks the *exact* exhaustive-optimal
    assignment, but achieves **identical** priority-tier coverage and
    expected value every single time — the entire measured gap is extra
    travel distance, not lost economic coverage. This is a reassuring
    result: behavioral cloning from v2 wouldn't be learning a
    systematically worse economic policy from the fallback, just a
    somewhat less travel-efficient one. Worth revisiting if v3+ adds units
    where travel cost compounds further. Not a promotion blocker; a
    BC-teacher-readiness gate, and this item's finding argues *against*
    urgency on a smarter bounded algorithm.
