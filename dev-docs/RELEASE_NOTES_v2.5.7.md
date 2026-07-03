# Release Notes — v2.5.7

**Date:** July 2026
**Theme:** Better outcome data capture — the foundation for v2.6's
personalized recommendations

---

## Summary

QSO Predictor quietly logs the outcome of every calling attempt you make —
what the app recommended, what you did, the competition you faced, and
whether the target came back to you. That local data (never uploaded,
`~/.qso-predictor/outcome_history.jsonl`) is the raw material for the next
major release: **v2.6 is planned to use your own outcome history to tune
its recommendations to how *you* operate — your station, your band habits,
your pileup luck.**

This release fixes two bugs that were degrading that data:

1. **Competition was recorded as 0 in every outcome event.** A format
   mismatch meant the pileup-competition field — one of the most
   informative signals for "did following the recommendation pay off?" —
   was silently lost on every record. Fixed; competition is now captured
   correctly.
2. **Malformed grid squares produced bogus geometry.** A junk locator in a
   PSK Reporter spot (e.g. `ZZ99`) converted to impossible coordinates
   instead of being rejected, skewing bearing/sector analysis and the
   distance recorded with outcomes. Grids are now validated
   character-by-character.

**Why upgrade now rather than with v2.6:** outcome data only accumulates
while you operate. Records written by v2.5.6 and earlier carry an empty
competition field that can't be reconstructed afterwards. The sooner
2.5.7 is running, the more of your history v2.6 will be able to learn
from on day one.

Also in this release: Help → User Guide now opens the always-current guide
at [qsop.wu2c.net](https://qsop.wu2c.net), and the codebase gained a
285-test automated suite running on Windows, macOS, and Linux for every
change — the safety net for the v2.6 work ahead.

---

## What Changed

### Outcome recorder: competition field captured correctly

The dashboard formats competition as `"Low (2)"`, `"Medium (3) + QRM"`,
`"High (5) local"` — but the outcome snapshot still parsed the older
`"3 local"` format, failed on every string, and defaulted to 0. The
snapshot now extracts the count from the parenthesized form.

Effect on data analysis: outcome events from before this release have
`competition: 0` regardless of actual pileup size. Analysis of historic
data should treat pre-2.5.7 competition values as missing, not zero.

### Maidenhead grid validation

`grid_to_latlon()` validated locator length but not character ranges:
`'ZZ99'` yielded latitude 169.5 (impossible — field letters only go
A–R), and that garbage flowed into great-circle bearings, the 8-sector
signal distribution used for path classification, and the `distance_km`
recorded with outcomes. Grids are now checked field-by-field (A–R
letters, 0–9 digits, A–X subsquares); invalid locators are rejected and
the consuming code records "unknown" instead of a wrong number. Valid
grids of every shape — 2-char fields, lowercase, 6-char subsquares, and
`RR73` (a real Siberian square, despite moonlighting as the FT8 ack
token) — are covered by regression tests.

### Help menu: User Guide opens qsop.wu2c.net

Previously opened the GitHub blob view of the guide. The website version
is always current and easier to read.

### Internal: automated test suite + CI

285 tests now cover WSJT-X/JTDX protocol parsing (each case encoding a
historical user-reported regression), the persisted outcome-record
format, path-status display contracts, geometry helpers, and
architectural conventions. GitHub Actions runs the suite on Ubuntu
(Python 3.10–3.12), Windows, and macOS on every push. No user-facing
change — this is the safety net under everything that ships next.

---

## Compatibility

No settings, file-format, or protocol changes. Existing
`outcome_history.jsonl` files remain valid (schema v1 throughout);
records simply become more complete from this version forward.
