# QSO Predictor

**Real-Time Tactical Assistant for FT8 & FT4** *Copyright (C) 2025 Peter Hirst (WU2C)*

**Current Version:** v1.1.0 (The Tactical Update)

QSO Predictor is a "Moneyball" tool for digital amateur radio. It sits between **WSJT-X/JTDX** and the internet, analyzing live data to tell you **who you can work** and **where to transmit** to maximize your success rate.

Unlike standard mapping tools, this is a **Tactical Dashboard**. It calculates probabilities based on signal paths, pileup intensity, and remote QRM.

-----

## 噫 Key Features

### 1\. The Tactical Band Map (New in v1.1)

A visual representation of the 3kHz audio passband that acts as a "Thermal Camera" for band activity. It uses a **Hybrid Physics/Metadata Engine** to categorize signals into four tactical layers:

| Color | Status | Meaning | Tactical Action |
| :--- | :--- | :--- | :--- |
| **Cyan** | **CONFIRMED** | **Path Verified.** The Target station explicitly reported hearing this signal. | **ATTACK HERE.** This is a proven path into the Target's radio. |
| **Red** | **COLLISION** | **Direct QRM.** A station is transmitting *exactly* on the Target's frequency (within 35Hz). | **STOP.** The Target is deafened. Wait for the red bar to clear. |
| **Orange** | **CLUSTER** | **Pileup.** High-density activity (4+ stations in an 80Hz window). | **CAUTION.** Unless you have high power, avoid the center of the Orange block. |
| **Blue** | **TRAFFIC** | **Background Noise.** Random QSOs unrelated to your target. | **IGNORE.** Thread the needle between these bars. |

### 2\. Real-Time MQTT Engine

Moved beyond slow HTTP polling. The app connects directly to the **PSK Reporter Live Stream** (MQTT).
  * **Zero Latency:** Spots appear milliseconds after they are reported.
  * **No Rate Limits:** Eliminates API bans and quotas.

### 3\. Intelligent Recommendation

  * **Auto-Spotter:** The Green Line on the map automatically calculates the widest available gap in the spectrum, accounting for both local noise (what you hear) and remote QRM (what they hear).

-----

## 逃 Installation & Usage

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
1.  Open **Settings** -\> **Reporting**.
2.  Check **"Accept UDP Requests"**.
3.  Set **UDP Server** to `127.0.0.1`.
4.  Set **UDP Port** to `2237`.

-----

## ｧ Design Philosophy: Evolution of the Logic

The logic driving QSO Predictor v1.1 evolved through several iterations to solve a specific problem: **"The Blind Spot."**

### The Problem
Public data streams (PSK Reporter) tell us *where* a signal is, but they don't always contain the message text. We often know `K1ABC` is transmitting on 14.074.150, but we don't know *who* he is calling. Early versions of this tool assumed all traffic was irrelevant, leading to collisions.

### The Evolution
1.  **v1.0 (Naive QRM):** We simply drew a blue block for every signal reported. This resulted in a "Sea of Blue" that caused Alert Fatigue.
2.  **v1.0.x (The Wolfpack Fail):** We tried to color-code competitors based on callsigns. This failed because we couldn't see the "To:" field in the packet data.
3.  **v1.1 (Hybrid Physics Engine):** The current version uses a layered approach:
    * **Layer 1 (Metadata):** If a spot says `Receiver: TargetCall`, we mark it **Cyan (Confirmed)**. This is hard intelligence.
    * **Layer 2 (Physics):** If we don't know who they are calling, we measure **Signal Density**. If 4+ signals crowd into 80Hz, we mark it **Orange (Cluster)**. The logic assumes that an unnatural density of signals equals a pileup, regardless of who they are calling.
    * **Layer 3 (Geometry):** If a signal overlaps the Target frequency by <35Hz, we mark it **Red (Collision)**. Physics dictates the target cannot hear through this.

This approach turns incomplete data into actionable intelligence.

-----

## 糖 Project History & Changelog

### v1.1.0 - The Tactical Update (Major)

  * **New Band Map:** Completely rewritten rendering engine using Z-Order layering.
  * **Logic Engine:**
      * Implemented **Density Analysis** to detect pileups (Orange) without needing message text.
      * Implemented **Collision Detection** (Red) for direct frequency overlaps.
      * Restored **Receiver Verification** (Cyan) for confirmed spots.
  * **Visuals:**
      * Added "Safety Gap" between TX (Top) and RX (Bottom) bars to prevent visual clutter.
      * Capped signal height at 45% of view area.
      * Tuned colors for high contrast (Cyan/Orange/Red).

### v1.0.1 - The Real-Time Overhaul

  * **Architecture Shift:** Replaced HTTP Polling with `mqtt_client.py`.
      * *Benefit:* Data is now event-driven and instant.
  * **Band Map Physics:**
      * Adjusted signal bar width to **50Hz** (FT8 Bandwidth).
      * Increased signal persistence to **45 seconds** to fix "Even/Odd" cycle blindness.

### v0.9.x - Beta Era

  * **Dashboard Upgrade:** HTML Table layout for perfect alignment.
  * **Crash Fixes:** Robust UTF-8 handling for WSJT-X UDP packets.
  * **Table Engine:** Migrated to `QAbstractTableModel` for high performance.

-----

## 塘 License

**GNU General Public License v3 (GPLv3)**
*Copyright (C) 2025 Peter Hirst (WU2C)*

This program comes with ABSOLUTELY NO WARRANTY. This is free software, and you are welcome to redistribute it under certain conditions.