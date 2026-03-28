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
