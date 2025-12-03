# QSO Predictor

**Real-Time Tactical Assistant for FT8 & FT4** *Copyright (C) 2025 Peter Hirst (WU2C)*

**Current Version:** v1.2.0 (The Target Perspective Update)

QSO Predictor is a "Moneyball" tool for digital amateur radio. It sits between **WSJT-X/JTDX** and the internet, analyzing live data to tell you **who you can work** and **where to transmit** to maximize your success rate.

Unlike standard mapping tools, this is a **Tactical Dashboard**. It calculates probabilities based on signal paths, pileup intensity, and remote QRM — **from the perspective of the station you're trying to work.**

-----

## Key Features

### 1. The Target Perspective Band Map (New in v1.2)

The band map now shows **what the target station actually experiences** — not just global band activity. When you click on a station in the decode table, QSO Predictor builds a picture of their RF environment using geographic proximity as a proxy for propagation similarity.

**The Tiered Intelligence System:**

| Color | Tier | Source | Confidence | What It Means |
| :--- | :--- | :--- | :--- | :--- |
| **Cyan** | 1 | Target Station | **Highest** | Spots reported *by* the target. This is exactly what they hear. |
| **Bright Blue** | 2 | Same Grid Square | High | Spots from stations in the same 4-character grid (e.g., FN42). Similar propagation. |
| **Medium Blue** | 3 | Same Field | Medium | Spots from stations in the same 2-character field (e.g., FN). Regional proxy. |
| **Dark Blue** | 4 | Global | Low | All other band activity. Background context only. |
| **Red** | — | Collision | **Critical** | A Tier 1 or Tier 2 signal overlapping the target's frequency. **Do not transmit.** |

**Why This Matters:**

Previous versions showed global band activity — what *everyone* hears. But propagation is regional. A pileup visible from Europe may not exist from the target's location in Japan. By filtering spots geographically, you see the QRM environment that actually affects your target.

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

* **The Green Line:** Automatically calculates the widest available gap in the spectrum.
* **Weighted Analysis:** Tier 1 (target's actual receivers) signals are weighted most heavily when finding clear frequencies.

-----

## On-Air Usage Guide

### Basic Workflow

1. **Start QSO Predictor** and let it connect to WSJT-X/JTDX.
2. **Wait for decodes** to populate the table.
3. **Select a station** to work — either:
   - **Double-click in JTDX/WSJT-X** (decode window or receive window) — the target perspective updates immediately
   - **Click a row** in QSO Predictor's decode table
4. **Read the band map:**
   * **Top half:** What the target hears (tiered by geographic confidence)
   * **Bottom half:** What you hear locally
5. **Look for gaps** in the cyan/bright blue bars — these are clear frequencies at the target's location.
6. **Set your TX frequency** to avoid red collision zones.

### Tactical Decision Making

**Scenario 1: Cyan bars visible**
The target station is uploading to PSK Reporter. You have direct intelligence. Trust the cyan display — transmit in gaps between cyan bars.

**Scenario 2: No cyan, but bright blue bars visible**
The target isn't uploading, but nearby stations are. The bright blue bars show what stations in their grid square hear. This is a good proxy — use it.

**Scenario 3: Only dark blue visible**
Limited geographic intelligence. The display shows global activity, which may not reflect the target's actual environment. Proceed with caution; consider the target's location and likely propagation paths.

**Scenario 4: Red bar on target frequency**
A station the target can hear is transmitting on or near their frequency. **Wait.** The target is likely unable to decode you through the interference. Watch for the red bar to clear.

### Reading the Probability Column

The "Prob %" column in the decode table estimates your chance of completing a QSO:

* **> 75%:** Excellent conditions. Call confidently.
* **50-75%:** Good odds. May take a few cycles.
* **30-50%:** Marginal. Consider waiting for better conditions or a clearer frequency.
* **< 30%:** Difficult. Heavy QRM or weak path. Be patient or move on.

### Pro Tips

1. **Don't chase the green line blindly.** It finds the widest gap, but a narrower gap closer to where the target is listening may be better.

2. **Watch for cyan "Golden Paths."** If you see a cyan bar, that's a proven decode path into the target's radio. Transmitting near (but not on) that frequency leverages known-good propagation.

3. **Respect the red.** Collision detection is physics-based. If a strong station is on the target's frequency, no amount of power will help you — the target's receiver is saturated.

4. **Use the refresh.** The perspective updates every 3 seconds. Band conditions change rapidly. What was blocked may clear; what was open may fill.

5. **Grid squares matter.** Stations in the same grid square share similar propagation. If you see heavy bright-blue activity, the target's area is busy even if they aren't personally uploading spots.

-----

## Installation & Usage

### 1. Requirements
* Python 3.10 or higher.
* WSJT-X or JTDX.

### 2. Setup
1. **Clone/Download** this repository.
2. Run the **Launcher**:
   ```bash
   python launcher.py
   ```
   *The launcher will automatically install necessary dependencies (`PyQt6`, `paho-mqtt`, `numpy`).*

### 3. Configure WSJT-X / JTDX
1. Open **Settings** -> **Reporting**.
2. Check **"Accept UDP Requests"**.
3. Set **UDP Server** to `127.0.0.1`.
4. Set **UDP Port** to `2237`.

-----

## Project History & Changelog

### v1.2.0 - The Target Perspective Update (Current)

* **Major Feature: Geographic Perspective Engine**
    * Band map now shows what the *target* hears, not global activity.
    * Tiered system: Direct (Cyan) → Same Grid (Bright Blue) → Same Field (Blue) → Global (Dark Blue).
    * New caches in `analyzer.py`: `receiver_cache` and `grid_cache` index spots by reporter location.
    * New method: `get_target_perspective(call, grid)` returns tiered intelligence.

* **JTDX/WSJT-X Integration**
    * Double-clicking a station in JTDX/WSJT-X immediately updates the target perspective.
    * No need to re-click in QSO Predictor — the band map responds to your logging software.

* **Continuous Refresh**
    * Target perspective auto-updates every 3 seconds.
    * No need to re-click the target row.

* **UI Improvements**
    * Updated band map legend with local signal SNR colors.
    * Collision detection now focuses on Tier 1/2 signals (the ones that matter).
    * Info bar shows current band and dial frequency.
    * CONNECTED status highlighted in cyan (table and dashboard).
    * Competition column color-coded: cyan (connected), red (pileup), orange (high), green (clear).
    * "Who hears me" count now uses 3-minute window for tactical relevance.

### v1.1.0 - The Tactical Update

* **New Band Map:** Completely rewritten rendering engine using Z-Order layering.
* **Logic Engine:**
    * Implemented **Density Analysis** to detect pileups without needing message text.
    * Implemented **Collision Detection** for direct frequency overlaps.
    * Added **Receiver Verification** for confirmed spots.
* **Visuals:**
    * Added "Safety Gap" between TX (Top) and RX (Bottom) displays.
    * Capped signal height at 45% of view area.

### v1.0.1 - The Real-Time Overhaul

* **Architecture Shift:** Replaced HTTP Polling with MQTT streaming.
* **Band Map Physics:**
    * Adjusted signal bar width to **50Hz** (FT8 Bandwidth).
    * Increased signal persistence to **45 seconds** to handle Even/Odd cycles.

### v0.9.x - Beta Era

* Initial UDP/Table implementation.
* Dashboard layout and crash fixes.

-----

## License

**GNU General Public License v3 (GPLv3)**
*Copyright (C) 2025 Peter Hirst (WU2C)*

This program comes with ABSOLUTELY NO WARRANTY. This is free software, and you are welcome to redistribute it under certain conditions.
