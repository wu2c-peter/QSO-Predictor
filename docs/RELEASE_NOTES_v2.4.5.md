# Release Notes — v2.4.5

**Date:** April 2026  
**Theme:** Manual Target Entry & Consistency Fixes

---

## New Feature: Manual Target Entry

You can now target any station by callsign — even if you haven't decoded them 
locally. Click the **+** button next to the target callsign (available in both 
the Target View dashboard and the Insights panel), type a callsign, and press 
Enter. Press Escape to cancel.

### What You'll See

When a manual target is set, QSOP immediately shows everything available from 
PSK Reporter data:

- **Band map perspective** — full tiered view of signals at the target's location
- **Path Intelligence** — stations from your area getting through to the target
- **Pileup Status** — callers visible at the target
- **IONIS prediction** — propagation forecast (requires grid resolution)
- **Behavior prediction** — from log history if available

A **⚠** indicator appears next to the callsign in both panels, showing that the 
station has not been decoded locally. Fields that require local decode data 
(UTC, dB, DT, Freq) show "--".

When the station appears in your local decodes, the ⚠ clears automatically 
and full tactical mode engages — all fields populate, score calculates, and 
the target row highlights in the decode table.

### Grid Lookup Cascade

QSOP resolves the target's grid square from local data sources — no API keys 
required:

1. **PSK Reporter receiver cache** — if the station uploads to PSK Reporter, 
   their grid is in every spot they reported. Most active stations resolve here.
2. **Call/grid map** — grids seen in local decodes
3. **Decode table** — current session's decoded stations
4. **DXCC prefix table** — ~180 prefix→grid mappings covering all major entities. 
   Approximate (country centroid) but sufficient for IONIS and perspective.

If the grid isn't available at initial target set, QSOP retries every 3 seconds 
as new MQTT data arrives. IONIS and perspective activate automatically when the 
grid resolves.

### Use Cases

- **DXpedition preparation** — set the target before they appear on your band
- **Spot tips** — someone tells you 3B8XYZ is on 20m, you target them immediately
- **Pre-check propagation** — "Is the path to JA open right now?" without waiting 
  for a decode
- **AHK/Hammerspoon integration** — click the ⚠ callsign to copy and paste into 
  WSJT-X/JTDX DX Call field

---

## Bug Fixes

### Path / Status Bar Desync (Short Grid Gate)

**Symptom:** Status bar showed "3 near target" while the path column showed 
"Not Reported in Region" for the same station.

**Root cause:** PSK Reporter receivers with short grid squares (2–3 characters 
instead of the usual 4–6) were counted by the status bar's field-level check 
(`len >= 2`) but skipped by the path computation's grid check (`len >= 4` gate). 
The field-level comparison at `r_grid[:2] == target_major` was inside the 
`len >= 4` gate, making it unreachable for short grids.

**Fix:** Both `analyze_decode` and `update_path_only` now handle reporters with 
2–3 character grids. Field-level match uses a lower geo_bonus (10 vs 15) to 
reflect reduced confidence.

### IONIS "Awaiting Target Grid" Without UDP

**Symptom:** IONIS showed "Awaiting target grid…" even when the grid was known 
and the band map was fully populated.

**Root cause:** The IONIS check combined grid and band availability into one 
condition with a misleading error message. The `_current_band` attribute is only 
set from UDP status messages. Without UDP (e.g., running on a second computer 
with MQTT only), band info was never available — but the error said "grid."

**Fix:** Grid and band checks are now separate with distinct messages. When 
`_current_band` is not set from UDP, the band is derived from 
`analyzer.current_dial_freq` (which IS set from MQTT spot data).

### DX Grid from UDP Status

**Symptom:** Target grid sometimes unavailable when set via WSJT-X/JTDX 
double-click, requiring backfill from decode table.

**Root cause:** UDP Status message field 14 (DX Grid) was parsed but assigned 
to `_` (discarded). The grid was available in the message but never passed to 
`_set_new_target`.

**Fix:** DX grid now captured and included in the status emit dict. Passed to 
`_set_new_target` for immediate grid resolution.

### Band Edge Frequency Recommendations

**Symptom:** Green recommendation line occasionally appeared below 300 Hz or 
above 2700 Hz. Clicking to set this frequency could be rejected by WSJT-X or 
silently ignored by auto-paste scripts (which accept 300–3000 Hz).

**Root cause:** Three issues:
1. Edge score zones (0–200 Hz) were zeroed but then overwritten to score 10 
   by the local_busy penalty loop (`range(bandwidth)` instead of `range(200, 2800)`)
2. Soft penalty ramp (200–300, 2700–2800) didn't always prevent recommendations 
   when the rest of the band was heavily congested
3. Click-to-set clamped to 200–2800, below the auto-paste scripts' 300–3000 range

**Fix:** 
- Local_busy loop now runs `range(200, 2800)` only — edge zones stay at zero
- Recommendation clamped to 300–2700 Hz after smooth transition
- Click-to-set clamped to 300–2700 Hz, matching recommendation range
- All QSOP outputs now fall within auto-paste script accepted range

---

## Files Changed

### Modified
- `main_v2.py` — Manual target entry UI, `_on_manual_target()`, `_lookup_grid()` 
  cascade, DXCC prefix table, `_is_manual_target` flag, IONIS band derivation 
  from MQTT, DX grid pass-through from UDP status
- `insights_panel.py` — Manual target entry UI (`+` button, QLineEdit), 
  `manual_target_requested` signal, `set_target()` manual flag, ⚠ indicator
- `local_intel_integration.py` — `set_target()` manual flag pass-through, 
  `manual_target_requested` signal connection
- `analyzer.py` — Short grid gate fix in `analyze_decode` and `update_path_only`
- `udp_handler.py` — DX grid capture (field 14), `dx_grid` in status emit
- `band_map_widget.py` — Edge score fix, recommendation clamping (300–2700), 
  click-to-set clamping (300–2700)

---

## Upgrade Notes

- No new dependencies
- No configuration changes required
- Existing settings preserved
- New `+` button appears automatically in both target panels

---

**73 de WU2C**
