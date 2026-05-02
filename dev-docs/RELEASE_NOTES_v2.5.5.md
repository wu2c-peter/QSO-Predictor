# Release Notes — v2.5.5

**Date:** May 2026
**Theme:** Memory leak fix and Microsoft Store update-channel awareness

---

## Summary

Two changes in this release:

1. **Memory leak fixed.** A cache that was added in v2.1.0 (Phase 2 reverse
   lookups, `sender_cache`) was being populated on every spot but was never
   pruned by the maintenance loop. On long-running sessions this caused
   steady RSS growth — typically several MB per minute on a busy band,
   accumulating to multiple GB on multi-day runs. The cache now expires
   entries on the same 15-minute window as the other spot caches, and
   memory should remain stable indefinitely.

2. **MSIX/Microsoft Store installs now ignore the in-app GitHub update
   check.** Store-installed users get updates through the Microsoft Store
   automatically; the in-app "new version available" banner pointing at
   GitHub was redundant and potentially misleading for that audience.

No behavioral changes to scoring, decoding, propagation analysis, Hunt Mode,
OutcomeRecorder, or any user-facing feature.

---

## What Changed

### Memory: `sender_cache` pruning

`analyzer.py` — added a cleanup block in `_maintenance_loop` for
`sender_cache`, mirroring the existing pattern used for `band_cache`,
`receiver_cache`, and `grid_cache`. Same 15-minute cutoff. The cache is
also cleared on band change (existing behavior, unchanged).

### Memory: diagnostics added to cache health log

The periodic `Analyzer cache health` log line now includes:

* `rss_mb` — process working set in megabytes
* `vms_mb` — process virtual memory size in megabytes
* `sender_cache_calls` — number of unique sender callsigns currently cached
* `sender_cache_spots` — total spot count across all sender_cache entries

These help future diagnostics if memory issues recur. Adds `psutil` as a
new dependency. The app gracefully runs without `psutil` if missing — the
diagnostics are simply omitted, no crash, no error.

### Update check: MSIX install detection

`main_v2.py` — added `is_packaged_install()` helper using the Windows
`GetCurrentPackageFullName` API. Returns `True` for MSIX/Store installs,
`False` for everything else (source, PyInstaller exe, non-Windows). When
`True`:

* The startup auto-update-check is skipped
* The "Check for Updates" Help menu item is hidden
* The update-available banner never fires (because `update_available` is
  never set)

Defensive: any unexpected error in detection returns `False`, so the
worst-case failure is "Store user still sees the banner" — exactly the
status quo before this change. There is no failure mode that affects
source/GitHub users.

---

## Why the Memory Leak Was There

`sender_cache` was added in v2.1.0 as part of Phase 2 Path Intelligence —
specifically for the `analyze_near_me_station()` reverse-lookup feature.
Spots are stored keyed by sender callsign so the analyzer can compute "how
often is this station getting through to other receivers" without an
external API call.

The cache was correctly cleared on band change, but the per-time-window
maintenance loop was never updated to include it. The omission was easy to
miss because:

* The other spot caches (`band_cache`, `receiver_cache`, `grid_cache`) all
  use the same `spot` dict objects via shared references — clearing
  `sender_cache` alone doesn't free them, so the impact wasn't visible in
  short tests
* `sender_cache` size wasn't included in the `Analyzer cache health` log
  line, so it was invisible in production diagnostics
* The growth was slow enough (~3-5 MB/min on a busy band) that single-
  session use rarely surfaced it
* On Windows, working set numbers can hide the accumulation when the
  process is idle, because the OS aggressively trims pages that aren't
  being touched. The leak was most visible during active use with a
  target selected (which exercised target-specific code paths that
  touched the cached pages, forcing them resident)

The fix was a 17-line addition mirroring the existing cleanup blocks.

---

## What Didn't Change

* All scoring, path analysis, IONIS propagation, Hunt Mode, Fox/Hound,
  SuperHound, OutcomeRecorder behavior — identical to v2.5.4
* All UDP, MQTT, decode parsing, and band map rendering — identical to v2.5.4
* Configuration and data file formats (`qso_predictor.ini`,
  `behavior_history.json`, `outcome_history.jsonl`) — fully backward compatible
* GitHub release distribution — unchanged. The in-app update check still
  works for source/GitHub installs as before.

---

## Upgrading

Standard upgrade path. No user action required.

* **From source:** `git pull` and run. If you maintain your environment via
  `requirements.txt`, run `pip install -r requirements.txt` to pick up the
  new `psutil` dependency. (The app will still run without it; you just
  won't see the new memory diagnostics in the log.)
* **From GitHub release:** download v2.5.5 from
  [Releases](https://github.com/wu2c-peter/qso-predictor/releases) and
  run.
* **From Microsoft Store:** the Store will deliver the update
  automatically — typically within 24 hours of the Store-channel release.
  No action required.

No configuration changes. No data migration. The diagnostic fields appear
in your log automatically on first run with `psutil` installed.

---

## Files Modified

| File | Change |
|------|--------|
| `VERSION` | `2.5.4` → `2.5.5` |
| `analyzer.py` | `sender_cache` pruning in maintenance loop; `rss_mb`/`vms_mb`/`sender_cache_*` fields in cache health log; defensive `psutil` import |
| `main_v2.py` | `is_packaged_install()` helper; startup update-check gated; menu item gated |
| `requirements.txt` | Added `psutil>=5.9.0` |
| `packaging/AppxManifest.xml` | `Version="2.5.4.0"` → `Version="2.5.5.0"` |
| `dev-docs/RELEASE_NOTES_v2.5.5.md` | This file (new) |
| `README.md` | What's New section updated; v2.5.4 moved to Previous Releases |

---

## Credits

Memory leak diagnosed and fixed during a live session: Peter noticed
8.4 GB RSS in Task Manager during normal operation, and progressive
instrumentation of the cache health log narrowed the cause to an unpruned
`sender_cache`. The shared-references aspect (clearing the cache didn't
release memory immediately because spot dicts were also referenced from
the bounded caches) was caught only after running the diagnostic-only
build for a full session and seeing `sender_cache_spots` climbing while
RSS stayed temporarily flat.

The MSIX update-channel suppression was prompted by the question "what
happens to the Store users when the GitHub banner fires?" — a good
example of treating a small user population (n=4 at time of release) as
real users worth getting right.

---

**73 de WU2C**
