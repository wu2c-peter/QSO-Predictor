# Outcome Data Analysis — October 2026

**Dataset:** `~/.qso-predictor/outcome_history.jsonl`, schema v1 + v2
**Coverage:** 2026-04-13 through 2026-11-01 UTC — 999 outcome events (567 v1, 432 v2), 228 sessions
**Analyzed:** 2026-10-31, WU2C + Claude
**Predecessor:** `OUTCOME_ANALYSIS_2026-07.md` (v1 only, 547 events). This is the first look at schema v2 (`OUTCOME_SCHEMA.md`), live since 2026-07-03.
**Status of findings:** Observational, single-operator, single-station. Correlations, not proven causation. Many v2 strata are small (n = 10–60); no significance testing. See Caveats.

---

## Headline results

Overall conversion: 328 QSO_LOGGED (32.8%), 34 RESPONDED-not-logged (3.4%), 637 NO_RESPONSE (63.8%).
v1: 26.1% logged. v2: 41.7% logged.

Monthly logged rate: Apr 24% → May 25% → Jun 37% → Jul 43% → Aug 30% → Sep 52% → Oct 58% (n=43).

### 1. A quarter of v2 records are replies, not attempts — and they inflate the predictors

105 of 432 v2 events (24%) have `target_state = working_you`: the target was **already answering us** at the first TX cycle (the point where `success_prob` / `strategy` / `target_state` are promoted into the at-select snapshot). These convert at 92% logged / 100% responded and have median `tx_cycles` = 2. They are replies — a different decision from "should I call this station?".

Pooling them with cold attempts manufactures predictive skill:

| Measure | All v2 (n=432) | Cold attempts only (n=327) |
|---|---|---|
| Logged rate | 42% | **25%** |
| `strategy = call_now` vs `call_blind` | 51% vs 33% | **26% vs 26%** |
| `success_prob` calibration | AUC 0.62, Brier skill +0.02 | **flat: every decile 16–27%** |
| `path_at_select = Heard by Target` | 52% | **35%** (n=17) |

- **`success_prob` and `strategy` have no measurable discrimination on cold attempts.** Their apparent v2 skill comes entirely from reply cases (86 of the 105 replies were tagged `call_now`).
- `success_prob` takes only 7 distinct values (8, 23, 25, 32, 38, 49, 75); 336/432 events sit at 38 or 49.
- **The July headline "Heard by Target → 76% success" is probably partly reply leakage too.** v1 has no `target_state`, so replies can't be separated retroactively; treat that figure as an upper bound.

**Analysis rule going forward:** stratify on `target_state == 'working_you'` before any predictor analysis. All "cold" numbers below exclude it (records with null `target_state`, 21% of v2, are kept as cold).

### 2. What does predict success on cold attempts

| Signal | Groups (logged %) |
|---|---|
| Path reaches **H** during the attempt (trace) | reached H **80%** (n=76) vs never **9%** (n=251) |
| Per-cycle hazard by current path code (all v2) | H **31.5%** per cycle; R 1.0%; X 0.5%; N, T 0% |
| `score_reason` at TX freq | 4 proven **53%** · 8 congestion 24% · 3 local QRM 16% |
| `tier1_count_at_tx_bucket` | 0 → 19% · 1 → **55%** · 2 → 40% (n=10) |
| `near_me_heard` | 0 → 13% · 1–2 → 25% · 3+ → **33%** |
| `behavior_pattern` | methodical 34% · random 23% · loudest_first 21% |
| `target_state` | working_other 43% · completing_with_other 40% · cqing 31% · being_called 23% |
| `competition_at_select` | 0 → 22% · 1–3 → 29% · 4+ → 29% (no penalty visible) |

- **"Heard" is the conversion event.** Once the trace shows H, each cycle has a ~1-in-3 chance of being the logging cycle; on every other path code it's ≤1%. This is the strongest single signal in the dataset and argues for the CONNECTED-interrupt UX (July action list).
- **The proven-frequency result replicates** and now has a dose-response: a single Tier-1 decode at the TX bucket nearly triples conversion.
- **`near_me_heard` works as an independent path proxy** — it separates outcomes even when own-path evidence is weak (cold + all v2 strata):

  | path_at_select | near_me ≥ 3 | near_me < 3 |
  |---|---|---|
  | No Reporters in Region | 64% (n=11) | 32% (n=44) |
  | Not Transmitting | 41% (n=61) | 24% (n=29) |
  | (blank) | 65% (n=57) | 31% (n=83) |
  | Not Reported in Region | 32% (n=25) | 20% (n=15) |

- `path_at_select` on cold attempts is much flatter than in July (Heard 35%, Reported 32%, Not Transmitting 33%, Not Reported 17%, blank 14%). Part of July's spread was replies; the residual ordering still puts Not Reported at the bottom.
- `my_snr_at_target` (n=47 cold): ≤ −18 dB → 0/9 logged; −17…−10 → 38%; > −10 → 29%. Too sparse to use, but the floor effect is suggestive.

### 3. Following the frequency recommendation — the July question answered

July found "no measurable effect" and introduced `rec_reason` to test whether a *proven* rec behaves differently. It does (cold attempts):

| rec_reason | Followed | Not followed |
|---|---|---|
| Proven (4/5) | **42%** (n=72) | 25% (n=55) |
| Non-proven | **15%** (n=122) | 27% (n=78) |

- Following a proven rec is worth ~+17 points; **following a non-proven rec is ~12 points worse than ignoring it.**
- In the non-proven case, not-following mostly meant TXing on a reason-3 (local QRM) frequency (43% logged, all v2) — the operator's own pick beat the gap-based rec. Likely confounded (the operator deviates when they see something the engine doesn't, e.g. the target's working frequency), but the direction is consistent across strategies.
- Implication: the recommendation should **carry its confidence** — strong when proven, explicitly tentative (or suppressed) when gap-based. This is the "honest rec-confidence display" item from July, now with data behind it.

### 4. Cycle economics

| Outcome | n | median tx_cycles | p75 |
|---|---|---|---|
| QSO_LOGGED | 328 | **4** | 6 |
| RESPONDED (stalled) | 34 | 17 | 31 |
| NO_RESPONSE | 637 | 6 | 18 |

P(eventually logged | attempt reached ≥ N cycles): N=1 33% · 3 31% · 5 23% · **8 17%** · 10 13% · 15 10% · 20 8% · 30 7%.

Logged QSOs by cycle: peak at 2 (89) and 3 (61); 13 took 21+.

**38% of all TX cycles (3,977 of 10,433) were spent on NO_RESPONSE attempts past cycle 10.** That is the cost the cycle-budget nudge would recover; ~8–10 cycles remains the right threshold, ideally relaxed when the path is H.

Mid-attempt TX frequency moves (cold, attempts ≥ 6 cycles): 0 moves 17% · 1 move 31% · 2+ moves 21%. One deliberate move may help; churning doesn't. Duration-confounded — weak evidence.

### 5. Bands, IONIS, geography (all events)

- Bands: 20m 37% · 40m 32% · 17m 29% · 80m 22% · 10m 4% (1/25). 17m collapsed in v2 (1/12).
- IONIS: STRONG 39% · OPEN 32% · MARGINAL 36% (n=22) · CLOSED 4% (n=24). CLOSED is a real negative; above that, still not monotonic — "necessary, not sufficient" holds.
- Reporters: 0 → 14% · 1–2 → 29% · 3–5 → 20% · 6–15 → 28% · 16+ → 44%.
- Distance: < 1.5k km 46% · 1.5–4k 35% · 4–7k 35% · 7–10k 20% · 10k+ 17%. Continent: NA 37%, EU 36%, AS 24%, AF 15%.

## Capture bugs found (v2 fields)

| Field | Observation | Likely cause / action |
|---|---|---|
| `my_rank_at_select` + trace `rank` | **null in 100%** of v2 events and cycles | Capture broken — `get_your_status()['rank']` never int at read time, or wrong source. Investigate. |
| `local_callers_at_select` | non-zero in 0.5% — but trace `lcall` > 0 in 170 cycles | At-select read happens before the session tracker has populated pileup info; promote at first TX like `success_prob`. |
| `persona` | non-null 0.5% | Persona key inside `bayesian_metadata` likely wrong (flagged "to confirm" in OUTCOME_SCHEMA.md). |
| `path_at_select` | blank in 32% of v2 (140/432), not declining | Still a capture gap; first trace cycle is also blank in 98 of those. |
| trace `path` | blank in 2,677 of 4,557 cycles; worst in August | Target row often not resolvable at TX edge. |
| `competition` (at outcome) | 0 in 79% of v2 | Expected partly (Clear), but check against `competition_max` (non-zero 67%). |
| `success_prob` | 7 distinct values | Prospect index is effectively a 7-level lookup; see finding 1. |
| `elapsed_s` | 145 events > 1 h, max 196.6 h | Known; use `tx_cycles`. |
| `session_end` | 9 negative `elapsed_s` / out-of-order ts | All ≤ 2026-07-02, i.e. pre-fix historic data. No action. |

## Caveats

Single operator, single station, self-selected targets; the operator uses the tool to choose whom to call, so tool value and skill are entangled. v2 is three-and-a-half months and 327 cold attempts — most cold strata are n < 100 and several are n < 20 (Heard-at-select, SNR margin, tier1 = 2). The rec-following result in particular is confounded by operator judgment. The seasonal upswing (Sep–Oct) overlaps with the v2 period and with engine changes; v1↔v2 conversion differences are not attributable to the schema or to QSOP.

## Recommended actions

1. **Separate replies from attempts** in both analysis and the predictor: either gate `success_prob` / `strategy` on `target_state != working_you`, or record an explicit `attempt_kind` field (reply vs cold) at first TX.
2. **Rework `success_prob`** — on cold attempts it is uninformative. Candidate inputs with measured lift: path-reached-H (live), tier1 at TX bucket, `near_me_heard`, `score_reason` at TX, behavior pattern.
3. **Rec confidence display**: present proven recs as strong, gap-based recs as tentative (finding 3).
4. **Fix captures**: `my_rank`, `local_callers_at_select` (promote at first TX), `persona` key, blank `path_at_select`.
5. **Cycle-budget nudge** at ~8–10 cycles unless path is H (finding 4).
6. **CONNECTED-interrupt toast** when the trace path flips to H — 31.5% per-cycle hazard justifies interrupting.

*Reproduce: all figures come from streamed groupbys over the JSONL (scripts `analyze_outcomes.py`, `followup.py`, `followup2.py` from the 2026-10-31 session). "Cold" = v2 events with `target_state != 'working_you'`; "logged" = `outcome == 'QSO_LOGGED'`.*
