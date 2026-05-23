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

**Impact:** Fox/Hound auto-detection via UDP (Layer 1) only works with WSJT-X. For JTDX users, QSOP provides a manual F/H combo box as the reliable detection path. (Layer 2 decode-pattern inference was removed in v2.3.2 — it was either a false positive on standard frequencies or redundant on non-standard frequencies.)

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

## Module Structure & Refactor Conventions

`main_v2.py` started as a single 3,723-line `MainWindow` god class. After a
multi-stage refactor (May 2026) it's down to ~1,728 lines — a UI shell that
wires widgets to controllers. Several patterns were established along the way
and should be preserved by future changes.

### Top-level module map

| Module / package | Owns |
|---|---|
| `main_v2.py` | `MainWindow` + `init_ui` + signal routing |
| `widgets/` | Reusable Qt widgets: `TargetDashboard`, `TacticalToast`, `DecodeTableModel`, `HuntHighlightDelegate`, `ClickableLabel`, `ClickableCopyLabel` |
| `controllers/` | Focused subsystems: `UpdateChecker`, `HealthMonitor`, `HuntCoordinator`, `IonisIntegration`, `FoxHoundController`, `TargetCoordinator` |
| `analyzer/` | `QSOAnalyzer` (in `core.py`) + pure helpers (`geometry.py`) |
| `local_intel/` | Offline ML stack — models, predictor, session tracker, log parser |
| `ionis/` | IONIS propagation engine — numpy inference + features |
| `utils/` | Pure-stdlib helpers with no Qt / main-app deps (e.g. `version.py`) |
| `training/` | Out-of-process model training |

### Controller pattern (state-on-MainWindow)

Controllers are `QObject` subclasses instantiated with a back-reference to
`MainWindow` (`self.target = TargetCoordinator(self)`). They own the *methods*
for their subsystem but **not** the state attributes — those stay on
`MainWindow` (e.g., `current_target_call`, `_fh_active`, `_ionis_engine`).

The controller mutates the MainWindow state in place. This is on purpose:
many unrelated code paths still read these flags directly (outcome snapshot,
activity handling, target clearing, IONIS triggers). Pulling state into
controllers would have meant touching dozens of call sites in one PR. The
"methods home" approach kept each extraction small and reversible.

If you add a new controller, follow the same shape:
- Subclass `QObject`, take `main_window` in `__init__`, call `super().__init__(main_window)` so Qt parents it.
- Read/write state via `self.main_window.X` for things the rest of the app touches.
- Emit signals back to MainWindow only when you need a slot in code you can't reach directly. Most controllers don't need any.
- Register in `controllers/__init__.py`.

### PathStatus is the canonical domain type

`local_intel/models.py::PathStatus` is the single source of truth for the
path classification (HEARD_BY_TARGET, REPORTED_IN_REGION, NOT_REPORTED_IN_REGION,
NOT_TRANSMITTING, NO_REPORTERS, UNKNOWN). The enum carries its own display
attributes: `display_label`, `short_label`, `color`, `row_background`, `tooltip`.

**The `display_label` strings are byte-identical to historic UI strings** because
the outcome recorder persists them to disk in event logs (`~/.qso-predictor/outcome_history.jsonl`).
Changing a label would break older logs. If you ever need to add a new state,
keep existing labels frozen and pick a new one for the new state.

UI dispatch should always go through `PathStatus.from_display(s)` for parsing
and through the enum properties for rendering — never substring-match the
display labels (`"Not Reported in Region"` contains `"Reported in Region"`).

### Health warnings are sticky in the status bar

`MainWindow.update_status_msg(msg)` refuses to clobber a visible warning
(text starting with `⚠`) with a non-warning message. Normal messages are
saved to `_normal_status` for later restoration. When `HealthMonitor` decides
the warning has lifted, it calls `MainWindow.clear_health_warning()` — the
only path that bypasses the sticky check.

This is what makes a UDP-silent warning actually readable. The analyzer's
maintenance loop emits a `"Tracking N stations"` message every ~2 seconds
through `update_status_msg`; without the sticky check those messages would
overwrite the warning before the user could read it.

### Don't do `from main_v2 import X` from controllers

`main_v2.py` is loaded as the `__main__` module at startup. When *any* other
module does `from main_v2 import X`, Python loads it again under the new name
`main_v2` and re-runs every top-level statement, including `setup_logging()`.
The visible symptom is a second "QSO Predictor logging initialized" banner
in the log and a duplicated console handler.

Anything controllers need from `main_v2.py` (version helpers, etc.) must live
in a non-`main_v2` module. `utils/version.py` exists for exactly this reason.
If you find yourself wanting to import a helper from `main_v2`, move the
helper to `utils/` first.

### Pure helpers belong in `*/geometry.py` style modules

`analyzer/geometry.py` was carved out of `QSOAnalyzer` for the five helpers
that take their inputs explicitly and don't touch the locked spot caches
(`sector_distribution`, `max_concentration`, `bearing_to_region`, `freq_to_band`,
`is_callsign`). If you find yourself writing a helper that doesn't need `self`,
write it as a free function and put it in the package's helpers module —
makes it reusable and testable without the QObject machinery.

### Known follow-up: `freq_to_band` duplication

The function `freq_to_band(freq_hz) → "20m"` exists as a private method on
four separate classes (`analyzer/core.py`, `mqtt_client.py`, `hunt_manager.py`,
`local_intel/log_parser.py`) plus a slightly-different `ionis/features.py`
version. The canonical version is now `analyzer.geometry.freq_to_band` and
the other copies should eventually import from there. Not done as part of
the refactor because it touches multiple packages — saved for a focused
follow-up PR.

---

## Recurring Debugging Pattern

Multiple sessions showed the same pattern: AI overcomplicates the analysis while Peter asks "is it just the obvious thing?" and is right.

**Examples:**
- QDateTime parsing: Claude tried multiple format variations; Peter noticed the 1-byte packet size difference was just callsign length
- Bootstrap failure: Claude investigated corruption theories; Peter asked "could it be timeout or file size?"
- Layout issues: Peter noticed Mac vs Windows had opposite corner ownership, identifying the `restoreState()` override

**Lesson:** When systematic analysis gets complicated, step back and check the simple explanation first.

---

## v2.4.0: IONIS Propagation Prediction

### Numpy over PyTorch for Model Inference

The IONIS model (IonisGate V22-gamma, 205K parameters) was trained in PyTorch, but PyTorch adds 150-800 MB to the install. The model uses only standard operations: Linear layers, Mish activation, Softplus, Sigmoid, and absolute value for monotonicity constraints. The forward pass is ~40 lines of numpy matrix multiplications. Inference: 0.13 ms per prediction. Zero new heavy dependencies.

The `safetensors` library (~500 KB) loads the weights directly into numpy arrays — no PyTorch needed. This is the recommended approach for deploying small models in applications that can't afford a large ML framework dependency.

### Grid Backfill Bug

`current_target_grid` was only set in `_set_new_target()`. When a target was selected from a UDP status message (before decodes arrived), the grid was empty and never got filled in. The 3-second perspective refresh found the grid in the decode table but never copied it back to the main window's state variable.

This is a pre-existing bug affecting PSK Reporter perspective accuracy — not just IONIS. Fix: backfill the grid in `refresh_target_perspective()` when the decode table has it but the main state doesn't.

**Lesson:** State that's set in one place but read in many is fragile. When adding new consumers of shared state (like IONIS reading `current_target_grid`), verify the state is actually populated by tracing all the write paths.

### Lazy Re-trigger Pattern

IONIS predictions need data that arrives asynchronously (grid from decodes, SFI/Kp from NOAA). Rather than complex event wiring, the `_ionis_shown` flag tracks whether the prediction has been successfully displayed. The 3-second perspective refresh re-attempts if not shown. Once shown, it stops re-attempting (band change and solar refresh handle subsequent updates). Simple, robust, no wasted computation.

---

*Last updated: May 2026*

**73 de WU2C**
