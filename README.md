# QSO Predictor

**Real-Time Tactical Assistant for FT8 & FT4**

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Version](https://img.shields.io/badge/version-2.0.3-green.svg)](https://github.com/wu2c-peter/qso-predictor/releases)

---

## The Problem

You're calling a DX station. No response. Is the band dead? Is your signal too weak? Or are you buried under a pileup you can't even hear?

Today's tools show you the band from **your** perspective — who you're decoding, who's spotting you. They don't show you what's happening at the **DX station's** end.

## The Solution

QSO Predictor shows you the **"view from the other end."** Using PSK Reporter data, it builds a picture of band conditions at the target's location — what signals are arriving there, how crowded each frequency is, and whether your signal path is open.

| Traditional Tools | QSO Predictor |
|-------------------|---------------|
| "Who heard me?" | "What does the DX station hear?" |
| Global band activity | Target's local RF environment |
| Your waterfall | Their pileup |
| After-the-fact confirmation | Real-time tactical intelligence |

---

## Features

### Target Perspective Engine
- **Geographic tiering** — Prioritizes data from stations near your target
- **Tier 1 (Cyan):** Signals the target actually decodes
- **Tier 2-3 (Blue):** Regional proxy data from nearby stations
- **Collision detection** — Shows frequency conflicts at target's location

### Local Intelligence (v2.0)
- **Behavior prediction** — Learn how DX stations pick callers (Loudest First, Methodical, Random)
- **Persona classification** — Contest Op, Casual Op, DX Hunter, etc.
- **Pileup tracking** — See your rank in real-time
- **Strategy recommendations** — CALL NOW / WAIT / TRY LATER

### Path Status
- **CONNECTED** — Target has decoded YOUR signal — call them!
- **Path Open** — Stations near target heard you — path confirmed
- **No Path** — Reporters exist but haven't heard you

### Smart Frequency Recommendations
- **Score graph** — Visual representation of best TX frequencies
- **Proven vs Empty** — Frequencies where target IS decoding score higher
- **Sticky recommendations** — Won't bounce around chasing marginal improvements
- **Click-to-set** — Click band map to manually set frequency

### Workflow Features (v2.0.3)
- **Clear Target** — Button and Ctrl+R shortcut to reset target
- **Auto-clear on QSO** — Automatically clears target after logging
- **Window/column persistence** — Layout saved between sessions

---

## Quick Start (Windows)

1. Download the latest `.zip` from [Releases](https://github.com/wu2c-peter/qso-predictor/releases)
2. Extract and run `QSO Predictor.exe`
3. **First run:** Windows SmartScreen may warn — click "More info" → "Run anyway"
4. Configure WSJT-X/JTDX: Settings → Reporting → UDP Server = `127.0.0.1`, Port = `2237`
5. Start decoding — select a target station to see their perspective

### Running from Source (Windows/Mac/Linux)

```bash
git clone https://github.com/wu2c-peter/qso-predictor.git
cd qso-predictor
pip install -r requirements.txt
python main_v2.py
```

Requires Python 3.10+

---

## Understanding the Display

### Band Map (Three Sections)

**Top: Target Perspective** — What stations near the target are hearing
- Cyan bars with count numbers show signal density (1-3 ideal, 6+ crowded)

**Middle: Score Graph** — Algorithm's frequency recommendations
- Green peaks = best frequencies
- Solid line = proven data, Dotted = gap-based estimate

**Bottom: Your Local Decodes** — What your radio receives
- Green/Yellow/Red by signal strength

### Overlay Lines
| Line | Color | Meaning |
|------|-------|---------|
| Target | Magenta | Target station's TX frequency |
| TX | Yellow (dotted) | Your current TX frequency |
| Rec | Green | Recommended TX frequency |

### Path Column
| Status | Color | Meaning |
|--------|-------|---------|
| CONNECTED | Cyan | Target decoded YOU — call now! |
| Path Open | Green | Stations near target heard you |
| No Path | Orange | Reporters exist but didn't hear you |
| — | Gray | No data from that region |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+R | Clear target selection |
| Ctrl+S | Open Settings |
| F1 | Open Documentation (Wiki) |
| F5 | Force refresh spots |

---

## Configuration

### Network Settings

**Standard (single application):**
```ini
[NETWORK]
udp_ip = 127.0.0.1
udp_port = 2237
```

**Multicast (with JTAlert, GridTracker, N3FJP):**
```ini
[NETWORK]
udp_ip = 239.0.0.2
udp_port = 2237
```

### Config File Locations

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\QSO Predictor\qso_predictor.ini` |
| macOS | `~/Library/Application Support/QSO Predictor/` |
| Linux | `~/.config/QSO Predictor/` |

---

## Local Intelligence Setup

For best results, initialize behavior history from your logs:

1. Go to **Tools → Bootstrap Behavior**
2. Click **Start Bootstrap**
3. Wait 10-30 seconds (analyzes last 14 days of ALL.TXT)

Re-run after major operating sessions or contests.

---

## Troubleshooting

### No Decodes Appearing
1. Check WSJT-X/JTDX UDP settings match QSO Predictor
2. If using multicast, ensure QSO Predictor config matches
3. Check Windows Firewall allows UDP port

### Running with GridTracker / JTAlert
Use JTDX Secondary UDP Server or multicast mode. See [Wiki](https://github.com/wu2c-peter/qso-predictor/wiki/Help-and-Troubleshooting) for detailed setup.

### ML Prediction Errors
If you see prediction errors, delete the model files to use heuristic fallback:
```
del "%USERPROFILE%\.qso-predictor\models\*.pkl"
```

---

## Documentation

Full documentation available on the [GitHub Wiki](https://github.com/wu2c-peter/qso-predictor/wiki):

- [Quick Usage Guide](https://github.com/wu2c-peter/qso-predictor/wiki/Quick-Usage-Guide)
- [How and Why It Works](https://github.com/wu2c-peter/qso-predictor/wiki/How-and-Why-It-Works)
- [Help and Troubleshooting](https://github.com/wu2c-peter/qso-predictor/wiki/Help-and-Troubleshooting)

---

## Version History

### v2.0.3 (December 2025)
- **New:** Clear Target button and Ctrl+R shortcut
- **New:** Auto-clear on QSO logged option
- **New:** Window and column width persistence
- **Fixed:** ML prediction error spam
- **Fixed:** Crash when clearing target

### v2.0.0 (November 2025)
- Local Intelligence System with behavior prediction
- Persona-based classification
- Insights Panel with pileup tracking
- Purist Mode for offline operation

### v1.3.0
- Smart frequency scoring
- Click-to-set frequency
- Update notification system

[Full version history](https://github.com/wu2c-peter/qso-predictor/releases)

---

## Contributors & Acknowledgments

QSO Predictor is developed by **Peter Hirst (WU2C)** with AI assistance from Claude (Anthropic).

### Beta Testers & Feature Contributors

| Callsign | Contributions |
|----------|---------------|
| **Warren KC0GU** | Window/column persistence, Clear Target workflow, Auto-clear on QSO, Hunt Mode concept |

### Want to Contribute?

- **Bug reports:** [Open an issue](https://github.com/wu2c-peter/qso-predictor/issues)
- **Feature ideas:** [Start a discussion](https://github.com/wu2c-peter/qso-predictor/discussions)
- **Beta testing:** Contact WU2C via QRZ or GitHub

We welcome feedback from the amateur radio community!

---

## License

QSO Predictor is free software released under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0).

Copyright © 2025 Peter Hirst (WU2C)

---

## Acknowledgments

- **PSK Reporter** — Real-time spot data via MQTT
- **WSJT-X / JTDX** — The foundation of FT8/FT4 operation
- **Amateur Radio Community** — Feedback and testing

---

**73 de WU2C**
