# QSO Predictor v2.3.4 Release Notes

**Released:** April 2026  
**Type:** Bug Fixes  

---

## Bug Fixes

### Solar Data Fix (NOAA API Change)

**Symptom:** "Solar: SFI 0 | K 0 (Unknown)" in the status bar since March 31.

**Root cause:** NOAA SWPC changed their JSON data feed formats on March 31, 2026 (Service Change Notice SCN 26-21). Both endpoints QSOP uses were affected:

| Endpoint | Old format | New format |
|----------|-----------|------------|
| `summary/10cm-flux.json` | `{"Flux": "130"}` | `[{"flux": 130, "time_tag": "..."}]` |
| `noaa-planetary-k-index.json` | Header row + value arrays | Array of objects with `"Kp"` key |

**Fix:** Parser now handles both old and new formats, so it won't break if NOAA rolls back or other consumers still use the old format.

*Thanks to Brian KB1OPD for spotting this.*

### Score/Path Desync

**Symptom:** Decode table showing Score 99 on stations with "Not Reported in Region" or "No Reporters in Region" path status.

**Root cause:** `update_path_only()` refreshed the Path column every 2 seconds but never recalculated Score. When a PSK Reporter spot aged out and Path degraded, Score retained its original high value from when the path was active.

**Fix:** `update_path_only()` now recalculates Score using the same SNR + geo_bonus logic as `analyze_decode()`, keeping Score and Path in sync on every refresh cycle.

### Misleading "CALL NOW" With No Target Data

**Symptom:** Recommendation showed "▶ CALL NOW" with "No competition • You're calling" when PSK Reporter had zero coverage in the target's area.

**Root cause:** The strategy engine defaulted to `call_now` and the competition check treated `effective_size == 0` as "no competition" — but zero could mean "no data" rather than "verified empty."

**Fix:** Both heuristic and ML predictors now return `call_blind` action when PathStatus is UNKNOWN, displaying **"▶ CALL (no intel)"** in muted blue (#88bbff) with "No target area data" as the reason. Competition analysis is skipped when there's no data to analyze.

---

## Upgrade Notes

Drop-in replacement for v2.3.3. No config file changes required.

Solar data should appear within 15 minutes of startup (the refresh interval).

---

## Contributors

- **Brian KB1OPD** — NOAA solar data breakage report
- **Peter WU2C** — development

---

**73 de WU2C**
