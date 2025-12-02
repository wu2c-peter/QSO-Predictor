Here is a comprehensive, updated `README.md`. It reflects the architectural shift to MQTT, the visual overhauls, and includes a detailed "Changelog / History" section documenting our work.

-----

# QSO Predictor

**Real-Time Tactical Assistant for FT8 & FT4** *Copyright (C) 2025 Peter Hirst (WU2C)*

QSO Predictor is a "Moneyball" tool for digital amateur radio. It sits between **WSJT-X/JTDX** and the internet, analyzing live data to tell you **who you can work** and **where to transmit** to maximize your success rate.

unlike standard mapping tools, this is a **Tactical Dashboard**. It calculates probabilities based on signal paths, pileup intensity, and remote QRM.

-----

## 🚀 Key Features

### 1\. Real-Time MQTT Engine

Moved beyond slow HTTP polling. The app now connects directly to the **PSK Reporter Live Stream** (MQTT).

  * **Zero Latency:** Spots appear milliseconds after they are reported.
  * **No Rate Limits:** Eliminates API bans and quotas.
  * **Auto-Band Detection:** Automatically subscribes to traffic on your current dial frequency.

### 2\. Intelligent Band Map

A visual representation of the 3kHz audio passband.

  * **50Hz Accurate Rendering:** Signal bars match the actual bandwidth of FT8 signals.
  * **Smart Persistence:** Remembers signals from the previous cycle (45s retention). This allows you to see "Even" stations even while you are transmitting on "Even" (when your radio is blind).
  * **Remote QRM Viz:** Draws **Blue Blocks** where the DX station is hearing noise or other callers, warning you not to transmit there.

### 3\. Probability Scoring

Don't waste time calling stations that can't hear you.

  * **SNR Analysis:** Base score derived from signal strength.
  * **Reverse Beacon:** Bonus points if the target (or their neighbor) has recently spotted *you*.
  * **Competition Logic:** Detects "Pileups" by counting how many other people are calling your target within a 60Hz window.

-----

## 📦 Installation & Usage

### 1\. Requirements

  * Python 3.10 or higher.
  * WSJT-X or JTDX.

### 2\. Setup

1.  **Clone/Download** this repository.
2.  Run the **Launcher**:
    ```bash
    python launcher.py
    ```
    *The launcher will automatically install necessary dependencies (`PyQt6`, `paho-mqtt`, `numpy`).*

### 3\. Configure WSJT-X / JTDX

1.  Open WSJT-X **Settings** -\> **Reporting**.
2.  Check **"Accept UDP Requests"**.
3.  Set **UDP Server** to `127.0.0.1`.
4.  Set **UDP Port** to `2237` (or match the setting in QSO Predictor).

### 4\. Configure App

On first launch, go to **File -\> Settings**:

  * Enter your **Callsign** and **Grid Square** (Required for Reverse Beacon analysis).

-----

## 📊 Reading the Band Map

The Band Map at the bottom of the window is your tactical view.

| Visual Element | Meaning | Action |
| :--- | :--- | :--- |
| **Green Bar** | Strong Signal (\> 0dB) | **Avoid.** Do not transmit on top of strong locals. |
| **Yellow Bar** | Average Signal (-10dB) | **Avoid.** |
| **Red Bar** | Weak Signal (\< -20dB) | Avoid if possible. |
| **Blue Bar** | **Remote QRM** | **CRITICAL AVOID.** The Target station hears noise/traffic here. |
| **Magenta Line** | Target Freq | The frequency the DX is transmitting on. |
| **Yellow Dotted** | Your TX Freq | Where you are currently set to transmit. |
| **Green Line** | **Recommended** | The algorithm's calculated "Cleanest Spot." |

-----

## 📜 Project History & Changelog

### v1.3 - The "Real-Time" Overhaul (Current)

  * **Architecture Shift:** Completely replaced `psk_client.py` (HTTP Polling) with `mqtt_client.py`.
      * *Benefit:* Data is now event-driven and instant. Removed "Fetching..." delays.
  * **Band Map Physics:**
      * Adjusted signal bar width to accurately represent **50Hz** (FT8 Bandwidth).
      * Increased signal persistence to **45 seconds**. This solves the "Blind Spot" issue where "Even" stations disappeared from the map while the user was transmitting on "Even."
      * Implemented "Dimming" fade-out logic so old signals remain visible but subtle.
  * **Logic Tuning:**
      * Tightened Competition/Pileup matching from 200Hz down to **60Hz** to reduce false positives.
      * Fixed "Clear" status bug by normalizing Audio vs RF frequencies.
  * **UI Polish:**
      * Fixed table styling to remove white focus artifacts.
      * Added `setStretchLastSection` to eliminate empty columns.
      * Added fallback logic to auto-detect bands if WSJT-X hasn't sent a UDP packet yet.

### v1.2 - Visualization & Stability

  * **Dashboard Upgrade:** Switched the "Rec/Cur" dashboard display to use an HTML Table layout for perfect vertical alignment of numbers.
  * **QRM Visualization:** Added the **Blue Bar** logic to the Band Map. If a station spots QRM, it is drawn over the local signals to show "Danger Zones."
  * **Crash Fixes:** Rewrote `udp_handler.py` to robustly handle variable-length UTF-8 strings in WSJT-X packets, preventing crashes on decoding generic status updates.

### v1.1 - The "High Performance" Update

  * **Table Engine:** Migrated from `QTableWidget` to `QAbstractTableModel`. This allows the app to handle thousands of rows without UI freezing.
  * **Target Pinning:** Added logic to keep the currently selected target pinned to the top of the list, regardless of sorting.
  * **Smart sorting:** Added multi-type sorting (numeric for SNR/DT, string for Callsigns).

### v1.0 - Initial Prototype

  * Basic UDP listening.
  * Simple HTTP polling of PSK Reporter.
  * Static probability logic.

-----

## 📄 License

**GNU General Public License v3 (GPLv3)** You may copy, distribute and modify the software as long as you track changes/dates in source files. Any modifications to or software including (via compiler) GPL-licensed code must also be made available under the GPL along with build & install instructions.

**Disclaimer:** This software is provided "as is" with no warranty. It is a hobbyist tool.