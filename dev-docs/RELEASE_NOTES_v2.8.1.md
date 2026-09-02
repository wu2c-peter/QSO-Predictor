# Release Notes — v2.8.1

**Date:** September 2026
**Theme:** The audit release — forty verified fixes, and the tests that keep them fixed

---

## Summary

v2.8.1 is a bug-fix release. A systematic five-part code audit of the
2.8.0 codebase turned up a family of defects with a common shape: a
subsystem failed quietly and kept showing confident output. Every
finding was re-verified against the source before it was fixed, and
every fix the test suite can express has a regression test (688 → 798
tests). The most consequential item: the sweep-aware frequency
recommendation shipped as a feature in the code but had **never fired
in any packaged build** — it does now.

Nothing here changes how you operate the app. A few things will look
different, listed first.

## What you'll notice

- **Sweep-aware recommendations now work in the exe / DMG.** When the
  Insights panel detects a target working its pileup high-to-low (or
  low-to-high), the band map's green line tilts toward the end of the
  passband the target reaches first. The correlation behind this used
  scipy, which the frozen builds deliberately exclude, so packaged
  users always got "Random". It is pure stdlib now.
- **The recommendation is no longer pinned to 300 Hz** when the target
  has no tier-1 spots. Every regionally-quiet slot scored identically
  and the first tie won; a small clearance/centrality tie-break now
  picks a slot in the middle of a quiet stretch. (This was the real
  mechanism behind the 1087 Hz pick in the OH0ERF session.)
- **Status-bar warnings you were never getting.** A PSK Reporter
  outage, a broker that never connected, or an FT8web listener that
  could not bind its port now say so. The MQTT health check had been
  looking for the client on the wrong object for two releases.
- **Solar header is honest.** A failed NOAA fetch used to display
  "SFI 0 | K 0 (Poor)" and feed those impossible values to IONIS. Now
  the header shows the last good reading marked with its age, or
  "Solar: unavailable", and IONIS refuses out-of-range inputs.
- **Two dead controls work again:** right-click → "Set X as Target"
  in the decode table (raised an error), and the "+" manual-target
  entry in the Insights panel (silently unwired). The dashboard's "+"
  always worked.
- **Settings → Appearance does something.** The tab was saved and
  displayed but read by nothing. Font now applies to the decode table;
  the two colours drive the Prob column and dashboard probability.
- **"Not Transmitting" is only shown when you aren't.** Since v2.7.0
  the reception cache is per-band and cleared on every QSY, so the
  first minutes on a new band mislabelled every row while you were
  calling. The label now requires the WSJT-X status stream to say you
  are off the air; otherwise it's "Not Reported in Region".
- **Clear Target really clears.** The cleared station's pileup kept
  being tracked in the background, and its sweep pattern could
  re-tilt the band map with no target selected.
- **Dock layout comes back** even when Local Intelligence fails to
  load; the restore was nested inside that branch.
- **Behavior bootstrap no longer freezes the window** — it runs on a
  worker thread against the live history, so its results can't be
  overwritten by the background scanner's next save.

## Fixes by area

### Data ingest
- Click-to-call routing and the "data flowing" timestamp are recorded
  only after a datagram passes the WSJT-X magic check. A logger
  replying to QSOP's forwards, or any stray packet on the port, could
  previously hijack where Reply/Configure requests went — the UI still
  said "sent".
- A forwarded packet that loops back to QSOP's own listener is
  consumed once and never re-forwarded; the config-time filter also
  recognises this machine's hostname, `.local` name and LAN addresses
  (`my-mac.local:2237` used to sail past it).
- MQTT subscriptions are tracked in a ledger. `unsubscribe("#")`
  matches nothing under MQTT's literal-filter rules, so every band you
  visited stayed subscribed and the main thread decoded all of them
  for the whole session.
- **FT4** operators get FT4 spots: the PSK Reporter topic, the
  session tracker's cycle clock (7.5 s, not 15) and the Local
  Intelligence decode stream all follow the mode now.
- An unknown dial frequency (VHF, or garbage) subscribes to no band
  topic instead of silently pulling 20 m's firehose.
- A config file missing a key (hand-edited, or truncated by a crash
  mid-save) used to kill the app before Settings was reachable.
  Missing keys are filled from defaults, corrupt files are backed up
  and reset, and saves are atomic.
- FT8web: the WebSocket handshake now checks the browser's `Origin`
  header — any page open in your browser could previously connect to
  `ws://localhost:2442` and inject decodes that QSOP re-broadcast to
  your logger. Fragmented messages are capped. A listener that dies
  logs why instead of exiting silently.
- The periodic health check can no longer take the whole app down if
  one source's check raises (PyQt6 aborts on an unhandled slot
  exception).

### Decision core
- The strongest regional reporter wins path classification; a later,
  weaker reporter could overwrite a better one, so the displayed
  bonus and SNR depended on cache order.
- Hound mode enforces the 1000 Hz floor on the automatic
  recommendation, not just on clicks — the green line could land
  inside the red Fox TX zone.
- The cycle clock advances by whole periods; sub-period jitter used to
  skip roughly one boundary in two.
- IONIS: invalid grids no longer resolve to the Gulf of Guinea, NaN
  no longer reads as a confident "CLOSED", the 12-hour forecast's
  first column matches the headline prediction (they used to differ by
  up to an hour of solar elevation), and the year-end wrap is right
  in leap years.
- The station-grid placeholder check is case-insensitive. Settings
  upper-cases the grid on save, so one premature Save turned `FN00aa`
  into `FN00AA` and IONIS confidently predicted from western
  Pennsylvania forever.

### Local Intelligence
- The behavior history dict is now locked; it was written from the
  scanner thread, the bootstrap, and the GUI thread with no
  synchronisation, and a collision during the save silently stopped
  history from persisting.
- History and file-position saves are atomic (temp file + rename);
  a corrupt history file is quarantined and reported rather than
  treated as "no history".
- The incremental log scanner used the text iterator, which disables
  `tell()`; when shutdown interrupted a scan mid-file the offset was
  never advanced and the same lines were counted again on the next
  launch. It also froze its file list at startup, so a log created
  later (JTDX's monthly rollover) was never read.
- Re-running Bootstrap doubled every station's session and QSO
  counters (and shifted its persona). It now keeps a watermark and only
  counts new data.
- Live picking observations no longer inflate `total_qsos`, which
  fed the persona traits and drove bootstrapped stations toward the
  "DX hunter" persona.
- Idle sessions are evicted and stale answers dropped, so a station
  worked an hour ago doesn't replay its old sweep on the next answer.
- Live Bayesian beliefs are persisted when the target changes; nothing
  ever called the end-of-session hook before.

### Outcome recording (research data)
- Outcome file rotation keeps timestamped archives. The single `.bak`
  scheme meant the second rotation permanently destroyed the first
  ~40K events.
- `behavior_source` now records `live` / `historical` / `persona` /
  `prefix` / `default` as the schema document always said; persona
  and prefix priors were indistinguishable in the data.
- `score_delta` is recorded whenever a recommendation existed, not
  only when its score was non-zero.
- Targeting a station from its pileup decodes kept `distance_km`
  even though those messages carry no locator — the grid is now
  backfilled from earlier CQ decodes and the WSJT-X DX Grid box.

### UI and shutdown
- Every periodic timer is stopped before the data sources are torn
  down.
- Modal dialogs (Training, Checkup, Setup Wizard, Connection Help)
  release themselves on close; each open used to leak a widget tree,
  and the Training dialog re-connected five signals per open.
- The Fox/Hound disambiguation dialog is deferred out of the UDP
  status handler instead of spinning a nested event loop inside it.
- Click-to-copy feedback no longer restores a stale callsign if the
  target changes within the second.
- Band-map spot freshness fades as designed; every refresh had been
  re-stamping spots as brand new.
- The window/tray icon resolves from the install folder, not the
  working directory (blank icon when launched from a shortcut with a
  different "Start in").
- Right- and middle-clicks on the info bar no longer open the browser.
- Connection Help renders correctly under a dark system palette; its
  dead "don't show again" checkbox is gone.

### Packaging
- The macOS release build had a shell fallback that re-ran PyInstaller
  without the icon and bundle identifier and still reported success.
  Removed; the conventions test now covers the macOS job too.
- The MSIX spec no longer lists sklearn/joblib hidden imports the
  main spec dropped in July.
- `launcher.py` installs from `requirements.txt` instead of a list that
  had gone four dependencies stale (IONIS silently missing).
- Third-party notices now cover psutil, pycaw and comtypes, which are
  compiled into the frozen builds.

## Compatibility notes

- **Self-hosted FT8web:** the new `Origin` check allows
  `ft8web.ok1cdj.com`, `localhost` and `127.0.0.1` by default. If your
  FT8web runs on another host, add it to a new `FT8WEB/allowed_origins`
  key in `qso_predictor.ini` (comma-separated host names).
- **Outcome history files** are read unchanged. New events carry the
  extra `behavior_source` values above; archives are named
  `outcome_history.jsonl.<UTC timestamp>.bak`.
- **Behavior bootstrap** writes `~/.qso-predictor/behavior_bootstrap.timestamp`
  and only counts data newer than it on re-runs. Delete the file to
  force a full 14-day re-scan.
- The Appearance settings you may have saved in the past take effect
  at the next launch.

## For developers

- 110 new tests, including the first coverage of `ionis/` (golden
  vectors pinned to the committed V22-gamma checkpoint) and
  `tests/test_conventions.py::test_controllers_only_reference_attributes_mainwindow_has`,
  which fails when a controller references an attribute MainWindow
  does not define — the exact failure mode behind three of the dead
  features above.
- `CLAUDE.md` and `dev-docs/DEVELOPMENT_NOTES.md` corrected (the
  `freq_to_band` duplication note, and the behavior-prior hierarchy,
  which does include prefix aggregation).
