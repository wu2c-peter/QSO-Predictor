# QSO Predictor

[![Version](https://img.shields.io/badge/version-2.0.8-blue.svg)](https://github.com/wu2c-peter/qso-predictor/releases)
[![License](https://img.shields.io/badge/license-GPL--3.0-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey.svg)](https://github.com/wu2c-peter/qso-predictor/releases)

**Real-Time Tactical Assistant for FT8 & FT4**

QSO Predictor shows you the "view from the other end" — what the DX station is experiencing at their location, not just what you're hearing. Using PSK Reporter data and local intelligence, it helps you make smarter decisions about when and where to call.

---

## 🆕 What's New in v2.0.8

### Local Intelligence Improvements
- **Fixed:** Bootstrap timeout with large log files — now runs in background thread
- **Added:** Background scanner for incremental log processing (no more timeouts!)
- **Added:** Behavior distribution bar showing L/M/R percentages in Insights panel
- **Fixed:** JTDX dated file parsing (trailing `^` `*` `.` `d` markers)

### How It Works Now
- On first run, background scanner processes your full log history (may take 1-2 minutes for large files)
- Saves file position — subsequent runs only scan new data
- UI stays responsive during scanning
- Distribution bar shows observed picking behavior breakdown (Loudest/Methodical/Random)

---

## Downloads

| Platform | Download |
|----------|----------|
| **Windows** | [QSO_Predictor_v2.0.8_Windows.zip](https://github.com/wu2c-peter/qso-predictor/releases/latest) |
| **macOS** | [QSO_Predictor_v2.0.8_macOS.dmg](https://github.com/wu2c-peter/qso-predictor/releases/latest) |

---

## Features

### Target Perspective Engine
- See what the DX station hears, not just what you hear
- Geographic tiering shows signals by proximity to target
- Real-time pileup visualization

### Local Intelligence (v2.0)
- Behavior prediction based on station patterns
- Persona classification (Contest Op, Casual, DX Hunter, etc.)
- Works offline using your WSJT-X/JTDX logs

### Smart Frequency Recommendations
- Proven frequencies scored higher than empty gaps
- Visual score graph across the band
- Click-to-set with dwell timer

### Path Status
- CONNECTED — target has decoded your signal
- Path Open — nearby stations heard you
- No Path — propagation not confirmed

---

## Quick Start

### Windows
1. Download and extract the `.zip` file
2. Run `QSO Predictor.exe`
3. Windows SmartScreen may warn — click **"More info"** → **"Run anyway"**

### macOS
1. Download and open the `.dmg` file
2. Drag QSO Predictor to Applications
3. App is signed and notarized — should open without warnings

### Both Platforms
4. Configure WSJT-X/JTDX: Settings → Reporting → UDP Server = `127.0.0.1`, Port = `2237`
5. Start decoding — select a target station to see their perspective

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Ctrl+R** | Clear target selection |
| **Ctrl+Y** | Sync target to WSJT-X/JTDX |
| **Ctrl+S** | Open Settings |
| **F1** | Open Documentation |
| **F5** | Force refresh spots |

---

## Workflow Features (v2.0.3+)

### Clear Target
- **Button:** "Clear Target" in toolbar
- **Shortcut:** Ctrl+R
- Clears current target and resets all displays

### Auto-Clear on QSO
- **Checkbox:** "Auto-clear on QSO" in toolbar
- Automatically clears target after logging a contact with that station

### Sync to WSJT-X/JTDX (v2.0.6)
- **Button:** "Sync to JTDX" in toolbar, or ⟳ next to target callsign
- **Shortcut:** Ctrl+Y
- Forces QSO Predictor to match JTDX's current DX call selection

---

## Documentation

- **[Wiki Home](https://github.com/wu2c-peter/qso-predictor/wiki)** — Overview and quick start
- **[Quick Usage Guide](https://github.com/wu2c-peter/qso-predictor/wiki/Quick-Usage-Guide)** — Operational workflows
- **[How It Works](https://github.com/wu2c-peter/qso-predictor/wiki/QSO-Predictor-How-and-Why-It-Works)** — Technical deep-dive
- **[Help & Troubleshooting](https://github.com/wu2c-peter/qso-predictor/wiki/Help-and-Troubleshooting)** — Common problems

---

## Version History

# README Updates for v2.0.10

## Instructions
Apply these changes to your existing README.md

---

## 1. Update Version Badge

**Find:**
```markdown
[![Version](https://img.shields.io/badge/version-2.0.9-blue.svg)]
```

**Replace with:**
```markdown
[![Version](https://img.shields.io/badge/version-2.0.10-blue.svg)]
```

---

## 2. Update "What's New" Section

**Replace existing "What's New" section with:**

```markdown
## 🆕 What's New in v2.0.10

### Bug Fixes
- **Fixed:** Windows UDP socket dying when forwarding to closed port (Error 10054)
- **Fixed:** Self-forward detection prevents accidental configuration loops

### Improvements  
- Forward errors now logged once per port (no more log spam)
- Forward port configuration shown in startup log for easier debugging
- Better diagnostic information in logs

### Note
If using UDP forwarding (e.g., to GridTracker), the forward target no longer needs to be running before QSO Predictor starts.
```

---

## 3. Add to Version History Section

**Add this entry at the top of your Version History:**

```markdown
### v2.0.10 (January 2025)
- **Fixed:** Windows UDP socket dying when forwarding to closed port (Error 10054)
- **Fixed:** Self-forward detection prevents accidental loops
- **Improved:** Forward errors logged once per port instead of spamming
- **Improved:** Forward port configuration shown in startup log
- **Thanks:** Brian KB1OPD for detailed bug report and logs

### v2.0.9 (January 2025)
- **New:** Centralized logging system for debugging
- **New:** Help menu items: Enable Debug Logging, Open Log Folder
- **New:** About dialog shows log file path
- **Fixed:** Reduced log verbosity (smart "log first, then summarize" pattern)
- **Technical:** 27 files converted from print() to logging framework
```

---

## 4. Update Troubleshooting Section

**Add to the Troubleshooting section:**

```markdown
### UDP Forwarding Issues (Windows)
If you're forwarding UDP to another application (GridTracker, JTAlert, etc.):
- The forward target no longer needs to be running first
- Check the log for: "UDP: Forwarding enabled to ports: [...]"
- If you see "Forward to port X - target not listening", that's normal when the target app isn't running
```

---

## Commit Message for v2.0.10

```
v2.0.10: Fix Windows UDP forwarding error 10054

BUG FIX:
- Fixed Windows-specific issue where forwarding UDP packets to a closed
  port would kill the entire UDP listener (WinError 10054)
- Applied SIO_UDP_CONNRESET ioctl to disable ICMP error reporting
- Added fallback to catch and ignore error 10054 if ioctl fails

IMPROVEMENTS:
- Self-forward detection prevents accidental loops (forward port = listen port)
- Forward errors logged once per port to avoid log spam
- Forward port configuration shown at startup for easier debugging

Thanks to Brian KB1OPD for the detailed log that identified this issue.

73 de WU2C
```


### v2.0.8 (December 2025)
- Fixed: Bootstrap timeout with large log files (background processing)
- Added: Background scanner for incremental log file processing
- Added: Behavior distribution bar in Insights panel (L/M/R percentages)
- Fixed: JTDX dated file trailing markers (^ * . d)

### v2.0.7 (December 2025)
- Fixed: UI freeze when clicking stations (large ALL.TXT file scan)
- Fixed: Rapid table refresh and re-sorting from UDP flooding
- Fixed: Yellow TX line flickering on band map
- Changed: Station lookup uses cache-only (requires Bootstrap for history)
- Added: Throttling for status updates and path refresh

### v2.0.6 (December 2025)
- Fixed: Severe CPU usage on macOS (38% → 6% idle)
- Fixed: Window layout persistence (splitters, dock widgets)
- Fixed: "Check for Updates" in packaged builds
- Fixed: macOS version display
- Added: Sync to WSJT-X/JTDX button and Ctrl+Y shortcut

### v2.0.4 (December 2025)
- Fixed: Cache cleanup thread crash with invalid timestamps
- Fixed: MQTT auto-reconnect after connection loss
- Fixed: Status bar shows unique stations instead of total spots
- Added: Solar data refresh timer

### v2.0.3 (December 2025)
- Added: Clear Target button and Ctrl+R shortcut
- Added: Auto-clear on QSO logged
- Added: Window size/position and column width persistence
- Fixed: QSO Logged message parsing

### v2.0.0 (December 2025)
- Major release: Local Intelligence system
- Persona-based behavior prediction
- Insights panel with pileup status
- Purist mode (offline operation)

### v1.3.0 (November 2025)
- Smart frequency scoring
- Score graph visualization
- Click-to-set frequency

---

## Requirements

- Windows 10/11 or macOS 10.15+
- WSJT-X or JTDX configured for UDP output
- Internet connection (for PSK Reporter features)

---

## Running from Source

```bash
git clone https://github.com/wu2c-peter/qso-predictor.git
cd qso-predictor
pip install -r requirements.txt
python main_v2.py
```

---

## Contributing

Contributions welcome! Please open an issue or pull request.

### Contributors
- **Warren KC0GU** — Feature suggestions (Clear Target, Auto-clear, UI persistence, Sync button), bug reports (CPU usage)
- **Doug McDonald** — Bug reports (UI freeze with large logs, startup health check feedback)

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.

---

## Links

- [Releases](https://github.com/wu2c-peter/qso-predictor/releases)
- [Discussions](https://github.com/wu2c-peter/qso-predictor/discussions)
- [Issues](https://github.com/wu2c-peter/qso-predictor/issues)
- [Wiki](https://github.com/wu2c-peter/qso-predictor/wiki)

---

**73 de WU2C**
