QSO Predictor - Developer Context & System Architecture

Version: 1.1.0 (The Tactical Update)
Date: December 2025
Developer: Peter Hirst (WU2C)

1. Project Philosophy

QSO Predictor is a Tactical Dashboard for FT8/FT4. Unlike standard mapping tools, it is opinionated and probabilistic.

* **Goal:** Tell the operator who they can work and where to transmit to avoid QRM.
* **Core Principle:** "Real-Time Physics." We do not rely on 5-minute old API polls. We stream live data and visualize the actual bandwidth of signals.
* **The "Hybrid" Approach:** We combine **Metadata** (Hard facts from packets) with **Physics** (Inferred facts from signal density) to create actionable intelligence.

2. Architecture Overview

### A. Data Pipeline (Event-Driven)
The application operates on a "Reactive Stream" architecture.

1.  **UDP Listener (`udp_handler.py`):**
    * Listens on `127.0.0.1:2237` for WSJT-X packets.
    * **Role:** Local Truth. Tells us what *we* are decoding and where *we* are transmitting.
    * **Critical:** Parses variable-length UTF-8 strings manually to avoid crashes.

2.  **MQTT Stream (`mqtt_client.py`):**
    * Connects to `mqtt.pskreporter.info` (Port 1883).
    * **Role:** Global Truth. Tells us what the rest of the world hears.
    * **Subscriptions:**
        * `pskr/filter/v2/{BAND}/FT8/#` (Band Activity)
        * `pskr/filter/v2/+/FT8/{MY_CALL}/#` (Reverse Beacon)

3.  **The Brain (`analyzer.py`):**
    * **In-Memory Cache:** Stores spots in `self.band_cache` (keyed by Frequency).
    * **Maintenance Loop:** Prunes old spots (>45s age) to prevent "Ghost Signals" from previous transmit cycles.
    * **Probability Engine:** Calculates % chance of contact based on SNR, Pileup Density, and Signal Path history.

### B. The Tactical Band Map (`band_map_widget.py`)
*New in v1.1.0*

The Band Map is no longer just a passive display. It is a **Layered Intelligence Engine** that renders signals based on a hierarchy of importance (Z-Order).

**The Logic Hierarchy (Top to Bottom):**

1.  **Layer 1: CONFIRMED (Cyan)**
    * **Logic:** `Receiver Call == Target Call`
    * **Meaning:** Hard Intelligence. The target station explicitly reported hearing this signal.
    * **Tactical Value:** "Golden Path." Transmit here.

2.  **Layer 2: COLLISION (Red)**
    * **Logic:** `abs(Signal Freq - Target Freq) < 35Hz`
    * **Meaning:** Direct Physics. Two signals are occupying the same physical space.
    * **Tactical Value:** "Jamming." The target is deafened. Do not call.

3.  **Layer 3: CLUSTER (Orange)**
    * **Logic:** `Density > 4 signals within 80Hz window`
    * **Meaning:** Inferred Physics. A high-density "Wolfpack" or Pileup.
    * **Tactical Value:** "Competition." Avoid unless high power.

4.  **Layer 4: TRAFFIC (Blue)**
    * **Logic:** All other signals.
    * **Meaning:** Background Noise floor.
    * **Tactical Value:** "Obstacles." Thread the needle between them.

3. File Manifest (The Clean State)

| File | Status | Role |
| :--- | :--- | :--- |
| `main.py` | Active | UI Controller, Table Model, Dashboard. |
| `analyzer.py` | Active | Logic Engine, Caching, Probability Math. |
| `band_map_widget.py` | **REVISED** | **Tactical Rendering Engine (Hybrid Logic).** |
| `mqtt_client.py` | Active | Paho-MQTT connection to PSK Reporter. |
| `udp_handler.py` | Active | WSJT-X UDP Listener & Parser. |
| `config_manager.py` | Active | INI file handler. |
| `solar_client.py` | Active | NOAA Solar Data fetcher. |
| `settings_dialog.py` | Active | Settings UI. |
| `launcher.py` | Active | Dependency Installer. |
| `psk_client.py` | **DELETED** | Obsolete HTTP poller. |

4. Change History & Regressions Log

### v1.1.0 (The Tactical Update) - Current
* **Major Logic Shift:** Moved from "Callsign Matching" (which failed due to missing metadata) to "Density Analysis" (Physics-based pileup detection).
* **Visuals:** Implemented "Safety Gap" (split screen) and capped signal height to prevent visual overlap between Local (TX) and Remote (RX) waterfalls.
* **Colors:** Introduced **Cyan** for confirmed paths to distinguish from Orange pileups.

### v1.0.1 (Real-Time)
* Switched data source from HTTP to MQTT.
* Fixed "Even/Odd" cycle blindness by increasing cache retention to 45s.
* Corrected Signal Width to 50Hz (Physics accurate).

### v0.9.x (Beta)
* Initial UDP/Table implementation.