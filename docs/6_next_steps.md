# 6. Next Steps

Rolling submit/wait recommendation, per `docs/0_coding_standards.md` §5.

## Current Recommendation (2026-08-02)

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

Still not submitted to the ladder — re-ask before submitting or continuing
to delay, per the standing rule from earlier (design doc §9's execution-
status audit).

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
9. **`task_teacher_v3`** (per the construction sequence: ongoing crops —
   Tomato/Strawberry — and fertilizer timing; no animals in this version).
   Needs the ongoing-crop ROI ranking deferred in `docs/3_agent_strategy.md`
   resolved first, or as part of this version — specifically a
   season-length assumption for a fair ROI/day comparison against one-time
   crops (ongoing crops run for the rest of the season with no fixed
   lifespan). Feed-cost accounting is a separate, animal-specific concern
   (Goose/Cow/Sheep consume wheat) that doesn't apply to Tomato/Strawberry
   and is out of scope until a version adds animals.
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
