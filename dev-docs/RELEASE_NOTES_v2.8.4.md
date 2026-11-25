# Release Notes — v2.8.4

**Date:** November 2026
**Theme:** One more log-scanner fix — a log that has shrunk is read again

---

## Summary

v2.8.4 is a one-fix release. Checking 2.8.3 on a live Windows station
turned up a second, older fault in the same background log scanner:
its live WSJT-X `ALL.TXT` had not been read for more than three
months.

Nothing here changes how you operate the app.

## What you'll notice

- **A log file that has been archived, split or restarted is read
  again.** The background scanner builds station behavior history
  (who a station tends to answer in a pileup) from your WSJT-X / JTDX
  logs, and remembers how far into each file it has read.

  If a log became *smaller* — you archived `ALL.TXT`, split it into
  monthly files, or deleted it and the program started a fresh one —
  the new file sat below the remembered position. The scanner read
  "file is not longer than where I stopped" as "nothing new" and
  skipped it, and kept skipping it until the file grew back past its
  old size. In the case that exposed this, a 1.19 GB `ALL.TXT` had
  been split in August; the fresh file had reached 470 MB by late
  November and not one line of it had been scanned.

  Nothing on screen shows this. Behavior history simply stops
  learning from the live log.

  The scanner now treats a file smaller than its remembered position
  as replaced and reads it again from the start.

- **Catching up is automatic.** If you were affected, the first launch
  of 2.8.4 writes one line to the log,
  `Log file shrank (… -> … bytes), rescanning from start: <path>`,
  and scans the file in the background. With the 2.8.3 batching this
  is cheap: on the station above, 470 MB took about three minutes,
  process memory peaked at 172 MB (about 150 MB at idle), and the
  saved position advanced once a minute throughout.

## Compatibility notes

- No settings or file formats change.
- **Known limit:** if a log is trimmed but still holds lines that were
  already scanned (for example, the oldest half removed with an
  editor), those remaining lines are counted a second time. A log
  that was archived or restarted — the usual cases — holds only new
  lines and is not affected.
- **Tested on Windows** (live station, from source) **and macOS** (test
  suite). The 2.8.3 scanner changes were confirmed on Windows in the
  same session.
- Still open from 2.8.2: the FT8web browser listener and UDP
  forwarding have not been re-tested live since the 2.8.2 listener
  startup change. Neither is touched in 2.8.3 or 2.8.4.

## For developers

- 2 new tests (826 → 828): a file smaller than its saved offset is
  rescanned from byte 0, and unchanged or grown files keep their
  offset.
- `BackgroundScanner._file_has_new_data(pos, file_size)` replaces the
  inline `file_size <= pos.byte_offset` check in `run()` and owns the
  shrink reset.
