# QSO Predictor

[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](https://github.com/wu2c-peter/qso-predictor/releases)
[![License](https://img.shields.io/badge/license-GPL--3.0-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey.svg)](https://github.com/wu2c-peter/qso-predictor/releases)

**Real-Time Tactical Assistant for FT8 & FT4**

QSO Predictor shows you the "view from the other end" — what the DX station is experiencing at their location, not just what you're hearing. Using PSK Reporter data and local intelligence, it helps you make smarter decisions about when and where to call.

---

## 🆕 What's New in v2.1.0

### Hunt Mode 🎯
Track your most-wanted stations with the new Hunt Mode feature:
- **Hunt List** — Add callsigns, prefixes, grids, or DXCC entities (e.g., "ZL", "VU4", "JAPAN", "USA")
- **Visual Highlighting** — Hunted stations appear with gold background in decode table
- **MQTT Alerts** — System tray notifications when hunted stations are spotted
- **Right-Click to Add** — Quickly add any station to your hunt list from the decode table
- **DXCC Entities** — Hunt entire countries by name (100+ entities supported)

### Row Highlighting by Path Status
Instantly see propagation status with color-coded rows:
- **Teal** — CONNECTED (target has decoded your signal!)
- **Green** — Path Open (propagation to region confirmed)
- **Gold** — Hunted station from your list

### Auto-Clear on QSY
- New "Auto-clear on QSY" checkbox in toolbar
- Automatically clears decode table, band map, and target when you change bands
- Great for contest operation

### Click-to-Clipboard (Band Map)
- Click anywhere on the band map to copy that frequency to clipboard
- Visual cursor feedback and toast notification

---

## Downloads

| Platform | Download |
|----------|----------|
| **Windows** | [QSO_Predictor_v2.1.0_Windows.zip](https://github.com/wu2c-peter/qso-predictor/releases/latest) |
| **macOS** | [QSO_Predictor_v2.1.0_macOS.dmg](https://github.com/wu2c-peter/qso-predictor/releases/latest) |

---

## Features

### Target Perspective Engine
- See what the DX station hears, not just what you hear
- Geographic tiering shows signals by proximity to target
- Real-time pileup visualization

### Hunt Mode (v2.1.0) 🎯
- Track specific callsigns, prefixes, grids, or countries
- Visual highlighting and system tray alerts
- Right-click context menu integration
- Supports 100+ DXCC entities by name

### Local Intelligence (v2.0)
- Behavior prediction based on station patterns
- Persona classification (Contest Op, Casual, DX Hunter, etc.)
- Works offline using your WSJT-X/JTDX logs

### Smart Frequency Recommendations
- Proven frequencies scored higher than empty gaps
- Visual score graph across the band
- Click-to-set with dwell timer

### Path Status with Row Highlighting
- **CONNECTED** — Target has decoded your signal (teal background)
- **Path Open** — Nearby stations heard you (green background)
- **No Path** — Propagation not confirmed

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

## Hunt Mode Quick Start

1. **Tools → Hunt List** to open the Hunt List dialog
2. **Add targets:**
   - Callsigns: `K5D`, `3Y0J`
   - Prefixes: `VU4`, `ZL`
   - Grids: `FN31`
   - Countries: `JAPAN`, `USA`, `NEW ZEALAND`
3. **Or right-click** any station in the decode table → "Add to Hunt List"
4. Hunted stations show **gold background** and trigger **tray notifications**

### Supported DXCC Entities
USA, CANADA, JAPAN, GERMANY, ENGLAND, FRANCE, ITALY, SPAIN, AUSTRALIA, NEW ZEALAND, BRAZIL, ARGENTINA, SOUTH AFRICA, INDIA, CHINA, SOUTH KOREA, and 80+ more. Type the country name (case-insensitive) to hunt all prefixes for that entity.

---

## Row Color Legend

| Background | Meaning |
|------------|---------|
| **Teal** | CONNECTED — target heard you, CALL NOW! |
| **Green** | Path Open — propagation confirmed to region |
| **Gold** | Hunted station from your list |
| **Blue** | Currently selected row |

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

## Workflow Features

### Clear Target
- **Button:** "Clear Target" in toolbar
- **Shortcut:** Ctrl+R
- Clears current target and resets all displays

### Auto-Clear on QSO
- **Checkbox:** "Auto-clear on QSO" in toolbar
- Automatically clears target after logging a contact with that station

### Auto-Clear on QSY (v2.1.0)
- **Checkbox:** "Auto-clear on QSY" in toolbar
- Clears decode table, band map, and target when you change bands

### Sync to WSJT-X/JTDX
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

### v2.1.0 (January 2025)
- **New:** Hunt Mode — track callsigns, prefixes, grids, DXCC entities
- **New:** Gold highlighting for hunted stations in decode table
- **New:** System tray notifications for hunted stations (MQTT alerts)
- **New:** Right-click context menu to add stations to hunt list
- **New:** Auto-clear on QSY (band change clears table/map/target)
- **New:** Path Open rows highlighted with green background
- **New:** CONNECTED rows highlighted with teal background
- **New:** Click-to-clipboard on band map
- **Fixed:** Qt stylesheet override preventing row highlighting
- **Thanks:** Warren KC0GU (Hunt Mode concept), Brian KB1OPD (Auto-clear on QSY)

### v2.0.10 (January 2025)
- **Fixed:** Windows UDP socket dying when forwarding to closed port (Error 10054)
- **Fixed:** Self-forward detection prevents accidental loops
- **Improved:** Forward errors logged once per port instead of spamming
- **Thanks:** Brian KB1OPD for detailed bug report and logs

### v2.0.9 (January 2025)
- **New:** Centralized logging system for debugging
- **New:** Help menu items: Enable Debug Logging, Open Log Folder
- **Fixed:** Reduced log verbosity (smart "log first, then summarize" pattern)

### v2.0.8 (December 2025)
- Fixed: Bootstrap timeout with large log files (background processing)
- Added: Background scanner for incremental log file processing
- Added: Behavior distribution bar in Insights panel (L/M/R percentages)

### v2.0.7 (December 2025)
- Fixed: UI freeze when clicking stations (large ALL.TXT file scan)
- Fixed: Rapid table refresh and re-sorting from UDP flooding
- Changed: Station lookup uses cache-only (requires Bootstrap for history)

### v2.0.6 (December 2025)
- Fixed: Severe CPU usage on macOS (38% → 6% idle)
- Fixed: Window layout persistence (splitters, dock widgets)
- Added: Sync to WSJT-X/JTDX button and Ctrl+Y shortcut

### v2.0.3 (December 2025)
- Added: Clear Target button and Ctrl+R shortcut
- Added: Auto-clear on QSO logged
- Added: Window size/position and column width persistence

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
- **Warren KC0GU** — Feature suggestions (Hunt Mode, Clear Target, Auto-clear, UI persistence, Sync button), bug reports
- **Brian KB1OPD** — Bug reports (UDP forwarding, Auto-clear on QSY)
- **Doug McDonald** — Bug reports (UI freeze with large logs)

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
