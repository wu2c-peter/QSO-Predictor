# QSO Predictor Session Notes
**Date:** April 12, 2026  
**Version:** 2.5.0  
**Session:** Regional consensus scoring, suspicious gap detection, score tooltips, score decay analysis

---

## Design Discussion: Conditions at the Target

### The Insight

Peter raised a key question about the quality of evidence at each tier level:

**Tier 1 (target's own decodes):** Presence is strong evidence (proven decode path). But absence is ambiguous — no decodes at a frequency could mean clear air OR local QRM at the target. The scoring already handled this correctly ("proven > empty" principle).

**Tier 2/3 (regional reporters):** The critical insight is that **multiple independent reporters provide statistical power that a single reporter cannot**. Any single FT8 receiver can only decode a limited number of signals per 15-second cycle. One reporter's silence at a frequency is a sample; five reporters' silence is a consensus. The aggregate from multiple regional stations "fills in" the picture that any individual station's decoder ceiling would miss.

**Tier 4 (global):** Gaps in global data are the weakest signal — "nobody worldwide is transmitting much here" reduces QRM probability but doesn't eliminate local interference at the target. Treated as a weak positive.

### The Problem with the Old Scoring

The old Step 5 treated every tier2/tier3/global spot as a flat penalty (20/15/8 points). This had three weaknesses:

1. **Reporter count ignored:** Five spots from one reporter vs. one spot each from five reporters produced identical congestion penalties, despite very different evidential meaning.

2. **Tier 2/3 used only as penalty, never as positive evidence:** An unproven gap (score 70) could outrank a slot where multiple regional reporters confirmed low density (score 55 after penalties) — which is backwards.

3. **No suspicious gap detection:** Empty slots flanked by heavy Tier 1 activity scored the same as empty slots in quiet regions, despite the former being much more likely to indicate hidden QRM.

---

## Features Implemented

### 1. Reporter-Count Confidence (Step 4b)

New analysis step counts distinct reporters per 60Hz frequency bucket and total regional coverage across Tier 2/Tier 3:

- `regional_bucket_reporters`: bucket → set of reporter callsigns
- `regional_bucket_signals`: bucket → total signal count
- `all_regional_reporters`: total distinct reporters (the "coverage" measure)
- `regional_coverage`: total distinct reporters — used as continuous confidence input (reporters/6)

**Rationale:** In FT8, every receiver decodes the entire passband simultaneously. If a reporter is active (uploading spots from any frequency), they would have decoded and reported anything decodable at any frequency. Absence in their reports IS evidence of absence.

### 2. Regional Consensus Scoring (Step 5b)

Replaces the flat penalty system with continuous confidence-based scoring. No hard threshold — confidence scales smoothly from 0 to 1 based on reporter count, and downstream thresholds (Step 7b's ≥65) naturally gate recommendations.

**Continuous confidence function:** `confidence = min(1.0, regional_coverage / 6.0)`

**Quiet slots** (no signals, no congestion): `score = 50 + confidence * 32`
- 0 reporters → 50 (baseline, no data)
- 1 reporter → 55 (weak signal)
- 2 reporters → 61 (approaching useful)
- 3 reporters → 66 (crosses 65 recommendation threshold)
- 6+ reporters → 82 (strong consensus)

**Light activity** (≤2 signals, ≥2 reporters): **72**

**Congested:** 25–55 (based on congestion severity)

### 3. Suspicious Gap Detection (Step 5c)

Post-processing step that dampens scores for empty slots flanked by heavy Tier 1 activity:

- Computes `tier1_adjacency`: sum of Tier 1 signals in neighboring buckets (~180Hz each side)
- Threshold: `adj_count ≥ 4` triggers dampening
- Dampening: 6% at adj=4, up to 30% at adj=8+
- Effect: A "regionally validated quiet" score of 78 dampens to 64 when flanked by tier1 — below the Step 7b recommendation threshold of 65, preventing the operator from being directed into probable QRM.

### 4. Regional Consensus Recommendation Path (Step 7b)

New decision path between proven candidates (Step 7) and blind gap-finding (Step 8):

- Triggers when: no proven candidates AND any regional reporters exist
- Uses numpy argmax on masked score_map to find best slot
- Threshold: best regional score ≥ 65 to recommend (self-regulating — requires ~3+ reporters for quiet slots to cross)
- Hysteresis: move only if best exceeds current by 12+ points
- If current position scores ≥ 65 regionally, holds position

**Key design:** No hard `regional_coverage >= 3` gate. The continuous confidence curve in Step 5b encodes reporter count into the score itself. The ≥65 threshold naturally requires ~3 reporters before a quiet slot qualifies. This eliminates a cliff in scoring behavior at the threshold boundary.

---

## Score Hierarchy (Updated)

| Rank | Condition | Score | Notes |
|------|-----------|-------|-------|
| 1 | Proven tier1, 1 signal | 100 | Unchanged |
| 2 | Proven tier1, 2 signals | 95 | Unchanged |
| 3 | Proven tier1, 3 signals | 90 | Unchanged |
| 4 | Regional quiet (6+ reporters) | 82 | **NEW** — continuous |
| 5 | Regional light (≥2 reporters) | 72 | **NEW** |
| 6 | Regional quiet (4 reporters) | 71 | **NEW** — continuous |
| 7 | Proven tier1, 4 signals (crowded) | 70 | Unchanged |
| 8 | Regional quiet (3 reporters) | 66 | **NEW** — crosses rec threshold |
| 9 | Regional quiet (2 reporters) | 61 | **NEW** — below rec threshold |
| 10 | Light congestion | 55 | Similar |
| 11 | Regional quiet (1 reporter) | 55 | **NEW** |
| 12 | Baseline (0 reporters, quiet) | 50 | **Was 70** |
| 13 | Suspicious gap (adj=4+) | dampened 6-30% | **NEW** |
| 14 | Moderate congestion | 45 | Similar |
| 15 | Heavy congestion | 25-35 | Similar |
| 16 | Local QRM | 10 | Unchanged |
| 17 | Edge/hound zone | 0 | Unchanged |

---

## Analysis: Score Decay (Backlog Item — Deferred)

### What was evaluated

The backlog item "Score decay by recency/stability — per-station decode history, freshness half-life, SNR stability" was analyzed against the current codebase.

### What already exists

Spots have age-based decay: 1.0 for <14s, 0.8 for <29s, fading to 0 by 60s. The scoring uses `decay > 0.3` or `> 0.4` as inclusion thresholds. Spots expire entirely after 60 seconds.

### Assessment

**Temporal decay within the 60-second window adds marginal value because:**

1. The window already covers only ~4 FT8 cycles. A 45-second-old observation is 3 cycles ago — still relevant since propagation rarely shifts that fast.

2. Reporter-count confidence (implemented above) provides **spatial stability** that captures most of the same information as temporal stability. Five reporters confirming a quiet slot in the current cycle is at least as strong a signal as one reporter confirming quiet across four consecutive cycles.

3. The existing 60-second expiry already handles propagation shifts. If finer response is needed, lowering the window to 45 seconds or adjusting the decay threshold (0.3 → 0.4) is a simpler intervention.

**Where temporal decay might still help:**

- Rapid band openings/closings where the picture changes within 2-3 cycles
- Weighting very recent spots higher to make the recommendation more responsive

**Recommendation:** Defer as incremental. If implemented later, the natural insertion point is the decay threshold checks in Step 5 (currently `> 0.3`). The in-code NOTE documents this for future reference.

---

## Files Modified

| File | Changes |
|------|---------|
| `band_map_widget.py` | Steps 4b, 5 (5a/5b/5c), 7b in `_calculate_best_frequency()`, updated docstring, score reason tooltips |

---

## Score Reason Tooltips (v2.5)

### Why

With three new scoring concepts (regional consensus, suspicious gaps, reporter coverage), the score graph became harder to interpret. A colored line and a number don't tell the operator *why* a frequency scored the way it did.

### Implementation

- **`score_reason` array** (int8, parallel to `score_map`): stores a reason code per Hz
- **`_scoring_context` dict**: saved at end of scoring — tier1_buckets, regional_bucket_reporters counts, regional_coverage, tier1_adjacency. Used by tooltip to add detail.
- **`_score_reason_tip(freq)` method**: maps reason code + context → human-readable string
- **`mouseMoveEvent` extended**: detects cursor in score graph section (using saved section geometry from `paintEvent`), shows tooltip with score + reason

### Tooltip Examples

| Hover Position | Tooltip |
|----------------|---------|
| Proven slot | `95  @1440 Hz — Proven: 2 signal(s) decoded by target` |
| Regional quiet (5 rptrs) | `76  @1800 Hz — Regional quiet: 5 reporter(s) in area, clear` |
| Regional quiet (1 rptr) | `55  @1800 Hz — Regional quiet: 1 reporter(s) in area, clear` |
| Regional light | `72  @1200 Hz — Regional light: 2 signal(s), 4 reporters` |
| Suspicious gap | `44  @1500 Hz — Suspicious gap: flanked by 5 target decodes` |
| No data | `50  @2000 Hz — No data` |
| Local QRM | `10  @1700 Hz — Local QRM (your receiver)` |
| Edge | `0  @100 Hz — Band edge` |

### Reason Codes

| Code | Label | Meaning |
|------|-------|---------|
| 0 | unscored | Default baseline / no regional data |
| 1 | edge | Band edge zone |
| 2 | hound | Fox TX zone in Hound mode |
| 3 | local_qrm | Local signal interference |
| 4 | proven_ideal | Tier1, 1-3 signals |
| 5 | proven_crowded | Tier1, 4+ signals |
| 6 | regional_quiet | Reporters active, no signals here |
| 7 | regional_light | Few signals, multiple reporters |
| 8 | congestion | Congested area |
| 11 | suspicious_gap | Flanked by heavy Tier1 activity |

---

## Testing Notes

### Scenarios Verified (Logic Trace)

| Scenario | Expected Score | Verified |
|----------|---------------|----------|
| 5 reporters, quiet slot | 78.3 | ✅ |
| 3 reporters, 2 signals from 2 reporters | 72 | ✅ |
| 1 reporter, quiet | 60 | ✅ |
| Suspicious gap (adj=6) | 78.3 → 64.2 | ✅ |
| All scores zero (edge case) | argmax guarded by ≥65 | ✅ |

### Needs Live Testing

- Verify score graph visualization reflects new scoring (should auto-work via score_map)
- Confirm Step 7b correctly takes over from gap-finding when regional data is available
- Check that suspicious gap dampening doesn't overly penalize legitimate clear slots
- Edge case: target in a grid with many PSK Reporter uploaders vs. sparse grid
- **Hover over score graph** — verify tooltips show correct reason for various frequency slots
- **Tooltip in all three sections** — perspective bars, score graph, local bars should all show appropriate tooltips without interfering

---

## Deployment Checklist

- [ ] Download `band_map_widget.py` from outputs
- [ ] Replace in local repo
- [ ] Test with live MQTT data — observe score graph behavior
- [ ] Verify no regression in proven (tier1) frequency recommendations
- [ ] Watch for scenarios with ≥3 regional reporters to confirm consensus scoring activates
- [ ] Commit when satisfied
- [ ] Consider version bump (v2.5.0 given scoring engine significance?)

---

**73 de WU2C**
