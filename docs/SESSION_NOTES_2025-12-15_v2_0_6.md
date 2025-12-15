# QSO Predictor Session Notes
**Date:** December 15, 2025  
**Version:** 2.0.6  
**Session:** CPU optimization, UI persistence, Sync to JTDX feature

---

## Summary

Performance optimization, UI persistence improvements, and new sync feature addressing user feedback from Warren KC0GU.

---

## Changes by File

### `band_map_widget.py` — CPU Optimization
- **Problem:** 38% CPU usage at idle on macOS (Warren's "CPU hog" complaint)
- **Root cause:** 20Hz timer (50ms) + synchronous `repaint()` calls + paint object allocation every frame
- **Fix:**
  - Reduced timer from 20Hz → 4Hz (250ms interval)
  - Changed `repaint()` → `update()` (async, coalesced repaints)
  - Cached paint objects (pens, brushes, fonts) as class attributes
- **Result:** 6% idle CPU (84% reduction), 20% with active decodes

### `build-release.yml` — Build Fixes
- Added `requests` to pip install for both Windows and macOS builds
- Added `--hidden-import=requests` to macOS pyinstaller command
- Added `--add-data "VERSION:."` to macOS build (fixes "Version: 0.0.0" display)

### `main_v2.py` — UI Persistence & Sync Feature
- **Splitter persistence:** Vertical splitter (table/bandmap) position now saved/restored
- **Dock persistence:** Local Intelligence panel width now saved/restored
- **Sync to JTDX button:** Added to toolbar between "Clear Target" and "Auto-clear"
- **Sync button in dashboard:** Small ⟳ button next to target callsign
- **Ctrl+Y shortcut:** Menu action in Edit menu
- **`sync_to_jtdx()` method:** Forces QSO Predictor target to match JTDX's current DX call

### `insights_panel.py` — Sync Button
- Added `sync_requested` signal
- Added ⟳ button next to "Target:" label in panel header

### `local_intel_integration.py` — Signal Connection
- Connected insights panel's `sync_requested` signal to main window's `sync_to_jtdx()`

---

## New Feature: Sync to JTDX

**Problem:** When user clicks a different station in QSO Predictor, then double-clicks the original station in JTDX, nothing happens (JTDX thinks it's already on that station so doesn't re-send UDP).

**Solution:** Manual sync button (3 locations) + Ctrl+Y shortcut to force QSO Predictor to match JTDX's selection.

| Location | Button |
|----------|--------|
| Toolbar | "Sync to JTDX" |
| Dashboard | ⟳ (next to callsign) |
| Local Intelligence panel | ⟳ (next to "Target:") |

---

## Config Keys Added

| Key | Purpose |
|-----|---------|
| `WINDOW.splitter_state` | Vertical splitter position |
| `WINDOW.dock_state` | Dock widget positions/sizes |

---

## Performance Analysis

### Before (v2.0.4)
- Idle CPU: 38%
- Active CPU: 40%+
- Profiler showed: 1137 timer samples, 993 repaint() samples

### After (v2.0.6)
- Idle CPU: 6%
- Active CPU: 20%
- Profiler showed: 143 timer samples, 0 repaint() hotspots, 80% mach_msg_trap (idle)

---

## Bug Fixes

### `requests` not bundled in builds
- **Symptom:** "Check for Updates" failed on packaged app
- **Cause:** `requests` not installed in build environment (lazy import missed by PyInstaller)
- **Fix:** Added to pip install in workflow + hidden-import flag

### VERSION file missing on Mac
- **Symptom:** "Version: 0.0.0 (0)" in Mac app
- **Cause:** Mac build used command-line pyinstaller, not spec file
- **Fix:** Added `--add-data "VERSION:."` to Mac build command

---

## Contributors

- **Warren KC0GU** — Reported CPU issue, suggested splitter persistence, identified JTDX sync problem

---

## Files Modified

```
band_map_widget.py
build-release.yml  
main_v2.py
insights_panel.py
local_intel_integration.py
```

---

## Testing Done

- ✅ CPU usage verified via macOS Activity Monitor profiler
- ✅ Splitter persistence confirmed (horizontal and vertical)
- ✅ Dock widget (Local Intelligence panel) persistence confirmed
- ✅ Sync button tested with JTDX workflow
- ✅ Ctrl+Y shortcut functional

---

## Git Commands

```bash
git add band_map_widget.py build-release.yml main_v2.py insights_panel.py local_intel_integration.py
git commit -m "v2.0.6: CPU optimization, UI persistence, Sync to JTDX feature"
git tag v2.0.6
git push && git push --tags
```

---

**73 de WU2C**
