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

### What's Next

- Peter: deploy, test, verify JSONL file looks reasonable
- Phase 2 (future): analysis dialog with filters, cached results, dashboard
- Phase 3 (future): anonymous data export for aggregate analysis
- Document the decoder physics analysis in design docs (density_score breakpoints grounded in FT8 mechanics)

---

**73 de WU2C**
