# DEVELOPMENT_NOTES — v2.3.1 Additions

*Append these sections to docs/DEVELOPMENT_NOTES.md*

---

## v2.3.1 — SuperFox/SuperHound Disambiguation (March 2026)

### Problem

v2.3.0 shipped a single F/H checkbox and Layer 2 inference. Two issues emerged from live testing:

1. **False positive:** A station (A71 prefix) operating near 973 Hz triggered Layer 2 Fox detection. Real Fox TX is 300–900 Hz; 973 Hz is a Hound calling near the bottom.
2. **SuperFox vs F/H conflation:** WSJT-X reports `special_mode=7` for BOTH old-style Hound and SuperHound. No UDP field distinguishes them. A checkbox gives no way to signal which you're in. The 1000 Hz clamping that helps old-style Hound **actively harms** SuperHound users (Hounds can call anywhere ≥200 Hz in SuperFox mode).

### Solution

**Three-state combo box:** Off / F/H / SuperF/H — replaces the checkbox. User explicitly selects mode.

**Disambiguation dialog:** When UDP or Layer 2 triggers a detection, instead of auto-activating, QSOP shows a dialog: "Fox/Hound activity detected — which mode?" with three buttons: F/H / SuperF/H / Ignore. This makes the ambiguity explicit and puts the user in control.

**Tightened Layer 2 threshold:** 950 Hz (was 1000 Hz), 4+ observations required (was 3). The A71 false positive was at 973 Hz with 3 observations; the tighter rules would have correctly rejected it.

**Clamping scope:** 1000 Hz minimum recommendation only applies to old-style F/H. SuperF/H leaves recommendations unclamped (Hounds may call anywhere ≥200 Hz per protocol spec).

### SuperFox Protocol Notes (for future development)

Key findings from CY0S 2026 live testing:

- **SuperFox dial frequency is NOT 14.074** — it's a non-standard frequency (e.g. 14.091 MHz). The 1512 Hz wide signal would obliterate standard FT8 traffic if on 14.074.
- **SuperFox lowest tone is ~750 Hz**, spanning 750–2262 Hz. This is detectable in decodes (all Fox decodes appear at freq ~750 in the decode window).
- **"verified" appears in decoded SuperFox messages** — this string is unique to SuperFox and could be used for auto-detection in future.
- **SuperFox uses even TX cycles only** — odd cycles are RX. Our activity state parser may show spurious "Idle" on the odd cycle; this is expected behaviour, not a bug.
- **WSJT-X locks TX freq field in SuperHound mode** — intentional. AHK scripts that try to set TX freq by injecting keystrokes into the WSJT-X field will fail.
- **Clicking decode window in SuperHound mode sends no UDP** — WSJT-X suppresses target-selection UDP packets. QSOP target must be set manually when operating SuperHound.

### WSJT-X UDP Limitations Summary (updated)

| Detection path | WSJT-X | JTDX |
|---------------|--------|------|
| UDP special_mode (field 18) | Works (returns 6 or 7) | Always 0 — unusable |
| UDP SuperFox vs Hound distinction | No — both return 7 | N/A |
| Layer 2 decode inference | Works | Works |
| Manual combo box | Works | Works (primary path) |

### False Positive Analysis

Brian KB1OPD reported: an A71 station operating at 973 Hz triggered the v2.3.0 Layer 2 inference after 3 observations, briefly activating F/H mode.

Root cause: 973 Hz is just above our old 1000 Hz threshold — technically below it, so it was counted. A Hound calling at 973 Hz is unusual but legal in old-style F/H (Hounds call above 1000 Hz in old mode, but this station may have been unaware).

Fix: Threshold moved to 950 Hz. At 973 Hz the station would now be ignored by Layer 2. Additionally, requiring 4+ observations rather than 3 adds another layer of protection.

---

## SuperFox Operating Workflow (for Wiki)

Documented from live CY0S 2026 testing on WSJT-X 3.0.0 Improved PLUS:

1. Tune rig to DXpedition's published frequency (NOT standard FT8 frequency)
2. Set RX audio offset to ~750 Hz
3. Set QSOP combo to SuperF/H
4. Watch waterfall for wide 1512 Hz block (looks nothing like normal FT8)
5. When Fox decodes appear in Band Activity window, double-click a Fox line
6. WSJT-X auto-sequences — Enable TX flashing momentarily is normal if no Fox decoded yet
7. SuperHound label turns green when Fox signal is verified
8. Do not touch anything once QSO starts — WSJT-X handles everything
9. After RR73 received, QSO is logged automatically

---

## v2.3.2 — Layer 2 Removal & Multicast Fix (March 2026)

### Layer 2 F/H Inference Removed

The frequency-counting Layer 2 inference (added in v2.3.0, tightened in v2.3.1) was removed entirely in v2.3.2.

**Reasoning:** On standard FT8 frequencies (14.074 MHz, etc.), nobody operates as Fox — so any Layer 2 trigger there was a false positive. On non-standard frequencies (14.090 MHz, etc.), the frequency alone is a strong indicator of F/H — the counting logic was redundant. Layer 2 was either wrong or unnecessary.

**Updated detection summary:**

| Detection path | WSJT-X | JTDX |
|---------------|--------|------|
| UDP special_mode (field 18) | Works (returns 6 or 7) | Always 0 — unusable |
| Manual combo box | Works | Works (primary path) |
| SuperFox "verified" auto-detect | Works | N/A (JTDX can't decode SuperFox) |
| ~~Layer 2 decode inference~~ | ~~Removed v2.3.2~~ | ~~Removed v2.3.2~~ |

**Code removed:** `_fh_target_tx_below_1000` and `_fh_target_tx_above_1000` counters, `_check_fox_from_decodes()` function (replaced by `_check_superfox_from_decodes()`), `'inferred'` branch in disambiguation dialog.

**What remains:** SuperFox auto-detection from "verified" / "$VERIFY$" decode content is preserved — this is a definitive signal, not a statistical inference. The `'inferred'` source value is still used for this SuperFox auto-detect path.

### Multicast UDP Crash Fix

**Bug:** `OSError: [WinError 10065]` at startup when multicast UDP configured but system can't join group. App crashed in `udp_handler.__init__` at `setsockopt(IP_ADD_MEMBERSHIP)`, preventing user from reaching Settings to fix config.

**Root cause:** Single try/except wrapped both `bind()` and `setsockopt(IP_ADD_MEMBERSHIP)`, with unconditional `raise` on any failure.

**Fix:** Separated bind and multicast join into nested try/except blocks. Three fallback layers:
1. Multicast join fails → socket stays bound, app starts, user can fix in Settings → Network
2. Bind fails for multicast → attempts fresh unicast socket on 0.0.0.0
3. Everything fails → app starts with no UDP, user can still access Settings

Added `_bind_ok` flag for potential future UI warning banner.

**Reporter:** Bob K7TM

---

## v2.3.3 — Target Handler, Score Rename, Script Fix (March 2026)

### Unified Target-Change Handler (_set_new_target)

**Problem:** Four separate code paths changed the current target, each with inline state management:

| Path | Source | Issues |
|------|--------|--------|
| `clear_target()` | Ctrl+R / button | Most complete, but still missed perspective update |
| `sync_to_jtdx()` | Fetch Target button | Missing: analyzer grid, activity state, F/H reset, band map freq, perspective, toast, path status |
| `on_status()` | UDP dx_call change | Missing: activity state reset, competitor clear, F/H reset, toast reset |
| `on_row_click()` | Decode table click | Missing: activity state reset, F/H reset |

**Symptom:** Switching targets could leave stale data in the dashboard, band map perspective, insights panel, or status bar. The "near target" count in the status bar only reset on QSO completion, not on target change.

**Fix:** Single `_set_new_target(call, grid, freq, row_data)` method handles all 9 state update categories:

1. Core state (current_target_call, current_target_grid, analyzer.current_target_grid)
2. Per-target tracking reset (activity state, inferred competitors)
3. F/H per-target state reset (fox_qso, dialog_shown)
4. Table highlighting
5. Dashboard update (with re-analyze if row_data available)
6. Band map (freq, call, grid, perspective clear)
7. Local Intelligence (target, path status, competition forwarding)
8. Tactical toast state reset
9. Perspective display update (PSK Reporter fetch)

All four callers reduced to single-line calls. Future features that need target-change hooks have exactly one place to add code.

**Design decision:** `_set_new_target` auto-searches the decode table if `row_data` is not provided, filling in grid/freq from the table. This means `sync_to_jtdx` and `on_status` don't need to duplicate the table-scanning logic.

### UDP Silence Detection Improvement

**Problem:** `check_data_health()` only warned when data *stopped* flowing (tracked via `_last_packet_time`). If data never arrived at all — e.g. WSJT-X not running, wrong port, or multicast bind failure — the "never received" path returned `(True, "")` forever after startup.

**Fix:** Three distinct cases now handled:

1. `_bind_ok == False` → immediate specific warning about bind failure
2. `_last_packet_time is None` and `_start_time` exceeds threshold → "never received" warning
3. `_last_packet_time` stale → existing "data stopped" warning

Added `_start_time` tracking in `start()` to measure time since listener began (previously only tracked time since last packet).

The existing `_check_data_health` timer in main_v2.py (10-second interval) and `_check_startup_health` (20-second one-shot) already surface these to the status bar — no main_v2.py changes needed.

### "Prob %" Renamed to "Score"

The decode table column "Prob %" and insights panel "Success Prediction" were renamed to "Score" and "Opportunity Score" respectively. The values (0–99) are a heuristic combining SNR base score + path geo_bonus - competition penalty, not a statistical probability. The `%` suffix was removed from the output in `analyzer.py`.

**Files changed:**
- `analyzer.py` — output format changed from `f"{final_prob}%"` to `str(final_prob)`
- `main_v2.py` — column header "Prob %" → "Score", dashboard label, sort key mappings, tooltips, `%`-stripping logic removed from sort/display code
- `insights_panel.py` — group box title "Success Prediction" → "Opportunity Score", tooltip updated, `%` removed from display

Internal key name `'prob'` unchanged — renaming the dict key across the whole codebase was unnecessary churn.

### Auto-Paste Script: Generate Std Msgs

**Problem:** The AHK/Hammerspoon scripts pasted a callsign into the DX Call field and clicked Enable TX, but did not click "Generate Std Msgs". Without this step, the TX message sequence (Tx1–Tx5) remained populated for the previous station. Both WSJT-X and JTDX require Generate Std Msgs to be clicked after manually entering a callsign.

**Fix:** Added `GEN_X`/`GEN_Y` coordinates for both JTDX and WSJT-X. Split the old `PasteToField` function into two: `PasteToField` (frequency only, simple) and `PasteCallsign` (callsign + Gen Std Msgs + Enable TX). Sequence is now: type callsign → Enter → click Gen Std Msgs → click Enable TX.

**Also added:** Tooltips on clickable dashboard elements (target callsign, recommended frequency) mentioning auto-paste script integration.

---

## v2.3.4 — Solar API Fix, Score/Path Desync, CALL NOW Fix (April 2026)

### NOAA SWPC JSON Format Change (SCN 26-21)

NOAA changed their JSON data feeds effective March 31, 2026. Both endpoints used by solar_client.py were affected.

**10cm-flux.json:**
- Old: `{"Flux": "130", "TimeStamp": "2026-02-26 20:00:00 UTC"}`
- New: `[{"flux": 130, "time_tag": "2026-02-26T20:00:00"}]`
- Changes: key `Flux` → `flux`, wrapped in array, values numeric not quoted

**noaa-planetary-k-index.json:**
- Old: `[["time_tag", "Kp", ...], ["2026-02-19 00:00:00", "3.33", ...]]` (header + rows)
- New: `[{"time_tag": "...", "Kp": 3.33, "a_running": 18, "station_count": 8}, ...]`
- Changes: positional arrays → keyed objects, values numeric

**Fix:** Type-check response (list vs dict, dict vs list entries) and handle both formats. Reference: https://www.weather.gov/media/notification/pdf_2026/scn26-21_Data_Format_Changes_Impacting_SWPC_Products.pdf

**Reporter:** Brian KB1OPD

### Score/Path Desync in update_path_only

Documented in post-v2.3.3 memory. `update_path_only()` ran every 2s via `refresh_paths()` but only updated the Path column. Score was set once in `analyze_decode()` when the decode first arrived and never recalculated.

Fix: Added full score recalculation (SNR base + geo_bonus derivation from path status) at the end of `update_path_only()`. Same logic as `analyze_decode()` but without the expensive competition/perspective analysis.

### Misleading "CALL NOW" on PathStatus.UNKNOWN

Both `HeuristicPredictor.get_strategy()` and the ML predictor's `get_strategy()` defaulted `recommended_action = "call_now"` and had no `elif` for `PathStatus.UNKNOWN`. The competition check at `effective_size == 0` added "No competition" — conflating "no data" with "verified empty."

Fix: Added `PathStatus.UNKNOWN → action = "call_blind"` with reason "No target area data". Competition check skipped for `call_blind`. Display: "▶ CALL (no intel)" in muted blue (#88bbff) in insights_panel.py StrategyWidget.

---

## v2.4.5 — Manual Target Entry & Consistency Fixes (April 2026)

### Manual Target Entry

**Motivation:** Operators often know about a station before decoding them — from DX cluster spots, friend tips, DXpedition announcements. Previously, QSOP could only target stations already in the decode table.

**Architecture:** The `+` button in both `TargetDashboard` and `InsightsPanel` toggles a `QLineEdit` overlay. On Enter, emits `manual_target_requested(str)` signal → `MainWindow._on_manual_target()` → `_lookup_grid()` cascade → `_set_new_target()`.

**Grid lookup cascade (`_lookup_grid`):**
1. `analyzer.receiver_cache[call]` — if station uploads to PSK Reporter, their grid is in `spot['grid']` (the receiver's grid). This is the highest-quality source for active stations.
2. `analyzer.call_grid_map[call]` — grids from locally decoded stations.
3. `model._data` — decode table rows for current session.
4. `_PREFIX_GRIDS` class dict — ~180 DXCC prefix → approximate grid centroid. Covers all major entities. Longest-prefix-first matching handles special prefixes (KH6, KL7, KP4) before single-letter (K, G, F).

**`_is_manual_target` flag:** Set True by `_on_manual_target()`, cleared by row click, UDP status, sync, or when the target appears in the decode table (checked in `refresh_target_perspective`). Flows through `_set_new_target` → `local_intel.set_target(manual=True)` → `insights_panel.set_target(manual=True)` for ⚠ indicator display.

**Grid retry:** `refresh_target_perspective` (3-second timer) retries `_lookup_grid` when `current_target_grid` is empty. As MQTT spots arrive and populate `receiver_cache`, the grid auto-resolves and IONIS prediction activates.

**Design decision:** No online API (QRZ, HamQTH) in the initial implementation. Local sources resolve most active stations. Online lookup can be added later as an optional step in the cascade.

### Short Grid Gate Bug

**Root cause analysis:** Two code paths compute "near target" — the status bar cleanup loop in the MQTT thread (`analyzer.py` line ~1304) and the path computation in `analyze_decode`/`update_path_only`. The status bar used `len(rep_grid) >= 2` while path used `len(r_grid) >= 4` as a gate, with the field-level check `r_grid[:2] == target_major` nested INSIDE the `len >= 4` block. Reporters with 2–3 character grids passed the status bar check but silently failed the path check.

**Fix:** Added `elif len(r_grid) >= 2` block after the `len >= 4` block in both `analyze_decode` and `update_path_only`. Uses lower `geo_bonus` (10 vs 15/25) to reflect reduced geographic precision.

### IONIS Band Derivation Without UDP

**Root cause:** `_update_ionis_prediction` combined grid and band availability into a single `if` with the message "Awaiting target grid…". The `_current_band` attribute is only set from `handle_status_update` (UDP). Without UDP (e.g., Mac testing with MQTT only), `_current_band` was never set. The `analyzer.current_dial_freq` was available from MQTT but not consulted.

**Fix:** Split grid and band checks with distinct messages. Added fallback: `band = self._freq_to_band(self.analyzer.current_dial_freq)` when `_current_band` is not set.

### Band Edge Recommendation Clamping

**Three issues identified:**
1. `score_map[0:200] = 0` (line 444) was overwritten to 10 by the local_busy loop at line 455 (`range(self.bandwidth)` included edges).
2. Soft penalty ramp (200–300, 2700–2800) didn't prevent recommendations when the rest of the band was heavily congested and edge gaps scored highest.
3. Click-to-set clamped to 200–2800, below the auto-paste scripts' 300–3000 floor.

**Fix:** Local_busy loop restricted to `range(200, 2800)`. Both recommendation paths clamped to `max(300, min(2700, best_offset))`. Click-to-set clamped to 300–2700. All QSOP-produced frequencies now fall within auto-paste script accepted range.

---
