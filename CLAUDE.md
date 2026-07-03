# Project context for Claude

QSO Predictor is a PyQt6 desktop app for amateur-radio FT8/FT4 operators. It
listens to WSJT-X / JTDX over UDP, ingests PSK Reporter spots over MQTT, and
helps the operator pick the best frequency to call a target station based on
propagation, pileup competition, and the target's observed behavior.

## Running the app

```
./venv/bin/python3 main_v2.py        # macOS / Linux from project root
venv\Scripts\python.exe main_v2.py   # Windows
```

## Tests

```
./venv/bin/python3 -m pytest        # from project root
```

The suite (`tests/`) covers protocol parsing (WSJT-X/JTDX UDP), persisted-
format contracts (PathStatus display labels, outcome-recorder JSONL schema),
pure helpers (geometry, bearing, version), cross-module consistency
(`freq_to_band` copies), and architectural conventions (no `main_v2` imports,
`utils/` stays stdlib-only). Config lives in `pyproject.toml`. CI runs it on
every push (`.github/workflows/tests.yml`: Ubuntu 3.10–3.12 + Windows/macOS).
Tests import QtCore-based modules but never QtWidgets — no display needed.

**When fixing a bug, add a test that reproduces it first** — most of the
suite's parser cases encode historical user-reported regressions.

UI behavior isn't covered by tests: after UI-touching changes, smoke-test by
launching the app and watching the log at
`~/Library/Application Support/QSO Predictor/logs/qso_predictor.log`
(macOS) or `%APPDATA%\QSO Predictor\logs\qso_predictor.log` (Windows).

## Module layout

| Path | What lives here |
|---|---|
| `main_v2.py` | `MainWindow` (UI shell + signal routing); ~1,700 lines. |
| `widgets/` | Reusable Qt widgets — dashboard, decode table, toast, clickable labels. |
| `controllers/` | Focused subsystems split out of MainWindow. |
| `analyzer/` | `QSOAnalyzer` in `core.py`; pure helpers in `geometry.py`. |
| `local_intel/` | Offline ML stack — models, predictor, session tracker, log parser. The `models.py` module is pure-stdlib and defines `PathStatus`. |
| `ionis/` | IONIS propagation engine (numpy inference + features). |
| `utils/` | Pure-stdlib helpers with no Qt / main-app deps (`version.py`). |
| `training/` | Out-of-process model training. |
| `dev-docs/DEVELOPMENT_NOTES.md` | "Don't break this" rules, performance lessons, platform gotchas, architectural conventions. **Read this before significant changes.** |

## Conventions to respect

### Controllers own methods, MainWindow owns state

Controllers are `QObject` subclasses (`controllers/*.py`) that take a
`main_window` back-reference and read/write state via `self.main_window.X`.
State attributes (`current_target_call`, `_fh_active`, `_ionis_engine`, etc.)
live on `MainWindow` because many other code paths read them directly.
Adding a new controller? Follow the existing pattern in `controllers/`.

### `PathStatus` is the canonical path classification

`local_intel/models.py::PathStatus` enum carries display attributes
(`display_label`, `short_label`, `color`, `row_background`, `tooltip`) and
parsing (`from_display(s)`). The `display_label` strings are **byte-identical**
to historic UI text because `outcome_recorder.py` persists them to JSONL —
don't rename them. Use `PathStatus.from_display(...)` for parsing, not
substring matching.

### Don't `from main_v2 import X` from a controller or worker thread

`main_v2.py` runs as `__main__`. A `from main_v2 import …` from any other
module causes Python to load it *again* under the new name `main_v2`,
re-running `setup_logging()` and duplicating log handlers. Helpers that
controllers need (e.g. version detection) belong in `utils/`. The
`UpdateChecker` worker thread imports `compare_versions` from
`utils.version` for exactly this reason.

### Health warnings are sticky

`MainWindow.update_status_msg(msg)` refuses to overwrite a visible `⚠`
warning with a non-warning message. To clear a warning, use
`clear_health_warning()`. This stops the analyzer's ~2 s "Tracking N
stations" status updates from blowing away a UDP-silent warning before
the user can read it.

### Main thread must never block on I/O

File scans, network calls, log parsing — all in background threads. The
band map is repaint-throttled. UDP status updates are throttled to 2 Hz.
See `DEVELOPMENT_NOTES.md` § "Performance Lessons" for context.

### Qt dock layout is fragile on Windows

The MainWindow dock layout was hand-tuned for cross-platform behavior.
`setCorner()` must be re-applied after `restoreState()`. If you're tempted
to replace docks with `QSplitter`, don't — that path was explored and
abandoned. See `DEVELOPMENT_NOTES.md` § "Qt Dock Widget Layout".

## Where to look first for common tasks

| Task | Start here |
|---|---|
| Adding a UI widget | `widgets/` — pick the closest existing file, model the new one on it. |
| New menu action / signal wiring | `main_v2.py::MainWindow.init_ui` and `setup_connections`. |
| Target-related logic | `controllers/target_coordinator.py`. **All target changes flow through `set_target()`.** |
| Path classification logic | `analyzer/core.py` (decode evidence + maintenance loop), `local_intel/models.py::PathStatus`. |
| New geometric / math helper | `analyzer/geometry.py` (free function, no `self`). |
| Background data check or timer | Add a controller in `controllers/`, follow `HealthMonitor` pattern. |
| Outcome / event logging | `outcome_recorder.py`. Display strings are persisted — don't rename. |

## Known follow-ups (not done)

- `freq_to_band(freq_hz)` is duplicated as a private method in `analyzer/core.py`,
  `mqtt_client.py`, `hunt_manager.py`, and `local_intel/log_parser.py`
  (plus a different signature in `ionis/features.py`). The canonical version
  is now `analyzer.geometry.freq_to_band` — the other copies could eventually
  import from there.
- `insights_panel.py` (~1,700 lines) holds 7 sub-widgets in one file. Splitting
  them per file would improve navigation but is cosmetic; not currently planned.

## Git / push workflow

Branches use `refactor/…`, `fix/…`, `feat/…` prefixes. Direct pushes to `main`
are fine for small/personal commits; larger changes typically merge via
fast-forward after Windows-machine verification. See git log on `main` for
recent commit message style.

## Cutting a release

**Use the checklist** — `dev-docs/RELEASE_CHECKLIST.md` lists every file
that needs to move on a release, including the easy-to-miss ones (the
`docs/USER_GUIDE.md` "Current as of Version" header in particular). The
GitHub Actions workflow `.github/workflows/build-release.yml` builds and
publishes the Release page automatically when a `v*` tag is pushed.
