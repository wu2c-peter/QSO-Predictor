# Release Notes — v2.5.6

**Date:** May 2026
**Theme:** Minor bug fixes + a substantial internal refactor with no
behavior change

---

## Summary

A maintenance release. Three small user-visible fixes and a large
internal architecture cleanup that future-proofs the codebase without
touching any feature behavior.

1. **Windows console no longer spams `--- Logging error ---` tracebacks**
   on every target change. Caused by Python's logging stream handler
   inheriting Windows' default cp1252 encoding while log messages
   contain Unicode characters (arrows, emoji). The console stream is
   now reconfigured to UTF-8 with a backslash-replace fallback.
2. **The connection-help dialog title now reflects actual data state.**
   Previously it always said "No Data Detected" even when opened from
   the Help menu with both UDP and MQTT clearly running.
3. **UDP-silent warnings stay visible in the status bar** instead of
   flashing once and disappearing. The analyzer's "Tracking N stations"
   message was overwriting the warning every ~2 seconds; warnings are
   now sticky until conditions clear.

No changes to scoring, propagation analysis, Hunt Mode, Fox/Hound mode,
OutcomeRecorder, decoding, or any user-facing feature.

---

## What Changed

### Windows: UTF-8 on console stdout

`logging_config.py` reconfigures `sys.stdout` to UTF-8 with
`backslashreplace` error handling before adding the console
`StreamHandler`. Guarded against detached-stdout environments
(pythonw / MSIX), so non-console runs are unaffected.

The file handler always used `encoding='utf-8'` and was fine — only
the console mirror was emitting `UnicodeEncodeError` and dumping
`--- Logging error ---` tracebacks. macOS and Linux were unaffected
because their default console encoding is already UTF-8.

### Connection-help dialog: dynamic title

`startup_health_dialog.py` now derives the window title, header
emoji, and intro paragraph from the actual `udp_ok` / `mqtt_ok`
flags. Three states:

* **Both sources connected:** "Data Sources Connected" — green check
* **One source connected:** "Partial Data" — yellow warning
* **Neither connected:** "No Data Detected" — original red wording

The original wording was hardcoded because the dialog was originally
only triggered automatically when no data was flowing. The Help-menu
entry point added later opened the same dialog regardless of state.

### Status bar: sticky health warnings

`main_v2.py::MainWindow.update_status_msg` refuses to overwrite an
active `⚠`-prefixed warning with a non-warning message. The would-be
normal message is still saved to `_normal_status` so it can be
restored later, but the warning stays visible. A new
`clear_health_warning()` method is the only path that bypasses the
sticky check; `HealthMonitor` calls it when data sources resume.

Previously the analyzer's `"Tracking N stations"` status update
(emitted every ~2 seconds by the maintenance loop) overwrote the
UDP-silent warning before users could read it.

---

## Internal Architecture Refactor

`main_v2.py` shrank from 3,723 lines to 1,728 lines (-54%). The
`MainWindow` god class was split into focused modules:

* `widgets/` — six reusable Qt widgets (target dashboard, decode
  table model, tactical toast, clickable labels)
* `controllers/` — six subsystem controllers (`UpdateChecker`,
  `HealthMonitor`, `HuntCoordinator`, `IonisIntegration`,
  `FoxHoundController`, `TargetCoordinator`)
* `analyzer/` — what was `analyzer.py` becomes a package with the
  `QSOAnalyzer` class in `core.py` and pure helpers in `geometry.py`
* `utils/` — small pure-stdlib helpers (`version.py`)

A new `PathStatus` enum (`local_intel/models.py`) is now the canonical
domain type for path classification. Display strings remain
byte-identical — the outcome recorder persists them, so they must not
change. Three duplicated dispatch chains in `main_v2.py` collapsed
into single enum lookups, eliminating a substring-match bug class
(`"Not Reported in Region"` previously had to be checked before
`"Reported in Region"` to avoid false matches; with exact-match
lookup, that hazard is gone).

Conventions documented in
[`dev-docs/DEVELOPMENT_NOTES.md`](DEVELOPMENT_NOTES.md) § "Module
Structure & Refactor Conventions" and in a new
[`CLAUDE.md`](../CLAUDE.md) at the project root.

**Why this matters to users:** strictly speaking, it doesn't. The
refactor was behavior-preserving and exhaustively tested on both Mac
and Windows during incremental landing. The benefit is that future
features and fixes can be developed faster and with less risk of
unintended regressions, because each subsystem is now isolated in its
own module with a clear interface.

---

## What Didn't Change

* All scoring, path analysis, IONIS propagation, Hunt Mode, Fox/Hound,
  SuperHound, OutcomeRecorder behavior — identical to v2.5.5
* All UDP, MQTT, decode parsing, and band map rendering — identical
* Configuration and data file formats (`qso_predictor.ini`,
  `behavior_history.json`, `outcome_history.jsonl`,
  `hunt_list.json`) — fully backward compatible
* GitHub release distribution — unchanged

---

## Microsoft Store

**Not submitted to the Microsoft Store this cycle.** The user-visible
changes in this release are minor enough that the Store certification
overhead is not justified. Store users will pick these up as part of
the next substantive release (likely a feature release).

The MSIX manifest version is still bumped to `2.5.6.0` for
consistency, but no `.msix` package was submitted to Partner Center
for this release.

---

## Upgrading

Standard upgrade path. No user action required.

* **From source:** `git pull` and run. `requirements.txt` is unchanged.
* **From GitHub release:** download v2.5.6 from
  [Releases](https://github.com/wu2c-peter/qso-predictor/releases).
* **From Microsoft Store:** no Store update this cycle — your install
  remains at v2.5.5 until the next Store-bound release.

No configuration changes. No data migration.

---

## Files Modified

| File | Change |
|------|--------|
| `VERSION` | `2.5.5.1` → `2.5.6` |
| `logging_config.py` | UTF-8 stdout reconfiguration |
| `startup_health_dialog.py` | Dynamic title/header from data state |
| `main_v2.py` | Sticky warning + `clear_health_warning()`; refactor split into widgets/controllers/analyzer/utils packages |
| `controllers/` (new) | Six controllers split out of MainWindow |
| `widgets/` (new) | Six reusable widgets relocated from MainWindow |
| `analyzer/` (was `analyzer.py`) | Package with `core.py` + `geometry.py` |
| `utils/` (new) | `version.py` — version helpers usable from worker threads |
| `local_intel/models.py` | Expanded `PathStatus` enum with display attributes |
| `local_intel/predictor.py`, `local_intel_integration.py`, `insights_panel.py` | Renamed enum references to new `PathStatus` values |
| `CLAUDE.md` (new) | Project context file for AI-assisted future work |
| `dev-docs/DEVELOPMENT_NOTES.md` | New "Module Structure & Refactor Conventions" section |
| `packaging/AppxManifest.xml` | `Version="2.5.5.0"` → `Version="2.5.6.0"` |
| `dev-docs/RELEASE_NOTES_v2.5.6.md` | This file (new) |
| `README.md` | "What's New" section updated; v2.5.5 moved to Previous Releases |

---

## Credits

The Windows UTF-8 console fix was caught during the first refactor
testing pass on Windows — the spam was easy to spot once the refactor
moved log calls onto code paths that fired more often.

The sticky-warning bug was surfaced specifically by Mac testing
*without* WSJT-X connected — a deliberate edge case that the
pre-refactor code paths had never been exercised against. The bug was
pre-existing; the refactor just gave it a place to be noticed and a
clean place to be fixed.

The internal architecture refactor was a multi-session, incremental
effort: 10 PRs total, each Windows-tested with live WSJT-X / JTDX
before merging, none of which changed any observable app behavior.
Documented for posterity in
[`dev-docs/DEVELOPMENT_NOTES.md`](DEVELOPMENT_NOTES.md).

---

**73 de WU2C**
