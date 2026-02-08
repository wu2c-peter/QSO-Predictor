# QSO Predictor

[![Version](https://img.shields.io/badge/version-2.1.2-blue.svg)](https://github.com/wu2c-peter/qso-predictor/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/wu2c-peter/qso-predictor/releases)

**Real-time tactical assistant for FT8/FT4 — see the band from the DX station's perspective.**

![QSO Predictor Screenshot](docs/screenshot.png)

## v2.1.4
- **Fixed: JTDX detection in auto-paste scripts** — JTDX's title bar contains "WSJT-X" (it's a fork), so scripts that check for WSJT-X first match JTDX and use wrong coordinates. Scripts now check JTDX first. Thanks to Brian KB1OPD for reporting.
- **Auto-paste scripts: Enable TX** — after pasting a callsign into the DX Call field, the script now clicks the Enable TX button automatically. One click from QSO Predictor to calling.
- **Auto-paste scripts: separate coordinates** — JTDX and WSJT-X have different field positions, scripts now have independent coordinate settings for each app

## v2.1.3
- **Click-to-copy target callsign** — click the target in either panel to copy to clipboard, then paste into WSJT-X/JTDX (or use the auto-paste scripts in the User Guide)
- **Local decode evidence** — path detection now uses your local decodes as proof, not just PSK Reporter. If you decode a station responding to you, that's "Heard by Target" immediately — no PSK Reporter lag
- **Path column relabeled** for clarity: Heard by Target, Heard in Region, Not Heard in Region, Not Transmitting, No Reporters in Region
- **"Sync to JTDX" → "← Fetch Target"** — button renamed so direction is obvious (pulls JTDX's selection into QSO Predictor)
- **Combined auto-paste scripts** — updated AutoHotkey/Hammerspoon scripts handle both frequency AND callsign clipboard copies
- Handles AP codes correctly (strips them instead of showing as callsign) — thanks to Brian KB1OPD for bug report

## What's New in v2.1.2

### 🐛 Critical Fix: Target Perspective Data
Fixed a timing issue where PSK Reporter spots were rejected as "stale" — the freshness filter was comparing against the original decode timestamp (3-5 minutes old by the time it reaches us) instead of receipt time. **This was the root cause of empty Target Perspective band maps** reported by Brian KB1OPD and others.

### 🛡️ Grid Square Validation
FT8 protocol tokens like `RR73` were being misidentified as Maidenhead grid squares (both match the pattern `[A-Z][A-Z][0-9][0-9]`). Fixed with two layers of defense:
- Suffix check (`RR73`, `73`, signal reports) now runs **before** grid check
- Grid validation tightened to Maidenhead range `[A-R]` (was `[A-Z]`)

### 🔇 ICMP Log Spam Fix
Windows ICMP "connection reset" errors from UDP forwarding to closed ports were flooding the log (1,697 identical lines in one session). Now logs once on first occurrence, with cumulative count shown in periodic stats.

---

## What's New in v2.1.1

### 🔍 Band Map Tooltips
Hover over any signal bar on the band map to see:
- **Callsign**, SNR, audio frequency, and grid square
- **Tier** (Target / Grid / Field / Global) for perspective signals
- Works for both target perspective (top) and local decode (bottom) sections

### 📏 Frequency Scale
Hz labels along the band map sections — 500 Hz major ticks with labels, 100 Hz minor ticks. No more guessing where frequencies are.

### ⚠️ Resilient Data Source Monitoring
Status bar now warns you when data sources go silent:
- **UDP:** Warning after 30 seconds with no data from WSJT-X/JTDX
- **MQTT:** Warning after 60 seconds with no PSK Reporter spots
- Warnings auto-clear when data resumes

### 🔧 Diagnostic Logging
Improved observability for troubleshooting:
- Analyzer module now logs first error with full traceback (was silently swallowing all exceptions)
- Periodic cache health stats for diagnosing empty Target Perspective issues

---

## Highlights from v2.1.0

### 🎯 Hunt Mode
Track specific stations, prefixes, or DXCC entities you want to work:
- Add targets via **Tools → Hunt List** (Ctrl+H) or right-click context menu
- **System tray alerts** when hunt targets are spotted
- **"Working Nearby" alerts** — high-priority notification when your target is working stations from your area
- Gold highlighting in decode table
- Supports callsigns (`3Y0K`), prefixes (`3Y`), and countries (`Japan`)

### 📡 Path Intelligence
Know if others from your area are getting through:
- **Phase 1:** Shows nearby stations the target is hearing with SNR and frequency
- **Phase 2:** Click **Analyze** to understand WHY they're succeeding:
  - Beaming detection (compares directional patterns to peers)
  - Power/antenna advantage detection (+6dB above peers)
  - Frequency suggestions based on their clear spots

### 🖥️ Undockable Panels
Customize your layout for multi-monitor setups:
- Drag panels to float, dock to edges, or rearrange
- **View → Reset Layout** to restore defaults
- Layout saved between sessions

### ✨ Other Improvements
- **Click-to-clipboard:** Click band map or Rec frequency to copy Hz value
- **Auto-clear on QSY:** Optionally clear target when changing bands
- **Improved stability:** Fixed Windows UDP Error 10054 crashes
- **Better error handling:** Graceful degradation when data unavailable

---

## The Problem

You're calling a DX station. No response. Is the band dead? Is your signal too weak? Or are you buried under a pileup you can't even hear?

Traditional tools show the band from **your** perspective. QSO Predictor shows you **the DX station's** perspective.

## The Solution

Using real-time PSK Reporter data, QSO Predictor shows:
- **What the target is hearing** — signals arriving at their location
- **How crowded each frequency is** — at their end, not yours
- **Whether your signal path is open** — before you call
- **Who else from your area is getting through** — and why

## Quick Start

### Windows
1. Download latest `.zip` from [Releases](https://github.com/wu2c-peter/qso-predictor/releases)
2. Extract and run `QSO Predictor.exe`
3. Configure WSJT-X/JTDX: Settings → Reporting → UDP Server = `127.0.0.1`, Port = `2237`

### macOS / Linux (from source)
```bash
git clone https://github.com/wu2c-peter/qso-predictor.git
cd qso-predictor
pip install -r requirements.txt
python main_v2.py
```

### First-Time Setup
1. **File → Settings** — enter your callsign and grid
2. **Tools → Bootstrap Behavior** — analyze your logs for behavior prediction (optional but recommended)

## Features

### Target Perspective Band Map
See what the DX station hears, color-coded by data quality:
- **Cyan** — Target is directly decoding these signals
- **Blue tiers** — Nearby stations (proxy data)
- **Count numbers** — Signal density (1-3 ideal, 6+ crowded)

### Path Status
Your signal's reach, at a glance:
- **Heard by Target** — Target has decoded YOUR signal — call now!
- **Heard in Region** — Stations near the target heard you — path confirmed
- **Not Heard in Region** — Reporters exist but haven't heard you yet
- **Not Transmitting** — You haven't transmitted recently
- **No Reporters in Region** — No PSK Reporter data from that area
- **Analyze button** — Deep dive into why others succeed

### Local Intelligence
Predicts DX station behavior from observed patterns:
- **Loudest First** — favors strong signals
- **Methodical** — works through pileup systematically  
- **Random/Fair** — no clear preference

### Hunt Mode
Never miss a wanted station:
- Track by callsign, prefix, or country
- Desktop notifications when spotted
- Special alerts when working your area

### Smart Frequency Recommendations
- **Green line** — Algorithm's recommended TX frequency
- **Score graph** — Visual scoring across the band
- **Solid vs dotted** — Confidence indicator (proven vs estimated)

## Documentation

📖 **[User Guide](docs/USER_GUIDE.md)** — Complete usage documentation

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+R | Clear target selection |
| Ctrl+H | Open Hunt List |
| Ctrl+S | Open Settings |
| F1 | Open User Guide |
| F5 | Force refresh |

## Requirements

- Windows 10/11, macOS, or Linux
- Python 3.10+ (if running from source)
- WSJT-X or JTDX
- Internet connection (for PSK Reporter data)

## Version History

### v2.1.2 (February 2026)
- **FIXED:** Critical bug where Target Perspective never populated — PSK Reporter spots rejected as stale due to timestamp comparison using decode time instead of receipt time (reported by Brian KB1OPD)
- **FIXED:** FT8 tokens (`RR73`) misidentified as Maidenhead grid squares, causing incorrect tiering
- **FIXED:** ICMP "connection reset" log spam — rate-limited to single message with periodic count summary

### v2.1.1 (February 2026)
- **NEW:** Band map hover tooltips — callsign, SNR, grid, tier (suggested by Brian KB1OPD)
- **NEW:** Frequency scale with Hz labels on band map (suggested by Brian KB1OPD)
- **NEW:** Resilient data source monitoring — status bar warns if UDP/MQTT data stops
- **NEW:** Diagnostic logging in analyzer for troubleshooting empty Target Perspective
- **FIXED:** Silent exception handler in analyzer that could cause empty band map with no error

### v2.1.0 (January 2026)
- **NEW:** Hunt Mode — track stations/prefixes/countries with alerts
- **NEW:** Path Intelligence — see who from your area is getting through and why
- **NEW:** Undockable panels — customize layout for multi-monitor
- **NEW:** Click-to-clipboard for frequencies
- **NEW:** Auto-clear on QSY option
- **FIXED:** Windows UDP Error 10054 crashes
- **FIXED:** Layout issues with right dock panel

### v2.0.10 (December 2025)
- **FIXED:** Critical Windows UDP Error 10054 causing crashes
- Improved error handling for network disruptions

### v2.0.9 (December 2025)
- **NEW:** Debug logging toggle (Help menu)
- **NEW:** Connection Help dialog
- **NEW:** Open Log Folder menu item
- Improved troubleshooting capabilities

### v2.0.3 (December 2025)
- **NEW:** Clear Target button and Ctrl+R shortcut
- **NEW:** Auto-clear on QSO logged
- **NEW:** Window/column size persistence
- **FIXED:** QSO Logged message parsing

### v2.0.0 (November 2025)
- **NEW:** Local Intelligence — behavior prediction from log analysis
- **NEW:** Insights Panel — pileup status, behavior, strategy recommendations
- **NEW:** Multicast UDP support (JTAlert, N3FJP compatibility)
- **NEW:** Persona-based prediction (Contest Op, Casual, DX Hunter, etc.)

### v1.3.0
- Smart frequency scoring (proven > empty)
- Score graph visualization
- Click-to-set frequency with dwell timer

### v1.2.0
- Geographic perspective engine (tiered by proximity)
- Path status column
- WSJT-X/JTDX double-click integration

### v1.0.0
- Initial release
- Real-time MQTT streaming from PSK Reporter
- Basic band map visualization

## Contributing

Contributions welcome! Please open an issue first to discuss proposed changes.

### Contributors
- **Warren KC0GU** — Hunt Mode concept, Clear Target workflow, UI persistence suggestions
- **Brian KB1OPD** — Band map tooltips and frequency scale requests, auto-clear on QSY, testing and feedback
- **Doug McDonald, CaptainBucko, Bill K3CDY** — Beta testing and feedback

## License

This project is licensed under the GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.

## Support

- **Issues:** [GitHub Issues](https://github.com/wu2c-peter/qso-predictor/issues)
- **Discussions:** [GitHub Discussions](https://github.com/wu2c-peter/qso-predictor/discussions)

---

**73 de WU2C**
