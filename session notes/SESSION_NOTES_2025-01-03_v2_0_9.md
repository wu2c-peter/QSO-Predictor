# QSO Predictor Session Notes
**Date:** January 3, 2025  
**Version:** 2.0.9  
**Session:** Centralized logging system implementation

---

## Overview

Implemented a comprehensive logging system to replace scattered print() statements throughout the codebase. This enables proper debugging for user-reported issues (particularly Brian's UDP connection problem) while keeping logs manageable.

---

## Features Implemented in v2.0.9

### Centralized Logging Module (logging_config.py)

**New file:** `logging_config.py`

**Features:**
- Rotating file handler: 5MB max, 3 backups (total ~20MB max)
- Platform-appropriate log locations:
  - Windows: `%APPDATA%\QSO Predictor\logs\qso_predictor.log`
  - macOS: `~/Library/Application Support/QSO Predictor/logs/qso_predictor.log`
  - Linux: `~/.config/QSO Predictor/logs/qso_predictor.log`
- Consistent log format: `%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s`
- Debug format adds function/line: `%(funcName)s:%(lineno)d`
- Third-party library suppression (paho.mqtt, urllib3, PyQt6 → WARNING only)

**API:**
```python
setup_logging(console=True, file=True)  # Call once at startup
set_debug_mode(True/False)              # Toggle verbose logging
is_debug_mode()                         # Check current state
get_log_file_path()                     # Get Path object
open_log_folder()                       # Open in platform file browser
```

### Help Menu Additions

**New menu items under Help:**
- **Enable Debug Logging** - Checkbox to toggle debug mode
  - Shows confirmation dialog with log file path when enabled
  - Note: "Debug logging will be disabled on next restart"
- **Open Log Folder...** - Opens platform file browser to logs directory
- **About dialog** - Now includes log file path

### Smart Logging Patterns

**Problem:** Initial implementation logged every MQTT spot and UDP packet, generating 47,000+ lines in 6 minutes.

**Solution:** "Log first, then summarize" pattern:

```
INFO | MQTT: First spot received - N8CDY -> W1BW 11dB
INFO | MQTT: Spots are flowing (individual spots not logged to reduce verbosity)
DEBUG | MQTT: Spot rate: 480.0/min (total: 28800)   <- every 60 seconds
```

**Applied to:**
- MQTT spots (was flooding logs)
- UDP decodes and status updates
- Session tracker "No target session" polling
- Model manager "directory does not exist" checks

### Log Level Strategy

| Level | Usage |
|-------|-------|
| ERROR | Things that broke (exceptions, failed operations) |
| WARNING | Unexpected but recovered (disconnections, parse errors) |
| INFO | Key events (startup, connections, target changes, QSO logged) |
| DEBUG | Verbose details (packet contents, lookup details, periodic stats) |

### Files Converted (27 total)

**Core files:**
- `main_v2.py` - 13 print→logger, added logging setup, Help menu items
- `udp_handler.py` - Complete rewrite with smart logging, diagnostics method
- `mqtt_client.py` - Smart logging with periodic stats, diagnostics method
- `analyzer.py`, `solar_client.py`, `launcher.py`, `startup_health_dialog.py`

**Local Intelligence:**
- `local_intel_integration.py` - Smart message for frozen vs source builds
- `behavior_predictor.py` - Cleaned up duplicate logs
- `session_tracker.py` - State-change-only logging for "No target session"
- `model_manager.py` - Log-once pattern, DEBUG level for directory checks
- `background_scanner.py`, `log_discovery.py`, `log_parser.py`

**Already had logging (verified):**
- `insights_panel.py`, `training_dialog.py`, `training_manager.py`
- `local_intel/predictor.py`, `models.py`
- `training/*.py`

**No changes needed:**
- `band_map_widget.py`, `config_manager.py`, `settings_dialog.py`

---

## Bug Fixes During Implementation

### AttributeError: '_no_models_logged'
**Problem:** `_no_models_logged` flag initialized in `ensure_directory()` but `load_models()` called first.
**Fix:** Move initialization to `__init__`.

---

## Log Output Comparison

### Before (47,000+ lines in 6 minutes):
```
DEBUG | MQTT: Spot YC7ONI -> VK2WAJ -8dB
DEBUG | MQTT: Spot UA3IHJ -> VK2WAJ -15dB
... (every single spot)
DEBUG | get_target_behavior: No target session
DEBUG | get_target_behavior: No target session
... (every second)
INFO | Model directory does not exist: ...
INFO | Model directory does not exist: ...
... (7 times at startup)
```

### After (~30 lines for typical session):
```
INFO | QSO Predictor logging initialized
INFO | Log file: .../qso_predictor.log
INFO | Platform: Darwin 24.6.0
INFO | MQTT: Connecting to mqtt.pskreporter.info:1883
INFO | UDP: Bound to port 2237
INFO | Local Intelligence initialized
INFO | MQTT: Connected to PSK Reporter
INFO | MQTT: Subscribed to pskr/filter/v2/20m/FT8/# and ...
INFO | MQTT: First spot received - N8CDY -> W1BW 11dB
INFO | MQTT: Spots are flowing (individual spots not logged to reduce verbosity)
INFO | No trained models - using heuristic predictor
INFO | Background scanner started
INFO | Local Intelligence setup complete
INFO | UDP: Listener thread started
... (clean operation)
INFO | MQTT: Stopping client (total spots received: 1873)
INFO | UDP: Stopping listener (total: 0 packets, 0 decodes, 0 status)
```

---

## Diagnostic Methods Added

### udp_handler.get_diagnostics()
```python
{
    'port': 2237,
    'ip': '0.0.0.0',
    'is_multicast': False,
    'running': True,
    'messages_received': 1234,
    'decodes_received': 456,
    'status_received': 778,
    'last_packet_age': 0.5,
    'forward_ports': [],
}
```

### mqtt_client.get_diagnostics()
```python
{
    'broker': 'mqtt.pskreporter.info',
    'port': 1883,
    'running': True,
    'connected': True,
    'my_call': 'WU2C',
    'current_band': '20m',
    'spots_received': 5000,
    'last_spot_age': 0.3,
}
```

---

## Testing Notes

### macOS Log Location
```bash
# View log
cat ~/Library/Application\ Support/QSO\ Predictor/logs/qso_predictor.log

# Live monitoring
tail -f ~/Library/Application\ Support/QSO\ Predictor/logs/qso_predictor.log

# Access hidden Library folder in Finder
# Cmd+Shift+G → paste path
# Or: chflags nohidden ~/Library
```

### Windows Log Location
```
%APPDATA%\QSO Predictor\logs\qso_predictor.log
```

---

## For Brian's UDP Issue

With logging now in place, ask Brian to:
1. Help → Enable Debug Logging
2. Reproduce the connection issue
3. Help → Open Log Folder
4. Send `qso_predictor.log`

Log will reveal:
- UDP bind success/failure
- Packet reception (or lack thereof)
- Message type parsing
- Exact error messages

---

## Files in v2.0.9 Deliverable

```
logging_config.py          <- NEW
main_v2.py
udp_handler.py
mqtt_client.py
analyzer.py
band_map_widget.py
config_manager.py
settings_dialog.py
solar_client.py
startup_health_dialog.py
launcher.py
insights_panel.py
local_intel_integration.py
training_dialog.py
training_manager.py
local_intel/__init__.py
local_intel/background_scanner.py
local_intel/behavior_predictor.py
local_intel/log_discovery.py
local_intel/log_parser.py
local_intel/model_manager.py
local_intel/models.py
local_intel/predictor.py
local_intel/session_tracker.py
training/__init__.py
training/feature_builders.py
training/trainer_process.py
```

---

## Version Numbering Decision

**v2.0.9** (not v2.1.0) because:
- This is infrastructure/debugging improvement
- No user-facing features added
- v2.1.0 roadmap (Hunt Mode, band filtering, etc.) reserved for feature release

---

## Next Steps

1. Test on Windows to verify paths work
2. Build Windows .exe and verify frozen detection works
3. Release v2.0.9
4. Send logging instructions to Brian for UDP debugging
5. Update wiki with logging documentation

---

**73 de WU2C**
