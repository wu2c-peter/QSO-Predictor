# OutcomeRecorder — Design Specification

**Version:** 1.0  
**Date:** April 12, 2026  
**Status:** Approved for implementation  
**Author:** Peter WU2C / Claude  
**Target Release:** Next development cycle (backlog item)

---

## 1. Purpose

OutcomeRecorder is a silent, lightweight data collector that captures QSOP's ephemeral scoring context at the moment of each QSO attempt outcome. Its purpose is to enable future analysis of whether QSOP's scoring, frequency recommendations, and path intelligence correlate with actual on-air results.

### What It Is NOT

- Not a real-time analysis engine (analysis is on-demand, offline)
- Not a replacement for ALL.TXT or ADI logs (those capture radio data; this captures QSOP-unique context)
- Not telemetry (all data stays local unless user explicitly exports)

### Design Principles

1. **Record only what QSOP uniquely knows** — scoring context that vanishes when the session ends
2. **Never duplicate existing logs** — ALL.TXT has decodes, ADI has QSOs, we have scoring
3. **Never block the main thread** — one file append per outcome event, microseconds
4. **Fire only on user TX events** — not on every decode (the ALL.TXT lesson)
5. **Design collection around future analysis** — capture fields that enable filtering and correlation

---

## 2. Theoretical Foundation

### Why This Data Matters

QSOP's scoring heuristics (density_score breakpoints at 3/5/6+ signals) were designed to approximate FT8 decoder physics:

- FT8's multi-pass decoder handles ~3 overlapping signals via signal subtraction
- Beyond 3 signals in a ~50 Hz band, undecoded mutual interference degrades all remaining signals
- The density_score breakpoint at 3 is not arbitrary — it maps to decoder pass capacity

However, PSK Reporter data has a fundamental **survivorship bias**: we only see signals that were successfully decoded. The observed count is already clipped by decoder saturation:

```
N_observed ≤ N_actual
N_observed ≈ min(N_actual, decoder_capacity)
```

This means:
- Low counts (1–2) are reliable — absence-is-evidence principle confirms sparsity
- High counts (6+) are conservative — reality is worse than observed
- Middle counts (3–5) are ambiguous — could be real or decoder-filtered

OutcomeRecorder data will eventually let us validate these heuristics empirically: do frequencies scoring 90 actually yield more responses than those scoring 40?

### What We Can and Cannot Prove

**CAN prove (correlation):**
- Score calibration: P(response | score=high) vs P(response | score=low)
- Feature importance: which inputs (path, competition, IONIS) predict outcomes best
- Personal patterns: does this operator's success correlate with QSOP's advice

**CANNOT prove (causation):**
- "QSOP improved your success rate by X%" — the counterfactual problem
- Advice-followed vs advice-ignored has selection bias (users deviate when they see something QSOP doesn't)

**CAN show honestly:**
- Score correlation coefficient
- Response rates by score band
- Stats with sample sizes and bias warnings

---

## 3. Outcome Classification

### Three-Tier Outcomes

| Outcome | Trigger | What It Means |
|---------|---------|---------------|
| `NO_RESPONSE` | clear_target / target_changed / app_closed without response | You called, they never answered |
| `RESPONDED` | Target's decoded message contains your callsign | Exchange started, may or may not complete |
| `QSO_LOGGED` | UDP Type 5 (QSO Logged) | Full QSO completion |

### Why Three Tiers Matter

`RESPONDED` is the most valuable metric for evaluating QSOP's scoring, because it answers: "Did the frequency choice and timing help you get noticed?" — which is exactly what QSOP influences.

Whether the QSO then completes depends on fading, the other station's behavior, software issues — factors outside QSOP's control. If response→completion rate is roughly constant across score bands, it confirms QSOP influences the "getting noticed" part and everything after is independent.

### Detection Logic

**RESPONDED detection** (runtime, lightweight):

```python
def on_decode(self, message_text, from_call):
    """One string comparison per decode, only when target active."""
    if from_call == self._current_target:
        if self._my_call in message_text:
            self._target_responded = True
```

Note: Must distinguish actual responses ("WU2C JA1XYZ R-12") from other message types containing the callsign. The existing decode text parsing handles this.

**QSO_LOGGED detection:** Already implemented via UDP Type 5 in `on_qso_logged()`.

### Outcome Priority

If multiple outcomes occur for the same target:
```
QSO_LOGGED supersedes RESPONDED supersedes NO_RESPONSE
```

Only one outcome record is written per target attempt.

### Terminal Events (triggers outcome recording)

| Event | Outcome Written | Source |
|-------|-----------------|--------|
| QSO logged (UDP Type 5) | `QSO_LOGGED` | `main_v2.py → on_qso_logged()` |
| Clear target (button/Ctrl+R) | `RESPONDED` or `NO_RESPONSE` | `main_v2.py → clear_target()` |
| Target changed (new selection) | `RESPONDED` or `NO_RESPONSE` | `main_v2.py → target selection` |
| Band change / QSY | `RESPONDED` or `NO_RESPONSE` | `main_v2.py → band change detection` |
| App closed | `RESPONDED` or `NO_RESPONSE` | `main_v2.py → closeEvent()` |

---

## 4. Event Schema

### Outcome Event

```python
{
    "v": 1,                             # schema version
    "type": "outcome",                  # event type
    "ts": "2026-04-12T18:23:01Z",       # UTC timestamp (correlate with ALL.TXT)
    "band": "20m",                      # operating band
    "outcome": "RESPONDED",             # NO_RESPONSE | RESPONDED | QSO_LOGGED

    # QSOP scoring context (unique to us — lost if not captured)
    "rec_freq": 1523,                   # recommended frequency (green line)
    "rec_score": 89,                    # score at recommended freq
    "tx_freq": 1680,                    # actual TX frequency (from UDP Type 1)
    "tx_score": 54,                     # score at actual TX freq
    "followed": false,                  # abs(tx_freq - rec_freq) < 30
    "score_reason": 3,                  # top score_reason code from v2.5

    # Ephemeral context (from PSK Reporter / IONIS — not persisted elsewhere)
    "path": "CONNECTED",               # path status at outcome moment
    "competition": 3,                   # competition count at outcome
    "reporters": 5,                     # active reporter count (confidence proxy)
    "ionis": "OPEN",                    # IONIS propagation status
    "fh_mode": "normal",               # "normal" | "fox" | "hound"

    # Solar conditions (ephemeral — status bar values)
    "sfi": 148,                         # solar flux index
    "k": 2,                             # K-index
    "a": 7,                             # A-index (when implemented)

    # Session counters
    "tx_cycles": 8,                     # TX periods since target selected
    "elapsed_s": 240,                   # seconds since target selected

    # Filter-enabling fields (cheap to capture, hard to reconstruct later)
    "hour_utc": 18,                     # hour of day (avoids ISO parsing in analysis)
    "dow": 6,                           # day of week (0=Mon, 6=Sun)
    "distance_km": 9200,               # haversine from my grid to target grid
    "target_continent": "AS",           # derived from grid at event time
    "target_cq_zone": 25               # CQ zone from callsign prefix (if available)
}
```

### Session Boundary Events

```python
# Session start
{
    "v": 1,
    "type": "session_start",
    "ts": "2026-04-12T17:00:00Z",
    "band": "20m",
    "sfi": 148,
    "k": 2
}

# Session end
{
    "v": 1,
    "type": "session_end",
    "ts": "2026-04-12T19:30:00Z",
    "outcomes": 12,                     # outcome events this session
    "elapsed_s": 9000                   # total session duration
}
```

Session boundaries enable "attempts per hour of operating" normalization — an operator running 4 hours on Saturday shouldn't have stats diluted by comparison with 30 minutes on Tuesday.

### Schema Notes

- **No callsigns** — target identity is not recorded (privacy)
- **No grids** — replaced by distance_km and target_continent (anonymous)
- **No exact timestamps for correlation** — ts is sufficient to join with ALL.TXT if the operator chooses, but not enough to identify the target externally
- **All fields are integers, short strings, or booleans** — compact, fast to write
- **~380 bytes per outcome event** — negligible storage

---

## 5. Redundancy Analysis

### What Already Exists Elsewhere

| Data | Source | Persisted? |
|------|--------|------------|
| Every decode | ALL.TXT | ✅ Yes |
| Every TX | ALL.TXT | ✅ Yes |
| Completed QSOs | wsjtx_log.adi | ✅ Yes |
| SNR of decodes | ALL.TXT | ✅ Yes |
| Station behavior | behavior_history.json | ✅ Yes |
| Target callsign | ALL.TXT (join via timestamp) | ✅ Yes |

### What OutcomeRecorder Uniquely Captures

| Data | Why It's Unique |
|------|-----------------|
| QSOP score at TX frequency | Computed in real-time, never stored |
| QSOP recommended frequency | Computed in real-time, never stored |
| Whether user followed recommendation | Derived from score + TX freq comparison |
| Path status at outcome moment | Ephemeral PSK Reporter state |
| Competition count at outcome moment | Ephemeral PSK Reporter state |
| Reporter count (confidence) | Ephemeral, not logged |
| IONIS status | Ephemeral model output |
| RESPONDED outcome tier | Not detectable from ALL.TXT without complex parsing |
| Score reason code | Ephemeral v2.5 scoring context |

**Principle: We record QSOP's view of the world at the decision point. The radio's view is already in ALL.TXT.**

---

## 6. Storage

### File Location

```
~/.qso-predictor/outcome_history.jsonl
```

JSONL format — one JSON object per line. Simple, appendable, grep-friendly, no database dependency.

### Growth Projections

```
Events per session:        ~10–30 target attempts + 2 session markers
Bytes per outcome event:   ~380
Bytes per session marker:  ~120
Sessions per week:         ~5 (active operator)
Annual growth:             ~3 MB/year

Heavy contest weekend:     ~200 events = ~80 KB
```

### Rotation / Safety

```python
MAX_FILE_SIZE_MB = 50  # ~15 years of heavy use

def record_event(self, event):
    if os.path.exists(self.filepath):
        size_mb = os.path.getsize(self.filepath) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            self._rotate()  # rename to .bak, start fresh
    
    with open(self.filepath, 'a') as f:
        f.write(json.dumps(event) + '\n')
```

### Comparison to ALL.TXT Risk

| | ALL.TXT | OutcomeRecorder |
|---|---|---|
| Events per session | Thousands of decodes | 10–30 outcomes |
| File growth | 100+ MB/year | ~3 MB/year |
| Parsing at runtime | ❌ Caused freezes | Never parsed at runtime |
| Write pattern | Continuous | One append per outcome |
| Main thread risk | High (was the v2.0.7 root cause) | None |

---

## 7. Implementation

### New Class: OutcomeRecorder

```python
class OutcomeRecorder:
    """Records QSO attempt outcomes for future analysis.
    
    Silent data collector — no UI, no runtime analysis.
    Fires only on outcome events (target cleared, QSO logged, etc.)
    """

    def __init__(self, data_dir, my_callsign):
        self.filepath = os.path.join(data_dir, 'outcome_history.jsonl')
        self._my_call = my_callsign.upper()
        self._current_target = None
        self._target_selected_at = None
        self._first_tx_at = None
        self._tx_cycle_count = 0
        self._target_responded = False
        self._session_outcome_count = 0

    def on_target_selected(self, call, grid, band, dial_freq):
        """Called when user selects a new target.
        If previous target active, records outcome for it first."""
        if self._current_target:
            self._record_terminal_event('TARGET_CHANGED')
        
        self._current_target = call
        self._target_selected_at = datetime.utcnow()
        self._first_tx_at = None
        self._tx_cycle_count = 0
        self._target_responded = False

    def on_tx_cycle(self):
        """Called each time we detect a TX period (UDP Type 1)."""
        self._tx_cycle_count += 1
        if self._first_tx_at is None:
            self._first_tx_at = datetime.utcnow()

    def on_decode(self, message_text, from_call):
        """Called on each decode — checks for target response."""
        if (self._current_target 
                and from_call == self._current_target
                and self._my_call in message_text):
            self._target_responded = True

    def on_qso_logged(self, call):
        """Called on UDP Type 5."""
        if call.upper() == self._current_target:
            self._record_terminal_event('QSO_LOGGED')

    def on_clear_target(self):
        """Called when user clears target."""
        if self._current_target:
            self._record_terminal_event('CLEARED')

    def on_app_close(self):
        """Called from closeEvent."""
        if self._current_target:
            self._record_terminal_event('APP_CLOSED')
        self._write_session_end()

    def on_session_start(self, band, sfi, k):
        """Called when operating session begins."""
        self._session_outcome_count = 0
        self._write_event({
            "v": 1, "type": "session_start",
            "ts": datetime.utcnow().isoformat() + 'Z',
            "band": band, "sfi": sfi, "k": k
        })

    def _record_terminal_event(self, trigger):
        """Build and write the outcome event."""
        if self._target_responded:
            outcome = "QSO_LOGGED" if trigger == "QSO_LOGGED" else "RESPONDED"
        else:
            outcome = "QSO_LOGGED" if trigger == "QSO_LOGGED" else "NO_RESPONSE"
        
        now = datetime.utcnow()
        event = self._build_outcome_event(outcome, now)
        self._write_event(event)
        self._session_outcome_count += 1
        
        # Reset target state
        self._current_target = None
        self._target_responded = False

    def _build_outcome_event(self, outcome, now):
        """Snapshot QSOP's ephemeral state."""
        # These methods reach into main app for current values
        # Implementation will use callbacks or references set at init
        return {
            "v": 1,
            "type": "outcome",
            "ts": now.isoformat() + 'Z',
            "band": self._get_current_band(),
            "outcome": outcome,

            "rec_freq": self._get_recommended_freq(),
            "rec_score": self._get_recommended_score(),
            "tx_freq": self._get_tx_freq(),
            "tx_score": self._get_score_at_freq(self._get_tx_freq()),
            "followed": abs(self._get_tx_freq() - self._get_recommended_freq()) < 30,
            "score_reason": self._get_top_score_reason(),

            "path": self._get_path_status(),
            "competition": self._get_competition_count(),
            "reporters": self._get_reporter_count(),
            "ionis": self._get_ionis_status(),
            "fh_mode": self._get_fh_mode(),

            "sfi": self._get_sfi(),
            "k": self._get_k_index(),
            "a": self._get_a_index(),

            "tx_cycles": self._tx_cycle_count,
            "elapsed_s": int((now - self._target_selected_at).total_seconds()),

            "hour_utc": now.hour,
            "dow": now.weekday(),
            "distance_km": self._get_distance_km(),
            "target_continent": self._get_target_continent(),
            "target_cq_zone": self._get_target_cq_zone(),
        }

    def _write_event(self, event):
        """Append one JSON line. Rotate if file exceeds safety limit."""
        try:
            if os.path.exists(self.filepath):
                size_mb = os.path.getsize(self.filepath) / (1024 * 1024)
                if size_mb > 50:
                    self._rotate()
            
            with open(self.filepath, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            logger.warning(f"OutcomeRecorder write failed: {e}")
            # Never crash the app for a recording failure

    def _rotate(self):
        """Rename current file to .bak, start fresh."""
        bak = self.filepath + '.bak'
        if os.path.exists(bak):
            os.remove(bak)
        os.rename(self.filepath, bak)

    def _write_session_end(self):
        self._write_event({
            "v": 1, "type": "session_end",
            "ts": datetime.utcnow().isoformat() + 'Z',
            "outcomes": self._session_outcome_count
        })
```

### Integration Points

| Event | Hook Location | Call |
|-------|---------------|------|
| Target selected | `main_v2.py → _set_new_target()` | `recorder.on_target_selected(...)` |
| TX cycle | `udp_handler.py → Type 1 status` | `recorder.on_tx_cycle()` |
| Decode received | `udp_handler.py → Type 2 decode` | `recorder.on_decode(msg, call)` |
| QSO logged | `main_v2.py → on_qso_logged()` | `recorder.on_qso_logged(call)` |
| Clear target | `main_v2.py → clear_target()` | `recorder.on_clear_target()` |
| App close | `main_v2.py → closeEvent()` | `recorder.on_app_close()` |
| Session start | `main_v2.py → on first decode` | `recorder.on_session_start(...)` |

### Getter Callbacks

The `_get_*` methods need access to current application state. Two approaches:

**Option A: Pass references at init**
```python
recorder = OutcomeRecorder(data_dir, my_call)
recorder.set_state_source(main_window)  # recorder calls main_window.get_recommended_freq() etc.
```

**Option B: Pass snapshot dict at terminal event**
```python
recorder.record_outcome(trigger, {
    'rec_freq': self.current_rec_freq,
    'tx_freq': self.current_tx_freq,
    # ... all ephemeral state
})
```

Option B is simpler and more testable — the recorder doesn't need to know about the UI.

---

## 8. Settings

```ini
[ANALYSIS]
outcome_recording = true          # default ON (local data only)
```

```
Settings → Analysis
  ☑ Record outcome data for performance analysis
    "Stores scoring context locally for your personal analysis.
     No data is transmitted. See Tools → Analyze Performance."
```

Default ON — data is local-only, file is tiny, user can disable.

---

## 9. On-Demand Analysis (Phase 2)

### Approach

Analysis runs on-demand via `Tools → Analyze Performance`. It reads the JSONL file, applies user-selected filters, computes stats, caches results, and displays a dashboard.

### Filter UI

```
┌─────────────────────────────────────────┐
│  Performance Analysis                   │
│                                         │
│  Date range:    [Last 90 days    ▾]     │
│  Band:          [All bands       ▾]     │
│  Time of day:   [All hours       ▾]     │
│  Day type:      [All days        ▾]     │  (Weekday/Weekend/All)
│  Distance:      [All             ▾]     │  (<2000km / 2000-8000km / 8000km+)
│  Continent:     [All             ▾]     │
│  Path status:   [All             ▾]     │
│  IONIS status:  [All             ▾]     │
│  F/H mode:      [All             ▾]     │
│  Solar (SFI):   [All             ▾]     │  (<100 / 100-150 / 150+)
│  Solar (K):     [All             ▾]     │  (Quiet 0-2 / Unsettled 3-4 / Storm 5+)
│  Min events:    [20              ]      │
│                                         │
│  [Run Analysis]                         │
└─────────────────────────────────────────┘
```

### Dashboard Output

```
Performance Analysis — 20m, Last 90 days
════════════════════════════════════════════
247 attempts, 86 responses (35%), 73 QSOs (30%)

Response Rate by Score Band
───────────────────────────
  Score 80+:    43% responded   (n=89)
  Score 50-79:  28% responded   (n=104)
  Score <50:    14% responded   (n=54)

QSO Completion (of responses)
─────────────────────────────
  85% overall (consistent across score bands)

Path Status → Response Rate
───────────────────────────
  CONNECTED:    72%    (n=34)
  PATH_OPEN:    31%    (n=98)
  NO_PATH:       8%    (n=87)
  UNKNOWN:      19%    (n=28)

Recommendation Accuracy
───────────────────────
  Followed (Δ<30Hz):   38% response   (n=152)
  Deviated (Δ≥30Hz):   24% response   (n=95)
  ⚠ Selection bias: users deviate when they see 
    something QSOP doesn't. Not a fair comparison.

Efficiency
──────────
  Avg TX cycles to response:  4.2 (score 80+)
                               8.7 (score <50)

Score Correlation
─────────────────
  r = 0.38 (moderate positive)
  Score predicts response better than chance.

Solar Influence
───────────────
  SFI >150:  38% response   (n=112)
  SFI <100:  22% response   (n=48)
  K ≤ 2:    34% response   (n=198)
  K ≥ 4:    18% response   (n=22)
```

All stats include sample sizes. Bias warnings where relevant. If r ≈ 0, we show that too.

### Analysis Results Storage

```
~/.qso-predictor/analysis_results.json
```

Cached results from last analysis run. Dashboard reads this for instant display. Re-running analysis overwrites with fresh computation.

```python
{
    "generated_at": "2026-04-12T19:00:00Z",
    "filters_applied": {
        "date_range": "90d",
        "band": "20m",
        "distance": "all",
        ...
    },
    "total_attempts": 247,
    "total_responses": 86,
    "total_qsos": 73,
    "score_band_stats": { ... },
    "path_stats": { ... },
    "recommendation_stats": { ... },
    "correlation_r": 0.38,
    ...
}
```

---

## 10. Anonymous Data Sharing (Phase 3)

### Approach: Opt-In, User-Controlled

```
Settings → Privacy
  ☐ Share anonymous performance data to help improve QSOP
    "Shares only numerical statistics (scores, band, solar
     conditions). No callsigns, grids, or identifying
     information is ever transmitted. See details..."
```

**Default OFF.** Opt-in only.

### Anonymization

The outcome schema is already designed for privacy — no callsigns, no grids. Additional sanitization for sharing:

- Remove `ts` timestamp (replace with date-only or omit)
- Round `distance_km` to nearest 500 km
- Remove any field that could identify the operator in combination

### Phased Implementation

| Phase | Mechanism | User Control |
|-------|-----------|-------------|
| Phase 1 | Local JSONL only | Full — it's their file |
| Phase 2 | "Export anonymous data" button → produces sanitized file | User reviews before sending |
| Phase 3 | HTTPS upload (if community interest warrants) | Explicit opt-in toggle |

Phase 2 (manual export) keeps the user in complete control. They see exactly what's being shared before they share it. This builds trust before automating anything.

### Aggregate Value

With 10–20 users sharing data:
- Validate scoring curve across different stations and locations
- Identify bands or SFI ranges where the model breaks down
- Confirm whether the 3-signal decoder breakpoint is universal
- Calibrate CONNECTED→QSO rates by region

---

## 11. Implementation Phasing

| Phase | Deliverable | Effort | Dependency |
|-------|-------------|--------|------------|
| **1** | `OutcomeRecorder` class + integration hooks | ~50–80 lines new code | None |
| **1** | Settings toggle for recording | Trivial | Phase 1 class |
| **1** | Session start/end markers | Trivial | Phase 1 class |
| **2** | Analysis dialog with filters | Medium — new UI dialog | Phase 1 data |
| **2** | Dashboard display | Medium — read cached results | Phase 2 analysis |
| **2** | `analysis_results.json` caching | Small | Phase 2 analysis |
| **3** | Export anonymized data button | Small | Phase 1 data |
| **3** | HTTPS upload (if warranted) | Medium | Phase 3 export |
| **4** | Adaptive scoring — feed outcomes back into Score formula | Larger — touches core algorithm | Phase 2 stats |

**Phase 1 is the priority.** Every day it runs is data for future phases. The cost is minimal and the value compounds with time.

---

## 12. Open Questions

1. **CQ zone lookup:** Deriving `target_cq_zone` from callsign prefix requires a prefix→zone mapping table. Not currently in QSOP. Could defer this field or use a lightweight lookup (cty.dat or similar). Low priority — continent is the more useful filter.

2. **Session start detection:** When exactly does a "session" begin? First decode? First TX? App launch? Suggest: first decode after app launch or after a gap of >10 minutes with no decodes.

3. **Partial QSO detection edge cases:** Target answers you but QSO doesn't complete — currently detected as RESPONDED. If target sends RR73 but you don't log (software glitch), this is incorrectly classified. Acceptable for Phase 1.

4. **Multiple bands in one session:** If user QSYs, should that be a new session or the same session? Suggest: session_start/end per band, outcomes tagged with band.

5. **A-index availability:** Schema includes `a` field but A-index display is not yet implemented in QSOP. Record `null` until available.

6. **Score snapshot timing:** Ensure recommended_freq and scores are captured BEFORE clear_target resets them. The terminal event handler must snapshot state first, then clear.

---

## 13. Lessons Applied

| Past Mistake | Prevention in OutcomeRecorder |
|---|---|
| ALL.TXT parsed on main thread → freeze | Write-only at runtime; analysis is offline on-demand |
| ALL.TXT scanned millions of lines | ~10–30 events per session; never scanned at runtime |
| Blocking I/O caused UI freeze | Single file append, microseconds |
| File discovery was complex | One fixed file path |
| Format varied by application | We control the schema, versioned |
| Error in one subsystem crashed app | try/except around all writes; never crash for recording failure |

---

*This specification consolidates design discussions from February 2026 (initial OutcomeRecorder concept), April 2026 (decoder physics analysis, survivorship bias insight, three-tier outcomes, filter-enabling schema, on-demand analysis design). Ready for implementation.*

**73 de WU2C**
