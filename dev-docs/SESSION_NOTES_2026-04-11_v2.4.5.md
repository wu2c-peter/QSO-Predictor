# QSO Predictor Session Notes
**Date:** April 11, 2026  
**Version:** 2.4.5  
**Session:** Manual target entry, bug fixes, and product strategy

---

## Features Implemented in v2.4.5

### Manual Target Entry
- **"+" button** added to both TargetDashboard and InsightsPanel
- QLineEdit overlay with Enter to submit, Escape to cancel
- `manual_target_requested` signal on both panels → `MainWindow._on_manual_target()`
- **⚠ indicator** when target not decoded locally, auto-clears on decode
- Grid lookup cascade: receiver_cache → call_grid_map → decode table → DXCC prefix (~180 entries)
- Grid retry on 3-second refresh timer for late-arriving MQTT data
- `_is_manual_target` flag managed across all target-change paths

### Grid Lookup Cascade
- Priority 1: `analyzer.receiver_cache` — any PSK Reporter uploader's grid
- Priority 2: `analyzer.call_grid_map` — locally decoded stations
- Priority 3: `model._data` — decode table rows
- Priority 4: `_PREFIX_GRIDS` — ~180 DXCC prefix→grid mappings
- Longest-prefix-first matching (KH6 before K, etc.)

---

## Bug Fixes

### Path/Status Bar Desync (Short Grid Gate)
- **Symptom:** Status bar "3 near target" but path column "Not Reported in Region"
- **Root cause:** `len(r_grid) >= 4` gate in path computation excluded reporters with 2-3 char grids
- **Fix:** Added `elif len(r_grid) >= 2` block in both `analyze_decode` and `update_path_only`
- **Discovered from:** Screenshot of KL5NE (Alaska, BP50) target

### IONIS Without UDP
- **Symptom:** "Awaiting target grid…" when grid was known
- **Root cause:** `_current_band` only set from UDP; IONIS combined grid+band check with wrong message
- **Fix:** Split checks, derive band from `analyzer.current_dial_freq` (MQTT source)
- **Discovered from:** Mac testing without UDP stream

### DX Grid from UDP
- **Symptom:** Target grid sometimes unavailable from UDP double-click
- **Root cause:** UDP field 14 (DX Grid) parsed but assigned to `_` (discarded)
- **Fix:** Captured as `dx_grid`, added to status emit, passed to `_set_new_target`

### Band Edge Recommendations
- **Symptom:** Green line at <300 Hz or >2700 Hz; WSJT-X/auto-paste may reject
- **Root cause:** Edge score zones overwritten by local_busy loop; soft penalty insufficient
- **Fix:** Loop restricted to `range(200, 2800)`; recommendation clamped 300–2700; click-to-set clamped 300–2700; all aligned with AHK/Hammerspoon scripts (300–3000)

---

## Product Strategy Discussion

### Multi-Source Spot Data
- Identified four sources: PSK Reporter (MQTT), RBN (telnet), DX Cluster (telnet), WSPRnet (HTTP)
- PSK Reporter dominates (~23M spots/day), RBN ~400K/day, WSPRnet ~6.7M/day
- Architecture: separate collector threads feeding shared `queue.Queue` — no UDP, no IPC
- Each source is a `.py` file, thread with daemon=True, config checkbox to enable
- WSPR excluded from initial implementation (rate limits, beacon-only, no operator contact opportunity)

### "Worked Before on Other Modes" Feature
- Parse `wsjtx_log.adi` for worked-before callsign set (zero-config, standard ADIF)
- Cross-reference against DX Cluster spots for SSB/CW activity
- Alert: "JA1XYZ (worked FT8 Mar 15) spotted on SSB 14.210 — path open"
- Product story: "QSOP helps you turn a digital contact into a real conversation"
- Prioritized over global heat map (DXLook already does that well)

### QSOP Product Family (Explored, Not Committed)
- Discussed QSOP as platform brand: Tactical / Propagation / Contest / Log Intel
- Before/During/After operating cycle framing
- Concluded: DXLook already covers propagation visualization well
- Better strategy: enrich QSOP Tactical with multi-source data, not build competing map
- IONIS prediction-vs-reality overlay remains unique differentiator

### Outcome Tracking / Self-Evaluation
- Discussed whether QSOP can evaluate its own effectiveness
- Counterfactual problem: no control group (can't compare with/without QSOP)
- Workarounds: pre/post QSO rate comparison, advice-followed vs advice-ignored
- OutcomeRecorder (designed Feb 2026) is prerequisite — should ship as silent data collector

### A Index Display
- Brian KB1OPD asked about A index
- Not in current NOAA data we fetch — need separate endpoint or check if new format includes it
- Display only, not in condx algorithm (A is derived from K, would double-count)
- Peter to run test script to check NOAA endpoints

---

## Files Modified

| File | Changes |
|------|---------|
| `main_v2.py` | Manual target UI, `_on_manual_target()`, `_lookup_grid()`, DXCC prefix table, `_is_manual_target` flag, IONIS band derivation, DX grid from UDP, QLineEdit/QShortcut imports |
| `insights_panel.py` | Manual target UI (`+` button, QLineEdit), `manual_target_requested` signal, `set_target()` manual flag, ⚠ indicator, QLineEdit/QShortcut imports |
| `local_intel_integration.py` | `set_target()` manual flag, `manual_target_requested` signal connection |
| `analyzer.py` | Short grid gate fix in `analyze_decode` and `update_path_only` |
| `udp_handler.py` | DX grid capture (field 14), `dx_grid` in status emit |
| `band_map_widget.py` | Edge score fix, recommendation clamping (300–2700), click-to-set (300–2700) |
| `README.md` | Version badge 2.4.5, What's New section |
| `docs/RELEASE_NOTES_v2.4.5.md` | NEW |
| `docs/USER_GUIDE.md` | Manual Target Entry section |
| `docs/DEVELOPMENT_NOTES_v2.3.1_additions.md` | v2.4.5 technical notes |

---

## Backlog Updates

### Added This Session
- Multi-source spot collector (DX Cluster priority, then RBN)
- "Worked before on other modes" feature (wsjtx_log.adi + DX Cluster spots)
- A index display in solar status bar
- OutcomeRecorder → ship as silent data collector
- Self-evaluation dashboard (Phase 2-3, after OutcomeRecorder has data)

### Existing (Confirmed Still Active)
- Score decay by recency/stability
- TX cycle conflict detection
- Email QSL on QSO logged
- Band map UX redesign (color hierarchy)
- Hunt Mode frequency display

---

## Testing Notes

- Manual target tested on Mac without UDP stream (MQTT only)
- IONIS grid/band resolution confirmed working after fix
- ⚠ indicator displays correctly in both panels
- Band map perspective populates for manual targets
- Click-to-copy strips ⚠ prefix correctly
- Edge clamping needs verification on Windows with active band

---

**73 de WU2C**
