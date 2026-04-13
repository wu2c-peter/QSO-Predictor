# Session Notes — April 12, 2026
## Decoder Physics Analysis & OutcomeRecorder Implementation

---

### Part 1: Decoder Physics Deep-Dive

Extended theoretical analysis of FT8 decoder mechanics and how they ground QSOP's scoring heuristics.

**Key findings:**

1. **FT8 modulation:** 8-GFSK, 8 tones × 6.25 Hz spacing = 50 Hz bandwidth. Each tone carries 3 bits (log₂(8)). 79 symbols total: 21 Costas sync + 58 LDPC-encoded data. 12.64 seconds per transmission.

2. **Signal separation:** All FT8 stations are time-synchronized to UTC (not random delays). Separation is frequency-only. Two signals in the same 50 Hz band overlap for the entire 12.64s — no time diversity escape. This makes frequency recommendation the central tactical lever.

3. **Costas sync arrays:** Same pattern for ALL FT8 transmissions. The decoder does a 2D (time, frequency) matched-filter search for this known pattern. Identity is in the LDPC-decoded payload, not the sync.

4. **Multi-pass decoder:** ~3 passes. Each pass decodes strongest candidate, reconstructs its spectrogram contribution, subtracts it (imperfectly, residual δ ≈ 3-5%). Signals ranked 1-3 by power get decoded. Rank 4+ face undecoded mutual interference.

5. **The 3-signal breakpoint is physics, not tuning:** With 50 Hz signals in 60 Hz QSOP buckets, 3+ signals must overlap. With ~3 decoder passes, signals ranked 4+ can't be reached. The `density_score()` breakpoint at 3 maps directly to decoder pass capacity.

6. **PSK Reporter survivorship bias:** We only see signals that were *successfully decoded*. Observed count ≤ actual count. Low counts (1-2) are reliable (absence-is-evidence). High counts (6+) are conservative (reality is worse). Middle counts (3-5) are ambiguous.

7. **Current heuristics are well-grounded:** The density_score curve, the proven-over-empty preference, the reporter-count confidence — all align with decoder physics. The scoring was never a "decoder capacity model" — it's a post-decoder census metric, which is the right thing to compute given our data.

**Conclusion:** No refactoring of density_score needed. The heuristics track the physics well. The main value of this analysis is intellectual grounding and documentation — we now know *why* the numbers work.

---

### Part 2: OutcomeRecorder Implementation

**Design decisions made in this session:**

- **Three-tier outcomes:** NO_RESPONSE / RESPONDED / QSO_LOGGED. RESPONDED is the key metric for evaluating QSOP (did the frequency choice help you get noticed?).
- **Option B (snapshot dict):** Caller builds the snapshot and passes it. Recorder never reaches into UI internals. Simpler, more testable.
- **Filter-enabling fields:** hour_utc, dow, distance_km, target_continent added to enable future analysis filtering without storing identifying information.
- **Session markers:** session_start/end events for normalizing attempts per hour.
- **CQ zone deferred:** Would need a prefix→zone lookup table. Continent is the useful filter.
- **On-demand analysis (Phase 2):** Filter dialog + cached results + dashboard. Not continuous.
- **Anonymous data sharing (Phase 3):** Opt-in only, default OFF, manual export before automation.

**Files created/modified:**

| File | Changes |
|------|---------|
| `outcome_recorder.py` | **NEW** — ~310 lines. OutcomeRecorder class, haversine, continent mapping |
| `main_v2.py` | Import, init, `_build_outcome_snapshot()`, `_record_outcome_for_current_target()`, 5 hooks |
| `config_manager.py` | Added `outcome_recording: true` default |
| `docs/OUTCOME_RECORDER_SPEC.md` | **NEW** — Full design specification |

**Integration hooks:**

1. `_set_new_target()` — records previous target (CLEARED/TARGET_CHANGED), registers new target
2. `on_qso_logged()` — records QSO_LOGGED BEFORE auto-clear
3. `handle_status_update()` — TX cycle edge detection BEFORE throttle
4. `process_buffer()` — RESPONDED detection from decodes + session start
5. `closeEvent()` — flushes pending outcome + session end BEFORE shutdown

**Critical ordering verified:**
- QSO_LOGGED → auto-clear: recorder resets after recording, _set_new_target finds no active target → no double-recording ✅
- Snapshot captured BEFORE state-clearing code runs ✅
- TX cycle detection runs before 0.5s throttle for reliable edge detection ✅
- RESPONDED detection: `call` field from parser = target callsign when target responds (position 2 = sender in FT8) ✅

---

### Key Learnings

1. **FT8 is time-synchronized, frequency-separated.** No time diversity — frequency recommendation is the entire game.

2. **The density_score breakpoint at 3 is not arbitrary.** It maps to FT8 signal bandwidth (50 Hz) fitting ~3 times in a 60 Hz bucket, combined with ~3 decoder passes.

3. **PSK Reporter data has survivorship bias.** We see what was decoded, not what arrived. Low counts are reliable, high counts are conservative, middle is ambiguous.

4. **The scoring heuristic is a post-decoder census metric**, not a pre-decoder physics model. This is the right thing to compute given our data.

5. **RESPONDED is a better QSOP validation metric than QSO_LOGGED.** QSOP influences "getting noticed" — whether the QSO then completes depends on factors outside QSOP's control.

---

### Part 3: Field Testing & Iterative Fixes (Evening Session)

Deployed OutcomeRecorder and operated on-air to collect real data. Three rounds of refinement driven by actual operating data.

**Round 1: Burst filtering**
- Band changes caused rapid-fire target cycling — 8+ events within 200ms
- `_was_transmitting` reset on each target selection credited false TX cycles
- **Fix:** Added minimum elapsed time filter (< 15s → skip) alongside existing tx_cycles=0 filter

**Round 2: Local QRM masking tier1 scores**
- Screenshot showed cyan bars (tier1 data) not elevating the score graph
- Root cause: `local_busy` mask in Step 4 overrode tier1 proven scores with score=10
- In FT8, TX and RX alternate — local signals don't prevent TX at that frequency
- **Fix:** Tier1 proven data now overrides local_busy in Steps 4 and 7b

**Round 3: Perspective data disappearing**
- Cyan bars blinked in and out between PSK Reporter upload batches
- Root cause: analyzer query window was 60s, but uploads can be minutes apart
- **Fix:** Extended perspective and path intelligence queries from 60s to 180s; matched band_map decay timeline

**Round 4: Followed recommendation tolerance**
- User clicks near green line on flat score plateau but misses by a few Hz
- Original 30 Hz threshold too strict
- **Fix:** `followed = True` if within 100 Hz OR tx_score within 5 points of rec_score. Added `score_delta` continuous field.

**Round 5: Path status tautology**
- "Heard by Target: 100% QSO rate" was potentially circular
- If path changed from "Reported in Region" to "Heard by Target" DURING the QSO, the correlation is tautological
- **Fix:** Added `path_at_select` field captured at target selection time (predictive, non-tautological). Existing `path` field is at outcome time (confirmatory).

**Round 6: Session management refinements**
- Sessions tied to target activity (Option B), not app lifetime
- Session start deferred to first TX cycle — browsing creates no records
- Gap detection with effective session_end at last activity time
- Cached band/sfi/k for session starts after QSY

---

### First Real Operating Session Analysis

18 attempts over ~1 hour, 2 QSOs:

| Metric | Value |
|--------|-------|
| Followed rec | 8 attempts, 1 QSO (12%) |
| Deviated | 10 attempts, 1 QSO (10%) |
| Heard by Target | 2 attempts, 2 QSOs (100%) |
| Avg score delta | 35 pts (rec was better) |
| Large misses (Δ≥75) | 6 attempts, 65 TX cycles wasted |
| QSO patience | avg 4 cycles |
| Gave-up patience | avg 8 cycles |
| TX freq reason=3 (local QRM) | 14 of 18 events |

**Key finding:** Path confirmation ("Heard by Target") was the strongest predictor — but requires `path_at_select` analysis to determine if it's truly predictive vs tautological.

---

### Ideas Surfaced

- **Operator coaching/trainer:** Template-based session debriefs from outcome data. Phase 1 in-app (arithmetic + templates), optional Phase 2 LLM debrief.
- **CQ mode recording:** Current recorder only tracks calling workflow. CQ sessions need separate detection and different analytical questions.
- **Path freshness display:** Show "Heard by Target (30s ago)" vs "(3m ago)" and actively invalidate when target uploads new spots that don't include the operator. **Implemented** — analyzer tracks `path_heard_age` and `path_stale`, dashboard shows freshness in seconds/minutes and amber "Was Heard — fading?" state.

---

### Part 4: Path Freshness & Active Invalidation

**Problem:** "Heard by Target" persisted as long as the spot was cached, even if the target had since uploaded dozens of decode batches without the operator. No way to know if the path confirmation was 30 seconds old or 3 minutes stale.

**Solution — two layers:**

1. **Freshness display:** Every "Heard by Target" and "Reported in Region" now shows the age of the underlying spot. "25s" (fresh) vs "2m ago" (aging). Operators can gauge confidence at a glance.

2. **Active invalidation:** If the target uploaded newer spots to PSK Reporter and the operator is NOT in them, the status changes to "Was Heard (Xm ago) — fading?" in amber. This is absence-is-evidence from an active reporter — not just aging, but confirmation that the target's decoder was working and didn't hear you.

**Implementation:**
- `analyzer.py`: Added `path_heard_time` tracking for each path determination. Invalidation checks `receiver_cache` for target's newer uploads. New fields: `path_heard_age` (int seconds), `path_stale` (bool).
- `main_v2.py`: Dashboard path display reformatted with freshness suffix and amber color for stale state.
- Decode evidence (from local UDP) sets `path_heard_time = now` — always fresh, never stale via PSK Reporter timing.

**Also: path_at_select for non-tautological analysis**
- Peter caught that "100% QSO rate when Heard by Target" could be circular if the path status was established during the QSO exchange.
- Added `path_at_select` field to OutcomeRecorder — captured at target selection time (before calling), separate from `path` at outcome time.
- Phase 2 analysis can now ask the honest question without circular reasoning.

---

### Files Modified (v2.5.1)

| File | Changes |
|------|---------|
| `outcome_recorder.py` | **NEW** — ~530 lines, full OutcomeRecorder class with path_at_select |
| `main_v2.py` | Import, init, snapshot builder, 5 integration hooks, path_at_select, path freshness display |
| `config_manager.py` | Added `outcome_recording` default |
| `band_map_widget.py` | Tier1 override of local_busy; extended perspective decay |
| `analyzer.py` | Perspective + path intelligence 60s → 180s; path freshness tracking; active invalidation |
| `docs/OUTCOME_RECORDER_SPEC.md` | **NEW** — full design specification |
| `docs/RELEASE_NOTES_v2.5.1.md` | **NEW** — release documentation |

---

**73 de WU2C**
