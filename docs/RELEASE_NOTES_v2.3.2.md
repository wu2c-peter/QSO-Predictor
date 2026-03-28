# QSO Predictor v2.3.2 Release Notes

**Released:** March 2026  
**Type:** Simplification + Bug Fix  

---

## What's New

### Simplified Fox/Hound Detection — Layer 2 Inference Removed

v2.3.0 introduced a three-layer F/H detection system: manual, UDP, and "Layer 2" (automatic inference from decode frequency patterns). v2.3.2 removes Layer 2.

**Why:** On standard FT8 frequencies (14.074, etc.), nobody runs Fox — so Layer 2 could only produce false positives there. On non-standard frequencies (14.090, etc.), the frequency itself is a strong enough indicator — the counting logic was redundant. Layer 2 was either wrong or unnecessary.

**F/H detection is now:**

| Method | How it works | When it triggers |
|--------|-------------|-----------------|
| **Manual combo box** | Off / F/H / SuperF/H in toolbar | Always available — you set it |
| **WSJT-X UDP** | Field 18 (special_mode=7) | Automatic when WSJT-X detects Hound mode |
| **SuperFox auto-detect** | "verified" / "$VERIFY$" in decoded messages | Automatic — upgrades to SuperF/H |

> **JTDX note:** JTDX does not populate the UDP special mode field (always 0). For JTDX users, manual selection via the combo box is the reliable detection path.

The disambiguation dialog remains — it fires when UDP detects Hound mode (since WSJT-X can't distinguish old-style Hound from SuperHound). It no longer fires from decode inference.

---

## Bug Fixes

### Multicast UDP Crash at Startup

**Symptom:** `OSError: [WinError 10065] A socket operation was attempted to an unreachable host` — app crashed before reaching the settings screen.

**Root cause:** When QSOP was configured for multicast UDP (e.g. `239.0.0.2`) but the system couldn't join the multicast group — typically due to VPN software, missing network adapter, or firewall configuration — the `IP_ADD_MEMBERSHIP` call failed and the exception was re-raised, killing the app.

**Fix:** Three layers of resilience:
1. Multicast join failure is now caught separately — socket stays bound, app starts, user can fix settings in UI
2. If bind itself fails, attempts unicast fallback on `0.0.0.0`
3. If everything fails, app still starts with no UDP data — user can access Settings → Network

*Thanks to Bob K7TM for the bug report.*

### Target Change State Inconsistency

**Symptom:** After changing target, dashboard, band map perspective, or Local Intelligence panel could show stale data from the previous target.

**Root cause:** Four separate code paths handled target changes (table click, WSJT-X/JTDX double-click, Fetch Target button, Clear Target), each with its own inline state management. They were inconsistent — some paths missed updating analyzer grid, activity state, F/H state, tactical toast, perspective display, or competition forwarding.

**Fix:** Unified all target changes into a single `_set_new_target()` method. All four code paths now call this one method, ensuring every state update happens regardless of how the target was changed. The near-target status bar count also now resets correctly on target change (previously only reset on QSO completion).

---

## Improvements

### UDP Silence Detection

The status bar now provides context-specific warnings when no UDP data is being received:

| Condition | Message |
|-----------|---------|
| Bind/multicast failed | `⚠ UDP bind failed — check Settings → Network` |
| No data after 30s | `⚠ No UDP data received — check WSJT-X/JTDX is running and UDP settings match` |
| Data was flowing, then stopped | `⚠ No data from WSJT-X/JTDX for Xs — is it running?` |

Previously, the "never received any data" case was not detected — the health check only warned when data flow *stopped*, not when it never started. The bind failure case (from the multicast crash fix) also now surfaces a specific message.

Warnings clear automatically when data resumes.

---

## What Was Removed

| Removed | Reason | Replacement |
|---------|--------|-------------|
| Layer 2 F/H inference | False positive on standard frequencies, redundant on non-standard | Manual combo box + UDP detection |
| `_fh_target_tx_below_1000` counter | Part of Layer 2 | — |
| `_fh_target_tx_above_1000` counter | Part of Layer 2 | — |
| `'inferred'` branch in disambiguation dialog | No longer triggered | Dialog only fires from UDP |

---

## Upgrade Notes

Drop-in replacement for v2.3.1. No config file changes required.

If you had Layer 2 trigger F/H detection in a previous version, you'll now need to set the combo box manually — but in practice this is clearer and more reliable than the automatic inference was.

---

## Contributors

- **Bob K7TM** — multicast crash report
- **Peter WU2C** — development

---

**73 de WU2C**
