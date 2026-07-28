# Release Notes — v2.7.1

**Date:** July 2026
**Theme:** Point release — status-bar "reporting" count fixes
(v2.7.0's Doctors release, one day later, with two field-reported
counting fixes)

---

## Summary

v2.7.1 is v2.7.0 (see
[RELEASE_NOTES_v2.7.0.md](RELEASE_NOTES_v2.7.0.md) — the Doctors
diagnostics framework) plus two fixes to the status bar's
"N reporting <your call>" figure, both found within hours of release
by operating the real station:

1. **Distinct receivers, not raw reports.** The count was the raw
   length of the 3-minute reception-report list — while running
   frequency, every receiver that copies you appears once per TX
   cycle, so the display overstated your audience 3–6×. It now counts
   unique receiver callsigns (the same "count unique callsigns, not
   total spots" rule the Tracking figure has used since v2.0.4). The
   "(N near target)" count gets the same deduplication.

2. **Current band only.** The self-spot feed from PSK Reporter is
   band-wildcarded, and the reception cache had no band gate — so the
   status line could show "10m … | 12 reporting <call>" built from
   receptions of your transmissions on 20m (conspicuous when a second
   instance of the app runs under the same callsign on another
   machine). Receptions now pass the same ±5 kHz dial gate as the band
   map. This also tightens Path Intelligence: "target decoded your
   signal" evidence is now strictly current-band — a reception on
   another band says nothing about who hears you here.

Note: with two same-callsign stations transmitting on the *same* band,
the count still includes both audiences — PSK Reporter keys on the
callsign and cannot distinguish transmitters.

No other changes. Test suite: 632 tests.
