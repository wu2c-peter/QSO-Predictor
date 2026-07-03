# OutcomeRecorder Schema v2 — Design

**Status:** DESIGN — not yet implemented
**Drafted:** 2026-07-01, WU2C + Claude
**Motivation:** `OUTCOME_ANALYSIS_2026-07.md`. v1 logs the scoring engine's view of each attempt but discards the tactical picture the operator actually saw — competition, rank, behavioral assessment, the tool's own predictions. v2 captures the *inputs to the decision*, plus a compact per-cycle trace enabling survival/hazard analysis.

## Governing principles

1. **Predictors are captured at select (or first TX), never only at the terminal event.** This is the path_at_select lesson generalized: competition measured when a QSO logs is competition after you won — biased.
2. **Every field maps to a named, testable hypothesis.** No hoarding.
3. **Capture copies values already computed for UI display.** No new computation in hot paths; no I/O except the single terminal-event write (existing behavior).
4. **Graceful absence.** Nulls are expected (behavior fields need bootstrap; SNR-at-target needs the target uploading). Absence never blocks capture.
5. **One schema epoch.** All v2 fields land in a single release. `SCHEMA_VERSION` bumps 1 → 2 (`outcome_recorder.py:35`); analysis scripts branch on `v`. v1's 547 events remain valid for the fields they have.

## New top-level scalar fields (at-select snapshot unless noted)

| Field | Type | Source | Hypothesis it tests |
|---|---|---|---|
| `success_prob` | int/null | PredictionWidget | **Calibration**: is QSOP's own prospect index predictive? Brier-style scoring. Note: widget explicitly documents this as "not a statistical probability" — calibration analysis either converts it into one or shows it needs rework. Highest-value field in v2. |
| `strategy` | str/null | StrategyWidget (`call_now`/`wait`/…) | Does following CALL NOW vs WAIT correlate with outcomes? |
| `competition_at_select` | int | target row (fixed parser) | Does target-side pileup size at decision time hurt conversion? |
| `competition_max` | int | running max during attempt | Peak pileup vs at-select pileup — which predicts better? |
| `local_callers_at_select` | int | local caller tracking | Local vs target-side competition are distinct phenomena (v2.2.0 split); which matters? |
| `my_rank_at_select` | int/null | PileupStatusWidget data | Does SNR rank among callers predict success — the loudest-first thesis applied to own station? |
| `my_snr_at_target` | int/null | SNR-at-Target feature | Quantifies "performance advantage": absolute signal at their end. |
| `best_rival_snr_at_target` | int/null | perspective data | Rank + margin: losing by 1 dB vs 15 dB are different situations. |
| `near_me_heard` | int/null | NearMeWidget (`_near_me_data`) | "Others near me are getting through" — does neighbor success predict own success (path proxy independent of own TX)? |
| `behavior_pattern` | str/null | BehaviorWidget | Does conversion differ vs Loudest-First / Methodical / Random targets? |
| `behavior_confidence` | int/null | BehaviorWidget | Weight for the above. |
| `behavior_source` | str/null | BehaviorWidget badge (live/historical/persona) | Does live observation outpredict persona inference? |
| `persona` | str/null | behavior predictor | Are Contest Ops actually harder for this station? |
| `target_state` | str/null | Target Activity State | Calling on fresh CQ vs mid-QSO vs idle. |
| `rec_reason` | int | `score_reason[rec_freq]` (terminal, alongside existing `rec_score`) | Does following a *proven* rec outperform a gap-based rec? The missing field from the v1 analysis. |
| `tier1_count_at_tx_bucket` | int/null | `_scoring_context` tier1_buckets (terminal) | Dose-response behind the reason-4 finding: 1 signal vs 3 at the TX bucket. |

## Per-cycle trace (nested array)

Enables survival/hazard analysis: per-cycle P(success | covariates), decay of expected value with cycles, whether WAIT-worthy conditions (thinning pileup, rising rank) actually materialize, effect of mid-attempt frequency moves.

```json
"trace": [
  {"c": 1, "rank": 3, "comp": 4, "lcall": 2, "path": "R", "t1": 1, "txf": 1831},
  {"c": 2, "rank": 2, "comp": 3, "lcall": 2, "path": "R", "t1": 1, "txf": 1831}
]
```

- `c` cycle number; `rank` own rank (null if unknown); `comp` target-side competition; `lcall` local callers; `path` compact code (H=Heard by Target, R=Reported in Region, N=Not Reported, X=No Reporters, T=Not Transmitting, ""=blank); `t1` tier-1 count at own TX bucket; `txf` TX audio offset Hz.
- **Compact path codes live on `PathStatus`**, not in the recorder: add a
  `compact_code` property to `local_intel/models.py::PathStatus` next to
  `display_label`/`short_label`, and derive the trace value via
  `PathStatus.from_display(...).compact_code`. Keeps the enum the single
  canonical mapping (per project convention) instead of an ad-hoc dict in
  `outcome_recorder.py`.
- **Hook (verified in clone 2026-07-01):** `OutcomeRecorder.on_status_update()` — rising-edge detection of the UDP Type 1 `transmitting` flag already increments `_tx_cycle_count` (`outcome_recorder.py` ~line 284, called from `main_v2.py:1208`). The trace append goes at that exact point. Values must be *passed in or read from already-current UI state* — no new queries.
- **Cap:** 40 entries; beyond that, append every other cycle (`c` values make gaps explicit). Median attempts are 4–5 cycles, so typical growth is a few hundred bytes/event; the 21-hour-selected-target outliers don't explode because the trace tracks TX cycles, not wall time.
- Trace supplements, never replaces, the at-select scalars. Static context stays top-level.

## Capture flow (verified against clone, 2026-07-01)

```
Select:   _set_new_target() → target_coordinator.py ~301
          → on_target_selected(call, grid, band, sfi, k, path_at_select, +NEW at-select dict)
          Recorder stores the at-select snapshot in instance state (pattern of _path_at_select).

Per TX:   UDP Type 1 → main_v2.py:1208 → on_status_update(transmitting)
          rising edge → _tx_cycle_count += 1  → +NEW trace append
          → +NEW running-max update (competition_max)

Terminal: record_outcome(trigger, snapshot)  ← main_v2.py:1053
          snapshot builder (main_v2.py ~955–1035) gains rec_reason + tier1_count_at_tx_bucket
          event dict (~outcome_recorder.py:407–440) merges at-select fields + trace, writes once.
```

**Open design choice:** extend `on_target_selected()`'s signature vs pass a single `tactical_snapshot: dict`. Recommend the dict — one parameter, forward-compatible, mirrors `record_outcome(trigger, snapshot)`.

## Verified capture sources (traced 2026-07-03)

All line numbers against main @ v2.5.7 (abf3d5d).

| Field | Verified source | Notes / null semantics |
|---|---|---|
| `success_prob` | **NEW** `InsightsPanel._last_prediction` — retain the `prediction` local in `refresh()` (insights_panel.py:1594-1599); capture `int(probability*100)` | Null when predictor failed / no target. **Do NOT use `local_intel_integration.get_prediction()`** — it recomputes with `PathStatus.UNKNOWN` and local-only competition (lines 436-476), i.e. NOT what the user saw. |
| `strategy` | **NEW** `InsightsPanel._last_strategy` — retain the `strategy` local (insights_panel.py:1601-1605); capture `.recommended_action` | Same caveat: the integration's `get_strategy()` getter recomputes differently. Clear both new attrs in `clear()`. |
| `competition_at_select` | `row_data.get('competition')` in the same target_coordinator block that reads `path_at_select` (~line 300), parsed with the paren regex | Third competition parser in the codebase (main_v2.py:983, insights_panel.py:1622) — consolidate into one helper as part of v2. |
| `competition_max` | recorder-internal running max, fed per cycle | — |
| `local_callers_at_select` | `mw.local_intel.session_tracker.get_pileup_info()['size']` (session_tracker.py:408) | 0 when getter returns None. |
| `my_rank_at_select` | `session_tracker.get_your_status()['rank']` (session_tracker.py:503) | Can be int, None, or `'?'` (in pileup, own signal not decodable) — map non-int → null. |
| `my_snr_at_target` | `row_data.get('my_snr_at_target')` (set by analyzer/core.py:1010) | Null when target hasn't uploaded spots of us. |
| `best_rival_snr_at_target` | **Needs a ~3-line analyzer addition**: the tier1/tier2 competition loop (analyzer/core.py:1029-1038) already reads each rival spot's `snr` for the strong-QRM flag but discards it; track the max → `decode_data['best_rival_snr']` | Only field not already computed. Alternative: drop from v2. |
| `near_me_heard` | `InsightsPanel._near_me_count` (set in `update_near_me`, insights_panel.py:1655) | 0 means both "none heard" and "never updated" — acceptable, documented. |
| `behavior_pattern` / `behavior_confidence` / `behavior_source` | `session_tracker.get_target_behavior()` → `bayesian_style` / `bayesian_confidence` / `bayesian_source` (session_tracker.py:485-501) | Canonical source is the getter (what BehaviorWidget renders). Null when no target session. |
| `persona` | same getter → `bayesian_metadata` dict | Metadata dict verified present; exact persona key inside it to confirm at implementation. |
| `target_state` | `mw._target_activity_state` (updated in target_coordinator.py:440-490) | Values: unknown/idle/active states; capture with `_target_activity_other` optional. |
| `rec_reason` | `band_map.score_reason[rec_freq]` — same guard pattern the snapshot builder already uses for tx_freq (main_v2.py:968-971) | Terminal capture, trivial addition. |
| `tier1_count_at_tx_bucket` | `band_map._scoring_context['tier1_buckets']` (band_map_widget.py:673; `bucket_size` in same dict) | Key verified; per-bucket lookup shape to confirm at implementation. |
| trace `txf` | `status['tx_df']` from the UDP status already flowing through `handle_status_update` | — |
| trace `rank`/`comp`/`lcall`/`path`/`t1` | same sources as their at-select scalars, read at TX rising edge | `path` via **NEW** `PathStatus.compact_code` property. |

**Trace hot-path design:** `on_status_update()` is called on *every* status
message (many/sec), pre-throttle (main_v2.py:1208). Building a snapshot dict
per message would be wasteful. Pass a zero-arg callable instead —
`on_status_update(transmitting, cycle_context_fn=...)` — which the recorder
invokes only on the rising edge (~once per 15s TX cycle).

## Pre-implementation checklist (per WU2C code-quality checklist)

- [x] For each scalar: grep the exact attribute/structure holding the value at select time; confirm readable from `target_coordinator` scope without recomputation. **Done 2026-07-03 — see "Verified capture sources" table above.** One exception flagged: `best_rival_snr_at_target` needs a small analyzer addition.
- [ ] Confirm data flow summary above with Peter before writing code.
- [ ] Trace one full path mentally: select → 3 TX cycles → QSO logged → written event contains all fields.
- [ ] Null-handling in every branch; a missing widget or hidden panel must degrade to null, never raise (follow the IONIS capture's defensive try/except + isVisible pattern, `main_v2.py` ~993–1009).
- [ ] Verify event size on a real logged event; document measured bytes/event.
- [ ] `py_compile` every touched file.
- [ ] Update this doc → rename to `OUTCOME_SCHEMA.md` as the living schema reference (field, type, capture point, null semantics) when implemented.
- [ ] Ship UX changes in separate commits from the schema change so the schema-epoch boundary is a clean tag.

## Explicitly out of scope

- Per-decode or per-second time series (event bloat; separate opt-in log if ever needed).
- Retrofitting v1 events.
- Score decay (deferred, unchanged).
- Using these fields *in scoring* — v2 is instrumentation only; algorithm changes come after the data speaks.
