QSO Predictor - Developer Context & System Architecture

Version: 1.2.0 (The Target Perspective Update)
Date: December 2025
Developer: Peter Hirst (WU2C)

## 1. Project Philosophy

QSO Predictor is a Tactical Dashboard for FT8/FT4. Unlike standard mapping tools, it is opinionated and probabilistic.

* **Goal:** Tell the operator who they can work and where to transmit to avoid QRM.
* **Core Principle:** "Target Perspective." Show the operator what the *target station* experiences, not just global band activity.
* **The Insight:** Propagation is regional. A pileup visible from one continent may not exist at the target's location. By filtering data geographically, we show the QRM environment that actually matters.

## 2. Architecture Overview

### A. Data Pipeline (Event-Driven)

The application operates on a "Reactive Stream" architecture.

1. **UDP Listener (`udp_handler.py`):**
   * Listens on `127.0.0.1:2237` for WSJT-X packets.
   * **Role:** Local Truth. Tells us what *we* are decoding and where *we* are transmitting.
   * **Critical:** Parses variable-length UTF-8 strings manually to avoid crashes.

2. **MQTT Stream (`mqtt_client.py`):**
   * Connects to `mqtt.pskreporter.info` (Port 1883).
   * **Role:** Global Truth. Tells us what the rest of the world hears.
   * **Subscriptions:**
       * `pskr/filter/v2/{BAND}/FT8/#` (Band Activity)
       * `pskr/filter/v2/+/FT8/{MY_CALL}/#` (Reverse Beacon)

3. **The Brain (`analyzer.py`):**
   * **Multi-Index Cache System (New in v1.2):**
       * `band_cache{}` - Keyed by RF frequency. All spots in the passband.
       * `receiver_cache{}` - Keyed by receiver callsign. What each station reports hearing.
       * `grid_cache{}` - Keyed by 4-char grid. What stations in each grid square hear.
   * **Maintenance Loop:** Prunes old spots (>15 min) from all caches.
   * **Probability Engine:** Calculates % chance of contact based on SNR, Pileup Density, and Signal Path history.

### B. The Target Perspective System (New in v1.2)

**The Problem We Solved:**

Previous versions displayed global band activity — what *everyone* hears. But this created two issues:

1. **False Positives:** A pileup in Europe doesn't affect a target in Japan.
2. **False Negatives:** A local QRM source near the target wouldn't appear if no one else reported it.

**The Solution: Geographic Tiering**

When the user clicks on a target, we query `get_target_perspective(call, grid)` which returns spots organized by geographic proximity to the target:

```
Tier 1 (Cyan)      : receiver_cache[target_call]     → Direct intelligence
Tier 2 (Bright Blue): grid_cache[target_grid[:4]]    → Same grid square (~100km)
Tier 3 (Medium Blue): grid_cache[*.grid[:2] match]   → Same field (~1000km)  
Tier 4 (Dark Blue)  : Everything else                → Global background
```

**Why This Works:**

Stations in the same grid square experience similar propagation. If K1ABC in FN42 hears a pileup, K1XYZ in FN42 probably hears it too. By weighting nearby reporters more heavily, we approximate the target's actual RF environment without requiring the target to upload spots.

**Graceful Degradation:**

* If target uploads to PSK Reporter → Tier 1 data available (best case)
* If target doesn't upload, but neighbors do → Tier 2/3 data (good proxy)
* If no nearby reporters → Tier 4 only (global fallback)

### C. The Tactical Band Map (`band_map_widget.py`)

The Band Map is a **Split-Screen Tactical Display:**

**Top Half: Target Perspective (Remote)**
What the target station (and nearby stations) hear. Rendered with tiered colors:

| Tier | Color | RGB | Opacity | Source |
|------|-------|-----|---------|--------|
| 1 | Cyan | (0, 255, 255) | 100% | Target's direct reports |
| 2 | Bright Blue | (80, 140, 255) | 80% | Same 4-char grid |
| 3 | Medium Blue | (60, 100, 180) | 50% | Same 2-char field |
| 4 | Dark Blue | (40, 60, 100) | 30% | Global |
| — | Red | (255, 0, 0) | 100% | Collision (Tier 1/2 on target freq) |

**Bottom Half: Local Decodes (What You Hear)**
Your own radio's decodes, color-coded by SNR:

| SNR | Color | RGB |
|-----|-------|-----|
| > 0 dB | Green | (0, 255, 0) |
| -10 to 0 dB | Yellow | (255, 255, 0) |
| < -10 dB | Red | (255, 50, 50) |

**The Gap Finder:**

The green "Rec" line shows the recommended TX frequency. The algorithm:

1. Build a busy map (boolean array, 3000 elements for 3kHz).
2. Mark local signals as busy (±30Hz each).
3. Mark perspective signals as busy, weighted by tier:
   * Tier 1: Full weight (if target hears it, avoid it)
   * Tier 2: 80% weight
   * Tier 3: 50% weight
   * Tier 4: 30% weight
4. Find the widest contiguous gap.
5. Smooth the recommendation (90% old + 10% new) to prevent jitter.

### D. Continuous Refresh System

**The Problem:** User clicks target, sees perspective, but data decays after 60 seconds.

**The Solution:** `perspective_timer` in `main.py` fires every 3 seconds:

```python
self.perspective_timer = QTimer()
self.perspective_timer.timeout.connect(self.refresh_target_perspective)
self.perspective_timer.start(3000)
```

When fired, if `current_target_call` is set, it re-queries the analyzer and updates the band map. The display stays current as new spots arrive from MQTT.

### E. JTDX/WSJT-X Target Integration

**The Problem:** Double-clicking a station in JTDX/WSJT-X sends a `dx_call` via UDP, but the target perspective wasn't updating.

**The Solution:** `handle_status_update()` now detects when the DX call changes:

```python
def handle_status_update(self, status):
    dx_call = status.get('dx_call', '')
    if dx_call:
        target_changed = (dx_call != self.current_target_call)
        # ... update state ...
        if target_changed:
            self._update_perspective_display()
```

This means the band map responds immediately when you double-click a station in your logging software — no need to also click in QSO Predictor. The optimization only triggers the perspective update when the target actually changes, since JTDX sends status packets frequently (multiple times per second).

## 3. File Manifest

| File | Status | Role |
| :--- | :--- | :--- |
| `main.py` | **REVISED** | UI Controller, Target State Management, Perspective Refresh Timer. |
| `analyzer.py` | **REVISED** | Multi-Index Cache System, `get_target_perspective()` method. |
| `band_map_widget.py` | **REVISED** | Tiered Rendering, `update_perspective()` method, Updated Legend. |
| `mqtt_client.py` | Active | Paho-MQTT connection to PSK Reporter. |
| `udp_handler.py` | Active | WSJT-X UDP Listener & Parser. |
| `config_manager.py` | Active | INI file handler. |
| `solar_client.py` | Active | NOAA Solar Data fetcher. |
| `settings_dialog.py` | Active | Settings UI. |
| `launcher.py` | Active | Dependency Installer. |

## 4. Data Flow Diagram

```
┌─────────────┐      ┌─────────────┐
│  WSJT-X/    │      │ PSK Reporter│
│  JTDX (UDP) │      │  (MQTT)     │
└──────┬──────┘      └──────┬──────┘
       │                    │
       ▼                    ▼
┌─────────────┐      ┌─────────────┐
│ udp_handler │      │ mqtt_client │
│  ├─decodes  │      └──────┬──────┘
│  └─status ──┼──┐          │
└──────┬──────┘  │          │
       │         │   ┌──────┴───────────┐
       │         │   │                  │
       ▼         │   ▼                  │
┌────────────────┼────────────────────┐ │
│          analyzer.py                │ │
│  ┌───────────┬───────────────┐      │ │
│  │band_cache │receiver_cache │      │ │
│  │(by freq)  │(by callsign)  │      │ │
│  ├───────────┼───────────────┤      │ │
│  │grid_cache │my_reception   │      │ │
│  │(by grid)  │_cache         │      │ │
│  └───────────┴───────────────┘      │ │
│                                     │ │
│  get_target_perspective(call,       │ │
│                         grid)       │ │
│         │                           │ │
└─────────┼───────────────────────────┘ │
          │                             │
          ▼                             │
┌─────────────────────────────────────┐ │
│         main.py                     │ │
│  ┌─────────────────────────┐        │ │
│  │ perspective_timer (3s)  │────────┼─┼──► refresh_target_perspective()
│  └─────────────────────────┘        │ │
│                                     │ │
│  handle_status_update() ◄───────────┼─┘
│    └─► if dx_call changed:          │    (JTDX double-click triggers
│          _update_perspective_display│     immediate perspective update)
│                                     │
│  current_target_call                │
│  current_target_grid                │
└─────────┬───────────────────────────┘
          │
          ▼
┌─────────────────────────────────────┐
│     band_map_widget.py              │
│  ┌─────────────────────────┐        │
│  │ Top: Target Perspective │        │
│  │ (Cyan/Blue tiers)       │        │
│  ├─────────────────────────┤        │
│  │ Bottom: Local Decodes   │        │
│  │ (Green/Yellow/Red)      │        │
│  └─────────────────────────┘        │
└─────────────────────────────────────┘
```

## 5. Change History & Regressions Log

### v1.2.0 (The Target Perspective Update) - Current

* **Major Feature: Geographic Perspective Engine**
    * New caches: `receiver_cache{}` (by callsign), `grid_cache{}` (by 4-char grid).
    * New method: `get_target_perspective(call, grid)` returns tiered spot data.
    * Band map now renders target's RF environment, not global noise.

* **JTDX/WSJT-X Integration**
    * `handle_status_update()` now triggers perspective update when `dx_call` changes.
    * Double-clicking in JTDX/WSJT-X immediately updates the band map.
    * Optimized to only update on target change (not every status packet).

* **Continuous Refresh**
    * Added `perspective_timer` (3-second interval) in `main.py`.
    * Target state tracked in `current_target_call` and `current_target_grid`.
    * Display stays current without re-clicking.

* **Collision Detection Improvement**
    * Red collision overlay now only triggers on Tier 1/2 signals.
    * Rationale: A collision only matters if the target (or nearby station) would hear it.

* **UI Polish**
    * Legend updated with Row 3 showing local signal SNR colors.
    * Tier colors tuned for visual hierarchy (brightest = highest confidence).
    * Info bar shows current band and dial frequency.
    * Competition column color-coded (cyan/red/orange/green).
    * CONNECTED rows highlighted with teal background.
    * "Who hears me" uses 3-minute window (was 15 minutes).

### v1.1.0 (The Tactical Update)

* **Major Logic Shift:** Moved from "Callsign Matching" (which failed due to missing metadata) to "Density Analysis" (Physics-based pileup detection).
* **Visuals:** Implemented "Safety Gap" (split screen) and capped signal height to prevent visual overlap between Local (TX) and Remote (RX) waterfalls.
* **Colors:** Introduced **Cyan** for confirmed paths to distinguish from Orange pileups.

### v1.0.1 (Real-Time)

* Switched data source from HTTP to MQTT.
* Fixed "Even/Odd" cycle blindness by increasing cache retention to 45s.
* Corrected Signal Width to 50Hz (Physics accurate).

### v0.9.x (Beta)

* Initial UDP/Table implementation.

## 6. Known Limitations & Future Work

**Current Limitations:**

1. **PSK Reporter Coverage Dependency:** If no one in the target's region uploads to PSK Reporter, we fall back to global data. Remote/rare locations may have poor coverage.

2. **Latency:** PSK Reporter spots are uploaded in batches by client software (typically 5-30 second delay). We're not seeing true real-time, but "near real-time."

3. **Grid Accuracy:** We use the *receiver's* reported grid, which may be approximate (4-char vs 6-char) or occasionally incorrect.

**Potential Enhancements:**

1. **Propagation Path Weighting:** Instead of just geographic proximity, weight by likely propagation paths (e.g., same azimuth from your QTH).

2. **Historical Success Rate:** Track which stations you've successfully worked and from which frequencies. Learn patterns.

3. **Cluster Integration:** Subscribe to DX cluster spots for additional intelligence on pileup targets.

4. **FT4 Support:** Currently optimized for FT8 timing. FT4's faster cycles may need adjusted persistence windows.
