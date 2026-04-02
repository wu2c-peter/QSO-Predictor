# QSO Predictor

[![Version](https://img.shields.io/badge/version-2.3.4-blue.svg)](https://github.com/wu2c-peter/qso-predictor/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/wu2c-peter/qso-predictor/releases)

**Real-time tactical assistant for FT8/FT4 — see the band from the DX station's perspective.**

![QSO Predictor Screenshot](docs/screenshot.png)

---

## 🆕 What's New in v2.3.4

### Solar Data Fix (NOAA API Change)

NOAA changed the format of their space weather JSON data feeds on March 31, 2026 (SCN 26-21). The SFI and K-index fields were renamed and restructured. QSOP now handles both the old and new formats, so "Solar: SFI 0 | K 0 (Unknown)" is resolved.

*Thanks to Brian KB1OPD for spotting this.*

### Score/Path Desync Fix

The Score column in the decode table was only calculated when a decode first arrived — it was never updated when the Path status changed. If a PSK Reporter spot aged out and Path changed from "Reported in Region" to "Not Reported in Region", the Score retained its original high value. Now Score is recalculated on every path refresh (every 2 seconds), staying in sync with the current path status.

### Misleading "CALL NOW" With No Target Data

When PSK Reporter had no coverage at the target's location (PathStatus UNKNOWN), the recommendation engine defaulted to "CALL NOW" with "No competition" — treating absence of data as favorable conditions. Now correctly shows **"▶ CALL (no intel)"** in muted blue with "No target area data" as the reason. Both heuristic and ML predictors fixed.

---

## Previous Releases

### v2.3.3

* **FIXED:** Target change state inconsistency — all target-change paths unified through single `_set_new_target()` handler
* **IMPROVED:** UDP silence detection — context-specific status bar warnings (bind failed, never received, data stopped)
* **CHANGED:** "Prob %" renamed to "Score", "Success Prediction" renamed to "Opportunity Score"
* **IMPROVED:** Auto-paste scripts now click "Generate Std Msgs" after pasting callsign
* **IMPROVED:** Tooltips on clickable elements mention auto-paste script integration

### v2.3.2

* **REMOVED:** Layer 2 F/H inference — either false positive or redundant; detection now via manual combo box, UDP, and SuperFox auto-detect only
* **FIXED:** Multicast UDP crash at startup (WinError 10065) — app now starts gracefully and falls back to unicast (Bob K7TM)

### v2.3.1

* **NEW:** Three-state F/H combo box — Off / F/H / SuperF/H (replaces checkbox)
* **NEW:** Disambiguation dialog when UDP detects Hound mode
* **FIXED:** 1000 Hz clamping now applies to F/H only, not SuperF/H
* **FIXED:** Path field truncation for long SNR labels

### v2.3.0

* **NEW:** Target Activity State — real-time status showing whether target is CQing, Working YOU, Working other, or Idle
* **NEW:** Fox/Hound Mode Awareness — manual combo box + WSJT-X UDP auto-detection
* **NEW:** Fox zone overlay on band map, recommendation clamping to ≥1000 Hz in F/H mode
* **NEW:** SNR at Target — surfaces PSK Reporter signal strength in Path field and Path Intelligence panel
* **NEW:** Band Edge Score Softening — gentle score ramp in 200–300 Hz and 2700–2800 Hz zones

### v2.2.1

* **FIXED:** Critical bug — local decode competition data incorrectly triggered "hidden pileup" warnings when PSK Reporter had zero perspective data from target's area

### v2.2.0

* **NEW:** Tactical observation toasts — real-time alerts for hidden pileups, path changes, competition shifts
* **NEW:** Pileup contrast intelligence — cross-references local vs target-side competition
* **NEW:** Column header tooltips
* **NEW:** Local decode competition fallback
* **FIXED:** Critical substring matching bug — "Not Reported in Region" incorrectly matched as "Reported in Region"

### v2.1.4

* Fixed JTDX detection in auto-paste scripts
* Band map frequency scale brightened for Windows visibility
* Auto-paste scripts click Enable TX automatically

### v2.1.3

* Click-to-copy target callsign from either panel
* Local decode evidence for path detection
* Path column relabeled for clarity

### v2.1.2

* **FIXED:** Target Perspective never populated — receipt time now used instead of decode time
* Grid square validation tightened

### v2.1.1

* Band map hover tooltips (callsign, SNR, grid, tier)
* Frequency scale with Hz labels
* Resilient data source monitoring

### v2.1.0

* **NEW:** Hunt Mode — track stations/prefixes/countries with alerts
* **NEW:** Path Intelligence — see who from your area is getting through and why
* **NEW:** Undockable panels — multi-monitor layout support
* Click-to-clipboard, auto-clear on QSY, Windows UDP Error 10054 fix

---

## The Problem

You're calling a DX station. No response. Is the band dead? Is your signal too weak? Or are you buried under a pileup you can't even hear?

Traditional tools show the band from **your** perspective. QSO Predictor shows you **the DX station's** perspective.

## The Solution

Using real-time PSK Reporter data, QSO Predictor shows:

* **What the target is hearing** — signals arriving at their location
* **How crowded each frequency is** — at their end, not yours
* **Whether your signal path is open** — before you call
* **Who else from your area is getting through** — and why

## Quick Start

### Windows

1. Download latest `.zip` from [Releases](https://github.com/wu2c-peter/qso-predictor/releases)
2. Extract and run `QSO Predictor.exe`
3. Configure WSJT-X/JTDX: Settings → Reporting → UDP Server = `127.0.0.1`, Port = `2237`

### macOS / Linux (from source)

```
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

* **Cyan** — Target is directly decoding these signals
* **Blue tiers** — Nearby stations (proxy data)
* **Count numbers** — Signal density (1-3 ideal, 6+ crowded)

### Path Status

Your signal's reach, at a glance:

* **Heard by Target** — Target has decoded YOUR signal — call now!
* **Heard in Region** — Stations near the target heard you — path confirmed
* **Not Heard in Region** — Reporters exist but haven't heard you yet
* **Not Transmitting** — You haven't transmitted recently
* **No Reporters in Region** — No PSK Reporter data from that area
* **Analyze button** — Deep dive into why others succeed

### Target Activity State

Real-time status of what the target station is doing:

* **CQing** — Target is calling CQ — open for contacts
* **Working YOU** — Target is in QSO with you
* **Working [call]** — Target is in QSO with another station
* **Idle** — No recent target activity

### Fox/Hound Mode Awareness

* Detection via manual combo box, WSJT-X UDP, and SuperFox auto-detect
* Fox zone overlay on band map (0–1000 Hz dimmed)
* Recommendations clamped to ≥1000 Hz in F/H mode
* Full SuperFox/SuperHound support with disambiguation dialog

### Local Intelligence

Predicts DX station behavior from observed patterns:

* **Loudest First** — favors strong signals
* **Methodical** — works through pileup systematically
* **Random/Fair** — no clear preference

### Hunt Mode

Never miss a wanted station:

* Track by callsign, prefix, or country
* Desktop notifications when spotted
* Special alerts when working your area

### Smart Frequency Recommendations

* **Green line** — Algorithm's recommended TX frequency
* **Score graph** — Visual scoring across the band
* **Solid vs dotted** — Confidence indicator (proven vs estimated)

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

* Windows 10/11, macOS, or Linux
* Python 3.10+ (if running from source)
* WSJT-X or JTDX
* Internet connection (for PSK Reporter data)

## Version History

### v2.3.4 (April 2026)
* **FIXED:** Solar data (SFI/K-index) showing zeros — NOAA changed JSON format on March 31 (SCN 26-21). Now handles both old and new formats. (Brian KB1OPD)
* **FIXED:** Score/Path desync — Score column now recalculated on every path refresh, no more stale 99s on stations whose path degraded
* **FIXED:** Misleading "CALL NOW" when no PSK Reporter coverage at target — now shows "CALL (no intel)" in muted blue

### v2.3.3 (March 2026)
* **FIXED:** Target change state inconsistency — dashboard, band map, and insights panel could show stale data from previous target. All target-change paths now unified through single handler.
* **IMPROVED:** UDP silence detection — status bar now warns with specific messages when no data is being received (bind failed, never received, data stopped)
* **CHANGED:** "Prob %" column renamed to "Score" — it's an opportunity score, not a statistical probability. "Success Prediction" panel renamed to "Opportunity Score"
* **IMPROVED:** Auto-paste scripts now click "Generate Std Msgs" after pasting callsign to DX Call field
* **IMPROVED:** Tooltips on clickable elements mention auto-paste script integration

### v2.3.2 (March 2026)
* **REMOVED:** Layer 2 F/H inference — either false positive or redundant; detection now via manual combo box, UDP, and SuperFox auto-detect only
* **FIXED:** Multicast UDP crash at startup (WinError 10065) — app now starts gracefully and falls back to unicast (Bob K7TM)

### v2.3.1 (March 2026)
* **NEW:** Three-state F/H combo box — Off / F/H / SuperF/H
* **NEW:** Disambiguation dialog for F/H mode detection
* **FIXED:** 1000 Hz clamping now applies to F/H only, not SuperF/H
* **FIXED:** Path field truncation for long SNR labels

### v2.3.0 (March 2026)
* **NEW:** Target Activity State (CQing/Working YOU/Working other/Idle)
* **NEW:** Fox/Hound Mode Awareness — manual combo box + WSJT-X UDP auto-detection
* **NEW:** SNR at Target in Path field and Path Intelligence
* **NEW:** Band Edge Score Softening (200–300 Hz and 2700–2800 Hz zones)

### v2.2.1 (February 2026)
* **FIXED:** Local decode competition incorrectly triggering hidden pileup warnings when PSK Reporter had no target-area data

### v2.2.0 (February 2026)
* **NEW:** Tactical observation toasts
* **NEW:** Pileup contrast intelligence
* **NEW:** Column header tooltips
* **FIXED:** Critical substring matching bug in path status

### v2.1.4 (February 2026)
* Fixed JTDX detection, band map scale, auto-paste Enable TX

### v2.1.3 (February 2026)
* Click-to-copy callsign, local decode path evidence, path column clarity

### v2.1.2 (February 2026)
* **FIXED:** Target Perspective stale data rejection bug (Brian KB1OPD)
* Grid square validation fix

### v2.1.1 (February 2026)
* Band map tooltips, frequency scale, resilient data monitoring

### v2.1.0 (January 2026)
* Hunt Mode, Path Intelligence, undockable panels

### v2.0.0 (November 2025)
* Local Intelligence, Insights Panel, Multicast UDP, persona prediction

### v1.x
* Band map, path status, WSJT-X/JTDX integration, frequency scoring

## Contributing

Contributions welcome! Please open an issue first to discuss proposed changes.

### Contributors

* **Brian KB1OPD** — SuperFox/SuperHound live testing (CY0S), F/H false positive report, band map and tooltip requests, extensive beta testing
* **Warren KC0GU** — Hunt Mode concept, Clear Target workflow, UI persistence suggestions
* **Bob K7TM** — Multicast crash bug report
* **Doug McDonald, CaptainBucko, Bill K3CDY, Edgar K9RE** — Beta testing and feedback
* **Jallu OH4NDU** — Linux testing

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE) for details.

## Support

* **Issues:** [GitHub Issues](https://github.com/wu2c-peter/qso-predictor/issues)
* **Discussions:** [GitHub Discussions](https://github.com/wu2c-peter/qso-predictor/discussions)

---

**73 de WU2C**
