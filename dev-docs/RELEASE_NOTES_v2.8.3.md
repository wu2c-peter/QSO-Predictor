# Release Notes — v2.8.3

**Date:** November 2026
**Theme:** Two fixes from a user report — bounded-memory log scanning, and macOS Preferences

---

## Summary

v2.8.3 is a two-fix release. Both bugs were reported by IW5DNZ
(GitHub #8 and #9), each with a correct diagnosis and a working patch;
the fixes here are his, with some restructuring and extra tests.

Nothing here changes how you operate the app.

## What you'll notice

- **A large `ALL.TXT` no longer eats memory, and is no longer rescanned
  on every launch.** The background scanner that builds station
  behavior history from your WSJT-X / JTDX logs had two faults that
  fed each other:

  1. It read every new line of a file into memory before processing
     any of it. A parsed line costs roughly ten times its text, so a
     log of a few hundred MB became several GB — reported at 6+ GB
     and "Not Responding" within minutes of launch on macOS.
  2. It saved its place only *between* files. Quit (or force-quit)
     while it was inside the big file and the progress was lost, so
     the next launch started that file from the beginning and the
     whole thing repeated.

  The scanner now reads at most 20,000 decodes at a time, processes
  and frees them, and continues the same file; and it saves its place
  about once a minute while doing so. On a synthetic 190 MB log, peak
  memory went from 1.2 GB to 68 MB.

  The scanner reads every `ALL.TXT` in the WSJT-X and JTDX folders,
  whether or not that program is the one you are running, so an old
  log from a program you no longer use could trigger this. The code is
  the same on every platform; any machine with a large enough log was
  exposed.

  If you were affected, the first launch of 2.8.3 still has to work
  through the big file once, but it does so in bounded memory, and
  it survives being interrupted.

- **macOS: Preferences… (⌘,) opens Settings again.** On macOS, Qt
  moves menu items into the application menu based on their names. When
  the Diagnostics menu arrived, "Config Doctor..." matched "config"
  and took the Preferences… slot, and "Settings" was removed from the
  File menu without landing anywhere — the only way left into
  Settings was Help → Connection Help… → Open Settings. Every such
  item now states its role explicitly: Settings is on
  **QSO Predictor → Preferences… (⌘,)**, the macOS convention, and
  Config Doctor stays under Diagnostics. Windows and Linux menus are
  unchanged (File → Settings).

## Compatibility notes

- No settings or file formats change. `file_positions.json` keeps its
  format; it is simply written more often.
- Station behavior statistics are built per batch, so a pileup that
  happens to span a 20,000-decode boundary is counted as two shorter
  ones. The effect on the statistics is negligible.
- **Tested on macOS only for this release** (test suite on all three
  platforms via CI). The menu change does nothing on Windows; the
  scanner change is platform-independent.
- Still open from 2.8.2: the FT8web browser listener and UDP
  forwarding have not been re-tested live since the 2.8.2 listener
  startup change. Neither is touched in 2.8.3.

## For developers

- 5 new tests (821 → 826): bounded batch reads (LF and CRLF), the
  positions file advancing mid-file, stop landing on a batch boundary,
  and a conventions test that fails if any `QAction` in `main_v2.py`
  whose text Qt's macOS heuristic would match (config / setting /
  preference / option / setup / about / quit / exit) does not call
  `setMenuRole()`.
- `BackgroundScanner._scan_file()` owns the per-file batch loop;
  `_scan_file_incremental()` now returns at most `MAX_BATCH_DECODES`
  and is called repeatedly.
