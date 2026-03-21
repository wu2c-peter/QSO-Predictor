# QSO Predictor v2.3.1 Release Notes

**Released:** March 2026  
**Type:** Enhancement + Bug Fix  

---

## What's New

### Fox/Hound Mode — SuperFox/SuperHound Support

v2.3.0 introduced Fox/Hound awareness with a manual checkbox. v2.3.1 extends this to properly handle the newer SuperFox/SuperHound protocol used by major DXpeditions (CY0S, TX5EU, etc.).

**New: Three-state F/H combo box** replaces the old checkbox:

| Setting | Use when |
|---------|----------|
| **F/H Off** | Normal FT8 operation |
| **F/H** | Old-style Fox/Hound (Fox transmits 300–900 Hz, Hounds above 1000 Hz) |
| **SuperF/H** | SuperFox/SuperHound (Fox transmits ~750–2262 Hz wide signal, Hounds anywhere 200 Hz+) |

**New: Disambiguation dialog** — when WSJT-X UDP or Layer 2 inference detects a possible Fox/Hound situation, QSOP now asks you to confirm which mode you're in rather than guessing. This prevents false activations.

**Behavior differences by mode:**

| | F/H | SuperF/H |
|-|-----|---------|
| Recommendation clamping | ≥1000 Hz | No clamping (Hounds can call anywhere ≥200 Hz) |
| Fox zone overlay | 0–1000 Hz dimmed | N/A |
| Click-to-set below 1000 Hz | Blocked | Allowed |

### Tightened Layer 2 Fox Detection

The automatic Fox pattern inference threshold has been tightened to reduce false positives:

- **Before:** 3+ observations of target decodes below 1000 Hz triggered F/H
- **After:** 4+ observations required, threshold tightened to 950 Hz

This fixes a false positive where a station operating near 973 Hz could incorrectly trigger Fox detection.

---

## Bug Fixes

- Fixed: Path field truncation — "Reported in Region (-11 dB)" was clipped; label shortened to "Rprtd in Region (-11 dB)"
- Fixed: Layer 2 inference false positive at ~973 Hz (A71-style stations near band bottom)

---

## Known Limitations

- **WSJT-X UDP does not distinguish SuperFox from old-style Fox** — both report `special_mode=7`. Manual selection via the combo box is required to differentiate. The disambiguation dialog makes this explicit.
- **JTDX does not populate UDP special_mode field** — always returns 0. Manual checkbox and Layer 2 inference are the only F/H detection paths for JTDX users.
- **WSJT-X locks TX frequency field in SuperHound mode** — this is intentional WSJT-X behaviour. AHK scripts that modify the TX freq field may not work in SuperHound mode.
- **WSJT-X decode window clicks suppressed in SuperFox mode** — WSJT-X does not send target-selection UDP packets when clicking in SuperHound mode. Set target manually in QSOP when operating SuperHound.

---

## SuperFox Operating Notes

If you're chasing a SuperFox DXpedition (e.g. CY0S):

1. Tune your rig to the DXpedition's published FT8 frequency (e.g. **14.091 MHz** — NOT 14.074 which is standard FT8)
2. Set RX audio offset to ~750 Hz
3. Set QSOP combo box to **SuperF/H**
4. Watch for the wide 1512 Hz signal block on the waterfall
5. When a decode appears showing the Fox callsign, double-click it in WSJT-X
6. Let WSJT-X auto-sequence — do not click Enable TX manually
7. The SuperHound label in WSJT-X turns **green** when the Fox signal is verified

---

## Upgrade Notes

Drop-in replacement for v2.3.0. No config file changes required. Settings are preserved.

---

## Contributors

- **Brian KB1OPD** — CY0S SuperFox live testing, A71 false positive report, AHK findings
- **Peter WU2C** — development

---

**73 de WU2C**
