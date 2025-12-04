# QSO Predictor

**Real-Time Tactical Assistant for FT8 & FT4** *Copyright (C) 2025 Peter Hirst (WU2C)*

**Current Version:** See [Releases](https://github.com/wu2c-peter/qso-predictor/releases) for latest

-----

## The Problem

You're calling a DX station. No response. Is the band dead? Is your signal too weak? Or are you buried under a pileup you can't even hear?

Today's tools show you the band from your shack — who you're decoding, who's spotting you. They don't show you conditions at the DX station's end.

## The Solution

QSO Predictor fills that gap. Using PSK Reporter data, it builds a picture of band conditions at the target's location — what signals are arriving there, from where, and how your path compares.

The result: fewer wasted calls, smarter timing, better target choices.

-----

## What This Tool Does

- Shows you **band conditions at the target's location**, not just global activity
- Uses geographic tiering: direct reports from the target (best), same grid square, same field, global (fallback)
- Tells you whether **your signal path is open** to a given station's region
- Recommends **clear TX frequencies** based on what the target is experiencing
- Integrates with **WSJT-X/JTDX** — double-click a station and the perspective updates immediately

## What This Tool Doesn't Replace

- **PSK Reporter** — QSOP uses PSK Reporter data; it's complementary, not a replacement
- **RBN/Ham Spots** — Those confirm your signal is getting out; QSOP shows your competition at the far end
- **GridTracker** — Great for mapping and alerts; QSOP adds the target perspective layer

Think of it this way: other tools answer "Am I being heard?" QSOP answers "What does the DX station's receiver look like right now?"

-----

## Quick Start (Windows)

1. Download the latest `.zip` from [Releases](https://github.com/wu2c-peter/qso-predictor/releases)
2. Extract and run `QSO Predictor.exe`
3. **First run:** Windows SmartScreen may warn about an unrecognized app. Click "More info" → "Run anyway". If it won't start, right-click → "Run as administrator" once. After the first run, it launches normally.
4. Configure WSJT-X/JTDX: Settings → Reporting → UDP Server = `127.0.0.1`, Port = `2237`

-----

## Key Features

### 1. The Target Perspective Band Map

The band map shows **what the target station's region experiences** — not just global band activity. When you click on a station in the decode table, QSO Predictor builds a picture of their RF environment using geographic proximity as a proxy for propagation similarity.

**The Tiered Intelligence System:**

| Color | Tier | Source | What It Means |
| :--- | :--- | :--- | :--- |
| **Cyan** | 1 | Target Station | Signals the target is actually decoding (if they upload to PSK Reporter) |
| **Bright Blue** | 2 | Same Grid Square | Signals heard by stations in the same 4-character grid. Good proxy for similar propagation. |
| **Medium Blue** | 3 | Same Field | Signals heard by stations in the same 2-character field. Regional approximation. |
| **Dark Blue** | 4 | Global | All other band activity. Background context only. |
| **Red** | — | Collision | A Tier 1 or Tier 2 signal overlapping the target's frequency. **Avoid transmitting here.** |

**Cyan Bar Density Indicators:**

Cyan bars now show a **count number** indicating how many signals the target is decoding at that frequency. Based on K1JT's decoder research, WSJT-X can decode 2-3 overlapping signals reliably via signal subtraction.

| Count | Bar Color | Label Color | Score | Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **1-3** | Bright Cyan | Cyan | 90-100 | **Ideal** — proven decode slot, not saturated |
| **4-5** | Cyan-Blue | Yellow | 60-70 | Warning — getting crowded |
| **6+** | Dim Blue-Purple | Orange | 30-50 | Crowded — decode probability drops |

**Why This Matters:** A proven frequency (where the target IS decoding) is often better than an empty gap (which might have local QRM you can't see). But a proven frequency with 6+ signals stacked on it is crowded — better to find one with 1-3 signals.

**Important:** Cyan bars show what the target is hearing from *everyone* — not specifically where *your* signal gets through. Your signal path status is shown separately in the **Path** column.

**Why Geographic Tiering Matters:**

Propagation is regional. A pileup visible from Europe may not exist from the target's location in Japan. By filtering spots geographically, you see the QRM environment that actually affects your target — not noise from the other side of the world.

### 2. The Lower Display: What You Hear

The bottom half of the band map shows **your local decodes** — signals your own radio is receiving. These are color-coded by SNR:

| Color | SNR | Meaning |
| :--- | :--- | :--- |
| **Green** | > 0 dB | Strong signal |
| **Yellow** | -10 to 0 dB | Medium signal |
| **Red** | < -10 dB | Weak signal |

### 3. Real-Time MQTT Engine

The app connects directly to the **PSK Reporter Live Stream** via MQTT, with data refreshing continuously.

* **Low Latency:** Spots appear seconds after they are reported.
* **No Rate Limits:** Eliminates API bans and quotas.
* **Continuous Refresh:** Target perspective updates every 3 seconds automatically.

### 4. Intelligent Frequency Recommendation

The recommendation system has been redesigned based on research into how the WSJT-X decoder handles overlapping signals.

**The Score Graph (Middle Section):**

A new score visualization shows the algorithm's reasoning across all frequencies:

| Score | Color | Line Style | Meaning |
| :--- | :--- | :--- | :--- |
| 85-100 | Green | Solid | Excellent — proven frequency with 1-3 signals |
| 60-84 | Cyan | Solid | Good — proven or clear gap |
| 40-59 | Yellow | Solid/Dotted | Moderate — unproven or light congestion |
| 20-39 | Orange | Solid/Dotted | Poor — crowded area |
| 0-19 | Red | Solid/Dotted | Avoid — blocked by local QRM or edge |

**Line Style Meaning:**
- **Solid line** = Tier 1 perspective data available (scores based on proven frequencies)
- **Dotted line** = No tier 1 data, "(gap-based scoring)" — scores based on avoiding congestion

**The Scoring Philosophy:**

Based on K1JT's research, the decoder handles 2-3 overlapping signals well via signal subtraction. The new algorithm:

1. **Prefers proven frequencies** where the target IS decoding (cyan bars with 1-3 signals)
2. **Discounts crowded slots** where 4+ signals are stacked
3. **Treats empty gaps as "unproven"** — they could be clear, or could have local QRM at the target you can't see
4. **Falls back to gap-finding** when no tier 1 data is available

**The Green Line:**

- Shows the highest-scoring frequency
- **Sticky behavior** — only moves when current spot gets busy or a significantly better option appears
- Score displayed next to the line

**Click-to-Set:**

Click anywhere on the band map to manually set the recommended frequency. The green line jumps to your click position and dwells for 3 seconds (countdown shown), then resumes auto-calculation. Use this to read off a specific frequency for manual entry into JTDX.

-----

## On-Air Usage Guide

### Basic Workflow

1. **Start QSO Predictor** and let it connect to WSJT-X/JTDX.
2. **Wait for decodes** to populate the table.
3. **Select a station** to work — either:
   - **Double-click in JTDX/WSJT-X** (decode window or receive window) — the target perspective updates immediately
   - **Click a row** in QSO Predictor's decode table
4. **Read the band map:**
   * **Top half:** What the target's region hears (tiered by geographic confidence)
   * **Bottom half:** What you hear locally
5. **Look for gaps** in the cyan/bright blue bars — these are clear frequencies at the target's location.
6. **Set your TX frequency** to avoid red collision zones.

### Tactical Decision Making

**Scenario 1: Cyan bars with counts 1-3**
The target station is uploading to PSK Reporter and these frequencies have light traffic. **Ideal spots.** The decoder handles 1-3 overlapping signals well. Transmit here for best decode probability.

**Scenario 2: Cyan bars with counts 4-5 (yellow labels)**
Getting crowded. Still proven decode slots, but competition is building. Consider these if no 1-3 options exist.

**Scenario 3: Cyan bars with counts 6+ (orange labels)**
Heavily saturated. Even though these are proven frequencies, decoder performance degrades with this many overlapping signals. Look for less crowded alternatives.

**Scenario 4: No cyan, but bright blue bars visible**
The target isn't uploading, but nearby stations are. The bright blue bars show what stations in their grid square hear — a good proxy for similar propagation. Score graph shows dotted line "(gap-based scoring)".

**Scenario 5: Only dark blue visible**
Limited geographic intelligence. The display shows global activity, which may not reflect the target's actual environment. Consider the target's location and likely propagation paths.

**Scenario 6: Red bar on target frequency**
A station the target can hear is transmitting on or near their frequency. **Wait.** The target is likely unable to decode you through the interference.

### Reading the Path Column

The **Path** column shows whether you have a confirmed signal path to that station's region:

| Status | Color | Meaning |
| :--- | :--- | :--- |
| **CONNECTED** | Cyan | Target has heard you — best case, call them! |
| **Path Open** | Green | A station in the same grid or field has heard you — propagation confirmed |
| **No Path** | Orange | Reporters exist near target but haven't heard you — path may not be open |
| **No Nearby Reporters** | Gray | No PSK Reporter data from that region — unknown |

**Note:** Path status requires you to have transmitted recently. The feature is most useful once you're actively operating.

### Reading the Dashboard (Selected Target)

When you select a target station, the dashboard shows:

**Path** — Your signal path status to this target (same as table column)

**Competition** — QRM at the target's location using the tiered perspective:

| Status | Color | Meaning |
| :--- | :--- | :--- |
| **CONNECTED** | Cyan | Target has heard you — you're in! |
| **Clear** | Green | No competition detected at target's location |
| **Low (1)** | Default | 1 competing station |
| **Medium (2-3)** | Default | Light competition |
| **High (4-6)** | Orange | Significant competition — consider waiting |
| **PILEUP (7+)** | Red | Heavy pileup — difficult conditions |
| **Unknown** | Gray | No data from target's region |

### Pro Tips

1. **Watch the count numbers.** Cyan bars with "1", "2", or "3" are your best bets. Those with "6" or higher are crowded despite being proven.

2. **Use the score graph.** Green peaks show where the algorithm thinks you should transmit. If you see a peak but no cyan bar there, it's a gap — unproven but clear of visible activity.

3. **Solid vs dotted line matters.** Solid score line = algorithm has proven data. Dotted = gap-based guessing. Trust solid-line recommendations more.

4. **Click to explore.** Click anywhere on the band map to set a manual frequency. Read the Hz value from the Rec display, then enter it in JTDX.

5. **Cyan shows activity, not your path.** Seeing cyan bars means the target is uploading spots — you know what they hear. But that doesn't mean they've heard *you*. Check the Path column for that.

6. **Respect the red.** Collision detection is physics-based. If a strong station is on the target's frequency, no amount of power will help.

7. **Grid squares matter.** Stations in the same grid square share similar propagation. Heavy bright-blue activity means the target's area is busy even if they aren't personally uploading.

8. **CONNECTED is gold.** If Path shows CONNECTED, the target has already decoded you. Call them!

-----

## Installation & Usage

### 1. Requirements
* Python 3.10 or higher.
* WSJT-X or JTDX.
* Dependencies: PyQt6, paho-mqtt, numpy, requests (auto-installed by launcher)

### 2. Setup
1. **Clone/Download** this repository.
2. Run the **Launcher**:
   ```bash
   python launcher.py
   ```
   *The launcher will automatically install necessary dependencies (`PyQt6`, `paho-mqtt`, `numpy`, `requests`).*

### 3. Configure WSJT-X / JTDX
1. Open **Settings** -> **Reporting**.
2. Check **"Accept UDP Requests"**.
3. Set **UDP Server** to `127.0.0.1`.
4. Set **UDP Port** to `2237`.

-----

## Project History & Changelog

### v1.3.0 - The Smart Frequency Update

* **Intelligent Frequency Scoring**
    * Algorithm now prefers "proven" frequencies (where target IS decoding) over empty gaps.
    * Based on K1JT's decoder research: 1-3 overlapping signals decode well, 4+ degrades.
    * Cyan bars show count numbers indicating signal density at each frequency.
    * Color-coded counts: Cyan (1-3 ideal), Yellow (4-5 warning), Orange (6+ crowded).

* **Score Graph Visualization**
    * New middle section shows score across all frequencies.
    * Green = excellent, Cyan = good, Yellow = moderate, Orange = poor, Red = avoid.
    * Solid line = proven data, Dotted line = gap-based scoring (no tier1 data).

* **Click-to-Set Frequency**
    * Click anywhere on band map to manually set recommended frequency.
    * 3-second dwell with countdown, then resumes auto-calculation.
    * Read Hz value from Rec display for manual entry into JTDX.

* **Update Notification System**
    * Checks GitHub for new releases on startup.
    * Gold info bar when update available, click to download.
    * Help → Check for Updates for manual check.

### v1.2.0 - The Target Perspective Update

* **Major Feature: Geographic Perspective Engine**
    * Band map now shows what the *target's region* hears, not global activity.
    * Tiered system: Direct (Cyan) → Same Grid (Bright Blue) → Same Field (Blue) → Global (Dark Blue).

* **New Path Column**
    * Shows signal path status: CONNECTED, Path Open, No Path, No Nearby Reporters.
    * Lightweight updates every 2 seconds.
    * Tells you at a glance which stations are reachable.

* **Sticky Frequency Recommendation**
    * Green line no longer bounces around chasing marginal improvements.
    * Only moves when current spot gets busy or a significantly better gap appears.

* **JTDX/WSJT-X Integration**
    * Double-clicking a station in JTDX/WSJT-X immediately updates the target perspective.

* **Case Sensitivity Fix**
    * Callsign matching now case-insensitive throughout.

* **Auto-scroll Table**
    * Decode table stays scrolled to bottom (like JTDX) unless you scroll up to review history.

* **UI Improvements**
    * Dashboard shows both Path and Competition.
    * CONNECTED rows highlighted with cyan text and teal background.
    * Info bar shows current band and dial frequency.

### v1.1.0 - The Tactical Update

* Implemented density analysis for pileup detection.
* Added collision detection for frequency overlaps.
* Split-screen band map with safety gap.

### v1.0.1 - The Real-Time Overhaul

* Switched from HTTP polling to MQTT streaming.
* Signal persistence tuned for FT8 Even/Odd cycles.

-----

## License

**GNU General Public License v3 (GPLv3)**
*Copyright (C) 2025 Peter Hirst (WU2C)*

This program comes with ABSOLUTELY NO WARRANTY. This is free software, and you are welcome to redistribute it under certain conditions.
