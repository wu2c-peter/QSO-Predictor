# QSO Predictor v2.3.3 Release Notes

**Released:** March 2026  
**Type:** Bug Fix + UI Improvements  

---

## Bug Fixes

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

Previously, the "never received any data" case was not detected — the health check only warned when data flow *stopped*, not when it never started. The bind failure case (from the v2.3.2 multicast crash fix) also now surfaces a specific message.

Warnings clear automatically when data resumes.

### "Prob %" Renamed to "Score"

The decode table column previously labelled "Prob %" and the insights panel "Success Prediction" implied a statistical probability. The values are actually a heuristic opportunity score (0–99) combining signal strength, path status, and competition. Renamed to:

| Before | After |
|--------|-------|
| Decode table: "Prob %" with values like "78%" | "Score" with values like "78" |
| Insights panel: "Success Prediction" | "Opportunity Score" |

Tooltips updated to explain the scoring. Sort by Score descending to rank stations by opportunity.

### Auto-Paste Script Improvements

**Generate Std Msgs step added:** The AutoHotkey (Windows) and Hammerspoon (Mac) auto-paste scripts now click the "Generate Std Msgs" button after pasting a callsign into the DX Call field. Without this step, the TX message sequence (Tx1–Tx5) was still populated for the previous station. Both WSJT-X and JTDX require this step.

**New tooltips:** Clickable elements in the dashboard (target callsign, recommended frequency) now show tooltips explaining that with the auto-paste scripts installed, clicking sends the value directly to WSJT-X/JTDX.

---

## What Changed

| Item | Before | After |
|------|--------|-------|
| Decode table column | "Prob %" with "78%" | "Score" with "78" |
| Insights panel title | "Success Prediction" | "Opportunity Score" |
| Auto-paste scripts | Callsign paste only | Callsign + Generate Std Msgs + Enable TX |
| Clickable element tooltips | "Click to copy" | Mentions auto-paste script integration |

---

## Upgrade Notes

Drop-in replacement for v2.3.2. No config file changes required.

If you use the auto-paste scripts (AutoHotkey or Hammerspoon), update your script from the User Guide to get the Generate Std Msgs step. You'll also need to find the coordinates for the Gen Std Msgs button using Window Spy (AHK) or `hs.mouse.absolutePosition()` (Hammerspoon).

---

## Contributors

- **Peter WU2C** — development

---

**73 de WU2C**
