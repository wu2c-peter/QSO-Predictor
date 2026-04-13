# Release Notes — v2.5.1

**Date:** April 13, 2026  
**Theme:** OutcomeRecorder (Data Collection) & Scoring Fixes

---

## OutcomeRecorder — Silent Performance Data Collector

QSOP now silently records the scoring context and outcome of each QSO 
attempt. This data enables future performance analysis (Phase 2, planned 
for v2.6) and operator coaching features.

### What It Records

Each time you select a target, transmit, and then clear or complete the 
QSO, one compact event (~380 bytes) is written to a local JSONL file. 
The event captures QSOP's ephemeral state at the moment of outcome — 
information that would otherwise be lost when the session ends.

**Recorded fields include:**
- QSOP's recommended frequency and score vs your actual TX frequency and score
- Whether you followed the recommendation (with tolerance for plateaus)
- Path status at target selection (predictive) AND at outcome (confirmatory)
- Competition count, reporter count, IONIS propagation status
- TX cycles, elapsed time, solar conditions
- Target distance and continent (anonymized — no callsigns or grids stored)

### Three-Tier Outcomes

| Outcome | Meaning |
|---------|---------|
| `NO_RESPONSE` | You called, they never answered |
| `RESPONDED` | Target sent your callsign (exchange started) |
| `QSO_LOGGED` | Full QSO completion (UDP Type 5) |

`RESPONDED` is the key metric for evaluating QSOP's frequency 
recommendations — it answers "did the scoring help you get noticed?" 
independent of whether the QSO then completed.

### Smart Filtering

The recorder only writes events for genuine attempts:
- **No TX cycles → skip** (browsing, not calling)
- **Elapsed < 15 seconds → skip** (band-change churn, rapid clicking)
- **QSO_LOGGED always records** (safety net)

### Session Management

Sessions are tied to operating activity, not app lifetime:
- Session starts on first TX cycle (not first decode)
- Session ends after 10 minutes with no target activity, or on app close
- Passive monitoring (receiving spots, no target selected) generates zero records

### Data Storage

- **Location:** `~/.qso-predictor/outcome_history.jsonl`
- **Growth:** ~3 MB/year for active operators
- **Privacy:** No callsigns, grids, or identifying information stored
- **Safety:** 50 MB rotation limit; write failures never crash the app

### Settings

Recording is enabled by default. Disable in Settings → Analysis:
```
☐ Record outcome data for performance analysis
```

### Coming in v2.6

- On-demand performance analysis with filters (band, time, distance, solar)
- Dashboard showing score calibration, path correlation, personal patterns
- Optional anonymous data export for aggregate analysis
- Operator coaching/trainer (template-based session debriefs)

---

## Scoring Fixes

### Tier 1 Proven Scores Now Override Local QRM

**Previously:** If a frequency had both a local decode (something you hear) 
AND tier 1 data (the target is decoding there), the local QRM mask won — 
score stayed at 10 regardless of tier 1 evidence.

**Now:** Tier 1 proven data takes priority. In FT8, TX and RX alternate 
on 15-second cycles — a local signal at your TX frequency doesn't prevent 
you from transmitting there. The target's perspective is what matters for 
choosing where to call.

**Effect:** The score graph now shows green peaks (90-100) at the same 
positions as the cyan bars, instead of suppressing them to 10. 
Recommendations will consider proven frequencies even when there's local 
activity nearby.

### Perspective Data Persistence Extended

**Previously:** PSK Reporter spots in the band map aged out after 60 
seconds. Most reporters upload in batches, so cyan bars would disappear 
between uploads — creating a blinking effect.

**Now:** Perspective data persists for 180 seconds (3 minutes), bridging 
typical upload gaps. Visual decay (bright → dim) communicates freshness. 
The analyzer's query window and the band map's cleanup timer are now 
matched at 180 seconds.

**Decay timeline:**
- 0–29s: Full brightness (fresh)
- 29–59s: Slightly dimmed (recent)
- 59–179s: Gradual fade (aging)
- 180s: Removed

### Path Freshness & Active Invalidation

The "Heard by Target" and "Reported in Region" path indicators now show 
**how recently** the evidence was established, and actively detect when 
the signal may have faded.

**Freshness display:**
```
Heard by Target (+8 dB) 25s           Fresh — target just decoded you
Heard by Target (+8 dB) 2m ago        Aging — but target hasn't uploaded since
Rprtd in Region (-12 dB) 45s          Regional confirmation with age
```

**Active invalidation:**
```
Was Heard (3m ago) — fading?          Target uploaded newer spots WITHOUT you
```

The amber "fading?" state means the target's decoder was active after 
last hearing you (they uploaded new spots to PSK Reporter) but your 
callsign wasn't in the latest batch. This is active negative evidence — 
not just aging, but the target's receiver confirming it no longer hears 
you. Time to consider adjusting frequency, power, or moving on.

**Why this matters:** Previously, "Heard by Target" persisted as long as 
the spot was in cache — even if the target had since uploaded dozens of 
decode batches without you. The operator had no way to know if the path 
confirmation was 30 seconds old or 3 minutes stale.

### Path at Selection (Non-Tautological Analysis)

The OutcomeRecorder now captures `path_at_select` — the path status at 
the moment you select a target, BEFORE you start calling. This enables 
non-tautological analysis in Phase 2.

Without this, "100% QSO rate when Heard by Target" could be circular — 
the "Heard by Target" status might have been established during the QSO 
exchange itself. With `path_at_select`, Phase 2 can ask the honest 
question: "When the target had already heard me before I called, what 
was my success rate?"

---

## Files Changed

| File | Changes |
|------|---------|
| `outcome_recorder.py` | **NEW** — OutcomeRecorder class with path_at_select |
| `main_v2.py` | Import, init, snapshot builder, 5 integration hooks, path freshness display |
| `config_manager.py` | Added `outcome_recording` default setting |
| `band_map_widget.py` | Tier 1 override of local_busy; extended perspective decay |
| `analyzer.py` | Perspective query 60s → 180s; path freshness tracking; active invalidation |

---

## Design Documentation

Full specification: `docs/OUTCOME_RECORDER_SPEC.md`  
Session notes: `docs/SESSION_NOTES_2026-04-12_outcome_recorder.md`

---

**73 de WU2C**
