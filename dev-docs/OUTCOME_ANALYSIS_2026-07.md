# Outcome Data Analysis — July 2026

**Dataset:** `~/.qso-predictor/outcome_history.jsonl`, schema v1
**Coverage:** 2026-04-13 through 2026-07-02 UTC — 547 outcome events, 101 sessions
**Analyzed:** 2026-07-01, WU2C + Claude
**Status of findings:** Observational, single-operator, single-station. Correlations, not proven causation. See Caveats.

---

## Headline results

Overall conversion: 143 QSO_LOGGED (26.1%), 23 RESPONDED-not-logged (4.2%), 381 NO_RESPONSE (69.7%).

### 1. Path status at select is the dominant predictor

| path_at_select | n | Success (responded or logged) | QSO logged |
|---|---|---|---|
| Heard by Target | 51 | **76%** | 61% |
| Reported in Region | 108 | **47%** | 43% |
| No Reporters in Region | 88 | 22% | 22% |
| (blank — capture gap) | 112 | 21% | 17% |
| Not Transmitting | 100 | 21% | 18% |
| Not Reported in Region | 88 | 14% | 11% |

"CONNECTED is gold" is now measured: **~2.5× baseline conversion**. The `path_at_select` field (captured before calling begins, avoiding the tautology of measuring path after a successful QSO) is doing its job — this is a genuinely predictive signal available at decision time.

### 2. The proven-frequency hypothesis holds — where coverage exists

By `score_reason` at the actual TX frequency:

| Reason code | Meaning | n | Success |
|---|---|---|---|
| 4 | Proven (target decoding there) | 82 | **48%** |
| 8 | Congested (regional) | 128 | 33% |
| 3 | Local QRM (own receiver) | 306 | 27% |
| 0 | No data | 18 | 6% |
| 7 | Regional light | 9 | 11% |

Proven frequencies outperform by roughly +20 points of success rate. However, **56% of all TX events sat on reason-3 frequencies**, where the score reflects the local receiver, not the target's environment. This coverage limit is why the recommendation-following comparison (below) is inconclusive.

### 3. Following the frequency recommendation: no measurable effect (yet)

Raw: followed 28% vs not-followed 33% — but this is confounded (blank-path early events skew the followed group). Within path strata the two groups are statistically identical (e.g., Reported in Region: 47% vs 47%). Deviation magnitude also doesn't matter (score_delta ≤15 → 32%; >15 → 33%).

Honest reading: either the rec doesn't move the needle, or its effect is swamped by path/propagation, which dominate. The reason-4 result above supports the second reading — the engine's *signal* is valid; its *delivered recommendation* is diluted by low Tier 1 coverage. The v2 schema's `rec_reason` field exists to settle this: does following a *proven* rec outperform following a gap-based one?

### 4. Reporter coverage is monotonically predictive

0 reporters → 15% success; 1–2 → 23%; 3–5 → 21%; 6–15 → 35%; 16+ → 39%. Validates the continuous-confidence scoring philosophy.

### 5. Cycle economics

Median `tx_cycles`: QSO_LOGGED = **4**, NO_RESPONSE = 5 (typical abandonment point), RESPONDED-never-logged = **13**. Successful QSOs land fast. The 23 responded-never-logged events are a distinct failure mode (exchange stalls) concentrated on 40m/20m. Supports a cycle-budget coaching heuristic (~8–10 cycles) and a separate stall-detection prompt.

### 6. Bands, IONIS, trend

- 40m best (36%), 17m 34%, 20m 28%, 80m 22%, 10m worst (9% — 20 of 22 unanswered, despite IONIS showing STRONG on 10 of 22).
- IONIS tiers are not monotonic vs success: MARGINAL 64% (n=11, small), STRONG 27% (n=118), CLOSED 0% (n=13). IONIS predicts path openness, not QSO success — necessary, not sufficient. UI should not imply otherwise.
- Monthly success trend: Apr 27% → May 30% → Jun 42% → Jul 58% (n=12). Cannot separate scoring-engine improvements, seasonal conditions, band mix, and operator learning.

## Bug found and fixed during analysis

`competition` was 0 in **all 547 events**. Root cause in `main_v2.py` snapshot code: `int(comp_str.split()[0])` against strings formatted as `"Clear"`, `"Low (2)"`, `"Medium (3) + QRM"`, `"Low (3) inferred"` (see `analyzer/core.py`) — the first token is never numeric, so the parse always fell through to 0. **Fixed 2026-07-01** (regex on the parenthesized count). All v1 data has an unusable competition axis; analysis of competition begins with data collected after the fix.

## Data-quality notes

- **`elapsed_s` is untrustworthy as an effort metric.** 81 events exceed one hour (max 21.5 h) — targets left selected during 24/7 remote operation. Use `tx_cycles` instead.
- **Blank `path_at_select`** in 112 events, concentrated April–May and declining; 23 oldest events predate the field entirely.
- `hour_utc` cuts show variation (05z 51%, 02z 18%) but are band-confounded; not analyzed further.

## Caveats

Single operator, single station, self-selected targets — the operator chooses whom to call partly *using* the tool, entangling tool value with skill. Path status *predicts* success; it cannot prove QSOP *caused* successes. The defensible causal claim: QSOP surfaces a decision-relevant signal (which targets can hear you, per decode row, at cycle cadence) that is empirically worth ~2.5× on target selection and is otherwise unavailable in real time. No significance testing performed; the path and reason-4 effects would clearly survive it at these n; the IONIS-MARGINAL and monthly-trend findings might not. Coefficients here are WU2C-station priors, not universal constants.

## Actions taken / queued

1. ✅ Competition parser fixed (2026-07-01).
2. Schema v2 (at-select tactical snapshot + per-cycle trace) — see `OUTCOME_SCHEMA_V2_DESIGN.md`.
3. UX candidates motivated by this data: callability ranking in decode table; CONNECTED-interrupt toast; cycle counter with expectation marker; cycle-budget coaching nudge; stall detector; honest rec-confidence display; IONIS reframed as path predictor.
4. Publishing: the 76%-vs-30% field result is the strongest available pitch material.

*Reproduce any figure with simple groupbys over the JSONL; all numbers derive from the 2026-07-01 analysis session transcript.*
