# QSO Predictor — v2.3.0 Feature Spec

**Session Date:** March 9, 2026  
**Status:** Draft  
**Theme:** Decode intelligence — extract more value from what your radio already hears

All four features in this spec work from local decodes and/or existing PSK Reporter cache. No new data sources required.

---

## Feature 1: Target Activity State & Inferred Competition

**Priority:** High  
**Origin:** Live observation — QSOP recommended "CALL NOW — No competition" while J51A was visibly mid-QSO with JA1XZF  
**Backlog items addressed:** Target Status row, local decode competition refinement

### Problem

Local decode competition counting only looks for stations **calling** the target. It misses the reverse — the target **responding to** someone else — which tells us both that competition exists and that the target is occupied.

### Solution

#### Part 1: Target Activity State

Parse local decodes involving the target callsign to infer what they're doing right now.

**State machine:**

| State | Detected When | Display |
|-------|---------------|---------|
| **CQing** | Decode: `CQ J51A GF25` | "CQing — open for calls" (green) |
| **Working You** | Decode: `WU2C J51A -04` | "Working YOU" (cyan, bold) |
| **Working Other** | Decode: `JA1XZF J51A -04` | "Working JA1XZF" (orange) |
| **Called You** | Decode: `WU2C J51A GF25` (target answering your CQ) | "Calling YOU" (cyan) |
| **Idle** | No decodes involving target for >2 minutes | "Idle" (gray) |
| **Unknown** | No decodes involving target yet | "—" |

**Message parsing key rule:** When target callsign is in Position 2 (second field), the station in Position 1 is who they're working. When target is in Position 1, someone is calling/responding to them.

#### Part 2: Inferred Competition

| Decode | Inference |
|--------|-----------|
| `CALL J51A grid/report` | Direct competition (already detected) |
| `CALL J51A -04` (target responding to CALL) | Inferred competitor — confirmed by target's response |
| `CALL J51A RR73` | Target completing QSO — will be free soon |
| `CQ J51A GF25` | Target is open — competition resets |

Competition count should merge direct (stations we see calling) with inferred (stations the target is responding to that we didn't see call). Age out after ~2 minutes.

#### Part 3: Strategy Recommendation Impact

The target working someone else does **not** mean they can't see you. Some operators (especially Contest Ops and Auto-Seq Runners) juggle multiple QSOs simultaneously. The activity state adjusts **competition awareness and probability**, not overrides strategy.

| Situation | Current | Proposed |
|-----------|---------|----------|
| Target working someone else | "CALL NOW — No competition" | "CALL NOW — Target in QSO with JA1XZF (may still respond)" |
| Target sent RR73 | (no change) | "CALL NOW — Target finishing QSO" |
| Target CQing, nobody visible | "CALL NOW — No competition" | "CALL NOW — Target CQing" |
| Target working you | (no change) | "QSO IN PROGRESS — Continue sequence" |

**Persona integration:** A Contest Op working someone else barely reduces your odds (they juggle). A Casual Op working someone else significantly reduces them (single-threaded). The persona system already has this data.

### Implementation

**Message parsing** — new function `parse_target_activity(message, target_call, my_call)` in `session_tracker.py` or `main_v2.py`. Returns `(state, other_call)`.

```python
def parse_target_activity(message, target_call, my_call):
    parts = message.split()
    if len(parts) < 2:
        return None, None
    
    # Target is CQing
    if parts[0] == 'CQ' and target_call in parts:
        return 'cqing', None
    
    # Target in Position 2 — they are transmitting TO Position 1
    if len(parts) >= 3 and parts[1] == target_call:
        other_call = parts[0]
        payload = ' '.join(parts[2:])
        
        if other_call == my_call:
            if 'RR73' in payload or '73' in payload:
                return 'completing_with_you', my_call
            return 'working_you', my_call
        else:
            if 'RR73' in payload or '73' in payload:
                return 'completing_with_other', other_call
            return 'working_other', other_call
    
    # Target in Position 1 — someone calling/responding TO target
    if len(parts) >= 3 and parts[0] == target_call:
        caller = parts[1]
        return 'being_called', caller
    
    return None, None
```

**Display** — new field in Target Dashboard between Path and Competition. Toast triggers on CQ transition and new QSO detection.

**Scope:** Standalone — works from local decodes only, no PSK Reporter needed. Works in Purist Mode.

### Edge Cases

1. **Partial decodes** — only update state if message parses cleanly
2. **Even/odd cycle blindness** — may not see target's messages directly, but responses TO them still provide inference
3. **Multiple targets** — only track for currently selected target
4. **State aging** — age out to "Idle" after ~2 minutes; `completing_with_other` implies "about to be free" for ~15-30 seconds
5. **AP decodes** — count for inference but could flag as lower confidence
6. **Multi-QSO operators** — persona modulates probability adjustment, not a blanket penalty

### Testing Scenarios

1. Decode `JA1XZF J51A -04` while calling J51A → "Working JA1XZF", competition +1, probability adjusted
2. Decode `JA1XZF J51A RR73` → "Finishing QSO", brief CALL NOW
3. Decode `CQ J51A GF25` → "CQing", CALL NOW
4. Decode `WU2C J51A R-11` → "Working YOU", QSO IN PROGRESS
5. No target decodes for 2+ min → "Idle"
6. Working other → CQ transition → toast: "J51A is now CQing — call now!"

---

## Feature 2: Fox/Hound Mode Awareness

**Priority:** High  
**Origin:** Brian KB1OPD — QSOP recommending frequencies below 1000 Hz while calling 3Y0K (Bouvet Island) operating F/H  
**Affects:** Frequency recommendation, click-to-set, band map display

### Problem

In Fox/Hound mode, the Fox (DX station) transmits below 1000 Hz and Hounds must TX above 1000 Hz. QSOP has no awareness of this and will recommend frequencies in the Fox's TX zone.

### Solution

**Detection:** The WSJT-X/JTDX UDP Status message (Type 1) includes a "Special Operation Mode" field (field 18, quint8):

| Value | Mode |
|-------|------|
| 0 | None |
| 1 | NA VHF |
| 2 | EU VHF |
| 3 | Field Day |
| 4 | RTTY RU |
| 5 | WW DIGI |
| 6 | Fox |
| 7 | Hound |

This tells us what mode **the user** has enabled in JTDX — not what the DX station is running. But that's the right trigger: if the user has enabled Hound mode, QSOP should respect that constraint. When `special_mode == 7` (Hound), clamp recommendations to 1000+ Hz.

Our current UDP parser (`_process_status`) stops at field 11 (Tx DF). We need to continue parsing through fields 12–18:

```
Field 12: DE call (utf8)
Field 13: DE grid (utf8)  
Field 14: DX grid (utf8)
Field 15: Tx Watchdog (bool)
Field 16: Sub-mode (utf8)
Field 17: Fast mode (bool)
Field 18: Special Operation Mode (quint8)  ← this one
```

**Note:** Fields 12–13 (DE call, DE grid) could also be useful — they'd give us the user's callsign and grid without requiring manual configuration, which would simplify the setup wizard.

**⚠️ Version note:** The enum values were renumbered when WW DIGI was added. Check the actual WSJT-X/JTDX version:
- Older: 0=None, 1=NA VHF, 2=EU VHF, 3=Field Day, 4=RTTY RU, 5=Fox, 6=Hound
- Newer: 0=None, 1=NA VHF, 2=EU VHF, 3=Field Day, 4=RTTY RU, 5=WW DIGI, 6=Fox, 7=Hound

Best approach: check for both 6 and 7 as Hound, or detect from schema version.

#### Layer 2: Proactive Fox Detection (DX station side)

Even if the user hasn't enabled Hound mode, QSOP should detect when the **target** is operating as Fox and alert the user. This serves two purposes:
- (a) Inform: "3Y0K appears to be in Fox mode"
- (b) Adapt: clamp recommendations above 1000 Hz and suggest enabling Hound mode

**Detection from local decodes:**
- Fox transmits between 300–900 Hz. If we decode the target and their TX frequency is consistently below 1000 Hz while many stations call above 1000 Hz, that's a Fox pattern.
- Fox messages use a distinctive multi-call format (responding to multiple Hounds in one transmission). These set a specific bit in the 75-bit FT8 payload.
- If the decode message contains two callsigns being worked simultaneously, it's definitely Fox.

**Detection from PSK Reporter:**
- MQTT spots showing the target transmitting below 1000 Hz confirm Fox operation.

**Display when Fox detected but Hound mode not enabled:**
```
Toast: "⚠️ 3Y0K appears to be operating Fox mode — enable Hound in JTDX to call above 1000 Hz"
Band map: shade 0-1000 Hz as "Fox TX zone"  
Recommendations: clamp to 1000-2800 Hz regardless of user's mode setting
```

**SuperFox exception:** In SuperFox mode, the 1000 Hz restriction for Hounds is removed — Hounds can TX anywhere 200–3000 Hz. If SuperFox is detected (verified signature, wider bandwidth signal), don't clamp recommendations. This means we need to distinguish between old-style Fox and SuperFox.

**When F/H detected:**

1. **Clamp frequency recommendations** to 1000–2800 Hz
2. **Clamp click-to-set** to same range
3. **Visual indicator** on band map — shade 0–1000 Hz zone with a "Fox TX" overlay or dim it with a label
4. **Score graph** — zero out scores below 1000 Hz so green line never points there

**Display:**
```
Band map top section:
┌──────────┬─────────────────────────────────┐
│ FOX ZONE │  Hound TX range (1000-2800 Hz)  │
│ (dimmed) │  (normal scoring)               │
└──────────┴─────────────────────────────────┘
```

### Implementation

**UDP parser extension** — in `udp_handler.py`, continue parsing `_process_status()` past field 11 to reach field 18. Add `special_operation_mode` to the emitted status dict:
```python
self.status_update.emit({
    'dial_freq': dial_freq,
    'dx_call': dx_call,
    'tx_df': tx_df,
    'tx_enabled': tx_enabled,
    'transmitting': transmitting,
    'special_mode': special_mode,  # 0=None, 6=Fox, 7=Hound
})
```

**Bonus:** Fields 12–13 give us DE call and DE grid for free — could auto-populate settings.

**Recommendation engine** — in `band_map_widget.py`, when Hound mode active:
```python
if self.hound_mode:
    freq = max(1000, min(2800, freq))  # Clamp to Hound range
```

**Score calculation** — in score_map computation, zero out indices 0–999 when F/H is active.

**Macro alignment** — the AutoHotkey script should also be updated to accept the wider valid range, but this is already done (200–3000).

### Edge Cases

1. **SuperFox vs old-style Fox** — SuperFox removes the 1000 Hz Hound restriction. Need to distinguish between the two. SuperFox uses a wider waveform (1512 Hz) and verified signatures. If decodes show "verified" flags, it's SuperFox → don't clamp Hound TX.
2. **Detecting when F/H ends** — when `special_mode` changes from Hound back to 0, or target stops transmitting below 1000 Hz, remove the restriction.
3. **Manual override** — if user clicks below 1000 Hz while in Hound mode, clamp to 1000 with toast: "⚠️ Hound mode — TX must be above 1000 Hz"
4. **JTDX vs WSJT-X** — both implement the same UDP protocol but may use different enum values. Test with both.
5. **Fox detected but user not in Hound mode** — show advisory toast and clamp recommendations proactively. User still needs to enable Hound in JTDX to actually call.
6. **Receiver passband rolloff** — many radios cut off audio below ~300 Hz in DATA mode, making Fox decodes unreliable at the very bottom. Don't assume failure to decode Fox means they're not there.

### Testing Scenarios

1. **User enables Hound mode** → UDP `special_mode` detected → recommendations clamp to 1000+ Hz
2. **Click below 1000 Hz in Hound mode** → clamp to 1000 with warning toast
3. **User disables Hound mode** → full range restored
4. **Target TX below 1000 Hz** (Fox detected from decodes) → toast alert, band map shows Fox zone, recommendations clamp — even if user hasn't enabled Hound mode yet
5. **SuperFox detected** → no 1000 Hz clamp for Hound TX, but still show Fox zone indicator
6. **Target switches from F/H to normal** → clamp removed, Fox zone overlay cleared
7. **Band map** should visually indicate Fox zone (0-1000 Hz dimmed/labeled)

---

## Feature 3: Show My SNR at Target in Path Intelligence

**Priority:** Medium — quick win  
**Origin:** Brian KB1OPD — VP8 spotted him on PSK Reporter, wanted to see the signal report without leaving QSOP  
**Affects:** Insights panel → Path Intelligence widget

### Problem

When Path Intelligence shows "Your signal confirmed!" (CONNECTED status), it doesn't show what SNR the target reported for the user's signal. This information is already in the PSK Reporter data — it just isn't displayed.

### Solution

The `my_reception_cache` in `analyzer.py` already stores the full spot data including `snr` when a station reports hearing us. When the CONNECTED path status is determined (line ~963 in `analyzer.py`), the matching `my_rep` spot contains the SNR.

**Pass the SNR through to the UI:**

```python
# In analyzer.py, where CONNECTED is detected:
for my_rep in my_reception_snapshot:
    if my_rep['receiver'] == target_call:
        path_str = "Heard by Target"
        my_snr_at_target = my_rep.get('snr', None)  # NEW
        break
```

**Display in Path Intelligence panel:**

Current:
```
✓ Target decoded you — call now!
```

Proposed:
```
✓ Target decoded you at -12 dB — call now!
```

If SNR is strong (≥ 0 dB), green text. If weak (< -15 dB), orange text with tactical note. If moderate, default text.

**Also show for PATH_OPEN (nearby station heard you):**
```
✓ Spotted at -8 dB by W2XYZ (nearby) — path confirmed
```

### Implementation

1. **`analyzer.py`** — when building path status, include `my_snr` in the returned/stored data. Add to `decode_data` dict or return separately.
2. **`insights_panel.py`** — `NearMeWidget.update_display()` reads the SNR and appends it to the status/insight labels.
3. **Dashboard** — optionally show in the Path field: "Heard by Target (-12 dB)"

### Edge Cases

1. **Multiple spots** — target may have spotted us multiple times with different SNRs. Use most recent, or show range.
2. **Stale SNR** — if the spot is old (>5 min), the SNR may no longer be accurate. Could note "(5 min ago)".
3. **No SNR in spot** — some spots may lack SNR data. Fall back to current display without it.

### Testing Scenarios

1. Target spots you at -12 dB → Path Intel shows "Target decoded you at -12 dB"
2. Nearby station spots you at -8 dB → shows "Spotted at -8 dB by W2XYZ"
3. No SNR data → falls back to current "Target decoded you" without dB

---

## Feature 4: Band Edge Score Softening

**Priority:** Low  
**Origin:** Session observation — green recommendation line sitting at 236 Hz, tempting click into extreme low edge  
**Affects:** Frequency recommendation algorithm

### Problem

The frequency recommendation algorithm can suggest frequencies very close to band edges (below ~300 Hz or above ~2700 Hz) where:
- Decoder performance is reduced
- Some rigs have IF filter rolloff
- It's unconventional operating territory
- The AutoHotkey macro was rejecting these values (now fixed, but the root question remains)

Frequencies near edges often score well simply because they're empty — but they're empty for a reason.

### Solution

Add a gentle edge penalty to the score calculation that ramps up as you approach 0 or 3000 Hz. This doesn't prevent edge recommendations — it just makes them less likely unless everything else is genuinely worse.

```python
def edge_penalty(freq):
    """Gentle penalty for frequencies near band edges.
    Returns 0 (no penalty) in the middle, up to ~20 points at extremes."""
    if freq < 300:
        return int(20 * (1 - freq / 300))    # 20 at 0 Hz, 0 at 300 Hz
    elif freq > 2700:
        return int(20 * ((freq - 2700) / 300))  # 0 at 2700, 20 at 3000
    return 0
```

Apply as a subtraction from the existing score for each frequency bucket.

### Implementation

In `band_map_widget.py` where `score_map` is calculated, subtract `edge_penalty(i)` from each score. The existing clamp (200–2800) stays as a hard boundary; this is a soft preference within that range.

### Edge Cases

1. **F/H mode** — when Fox/Hound is active, the 1000 Hz boundary is a hard clamp, not a soft penalty. Edge softening should still apply to the 2700–2800 range.
2. **Genuinely best option** — if everything above 300 Hz is packed, a score of 80 minus 15 edge penalty = 65 might still be the best available. That's fine — the penalty is gentle, not prohibitive.

---

## Dependencies Between Features

```
Feature 1 (Target Activity State)
    └── Standalone, no dependencies
    └── Feeds into: competition count, strategy recommendation, toasts

Feature 2 (Fox/Hound Awareness)  
    └── Depends on: extending UDP status parser to field 18
    └── Bonus: fields 12-13 give DE call/grid for free (setup wizard shortcut)
    └── Feeds into: score calculation, click-to-set clamping, band map display

Feature 3 (SNR at Target)
    └── Standalone, data already in my_reception_cache
    └── Feeds into: Path Intelligence display, dashboard Path field

Feature 4 (Band Edge Softening)
    └── Standalone
    └── Interacts with: Feature 2 (F/H hard clamp takes precedence over soft penalty)
```

**Suggested implementation order:**
1. Feature 3 (SNR at Target) — quickest win, data already there, just plumbing
2. Feature 4 (Band Edge Softening) — simple scoring tweak
3. Feature 1 (Target Activity State) — largest feature, most new code
4. Feature 2 (Fox/Hound) — needs UDP protocol research, DXpedition-specific

---

## Files Likely Affected

| File | Feature 1 | Feature 2 | Feature 3 | Feature 4 |
|------|-----------|-----------|-----------|-----------|
| `main_v2.py` | Activity state display, toast triggers | F/H indicator, clamp override | Dashboard SNR display | — |
| `band_map_widget.py` | — | Fox zone overlay, score zeroing, click clamp | — | Edge penalty in score_map |
| `analyzer.py` | — | — | Pass SNR through path status | — |
| `insights_panel.py` | — | — | SNR in Path Intelligence labels | — |
| `session_tracker.py` | Activity state tracking | — | — | — |
| `udp_handler.py` | — | F/H mode detection from status messages | — | — |

---

*All features originated from live operating observations and user feedback during the March 9, 2026 session.*

**73 de WU2C**
