# QSO Predictor Session Notes
**Date:** January 27, 2025  
**Version:** 2.1.0 (in progress)  
**Session:** Phase 2 Path Intelligence Implementation

---

## Feature Implemented: Phase 2 Path Intelligence

### Overview

Phase 2 adds on-demand analysis to answer: **"Why are nearby stations getting through when I'm not?"**

When the user clicks the "🔍 Analyze" button, the system:
1. Performs reverse PSK Reporter lookups for each near-me station
2. Analyzes directional patterns (beaming detection)
3. Compares SNR to peer stations
4. Checks frequency density
5. Generates human-readable insights

### Analysis Logic

```
For each near-me station:
┌─────────────────────────────────────────────────────────┐
│  1. BEAMING CHECK                                        │
│     Reverse lookup: who hears them?                      │
│     Calculate bearings to all receivers                  │
│     If >70% in 135-degree arc → likely beaming           │
│                                                          │
│     Result: "📡 Beaming toward [EU/AS/etc]"              │
│     (confidence %)                                       │
└─────────────────────────────────────────────────────────┘
                          │
                    Not beaming?
                          ▼
┌─────────────────────────────────────────────────────────┐
│  2. POWER CHECK                                          │
│     Compare their SNR to other near-me stations' SNR     │
│     If +6dB or more above peers:                         │
│        → likely running more power or better antenna     │
│                                                          │
│     Result: "⚡ +8dB above others nearby"                │
│     Actionability: LOW                                   │
└─────────────────────────────────────────────────────────┘
                          │
                    Not a big gun?
                          ▼
┌─────────────────────────────────────────────────────────┐
│  3. NO OBVIOUS ADVANTAGE                                 │
│     "No beaming pattern detected, SNR within normal"     │
│                                                          │
│     Frequency check: Is their freq relatively clear?     │
│       → If density 1-3: "Try piggybacking on X Hz"      │
│       → If crowded: Don't suggest                        │
└─────────────────────────────────────────────────────────┘
```

### Files Created/Modified

| File | Changes |
|------|---------|
| **psk_reporter_api.py** | NEW - PSK Reporter reverse lookup API client with caching |
| **analyzer.py** | Added `analyze_near_me_station()` method, typing imports |
| **insights_panel.py** | Enhanced `NearMeWidget` with Analyze button, analysis labels |
| **main_v2.py** | Added `_on_path_analyze_requested()` handler, signal connection |

### New Classes/Functions

**psk_reporter_api.py:**
- `PSKReporterAPI` - Cached/rate-limited API client
- `reverse_lookup(call)` - Find who hears a station
- `calculate_bearing(from_grid, to_grid)` - Grid-to-bearing calculation
- `classify_beam_pattern(bearings)` - Detect directional transmission
- `grid_to_latlon(grid)` - Maidenhead to lat/lon conversion

**analyzer.py:**
- `analyze_near_me_station()` - Phase 2 analysis orchestrator
- `_bearing_to_region_simple()` - Bearing to region name
- `_get_freq_density()` - Signal density at frequency

**insights_panel.py (NearMeWidget):**
- `_on_analyze_clicked()` - Handle button click
- `update_analysis_results()` - Display analysis results
- Analysis labels under each station

### UI Changes

**Before (Phase 1 only):**
```
┌─ Path Intelligence ─────────────────────────────────────┐
│  At target: 2 from your area heard                      │
│  ✓ Target decoding these directly                       │
│                                                          │
│  📍 W2XYZ (FN31) → -12 dB @ 1847 Hz                     │
│  🗺️ K2ABC (FN30) → -18 dB @ 1523 Hz                     │
│                                                          │
│  💡 Others getting through — you can too!               │
└──────────────────────────────────────────────────────────┘
```

**After (Phase 2 added):**
```
┌─ Path Intelligence ─────────────────────────────────────┐
│  At target: 2 from your area heard                      │
│  ✓ Target decoding these directly                       │
│                                                          │
│  📍 W2XYZ (FN31) → -12 dB @ 1847 Hz                     │
│     📡 Beaming toward EU (78% of spots)                 │
│                                                          │
│  🗺️ K2ABC (FN30) → -18 dB @ 1523 Hz                     │
│     No beaming pattern detected, SNR within normal      │
│     💡 Their freq has light traffic — try 1523 Hz?      │
│                                                          │
│  💡 Others getting through — you can too!               │
│                                                          │
│  [🔍 Analyze]                                            │
└──────────────────────────────────────────────────────────┘
```

### Rate Limiting & Caching

- **Cache TTL:** 5 minutes
- **Min refresh interval:** 60 seconds per station
- **Max requests:** 10 per minute
- **API calls per analyze:** 1-3 (one per near-me station, max 3)

### Key Design Decisions

1. **Only suggest what they can control** - No "run more power" suggestions
2. **Be honest about limitations** - "No beaming pattern detected" doesn't mean no advantage
3. **Piggybacking only if freq is clear** - Check density before suggesting
4. **Analysis is on-demand** - Button click triggers, not automatic

### Signal Flow

```
User clicks [🔍 Analyze]
    ↓
NearMeWidget._on_analyze_clicked()
    ↓
NearMeWidget.analyze_requested signal (list of stations)
    ↓
InsightsPanel._on_path_analyze_requested()
    ↓
InsightsPanel.path_analyze_requested signal
    ↓
main_v2._on_path_analyze_requested()
    ↓
analyzer.analyze_near_me_station() × N
    ↓
InsightsPanel.update_path_analysis_results()
    ↓
NearMeWidget.update_analysis_results()
    ↓
Analysis labels shown under each station
```

### Testing Needed

- [ ] Test with actual PSK Reporter data
- [ ] Verify beaming detection accuracy
- [ ] Test rate limiting (hammer the button)
- [ ] Test cache behavior
- [ ] Test error handling (network failure, etc.)
- [ ] Test on Windows and Mac

### Future Enhancements (Phase 3)

- Hunt Mode integration - analyze path for each hunt target
- Background periodic analysis
- More sophisticated beaming detection
- Timing analysis (which sequence are they using?)

---

**73 de WU2C**
