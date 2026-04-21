# QSO Predictor Session Notes
**Date:** March 20, 2026
**Version:** 2.3.1
**Session:** SuperFox disambiguation, release, live CY0S testing

---

## Context

v2.3.0 shipped with a single F/H checkbox. Two issues emerged from Brian KB1OPD's live testing against CY0S (Sable Island SuperFox DXpedition, March 19–31 2026):

1. **A71 false positive:** Station at 973 Hz triggered Layer 2 F/H inference (old threshold was 1000 Hz, 3 observations)
2. **SuperFox vs F/H conflation:** WSJT-X reports `special_mode=7` for both old-style Hound and SuperHound — no UDP distinction. A checkbox gives no way to indicate which mode is in use. 1000 Hz clamping hurts SuperHound users.

---

## Features Implemented in v2.3.1

### Three-State F/H Combo Box
- Replaces single checkbox
- Options: F/H Off / F/H / SuperF/H
- Persists between sessions
- Code location: `main_v2.py` → `_fh_combo`, `_on_fh_combo_changed()`

### Disambiguation Dialog
- Fires when UDP (special_mode=6/7) or Layer 2 inference triggers detection
- Asks user: "Which mode?" — F/H / SuperF/H / Ignore
- Prevents false auto-activation
- Code location: `main_v2.py` → `_show_fh_disambiguation_dialog()`

### Tightened Layer 2 Threshold
- Frequency threshold: 950 Hz (was 1000 Hz)
- Observation count: 4+ (was 3)
- Fixes A71 false positive (973 Hz, 3 observations)
- Code location: `main_v2.py` → `_check_layer2_fh_inference()`

### Clamping Scope Change
- 1000 Hz minimum clamping: F/H only
- SuperF/H: no clamping (Hounds may call anywhere ≥200 Hz per SuperFox spec)
- Code location: `main_v2.py` → `_apply_fh_clamping()`

### Path Field Truncation Fix
- "Reported in Region (-11 dB)" exceeded dashboard field width
- Fixed to "Rprtd in Region (-11 dB)"

---

## Key Technical Findings (Live CY0S Testing)

### SuperFox Protocol
- **Dial frequency:** Non-standard (14.091 MHz for 20m, not 14.074)
- **Lowest tone:** ~750 Hz, spanning 750–2262 Hz (1512 Hz wide)
- **"verified" string:** Appears in all SuperFox decoded messages — unique identifier
- **TX cycles:** Even only (Fox TX), odd (Fox RX / Hounds TX)
- **WSJT-X behaviour:** TX field locked, decode window clicks suppressed in SuperHound mode

### WSJT-X UDP
- `special_mode=7` for both old Hound AND SuperHound — no distinction
- TX freq field cannot be set by AHK scripts in SuperHound mode (WSJT-X locks it)
- No UDP packet sent when clicking decode window in SuperHound mode

### JTDX
- `special_mode` always 0 — Layer 2 and manual combo are only F/H paths
- Previously documented, confirmed again

---

## Live Testing — CY0S 2026

Peter WU2C worked CY0S on 20m FT8 SuperFox (14.091 MHz) on March 20, 2026 using WSJT-X 3.0.0 Improved PLUS. Confirmed:
- SuperHound mode working correctly
- QSO completed and logged automatically
- RR73 received, LoTW upload pending post-expedition

Key lesson learned: dial frequency must exactly match DXpedition's published frequency (not standard 14.074). RX audio offset ~750 Hz required for decode alignment.

---

## Files Modified

| File | Changes |
|------|---------|
| `main_v2.py` | Combo box, disambiguation dialog, tightened Layer 2, clamping scope |
| `RELEASE_NOTES_v2.3.1.md` | New file |
| `docs/DEVELOPMENT_NOTES.md` | SuperFox protocol notes, UDP limitations table update |

---

## Validation Status

| Path | Status |
|------|--------|
| Normal FT8 operation unaffected | ✅ Confirmed (WSJT-X) |
| UDP F/H detection fires | ✅ Confirmed (WSJT-X) |
| Combo box persists | ✅ Confirmed |
| SuperHound live QSO | ✅ CY0S worked by WU2C |
| Layer 2 tightened threshold | ⏳ Needs live Fox (Brian KB1OPD) |
| Old-style F/H live test | ⏳ Needs live old-style Fox |

---

## Backlog (unchanged from v2.3.0)

1. Target Status Row — show station states in dedicated dashboard row
2. Resilient UDP — prominent banner when JTDX/WSJT-X silent >60s
3. Bayesian QSO probability modeling — data collection phase first

---

## Future F/H Enhancements (identified this session)

- **"verified" auto-detection:** If target decode contains "verified", auto-select SuperF/H in disambiguation dialog or skip dialog entirely
- **750 Hz frequency detection:** If target always decodes at ~750 Hz, infer SuperFox
- **Even/odd cycle awareness:** Activity state parser may show spurious "Idle" on Fox's RX cycle — could filter this

---

## Session Notes

- Peter worked CY0S while figuring out SuperHound mode for the first time — perfect live validation
- Disambiguation dialog design came directly from the problem of WSJT-X not distinguishing SuperFox from old Hound in UDP
- SuperFox operating workflow now documented in DEVELOPMENT_NOTES for Wiki

---

**73 de WU2C**
