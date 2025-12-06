# QSO Predictor

**Real-Time Tactical Assistant for FT8 & FT4**

*Copyright (C) 2025 Peter Hirst (WU2C)*

**Current Version:** 2.0 — [Download Latest Release](https://github.com/wu2c-peter/qso-predictor/releases)

---

## What Makes QSO Predictor Different

Most ham radio tools show you the band from **your** perspective—who you're decoding, who's spotting you. QSO Predictor shows you the **"view from the other end"**—what the DX station is experiencing at their location.

This is the missing piece. You might be calling into a pileup you can't even hear. You might be on a frequency that's clear at your end but jammed at theirs. QSO Predictor fills that gap.

### How It Complements Other Tools

| Tool | What It Shows | QSO Predictor Adds |
|------|---------------|-------------------|
| **PSK Reporter** | Who heard you, who you heard | What the *target* is hearing (the pileup you're competing in) |
| **RBN/Clusters** | That your signal is getting out | Whether your signal reaches the *specific station* you're calling |
| **GridTracker** | Maps and alerts for worked grids | Target perspective layer—QRM at the DX's end |
| **WSJT-X/JTDX** | Decodes and transmission | Tactical intelligence for *when* and *where* to call |

**Think of it this way:** Other tools answer "Am I being heard?" QSO Predictor answers "What does the DX station's receiver look like right now, and what are my odds of getting through?"

---

## Version 2.0: Local Intelligence

Version 2.0 introduces **Local Intelligence**—a system that learns from your operating history to predict DX station behavior and optimize your calling strategy.

### The Key Innovation: Purist Mode

Some operators prefer not to rely on internet services during operation—whether for contest ethics, personal preference, or simply operating portable without connectivity. Version 2.0 enables **fully offline operation** using only your local logs.

**With Local Intelligence, QSO Predictor can:**
- Analyze your ALL.TXT history to learn station behavior patterns
- Predict whether a DX station picks the loudest caller, works methodically, or chooses randomly
- Estimate your success probability based on pileup size and competition
- Recommend optimal timing and strategy—all without internet access

### What Local Intelligence Tracks

**Operator Personas:** The system classifies DX operators into behavioral profiles based on observable activity:

| Persona | Characteristics | Your Strategy |
|---------|-----------------|---------------|
| **Contest Op** | High QSO rate, picks loudest signals | Maximize your signal strength |
| **Auto-Seq Runner** | Steady pace, high completion rate | Be patient, stay in the queue |
| **Casual Op** | Relaxed pace, methodical picking | Timing matters less than persistence |
| **DX Hunter** | Low completion rate, chases rare calls | Your prefix/grid may matter more than power |
| **Big Gun** | High rate despite big pileups | Likely has beam—signal strength critical |

**Activity Metrics:**
- QSO rate (contacts per minute)
- Completion rate (QSOs ending with 73)
- Session patterns (marathon vs. quick hits)
- Picking behavior (loudest-first vs. methodical vs. random)

### How It Works

1. **Bootstrap from History:** On first run, analyzes your ALL.TXT files (last 14 days) to build behavioral profiles for stations you've observed
2. **On-Demand Lookup:** Click any station to search your logs for their specific behavior
3. **Live Learning:** Watches current session and updates predictions in real-time
4. **Persona Matching:** Even for unknown stations, matches their activity pattern to predict behavior

---

## Feature Overview

### 1. Target Perspective Band Map

The band map shows **what the target station's region experiences**—not global activity. When you select a target, QSO Predictor builds a picture of their RF environment.

**Geographic Tiering:**

| Color | Tier | Source | Reliability |
|-------|------|--------|-------------|
| **Cyan** | 1 | Target Station | Best—signals they're actually decoding |
| **Bright Blue** | 2 | Same Grid Square | Good—similar propagation conditions |
| **Medium Blue** | 3 | Same Field | Regional approximation |
| **Dark Blue** | 4 | Global | Background context only |

**Signal Density Indicators:**

Cyan bars show count numbers indicating how many signals overlap at each frequency:

| Count | Meaning | Score |
|-------|---------|-------|
| **1-3** | Ideal—decoder handles this well | 90-100 |
| **4-5** | Warning—getting crowded | 60-70 |
| **6+** | Saturated—decoder performance drops | 30-50 |

### 2. Intelligent Frequency Scoring

The score graph (middle section) visualizes the algorithm's analysis across all frequencies:

| Score | Color | What It Means |
|-------|-------|---------------|
| 85-100 | Green | Excellent—proven frequency, light traffic |
| 60-84 | Cyan | Good—proven or clear gap |
| 40-59 | Yellow | Moderate—unproven or light congestion |
| 20-39 | Orange | Poor—crowded |
| 0-19 | Red | Avoid—blocked or edge |

**Line Style:**
- **Solid** = Based on proven data (target is uploading spots)
- **Dotted** = Gap-based estimate (no direct perspective data)

### 3. Local Intelligence Panel

The right-side panel displays real-time tactical intelligence:

**Pileup Status:**
- Current caller count
- Your rank (if calling)
- Trend indicators

**Target Behavior:**
- Detected picking pattern (Loudest First, Methodical, Random)
- Confidence level
- Persona classification
- Data source (live observation, historical, persona-based)

**Success Prediction:**
- Probability estimate with confidence
- Key factors affecting your chances

**Strategy Recommendation:**
- CALL NOW / WAIT / TRY LATER
- Specific reasoning

### 4. Path Status

The **Path** column shows whether your signal reaches each station:

| Status | Color | Meaning |
|--------|-------|---------|
| **CONNECTED** | Cyan | Target decoded you—call them! |
| **Path Open** | Green | Nearby stations heard you—path confirmed |
| **No Path** | Orange | Reporters exist but haven't heard you |
| **No Nearby Reporters** | Gray | No data from that region |

### 5. Real-Time Data Engine

- **MQTT Streaming:** Direct connection to PSK Reporter live stream
- **Low Latency:** Spots appear within seconds
- **No Rate Limits:** No API bans or quotas
- **Continuous Updates:** Target perspective refreshes every 3 seconds

---

## Quick Start

### Windows (Recommended)

1. Download the latest `.zip` from [Releases](https://github.com/wu2c-peter/qso-predictor/releases)
2. Extract and run `QSO Predictor.exe`
3. **First run:** Windows SmartScreen may warn—click "More info" → "Run anyway"
4. Configure WSJT-X/JTDX: Settings → Reporting → UDP Server = `127.0.0.1`, Port = `2237`
5. **Initialize Local Intelligence:** Tools → Bootstrap Behavior

### From Source

```bash
# Clone repository
git clone https://github.com/wu2c-peter/qso-predictor.git
cd qso-predictor

# Install dependencies
pip install -r requirements.txt

# Run
python main_v2.py
```

### First-Time Setup

After starting QSO Predictor:

1. **Bootstrap your history:** Tools → Bootstrap Behavior
   - Analyzes last 14 days of ALL.TXT data
   - Builds behavioral profiles for observed stations
   - Takes 10-30 seconds depending on log size

2. **Configure your callsign:** File → Settings → Enter your callsign
   - Required for path status to work

3. **Start operating:** The Local Intelligence panel will populate as you select targets

---

## On-Air Usage

### Basic Workflow

1. **Select a target** (click in QSO Predictor or double-click in WSJT-X/JTDX)
2. **Read the band map:**
   - Top: What the target hears (cyan = best intel)
   - Middle: Algorithm's frequency scores
   - Bottom: What you hear locally
3. **Check the Insights Panel:**
   - Pileup size and your rank
   - Target's picking behavior
   - Success probability
   - Recommended action
4. **Choose your frequency:**
   - Green line = recommended TX frequency
   - Click anywhere to manually explore options
5. **Time your call** based on the strategy recommendation

### Tactical Scenarios

**Scenario: Target picks loudest (Contest Op persona)**
- Focus on maximizing your signal strength
- If you're weak, consider waiting for the pileup to thin
- The "loudest first" indicator means power matters

**Scenario: Target works methodically (Auto-Seq Runner)**
- Be patient—they'll get to you
- Persistence beats power
- Watch for frequency sweeping patterns

**Scenario: Unknown station, no history**
- System matches to nearest persona based on activity
- Watch the first few QSOs to see pattern emerge
- Confidence will increase as data accumulates

**Scenario: "Observing..." displayed**
- No historical data for this station
- System is watching their current session
- After 3-5 QSOs, pattern detection kicks in

### Pro Tips

1. **CONNECTED is gold.** If Path shows CONNECTED, the target already decoded you—call immediately!

2. **Watch the count numbers.** Frequencies with 1-3 signals stacked are ideal. 6+ means saturation.

3. **Solid line = confidence.** Trust solid-line scores over dotted (gap-based guessing).

4. **Persona predicts behavior.** A "Contest Op" will almost always pick the loudest signal. Adjust your strategy accordingly.

5. **Bootstrap regularly.** After a big contest or DXpedition, re-run bootstrap to update behavioral profiles.

6. **Click to explore.** Click anywhere on the band map to read the frequency for manual entry.

7. **Use purist mode for contests.** Disable internet (MQTT) in settings to rely purely on local intelligence.

---

## Changelog

### v2.0.2
- Fixed: Target selection stability (removed processEvents causing re-entrant crashes)
- Fixed: Exe mode hides ML training UI (shows Bootstrap only)
- Fixed: "Models not trained" warning hidden in exe mode
- Added: Multicast UDP support for JTAlert/N3FJP setups

### v2.0.0 - The Local Intelligence Update

**New: Local Intelligence System**
- Persona-based behavior prediction (Contest Op, Casual Op, Auto-Seq Runner, DX Hunter, Big Gun)
- Activity trait tracking (QSO rate, completion rate, session patterns)
- Bootstrap from ALL.TXT history (14 days, configurable)
- On-demand station lookup from logs
- Live pattern detection during operation

**New: Insights Panel**
- Pileup status with caller count and your rank
- Target behavior analysis with confidence levels
- Success probability prediction
- Strategy recommendations (CALL NOW / WAIT / TRY LATER)

**New: Purist Mode**
- Full offline operation using only local logs
- No internet dependency for predictions
- Ideal for contests or portable operation

**New: Multicast UDP Support**
- Join multicast groups (224.x.x.x - 239.x.x.x)
- Works alongside JTAlert, N3FJP, and other apps
- Configure via `udp_ip` setting in config.ini

**Improved: Bootstrap Performance**
- Extended to 14 days, 500K decodes
- Tracks both picking behavior and activity traits
- Session boundary detection (5-minute gaps)
- QSO completion tracking (73/RR73 detection)

### v1.3.0 - The Smart Frequency Update

- Intelligent frequency scoring (proven > empty)
- Score graph visualization
- Click-to-set frequency with dwell timer
- Signal density indicators with count numbers
- Update notification system

### v1.2.0 - The Target Perspective Update

- Geographic perspective engine (tiered by proximity)
- Path status column (CONNECTED, Path Open, No Path)
- WSJT-X/JTDX double-click integration
- Sticky frequency recommendations

### v1.1.0 - The Tactical Update

- Pileup density analysis
- Collision detection
- Split-screen band map

### v1.0.0 - Initial Release

- Real-time MQTT streaming from PSK Reporter
- Basic band map visualization
- Frequency recommendation

---

## Technical Details

### Requirements

- Python 3.10+ (if running from source)
- WSJT-X or JTDX configured for UDP output
- Windows 10/11 (for .exe), or any OS with Python

### Dependencies

```
PyQt6>=6.4.0
paho-mqtt>=1.6.0
numpy>=1.21.0
requests>=2.28.0
scikit-learn>=1.0.0  # For ML models
```

### File Locations

**Windows:**
- Config: `%APPDATA%\QSO Predictor\qso_predictor.ini`
- Models: `%USERPROFILE%\.qso-predictor\models\`
- Behavior history: `%USERPROFILE%\.qso-predictor\behavior_history.json`

**macOS:**
- Config: `~/Library/Application Support/QSO Predictor/qso_predictor.ini`

**Linux:**
- Config: `~/.config/QSO Predictor/qso_predictor.ini`

**Logs searched:**
- WSJT-X: `%LOCALAPPDATA%\WSJT-X\` 
- JTDX: `%LOCALAPPDATA%\JTDX\`
- Both ALL.TXT and dated files (YYMMDD_ALL.TXT)

### Multicast Support

If you use UDP multicast with JTAlert, N3FJP, or other apps (common setup: `239.0.0.2:2237`), QSO Predictor can join the same multicast group.

Edit your config file (Windows: `%APPDATA%\QSO Predictor\qso_predictor.ini`):
```ini
[NETWORK]
udp_ip = 239.0.0.2
udp_port = 2237
```

QSO Predictor automatically detects multicast addresses (224.x.x.x - 239.x.x.x) and joins the group, allowing all your apps to share the same UDP stream from JTDX.

### Architecture

```
qso-predictor/
├── main_v2.py              # Application entry point
├── local_intel_integration.py  # Integration layer
├── insights_panel.py       # UI panel
├── band_map_widget.py      # Band visualization
├── local_intel/            # Core intelligence engine
│   ├── behavior_predictor.py   # Persona/behavior prediction
│   ├── session_tracker.py      # Live session analysis
│   ├── log_parser.py           # ALL.TXT parsing
│   └── log_discovery.py        # Log file discovery
└── training/               # ML training components
    ├── feature_builders.py
    └── trainer_process.py
```

### ML Training (Developers Only)

The Windows .exe uses Bootstrap for behavior prediction, which works entirely in-process. Full ML model training (success predictor, frequency recommender) requires running from source:

```bash
python main_v2.py
# Then: Tools → Train Models → Start Training
```

This spawns a subprocess for training, which isn't possible in a frozen executable.

---

## Contributing

Contributions welcome! Please see the [GitHub repository](https://github.com/wu2c-peter/qso-predictor) for issues and pull requests.

## License

**GNU General Public License v3 (GPLv3)**

*Copyright (C) 2025 Peter Hirst (WU2C)*

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

---

## Links

- [GitHub Repository](https://github.com/wu2c-peter/qso-predictor)
- [Download Releases](https://github.com/wu2c-peter/qso-predictor/releases)
- [Wiki Documentation](https://github.com/wu2c-peter/qso-predictor/wiki)
- [Report Issues](https://github.com/wu2c-peter/qso-predictor/issues)

**73 de WU2C**
