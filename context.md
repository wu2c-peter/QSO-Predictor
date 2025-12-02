QSO Predictor - Developer Context & System Architecture

Version: 1.3 (MQTT Real-Time Engine)
Date: December 2025
Developer: Peter Hirst (WU2C)

1. Project Philosophy

QSO Predictor is a Tactical Dashboard for FT8/FT4. Unlike standard mapping tools, it is opinionated and probabilistic.

Goal: Tell the operator who they can work and where to transmit to avoid QRM.

Core Principle: "Real-Time Physics." We do not rely on 5-minute old API polls. We stream live data and visualize the actual bandwidth of signals.

2. Architecture Overview

Data Pipeline (Event-Driven)

The application moved from a "Polling Loop" to a "Reactive Stream" in v1.3.

UDP Listener (udp_handler.py):

Listens on 127.0.0.1:2237 for WSJT-X Status (Heartbeat) and Decode (Message) packets.

Critical: Parses variable-length UTF-8 strings manually to avoid crashes on malformed packets.

Output: Emits signals to main.py to update the "Current TX" line and "Target" info.

MQTT Stream (mqtt_client.py):

Connects to mqtt.pskreporter.info (Port 1883).

Subscribes to:

pskr/filter/v2/{BAND}/FT8/# (Who is transmitting on this band).

pskr/filter/v2/+/FT8/{MY_CALL}/# (Reverse Beacon: Who hears me).

Output: Feeds raw spots instantly to analyzer.py.

The Brain (analyzer.py):

In-Memory Cache: Stores spots in self.band_cache (keyed by Frequency).

Maintenance Loop: runs every 2s to prune spots older than 15 minutes.

Auto-Detect: If WSJT-X is silent (no UDP), it auto-detects the current band from the first incoming MQTT spot.

3. Core Logic & Tuning Constants

DO NOT CHANGE THESE VALUES WITHOUT EXPLICIT REASONING.

A. Competition / Pileup Logic

How we determine if a frequency is "Busy."

Fuzzy Match Window: +/- 60 Hz.

Reasoning: FT8 signals are ~50Hz wide. 60Hz accounts for slight VFO drift while avoiding false positives from signals 200Hz away.

Time Gate: 45 Seconds.

Reasoning: A spot is only considered "Competition" if seen in the last 3 cycles. Older spots are ignored for pileup calculation.

B. Band Map Physics (band_map_widget.py)

The visual representation of the 3000Hz passband.

Persistence: 45 Seconds.

Critical Feature: Signals remain on the map for 3 cycles. This ensures that while you are transmitting (and your RX is blind), you can still see the "Even" stations that were transmitting 15s ago.

Signal Width:

Active Signals (Green/Yellow): Drawn dynamically to represent 50 Hz (approx 16px on standard screens).

Remote QRM (Blue): Drawn at 35 Hz width (slightly narrower) to visually distinguish them from local signals.

Fade Logic:

Signals fade over 45s but Alpha is clamped at 50. They never turn fully black/invisible until they expire.

C. Probability Algorithm

Score (0-99%) = Base SNR + Bonuses - Penalties.

Base: >0dB (80%), >-10dB (60%), >-15dB (40%), else (20%).

Bonuses:

Direct Hit (Reverse Beacon): +100% (Instant 99%).

Path Open (Grid Match): +15-25%.

Penalties:

Pileup: -10 to -50% based on caller count (Low/Med/High/Pileup).

Strong QRM: Additional -20% if a caller is >0dB.

4. Visual Design Specifications

A. The Band Map

Background: #101010 (Near Black).

Target Line: Magenta (#FF00FF), Solid.

Recommended Line: Green (#00FF00), Solid.

Current TX Line: Yellow (#FFFF00), Dotted (Qt.PenStyle.DotLine).

Legend: 2-Row Layout. Row 1 (Lines + Blue QRM), Row 2 (Signal Strength Colors).

B. The Main Table (main.py)

Engine: QAbstractTableModel (Not QTableWidget).

Styling:

outline: 0; (Removes white focus artifacts).

setStretchLastSection(True) (Prevents empty column on right).

Alignment:

Left: Callsign, Message, Competition.

Center: UTC, SNR, DT, Freq, Grid, Prob %.

Headers: All Centered.

Pinning: The "Target" callsign is always pinned to Row 0, regardless of sorting.

C. The Dashboard

Layout: HTML Table (<table>) used for the "Rec/Cur" box to ensure numbers align perfectly vertically.

Colors: "Cur" frequency turns Red if it mismatches "Rec," Green if matched.

5. File Manifest (The Clean State)

File

Status

Role

main.py

Active

UI Controller, Table Model, Dashboard.

analyzer.py

Active

Logic Engine, Caching, Probability Math.

mqtt_client.py

Active

Paho-MQTT connection to PSK Reporter.

udp_handler.py

Active

WSJT-X UDP Listener & Parser.

band_map_widget.py

Active

Custom Painting Widget (Spectrum).

config_manager.py

Active

INI file handler.

solar_client.py

Active

NOAA Solar Data fetcher.

settings_dialog.py

Active

Settings UI.

launcher.py

Active

Dependency Installer.

psk_client.py

DELETED

Obsolete HTTP poller. Do not restore.

wsjtx_packet.py

DELETED

Obsolete parser. Logic moved to udp_handler.

6. Change History & Regressions Log

v1.3 (Current) - The MQTT Overhaul

Major Change: Switched data source from HTTP to MQTT.

Visual Fix: Corrected Signal Width to 50Hz (Physics accurate).

Visual Fix: Corrected QRM Width to 35Hz.

Regression Fix: "No Spots / Clear Map" -> Fixed by auto-detecting band if UDP is silent.

Regression Fix: "Pileup Everywhere" -> Fixed by adding 45s Time Gate to competition logic.

Regression Fix: "Dashboard Lag" -> Fixed by forcing text update immediately on UDP status packet.

v1.2 - UI Polish

Fix: Removed white focus boxes in TableView.

Fix: Implemented HTML formatting for Dashboard "Rec/Cur" box.

Feature: Added Blue QRM bars to Band Map foreground.

v1.1 - Performance

Change: Moved to QAbstractTableModel for high-performance