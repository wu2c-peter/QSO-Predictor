# QSO Predictor v2.2.0 — "Clarity Update" Session Notes

**Date:** February 10, 2026  
**Files Modified:** analyzer.py, main_v2.py, insights_panel.py, band_map_widget.py  
**Theme:** Data provenance, labeling, tactical awareness

---

## Changes Implemented

### 1. Panel Rename ✅
- Dock title was already "Insights" (done in prior work)
- Updated remaining comment in main_v2.py header referencing "Local Intelligence panel"
- Internal system name "Local Intelligence" preserved (it IS local intelligence — the panel just shows more than that)

### 2. Language Audit: "hear" → "report" ✅

| Location | Before | After |
|----------|--------|-------|
| Status bar (analyzer.py:1238-1245) | "1 hear WU2C" | "1 reporting WU2C (0 near target)" |
| Variable name (analyzer.py:1174) | `hearing_me_count` | `reporting_me_count` |
| Comments (analyzer.py:42,44,46) | "what each station hears" | "spots reported by each receiver" |
| Comments (analyzer.py:1145,1168) | "who hears me" | "who reports me" |
| Comments (main_v2.py:553) | "don't hear you" | "haven't spotted you" |
| Near-me labels (insights_panel.py:345,348) | "heard" | "reported" |
| **NOT changed:** | "Heard by Target" / "Heard in Region" (path status — these ARE hearing) |

### 3. Source Badges ✅ (already done in prior session)
- PileupStatusWidget: "📡 Your Decodes"
- Path Intelligence: "🌐 PSK Reporter"
- BehaviorWidget: "📋 Log History" / "👁 Live Session" (dynamic)
- PredictionWidget: "📊 Combined Analysis" (already had source_badge)

### 4. Band Map Section Labels + Legend Relocation ✅

**New layout:**
```
┌──────────────────────────────────────────────────────────────────┐
│ [— Target  ··· TX  — Rec]          "Target's environment (spot data)"
│ [■1-3 ■4-5 ■6+ ■Grid ■Field ■Global]
│ PERSPECTIVE BARS (40%)                                           
│ [frequency scale]                                                
├──────────────────────────────────────────────────────────────────┤
│ [── proven  ···· gap-based]         "Offset score (calculated)"  
│ SCORE GRAPH (15%)                                                
├──────────────────────────────────────────────────────────────────┤
│ [■>0dB ■>-10 ■Weak]                "Your decodes"                
│ LOCAL DECODE BARS (45%)                                          
│ [frequency scale]                                                
└──────────────────────────────────────────────────────────────────┘
```

**Implementation:**
- Split `_draw_legend()` into dispatcher calling 4 sub-methods
- `_draw_section_labels()` — right-aligned gray text for each section
- `_draw_perspective_legend()` — overlay lines + tier colors (top section)
- `_draw_score_legend()` — solid vs dotted line samples (score section)
- `_draw_local_legend()` — decode SNR color legend (bottom section, MOVED from top)

### 5. Status Bar: Near-Target Count ✅

**New format:** `Tracking 550 stations | 1 reporting WU2C (0 near target)`

**Implementation:**
- Added `current_target_grid` attribute to analyzer (initialized to "")
- Main window sets it on target change, clears on target clear
- `_periodic_maintenance()` filters `my_reception_cache` by target field proximity
- Only shows parenthetical when a target is selected

### 6. Pileup Contrast Alert ✅ (already done in prior session)
- `contrast_label` in PileupStatusWidget shows warning when local vs target mismatch
- `update_competition()` method receives competition data
- Added `_last_caller_count` tracking for toast integration

### 7. Tooltip Pass ✅

**Decode table column headers** (via `headerData` ToolTipRole):
- All 9 columns have tooltips
- Prob % and Path explicitly note their PSK Reporter data sources

**Target View dashboard** (via `setToolTip` on labels):
- All fields: UTC, dB, DT, Freq, Message, Grid, Prob %, Path, Competition, Rec
- Path and Competition tooltips emphasize PSK Reporter source + "you may not hear these"

**Insights panel sections** (via `setToolTip` on QGroupBox):
- PileupStatusWidget, NearMeWidget, BehaviorWidget: already had tooltips (prior session)
- PredictionWidget: NEW — "Overall probability combining signal, path, competition, behavior"
- StrategyWidget: NEW — "Advisory only — you make the call"

### 8. Tactical Observation Toasts ✅ NEW

**Widget:** `TacticalToast` class (QFrame, 28px height, between info bar and table)

**Features:**
- Auto-dismiss after 8 seconds
- Rate-limited: min 15 seconds between toasts
- Queue system: if rate-limited, next toast replaces queue and shows after dismiss
- Dismissable via ✕ button
- Three style presets: warning (orange), success (green), info (cyan)
- State tracking with reset on target change/clear

**Triggers:**
| Trigger | Detection | Style |
|---------|-----------|-------|
| Hidden pileup | local_callers ≤ 1 AND target competition ≥ 3 | warning |
| Competition growing | count increased by 3+ | warning |
| Competition dropping | count decreased by 3+ | success |
| Heard by Target | path changed to "Heard by Target" | success |
| Path opened | path changed to "Heard in Region" | success |
| Path lost | path was connected, now "Not Heard"/"No Path" | warning |
| First spot near target | near_target_count went from 0 to >0 | success |

**Integration points:**
- `refresh_target_perspective()`: checks competition + path changes every ~3s
- `clear_target()`: resets toast state
- Target row click: resets toast state for new target

---

## Files Modified Summary

| File | Lines | Changes |
|------|-------|---------|
| analyzer.py | 1284 | Status bar language, near-target count, current_target_grid attr |
| main_v2.py | 2474 | TacticalToast class, tooltips (headers+dashboard), toast integration |
| insights_panel.py | 1262 | _last_caller_count tracking, PredictionWidget+StrategyWidget tooltips |
| band_map_widget.py | 1032 | Legend split into 4 methods, section labels, score legend |

---

## Testing Checklist

- [ ] Status bar shows "reporting" not "hear"
- [ ] Status bar shows "(N near target)" only when target selected
- [ ] "(N near target)" updates as target changes
- [ ] Band map shows "Target's environment (spot data)" right-aligned in top section
- [ ] Band map shows "Offset score (calculated)" right-aligned in score section
- [ ] Band map shows "Your decodes" right-aligned in bottom section
- [ ] Local decode legend (>0dB, >-10, Weak) appears at top of bottom section (not top)
- [ ] Score section shows solid/dotted legend
- [ ] Perspective tier legend stays in top section
- [ ] Hover column headers shows tooltips (especially Prob % and Path)
- [ ] Hover dashboard Path/Competition labels shows tooltips
- [ ] Hover Insights section titles shows tooltips
- [ ] Toast appears on hidden pileup detection (may need to simulate)
- [ ] Toast appears when "Heard by Target" first detected
- [ ] Toast auto-dismisses after ~8 seconds
- [ ] Toast ✕ button dismisses immediately
- [ ] No toast spam (15s minimum between toasts)
- [ ] Toast resets on target change/clear
- [ ] No visual regressions on Windows
- [ ] No CPU increase from toast (no new timers until toast shown)

---

## ⚠️ Before Pushing

1. Test on Windows in actual radio shack environment if possible
2. Test band map at various window sizes to ensure section labels don't overlap legends
3. Verify toast doesn't interfere with table scroll behavior
4. Consider: should toast be configurable (on/off in settings)? → Maybe v2.2.1

---

**73 de WU2C + Claude**
