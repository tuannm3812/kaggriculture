# Elite Replay EDA

Generated deterministically from the attributed manifest, normalized decisions, and pinned-runtime compatibility report.

## Evidence accounting

- Manifest sources: 5.
- Eligible public sources: 0.
- Quarantined public sources: 5.
- Compatible normalized turns: 0 (elite=0, teacher=0, repaired=0).
- Summarized episodes: 0.
- Notebook-authored descriptions are contextual evidence only. They are not counted as `1.29.3`-compatible executed measurements unless a normalized trajectory passes `elite_compatibility.csv`.
- All manifest sources are listed in `replays/analysis/elite_compatibility.csv`; exclusions and stable reasons are listed in `replays/analysis/elite_quarantine.csv`.

## Interpretation boundary

The CSVs describe observed states, actions, and next-bank changes. They do not assign causal proceeds or costs to simultaneous actions. Empty measured tables mean the required normalized evidence was unavailable; notebook prose and embedded outputs are not silently substituted.

Coverage-table scalar distances are signed median differences divided by the larger source IQR (with a one-unit floor). Categorical distances are Jensen-Shannon distances after normalizing both sources on their common union support; no distance is emitted when either source has zero total support.

## Capital and expansion

Evidence: `elite_daily.csv`, `elite_episode_summary.csv`, and `elite_coverage_gap.csv`. No complete compatible elite-versus-teacher episode pair is available.

Decision: REJECT: insufficient compatible evidence

## Portfolio and market

Evidence: `elite_source_comparison.csv` and `elite_coverage_gap.csv`. No complete compatible elite-versus-teacher episode pair is available.

Decision: REJECT: insufficient compatible evidence

## Labor and routing

Evidence: `elite_daily.csv`, `elite_episode_summary.csv`, and `elite_coverage_gap.csv`. No complete compatible elite-versus-teacher episode pair is available.

Decision: REJECT: insufficient compatible evidence

## Storage and terminal

Evidence: `elite_source_comparison.csv` and `elite_coverage_gap.csv`. No complete compatible elite-versus-teacher episode pair is available.

Decision: REJECT: insufficient compatible evidence

## Opponent and seat

Evidence: `elite_episode_summary.csv` and `elite_source_comparison.csv`. No complete compatible elite-versus-teacher episode pair is available.

Decision: REJECT: insufficient compatible evidence

## Coverage gap

Evidence: `elite_source_comparison.csv` and `elite_coverage_gap.csv`. No complete compatible elite-versus-teacher episode pair is available.

Decision: REJECT: insufficient compatible evidence

## Quarantine accounting

Stable reason counts: `missing_episode`=5, `version_mismatch`=3.

## Gate outcome

The EDA/data gate does not pass. BC collection remains blocked until compatible elite and teacher evidence supports the required strategy and coverage decisions.
