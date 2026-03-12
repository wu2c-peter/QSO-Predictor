# QSO Predictor — Development Notes

**Critical lessons, architectural decisions, and "don't break this" rules.**  
**Consolidated from development sessions, December 2025 – February 2026.**

---

## ⛔ Rules That Must Not Be Broken

### 1. Qt Dock Widget Layout (Windows)

The dock layout was debugged over multiple hours. It works. Don't change it.

**The correct layout:**
```
┌─────────────────────────────┬──────────────────┐
│   Decode Table              │                  │
│   (can resize vertically)   │  Insights Panel  │
├─────────────────────────────┤  (full height)   │
│   Target View               │                  │
│   (Dashboard + Band Map)    │                  │
└─────────────────────────────┴──────────────────┘
```

**Critical rules:**
- `setCorner()` must be called in `init_ui()` to assign both right corners to the right dock area
- `setCorner()` must be called **again AFTER** `restoreState()` — on Windows, `restoreState()` overrides corner ownership
- `_reset_layout()` must also re-apply `setCorner()` before re-docking widgets
- Right dock must be added **FIRST** so it claims the corners
- Target View container needs `setMinimumHeight(380)` to show all band map sections
- **Never suggest replacing docks with QSplitter** — we tried extensively, docks are correct

**Root cause:** Qt's `restoreState()` silently overrides `setCorner()` on Windows but not macOS, causing the layout to look correct on Mac and broken on Windows.

### 2. Main Thread Must Never Block on I/O

Any external I/O (file reads, network calls, log scans) must run in a background thread or use cache-only lookups on the main thread.

**Lesson learned:** `lookup_station()` was scanning 168MB log files synchronously on every target click, causing 45+ second UI freezes. Fixed by replacing with `has_cached_history()` (instant cache check) and running full scans in background threads only.

### 3. Linux Menu Bar

On Ubuntu/GNOME, Qt6 tries to export menus to the desktop's global menu bar. This silently swallows application-specific menus (Edit, View, Tools) while keeping "standard" ones (File, Help).

**Fix:** `self.menuBar().setNativeMenuBar(False)` on Linux, called before menu creation. This is guarded with `sys.platform.startswith('linux')` to preserve native menu bar behavior on macOS.

---

## Performance Lessons

### Band Map CPU Usage

**Problem:** 38% CPU at idle on macOS.

**Root causes and fixes:**
- Timer was 20Hz (50ms) → reduced to 4Hz (250ms)
- `repaint()` is synchronous → changed to `update()` (async, coalesced)
- Paint objects (pens, brushes, fonts) allocated every frame → cached as class attributes

**Result:** 6% idle CPU (84% reduction).

### UDP Status Flooding

JTDX sends UDP status messages many times per second. Without throttling, this causes console spam, rapid table refresh, and TX line flickering.

**Fix:** Throttle `handle_status_update()` to max 2Hz. Similarly, `refresh_paths()` is throttled to max once per 2 seconds, and sorting is disabled during batch updates to prevent jitter.

### Bootstrap Timeout with Large Logs

Bootstrap works fine with small log files but times out before completing the activity-tracking pass on large files (500K+ decodes). The timeout at 70% causes the third pass to find zero recorded QSOs, filtering out all stations.

**Current mitigation:** Works reliably with recent log files. Background scanner handles incremental processing for large histories.

---

## Platform-Specific Gotchas

### Windows UDP Error 10054

When forwarding UDP packets to a closed port on Windows, the OS receives an ICMP "port unreachable" and throws error 10054 on the next `recvfrom()`, killing the listener.

**Fix (two layers):**
1. `SIO_UDP_CONNRESET` ioctl disables ICMP error reporting on the socket
2. Fallback: catch error 10054 specifically and `continue` instead of `break`

This is a well-known Windows quirk. Linux/macOS silently ignore sends to closed ports.

### Qt Stylesheet vs Model BackgroundRole

Qt stylesheets **completely override** model `BackgroundRole` data. If you set background colors via `QTableView::item` in a stylesheet, the model's `BackgroundRole` return values are silently ignored.

**Fix:** Custom `HuntHighlightDelegate` that explicitly paints backgrounds before calling `super().paint()`. This bypasses the stylesheet layer.

### QToolTip Styling on Linux

Linux desktop themes often don't style Qt tooltips properly, resulting in invisible text (dark on dark). The app sets explicit `QToolTip` stylesheet at the `QApplication` level in `main_v2.py`.

### JTDX Does Not Report Special Operation Mode via UDP

Confirmed through testing (March 2026): JTDX sends the extended UDP status fields (DE call, DE grid parse correctly) but `special_mode` is always 0 regardless of Hound mode setting. Tested across three configurations including with/without Split rig control.

JTDX also does not enforce the 1000 Hz Hound TX boundary — "Use hound TX frequency control" checkbox is intermittently grayed out, and even when available, TX below 1000 Hz is not blocked. This may be related to using Ham Radio Deluxe as a CAT middleman; direct CAT to the radio may work better.

**Impact:** Fox/Hound auto-detection via UDP (Layer 1) only works with WSJT-X. For JTDX users, QSOP provides a manual F/H checkbox and Layer 2 inference (auto-detecting Fox from decode patterns) as alternatives.

---

## Logging Architecture

### Smart Logging Pattern

Initial logging implementation generated 47,000+ lines in 6 minutes. Pattern: "Log first occurrence, then summarize periodically":
```
INFO | MQTT: First spot received - N8CDY -> W1BW 11dB
INFO | MQTT: Spots are flowing (individual spots not logged)
DEBUG | MQTT: Spot rate: 480.0/min (total: 28800)    ← every 60s
```

### Log Levels

| Level | Usage |
|-------|-------|
| ERROR | Exceptions, failed operations |
| WARNING | Recovered issues (disconnections, parse errors) |
| INFO | Key events (startup, connections, target changes) |
| DEBUG | Verbose details (packet contents, periodic stats) |

### Log Locations

- Windows: `%APPDATA%\QSO Predictor\logs\qso_predictor.log`
- macOS: `~/Library/Application Support/QSO Predictor/logs/qso_predictor.log`
- Linux: `~/.config/QSO Predictor/logs/qso_predictor.log`

Rotating file handler: 5MB max, 3 backups (~20MB total).

---

## Data Architecture

### Row Background Color Priority

When multiple conditions match, highest priority wins:

| Priority | Condition | Color | Hex |
|----------|-----------|-------|-----|
| 1 | CONNECTED | Teal | #004040 |
| 2 | Path Open | Dark Green | #002800 |
| 3 | Hunted station | Gold/Amber | #7A5500 |
| 4 | Selected row | Blue | #1a3a5c |
| 5 | Alternating rows | Dark Gray | #141414 / #1c1c1c |

### Split Update Architecture

Full target perspective calculations are expensive. The table uses two separate update paths:

| Update | Frequency | Scope | Cost |
|--------|-----------|-------|------|
| Path column | 2s | All rows | Cheap — cache lookups only |
| Full perspective | 3s | Selected target only | Expensive — tiered analysis |

### Behavioral Prediction Hierarchy

When predicting a station's behavior, sources are checked in order:

1. **Session cache** — live observations from current session
2. **Historical record** — direct picking observations from logs (≥3 observations)
3. **Persona match** — activity traits match a known persona type
4. **Default** — "Observing..." with neutral priors

Prefix aggregation (by country) was explored and abandoned as too coarse.

---

## Log File Format Reference

| Source | Trailing Markers |
|--------|-----------------|
| WSJT-X standard | None |
| JTDX standard | None |
| JTDX dated files | `^` (AP decode), `*` (low confidence), `.`, `d`, `&` |

The log parser regex must strip these markers: `r'(.+?)\s*[*d^.&]?\s*$'`

---

## Key Architectural Decisions

### MQTT over HTTP for PSK Reporter

PSK Reporter's HTTP API has 5-minute polling delay. In 15-second FT8 cycles, 5-minute-old data is useless. MQTT delivers spots in seconds with no rate limits.

### Geographic Tiering over ML

Simple geographic proximity (same grid ≈ same propagation) is transparent, predictable, and degrades gracefully. ML would require training data we don't have and produce a black box users can't understand.

### Heuristics over ML for Behavior Prediction

Bayesian updating with observable traits is interpretable and works offline. The counts in `behavior_history.json` are sufficient statistics — just increment on new observations, no need to re-scan history.

### Path Intelligence: On-Demand Analysis

Phase 2 path analysis (reverse PSK Reporter lookups, beaming detection) runs only when the user clicks "Analyze", not automatically. This avoids unnecessary API load and keeps the UI responsive.

---

## Recurring Debugging Pattern

Multiple sessions showed the same pattern: AI overcomplicates the analysis while Peter asks "is it just the obvious thing?" and is right.

**Examples:**
- QDateTime parsing: Claude tried multiple format variations; Peter noticed the 1-byte packet size difference was just callsign length
- Bootstrap failure: Claude investigated corruption theories; Peter asked "could it be timeout or file size?"
- Layout issues: Peter noticed Mac vs Windows had opposite corner ownership, identifying the `restoreState()` override

**Lesson:** When systematic analysis gets complicated, step back and check the simple explanation first.

---

*Consolidated from 8 session notes files spanning v2.0.6 through v2.2.0.*  
*Last updated: March 2026*

**73 de WU2C**
