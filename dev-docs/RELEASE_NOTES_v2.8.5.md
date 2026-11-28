# Release Notes — v2.8.5

**Date:** November 2026
**Theme:** Path Intelligence no longer shows the last target's result

---

## Summary

v2.8.5 is a one-fix release, found on the air: the Insights panel's
Path Intelligence section claimed a PSK Reporter spot near the target
while the status bar, on the same screen, said nobody near the target
was reporting. The status bar was right.

Nothing here changes how you operate the app.

## What you'll notice

- **Switching to a target you haven't decoded yet clears the old path
  result.** Path Intelligence takes its "Heard by Target / Reported in
  Region" state from the target's row in the decode table. When a
  target arrived *without* a row — WSJT-X or JTDX handed over a DX
  call that isn't currently decoded, or you typed one in — nothing
  recomputed that state, and the panel went on showing the previous
  target's result under the new callsign.

  The case that exposed it, on 80m: the target changed from a US
  station to LY5A (KO15) through a JTDX sync. The panel kept
  "Your signal reported nearby — Spotted at -9 dB by NK5B", which was
  true of the US station, while the status bar read "39 reporting
  WU2C (0 near target)" and the dashboard's Path field was blank.

  The panel's path state is now reset whenever a target is set
  without a decode row, and when the target is cleared. Until the new
  target is decoded, Path Intelligence shows only what is known about
  it (typically "None from your area"); once it is decoded, the
  normal refresh takes over as before.

- This has the same symptom as the wording fix in v2.8.2 (Path
  Intelligence claiming a spot that PSK Reporter doesn't show) but a
  different cause, and it is older than 2.8.2.

## Compatibility notes

- No settings or file formats change. Outcome recording is not
  affected: it reads path state from the decode row, not from the
  panel.
- **Not changed:** for a target that has a known grid but no decode
  row, the dashboard's Path field still shows `--`; a real path
  status is not computed until the station is decoded.
- **Testing:** covered by new tests, and the fix has been running
  from source on a live Windows station since 25 November. The exact
  switch that triggered the bug was not re-staged on the air.
- Still open from 2.8.2: the FT8web browser listener and UDP
  forwarding have not been re-tested live since the 2.8.2 listener
  startup change. Neither is touched here.

## For developers

- 3 new tests (828 → 831) in `tests/test_target_coordinator.py`, the
  first to drive `TargetCoordinator.set_target()` directly (against a
  mocked MainWindow): a target with no decode row resets path state,
  a target with a row takes it from the row, and clearing resets it.
- The reset lives in `TargetCoordinator.set_target()` step 7, next to
  the existing `_update_local_intel_path_status(row_data)` call.
