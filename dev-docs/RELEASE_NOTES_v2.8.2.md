# Release Notes — v2.8.2

**Date:** November 2026
**Theme:** Saying what the evidence shows — honest Path Intelligence wording, WS support, and a startup that can't stall

---

## Summary

v2.8.2 is a small bug-fix release driven by two user reports. One was
a migration from WSJT-X Improved to its successor, **WS - Digital Mode
Suite**. The other was a contradiction: Path Intelligence said "Your
signal reported nearby" while PSK Reporter showed nobody hearing the
operator. Both turned out to be worth fixing properly.

Nothing here changes how you operate the app.

## What you'll notice

- **Path Intelligence no longer claims a spot that didn't happen.**
  A green "Reported in Region" path can come from two kinds of
  evidence: a PSK Reporter receiver near the target spotting *you*, or
  QSO Predictor's own decodes. The decode kind includes "the target
  just answered another station in your grid field", which says the
  band is open your way but not that anyone has heard you. The panel
  used to describe all of it as "Your signal reported nearby / Spotted
  by receiver in target's region". It now tells them apart:

  | Evidence | Path Intelligence says |
  |---|---|
  | PSK Reporter spot of your signal | **Your signal reported nearby** — names the receiver and SNR |
  | Target answered a station in your grid field | **Target is working your area** — "From your decodes — you are not confirmed heard" |
  | A station in the target's field answered you | **Answered from target's region** — "From your decodes (not a PSK Reporter spot)" |

  The Path column itself is unchanged: all three still show green
  "Reported in Region".

- **WS - Digital Mode Suite works, and is covered by tests.** WS 3.2
  (the successor to WSJT-X Improved) identifies itself as "WS" over
  UDP, adds trailing fields to Status and QSO Logged, and sends a new
  message type. QSO Predictor already coped with all of that; it is
  now pinned with WS-shaped packets so it stays that way. You do
  **not** need WS's "WSJT-X compatibility mode" for QSO Predictor.

- **Startup can't stall on a hostname lookup.** Building the UDP
  listener looked up this machine's own hostname on the main thread.
  Where that lookup is slow (seen at ~35 seconds per call on
  GitHub's macOS build machines) the window would hang with it. The listener now
  starts immediately on the default route and loopback, and a
  background thread adds the remaining local addresses when the lookup
  returns. On multicast setups the log now shows two lines: "Multicast
  joined … on: …" followed by "Multicast also joined … on: …".

## Auto-paste scripts (User Guide)

If you use the AutoHotkey or Hammerspoon scripts, take the updated
copies from the User Guide:

- **AutoHotkey** finds stock WSJT-X, WSJT-X Improved and WS (window
  title "WS  v3.x Digital Mode Suite") in one branch, with no
  hard-coded version number.
- **Hammerspoon** never matched stock WSJT-X as published: the "-" in
  "WSJT-X" was being read as a Lua pattern character. Fixed, and WS
  is matched by its exact app name.
- **Copying callsigns from another program** (GridTracker's call
  roster, a cluster window): the script's WSJT-X callsign branch has
  been off since v2.8.0, because QSO Predictor sets DX Call over UDP.
  The guide now explains how to turn it back on, and how to stop after
  Generate Std Msgs instead of clicking Enable TX.
- Re-measure your field coordinates after switching apps; WS lays its
  window out differently.

## Outcome recording (research data)

Found by the October 2026 outcome analysis, the first look at schema
v2 data:

- `my_rank_at_select` and the per-cycle trace rank were always null.
  They now carry your SNR rank at the target's end.
- `best_rival_snr` no longer counts your own spot as a rival.
- `local_callers_at_select` (almost always 0 at the moment of
  selection) is promoted from the first TX cycle.
- A blank `path_at_select` is backfilled from the first TX cycle's
  path label.

`dev-docs/OUTCOME_SCHEMA.md` records the fix date so earlier events
are treated as known-gapped. Note that "Reported in Region" in the
outcome log still covers all three kinds of evidence in the table
above; the new distinction is display-only in this release.

## Compatibility notes

- No settings or file formats change.
- **Not re-tested for this release:** the FT8web browser listener and
  UDP forwarding to a downstream app. Neither was modified, but the
  UDP listener's startup was (the address lookup above), and the
  forward-loop guard now learns this machine's LAN addresses a moment
  after startup instead of during it.

## For developers

- 23 new tests (798 → 821), covering WS-shaped packets, the evidence
  kind behind each path result, and a slow hostname lookup at
  listener start.
- The macOS CI job dropped from 30+ minutes to under 90 seconds. Every
  `UDPHandler()` in the suite was paying the ~35 second hostname
  lookup on GitHub's macOS runners; an autouse fixture in
  `tests/conftest.py` keeps the suite off the resolver.
- `QSOAnalyzer._check_decode_path` returns `(path, bonus, kind)`, and
  analyzed rows carry `path_evidence` (`'pskr'` or a decode kind).
