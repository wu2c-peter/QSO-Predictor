# QSO Predictor v2.2.0 — "Clarity Update" Specification

**Date:** February 10, 2026  
**Goal:** Make every piece of data honest about where it comes from and what it means.  
**Theme:** Usability, labeling, data provenance, tactical awareness.

---

## Problem Statement

QSO Predictor shows data from multiple sources (local decodes, PSK Reporter, log history, 
live session tracking, algorithmic calculations) across three panels. Users can't easily 
tell which data comes from where, leading to confusion:

- "Local Intelligence" panel contains PSK Reporter data (not local)
- Status bar says "1 hear WU2C" — actually global PSK Reporter, not near target
- Pileup Status shows local callers (0), while Competition shows target-end pileup (4)
  — this contrast IS the key insight but users must discover it themselves
- Band map legend is at top, far from the local decode bars it describes
- "hear" vs "reporting" distinction matters for accuracy

---

## Changes Summary

| # | Change | Files | Effort |
|---|--------|-------|--------|
| 1 | Rename "Local Intelligence" → "Insights" | insights_panel.py, main_v2.py, local_intel_integration.py, README | Low |
| 2 | Language audit: "hear" → "report" where appropriate | analyzer.py, main_v2.py, insights_panel.py, band_map_widget.py | Low |
| 3 | Source badges on each Insights section | insights_panel.py | Low |
| 4 | Band map section labels + legend relocation | band_map_widget.py | Medium |
| 5 | Status bar: add "(N near target)" count | analyzer.py, main_v2.py | Medium |
| 6 | Pileup contrast alert in Pileup Status | insights_panel.py, main_v2.py, local_intel_integration.py | Medium |
| 7 | Tooltip pass across all panels | main_v2.py, insights_panel.py, band_map_widget.py | Medium |
| 8 | Tactical observation toasts | main_v2.py (new notification widget) | High |

---

## 1. Rename "Local Intelligence" → "Insights"

### What changes
- `insights_panel.py`: Dock title, class docstrings, comments
- `main_v2.py`: Any references to "Local Intelligence" in dock creation, View menu
- `local_intel_integration.py`: Variable names if needed, comments
- `README.md`: Documentation references

### What stays
- Internal class name `InsightsPanel` — already correct
- `local_intel_integration.py` filename — describes the integration layer, not the panel
- `local_intel/` directory — these ARE local intelligence modules

---

## 2. Language Audit: "hear" → "report"

### Principle
- **"hear/decode"** = appropriate for local reception (your radio decodes signals)
- **"report/spot"** = appropriate for PSK Reporter data (stations report spots)
- **"heard by"** in path context = keep (target literally decoded your signal)

### Changes

**Status bar (analyzer.py line 1230):**
```
BEFORE: "Tracking 550 stations | 1 hear WU2C"
AFTER:  "Tracking 550 stations | 1 reporting WU2C (0 near target)"
```

**Variable name (analyzer.py line 1173):**
- `hearing_me_count` → `reporting_me_count`

**Comments in analyzer.py:**
- Line 42: "what each station hears" → "spots reported by each receiver"
- Line 44: "what stations in that grid hear" → "spots reported from that grid"
- Line 46: "who hears that station" → "who reports that station"
- Line 1144: "who hears me" → "who reports me"
- Line 1167: "who hears me" → "who reports me"

**main_v2.py color comments:**
- Line 553: "reporters exist but don't hear you" → "reporters exist but haven't spotted you"

**insights_panel.py:**
- Line 343: "1 from your area heard" → "1 from your area reported"
- Line 346: "N from your area heard" → "N from your area reported"

### DO NOT change
- "Heard by Target" path status — accurately means target decoded you
- "Heard in Region" path status — station near target decoded you
- Any reference to local decoding (your radio hearing signals)
- `heard_by` dict keys in analyzer.py — internal data structure

---

## 3. Source Badges on Insights Sections

### Design
Small gray text below each QGroupBox title, indicating data source.

| Section | Badge Text | Color |
|---------|-----------|-------|
| Pileup Status | "📡 Your decodes" | #888888 |
| Path Intelligence | "🌐 PSK Reporter" | #888888 (already has source_label) |
| Behavior | "📋 Log history" OR "👁 Live session" (dynamic) | #888888 |
| Success Prediction | "📊 Combined analysis" | #888888 |
| Recommendation | (no badge) | — |

---

## 4. Band Map Section Labels + Legend Relocation

### New layout
```
┌─────────────────────────────────────────────────────────────────────┐
│ "Target's environment (spot data)"    [■1-3 ■4-5 ■6+ ■Grid ■Field ■Global]
│ [— Target  ··· TX  — Rec]                                          
│ TARGET PERSPECTIVE (40%)                                            
│ [frequency scale]                                                   
├─────────────────────────────────────────────────────────────────────┤
│ "Offset score (calculated)"           [solid=proven  dotted=gap-based]
│ SCORE GRAPH (15%)                                                   
├─────────────────────────────────────────────────────────────────────┤
│ "Your decodes"                        [■>0dB ■>-10 ■Weak]          
│ LOCAL DECODES (45%)                                                 
│ [frequency scale]                                                   
└─────────────────────────────────────────────────────────────────────┘
```

### Implementation
- Split `_draw_legend()` into `_draw_perspective_legend()` and `_draw_local_legend()`
- Add section label drawing in paintEvent
- Score legend drawn inside `_draw_score_graph()`

---

## 5. Status Bar: Add "(N near target)" Count

### New format
```
Tracking 550 stations | 1 reporting WU2C (0 near target)
```

### Data flow
- `reporting_me_count` = `len(self.my_reception_cache)` (global, exists)
- `near_target_count` = NEW: filter `my_reception_cache` by target grid proximity
- When no target selected: just show "1 reporting WU2C" (no parenthetical)

---

## 6. Pileup Contrast Alert

### Design
Add contrast warning inside PileupStatusWidget when discrepancy detected:

```
⚠️ At target: High (4)
   Hidden pileup — you can't hear your competition
```

- Only shows when target competition > 0 AND local callers ≤ 1
- Orange warning color (#FFA500)

### New data flow
`analyzer.analyze_decode()` → `row['competition']` → `main_v2.py` → 
`local_intel_integration` → `InsightsPanel.pileup_widget.update_competition()`

---

## 7. Tooltip Pass

### Decode Table Column Headers (via headerData ToolTipRole)
- Prob %: "Estimated success probability. Based on signal strength and PSK Reporter path data."
- Path: "Propagation status. Based on PSK Reporter spots and local decode analysis."

### Target View Dashboard (via setToolTip on each widget)
- Competition: "Signal density near target FROM THEIR PERSPECTIVE (PSK Reporter). You may not hear these stations."
- Path: "Has your signal been detected near this station? Sources: PSK Reporter + local decodes."
- Rec: "Algorithm-recommended TX frequency based on target perspective analysis."

### Insights Panel (via setToolTip on QGroupBox titles)
- Pileup Status: "Callers visible in YOUR local decodes. The target may see more — check Competition in Target View."
- Path Intelligence: "Are stations from your area getting through? Data from PSK Reporter."
- Behavior: "How this station picks callers. Based on log history and/or live observation."
- Success Prediction: "Overall probability combining signal, path, competition, and behavior."
- Recommendation: "Tactical suggestion based on all available intelligence. Advisory only."

---

## 8. Tactical Observation Toasts

### Design
Thin notification bar below toolbar, above decode table. Auto-dismiss 8s. Rate-limited 15s.

### Triggers
| Trigger | Message | Priority |
|---------|---------|----------|
| Hidden pileup | "⚠️ Hidden pileup: 0 callers locally, {N} at target's end" | High |
| First spot near target | "📡 You've been spotted near {target}!" | High |
| Pileup thinning | "📉 Competition dropping: was {old}, now {new}" | Medium |
| Pileup growing | "📈 Competition increasing: now {N} at target" | Medium |
| Path opened | "🟢 Path to {target}'s region opened!" | High |
| Path lost | "🔴 Path to {target}'s region lost" | Medium |

### Implementation
- New class: `TacticalToast` (QLabel with timer, styling)
- State tracking: previous competition count, path status
- Rate limiter + queue

---

## Implementation Order

1→2→3→4→5→6→7→8

---

## Testing Checklist

- [ ] Panel title shows "Insights" not "Local Intelligence"
- [ ] Status bar shows "reporting" not "hear"
- [ ] Status bar shows "(N near target)" when target selected
- [ ] Each Insights section has appropriate source badge
- [ ] Band map section labels in correct positions
- [ ] Local decode legend at bottom of band map
- [ ] Score section shows proven/gap-based legend
- [ ] Pileup contrast alert appears when local=0, target>0
- [ ] All column headers show tooltips
- [ ] All dashboard fields show tooltips
- [ ] All Insights sections show tooltips
- [ ] Toasts appear on trigger conditions
- [ ] Toast auto-dismisses and rate-limits correctly
- [ ] No visual regressions Windows/macOS
- [ ] No CPU increase (no new high-frequency timers)

---

**73 de WU2C + Claude**
