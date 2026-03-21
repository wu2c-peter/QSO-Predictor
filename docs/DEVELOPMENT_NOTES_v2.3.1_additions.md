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
