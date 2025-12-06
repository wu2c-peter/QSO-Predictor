# QSO Predictor v2.0.3 Release Notes

**Release Date:** December 2025  
**Type:** Feature release with bug fixes

---

## New Features

### Clear Target Functionality
- **Clear Target button** in toolbar for quick target reset
- **Ctrl+R keyboard shortcut** to clear target (now actually implemented!)
- Clears all target-related state: dashboard, band map, Local Intelligence panel

### Auto-Clear on QSO Logged
- **New checkbox:** "Auto-clear on QSO" in toolbar
- When enabled, automatically clears target after logging a QSO with that station
- Supports both WSJT-X and JTDX UDP message formats
- Setting persists between sessions

### Window & Column Persistence
- **Column widths** now saved and restored between sessions
- **Window size and position** persist across restarts

---

## Bug Fixes

- **Fixed:** Ctrl+R shortcut was documented but never implemented
- **Fixed:** ML prediction errors no longer spam console (graceful fallback to heuristics)
- **Fixed:** Crash when clearing target with Local Intelligence enabled
- **Fixed:** Slow 3-second lookup when clearing target (now instant)

---

## Technical Notes

### QSO Logged Message Handling
Added support for WSJT-X/JTDX UDP Message Type 5 (QSO Logged). The parser auto-detects QDateTime format variations between different software versions.

### Files Changed
- `main_v2.py` - Clear target, auto-clear, column persistence
- `udp_handler.py` - QSO Logged message parsing
- `local_intel_integration.py` - Fixed None handling, removed slow lookup on clear
- `insights_panel.py` - Added error handling for ML prediction failures

---

## Contributors

Special thanks to **Warren KC0GU** for feature suggestions and beta testing:
- Window/column persistence
- Clear Target workflow (Ctrl+R)
- Auto-clear on QSO logged
- Hunt Mode concept (planned for v2.1.0)

---

## Upgrade Notes

Simply replace the executable or Python files. Settings are preserved.

If you experience issues with ML predictions, you can safely delete the model files:
```
%USERPROFILE%\.qso-predictor\models\*.pkl
```
The application will fall back to heuristic predictions which work well for most users.

---

## What's Next (v2.1.0)

- **Target Status row** - Shows "CQing / Working CALL / Calling CALL" in real-time
- **Hunt Mode** - Persistent tracking for rare DX targets
- **Debug logging mode** - Optional diagnostic output for troubleshooting

---

**73 de WU2C**
