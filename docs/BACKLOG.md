# QSO Predictor — Backlog

Lightweight backlog of items worth doing but not yet scheduled. Items are grouped by intent, not by priority within groups. See `SESSION_NOTES_*` (in this folder) for context on specific items.

For the active development roadmap (Hunt Mode, multi-source spot collector, etc.), see the main project context documents and GitHub Issues.

---

## Documentation

### Wiki install instructions need the same update as README/USER_GUIDE

The GitHub Wiki Home page still shows Windows-only install with Mac/Linux as "from source." Same fix pattern applied in the in-repo docs should be mirrored to the Wiki. Wiki is maintained outside the normal commit flow so this needs a separate manual edit on GitHub.

**When to do it:** Next time the Wiki is being edited for any other reason.

---

## Code Quality

### OutcomeRecorder crash-resilience (pending in-memory state)

OutcomeRecorder currently holds all pending session state in memory (`_current_target`, `_pending_session`, snapshot variables). A mid-QSO crash — Windows update, app crash, power loss — loses that target's outcome record. Not catastrophic (outcome data is a best-effort performance signal, not a QSO log), but worth considering if crashes ever prove non-rare.

**Design sketch:** Minimal write-to-disk of `_pending_session` and active snapshot on target selection; delete on clean outcome recording. Insertion point: `outcome_recorder.py` around the `_pending_session` assignment.

**Blocker:** None. **Priority:** Low. Only worth doing if we see evidence of actual data loss.

**Context:** Surfaced during v2.5.3 diagnostic session (`SESSION_NOTES_2026-04-17_v2.5.3.md`). That session found `pending_observations.jsonl` — a *different* file — and deleted it; this backlog item is about whether OutcomeRecorder should have its own (properly designed) on-disk pending state.

---

## Data Quality (OutcomeRecorder)

### `elapsed_s` outliers from idle-selected targets

Analysis of real outcome history shows ~9% of records have `elapsed_s > 1 hour`, with the worst being 21+ hours. These are "target selected, app left idle overnight" cases, not actual hour-long calling attempts (`tx_cycles` for these records is 5–32, consistent with a short attempt that then sat in state).

**Why it matters for Phase 2:** Any analysis using `elapsed_s` as a feature will be skewed without filtering.

**Options:**
1. Filter at read-time in Phase 2 analysis (`elapsed_s < 3600`)
2. Clip at write-time in OutcomeRecorder (cap at 1 hour before writing)
3. Flag outliers as suspect at write-time (add an `idle_outlier: true` field)

**Recommendation:** Option 3 preserves the raw data while making filtering trivial. Decision needed before Phase 2 dashboard work starts.

### ~20% of outcome records have blank `target_continent` and `distance_km=null`

Affects roughly 13 of 65 records in the April sample. Likely manual-entry targets where the grid lookup cascade (receiver cache → call_grid_map → decode table → DXCC prefix) returned no result, or a bug in the continent resolver.

**Why it matters:** Phase 2 stratification by continent/distance won't work for a fifth of records.

**Investigation needed before fix:** Reproduce with a manual-entry callsign and trace where the resolver returns empty. May be a legitimate "no grid available" case that should be handled gracefully rather than a bug.

---

## Features (from project context, tracked here for consolidation)

These are documented in the main project context as active backlog — listed here so BACKLOG.md is a single reference:

1. Hunt Mode frequency display in alerts
2. TX cycle conflict detection
3. Multi-source spot collector (PSK Reporter MQTT + RBN telnet + DX Cluster telnet; WSPRnet excluded)
4. "Worked before on other modes" — cross-reference `wsjtx_log.adi` against DX Cluster spots
5. A-index display (separate NOAA endpoint)
6. Email QSL on QSO logged (UDP Type 5)
7. Self-eval dashboard (Phase 2, on-demand analysis of OutcomeRecorder data)
8. Operator coaching/trainer from outcome data

---

## Open Design Questions to Observe

Not yet reproducible enough to diagnose — monitor over multiple operating sessions before treating as bugs:

### Green recommendation line sometimes misses visually obvious better positions

Smooth transition lag (40% per tick) and hysteresis (+15 point threshold to move) are likely candidates. Don't diagnose from a single session — watch across varied conditions.

### Band map color scheme redesign

Mute local decode colors to neutral/grey, strengthen Tier 2/3 hue distinction, push Tier 4 further into background, free one visual dimension from redundant SNR encoding on local bars. Design work needed before implementation.
