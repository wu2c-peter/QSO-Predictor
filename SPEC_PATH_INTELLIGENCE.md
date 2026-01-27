# Path Intelligence Feature Spec

**Version:** v2.1.0+  
**Status:** Planned  
**Author:** Peter WU2C / Claude  
**Date:** January 2025

---

## Overview

Extends QSO Predictor's path analysis to answer not just "Can they hear ME?" but also "Can they hear people LIKE me?" — and if so, why are they getting through when I'm not?

**Key differentiator:** No other tool synthesizes this data. Would take 5-10 minutes of manual PSK Reporter research per station.

---

## Current State

**Path Status (inbound to me):**

| Status | Meaning | Source |
|--------|---------|--------|
| CONNECTED | Target decoded ME | MQTT Tier 1 |
| Path Open | Stations near target decoded ME | MQTT Tier 2/3 |
| No Path | Reporters exist but don't hear ME | MQTT |
| No Nearby Reporters | No data from that region | MQTT |

This answers: **"Can they hear me?"**

---

## Phase 1: "Near Me" Detection

### Question
"Is anyone from my area getting through to the target?"

### Logic
```python
def find_near_me_stations(tier1_spots, my_grid):
    """
    Filter Tier 1/2/3 spots for senders near my grid.
    
    Near = same 2-char field (~1000km) or same 4-char grid (~100km)
    """
    near_me = []
    for spot in tier1_spots:
        if spot.sender_grid[:2] == my_grid[:2]:  # Same field
            distance = "field"
            if spot.sender_grid[:4] == my_grid[:4]:  # Same grid
                distance = "grid"
            near_me.append({
                'call': spot.sender_call,
                'grid': spot.sender_grid,
                'snr': spot.snr,
                'freq': spot.freq,
                'distance': distance
            })
    return near_me
```

### Data Source
- MQTT data we already have (Tier 1/2/3 spots)
- Filter by sender grid ≈ my_grid
- **No API calls needed** — passive/automatic

### UX

**In Path Status area:**
```
Path: No Path
      (but 2 stations near you ARE being heard)
```

**Or expanded:**
```
┌─ Path Status ───────────────────────────────────┐
│                                                  │
│  You → Target:       No Path                    │
│  Your Area → Target: ✓ 2 stations heard         │
│                                                  │
│  W2XYZ (FN31, 45km) → -12 dB @ 1847 Hz         │
│  K2ABC (FN30, 80km) → -19 dB @ 1523 Hz         │
│                                                  │
│  💡 Path exists from your area                  │
│                      [🔍 Analyze Why Not You?]  │
│                                                  │
└──────────────────────────────────────────────────┘
```

### Edge Cases

**Target not uploading to PSK Reporter:**
- Use Tier 2 (same grid) or Tier 3 (same field) as proxy
- Show: "Target not reporting — using 3 nearby stations as proxy"

**No stations near me getting through:**
```
│  You → Target:       No Path                    │
│  Your Area → Target: No stations heard          │
│                                                  │
│  💡 No path from your area currently            │
```

---

## Phase 2: "Why Not Me?" Analysis

### Question
"If people near me ARE getting through, what explains it? Is there anything I can try?"

### Trigger
**On-demand only** — user clicks `[🔍 Analyze]` button

### Data Required
1. **Reverse PSK Reporter lookup:** Who hears the "near me" station?
2. **Geographic analysis:** Are they heard directionally or omnidirectionally?
3. **Signal comparison:** How strong are they vs. typical signals?

### API Calls
```
GET https://retrieve.pskreporter.info/query?senderCallsign={call}&flowStartSeconds=-900&format=json
```
- ~1-3 calls per "near me" station
- Cache results for 5 minutes
- Rate limit: max 1 refresh per 60 seconds

### Analysis Algorithm

```python
def analyze_why_not_me(near_me_station, my_grid, target_grid):
    """Analyze why a nearby station is getting through."""
    
    # 1. Get reverse spots (who hears them?)
    spots = psk_reporter_query(near_me_station.call)
    
    # 2. Directional analysis
    bearings = []
    for spot in spots:
        bearing = calculate_bearing(near_me_station.grid, spot.receiver_grid)
        bearings.append(bearing)
    
    pattern = classify_pattern(bearings)  # "directional" or "omnidirectional"
    
    if pattern == "directional":
        primary_bearing = dominant_bearing(bearings)
        target_bearing = calculate_bearing(near_me_station.grid, target_grid)
        beaming_to_target = abs(primary_bearing - target_bearing) < 45
    
    # 3. Signal strength analysis
    avg_snr = mean([s.snr for s in spots])
    strong_signal = avg_snr > -10
    
    # 4. Generate insights
    insights = []
    
    if pattern == "directional" and beaming_to_target:
        insights.append({
            'icon': '📡',
            'text': 'Directional pattern — likely beaming toward target',
            'actionable': False
        })
    
    if pattern == "omnidirectional":
        insights.append({
            'icon': '📡', 
            'text': 'Omnidirectional pattern — similar setup to you',
            'actionable': True
        })
        insights.append({
            'icon': '💡',
            'text': f'Try their frequency ({near_me_station.freq} Hz)?',
            'actionable': True
        })
    
    if strong_signal:
        insights.append({
            'icon': '⚡',
            'text': 'Strong signal — possible power/antenna advantage',
            'actionable': False
        })
    
    return insights
```

### Pattern Classification

```python
def classify_pattern(bearings):
    """
    Determine if station is heard directionally or omnidirectionally.
    
    Directional: >70% of spots in 2 adjacent quadrants (90° arc)
    Omnidirectional: Spread across 3+ quadrants
    """
    quadrants = [0, 0, 0, 0]  # N, E, S, W
    
    for bearing in bearings:
        q = int(bearing / 90) % 4
        quadrants[q] += 1
    
    total = sum(quadrants)
    if total < 3:
        return "insufficient_data"
    
    # Check each pair of adjacent quadrants
    for i in range(4):
        adjacent = quadrants[i] + quadrants[(i+1) % 4]
        if adjacent / total > 0.7:
            return "directional"
    
    return "omnidirectional"
```

### UX

**Before clicking:**
```
│  W2XYZ (FN31, 45km) → -12 dB @ 1847 Hz         │
│  K2ABC (FN30, 80km) → -19 dB @ 1523 Hz         │
│                                                  │
│                      [🔍 Analyze Why Not You?]  │
```

**Loading:**
```
│  ⏳ Analyzing W2XYZ...                          │
│     Fetching PSK Reporter data                   │
```

**Results:**
```
│  W2XYZ (FN31, 45km) → -12 dB @ 1847 Hz         │
│    📡 Directional → beaming toward EU           │
│    ⚡ Strong signal (avg -8 dB in EU)           │
│    💡 Antenna advantage — not easily matched    │
│                                                  │
│  K2ABC (FN30, 80km) → -19 dB @ 1523 Hz         │
│    📡 Omnidirectional pattern                   │
│    ⚡ Modest signal (similar to yours)          │
│    💡 Try their frequency (1523 Hz)?            │
│    💡 Try their timing (:30 sequence)?          │
│                                                  │
│                      [🔄 Refresh]  2 min ago    │
```

### Actionable Insights

| Factor | Analysis | Suggestion |
|--------|----------|------------|
| **Directional** | Beaming toward target | "Antenna advantage — not easily matched" |
| **Omnidirectional** | Similar setup | "Try their frequency?" |
| **Strong SNR** | Power advantage | "High power station" |
| **Weak SNR** | Marginal but working | "If they got through, you can too" |
| **Timing** | Specific sequence | "They called at :30 — try same?" |
| **Frequency** | Clear spot | "Try {freq} Hz" |

---

## Phase 3: Hunt List Integration

### Question
"For each item in my hunt list, is there a path from my area?"

### UX

**In Hunt List dialog or Insights Panel:**
```
┌─ Hunt Path Status ──────────────────────────────┐
│                                                  │
│  JAPAN        🟢 2 near you heard   [Analyze]   │
│  NEW ZEALAND  🟡 1 near you heard   [Analyze]   │
│  VU4          ⚫ Unknown            [Check]     │
│  3Y0K         🔴 No path detected               │
│                                                  │
│               [🔍 Check All]        [🔄 Refresh]│
└──────────────────────────────────────────────────┘
```

### Status Icons

| Icon | Meaning | Data Source |
|------|---------|-------------|
| 🟢 | Multiple near-me stations heard | MQTT (passive) |
| 🟡 | One near-me station heard (marginal) | MQTT (passive) |
| 🔴 | Reporters active but no near-me heard | MQTT (passive) |
| ⚫ | Unknown (no reporters or not checked) | Needs API |

### Logic

```python
def check_hunt_path_status(hunt_item, my_grid, mqtt_spots):
    """
    Check path status for a hunt list item.
    Uses MQTT data (passive) — no API calls.
    """
    if hunt_item in DXCC_ENTITIES:
        prefixes = DXCC_ENTITIES[hunt_item]
    else:
        prefixes = [hunt_item]  # Specific call or prefix
    
    # Find spots where receiver matches hunt target
    target_spots = [s for s in mqtt_spots 
                    if any(s.receiver_call.startswith(p) for p in prefixes)]
    
    if not target_spots:
        return {'status': 'unknown', 'icon': '⚫'}
    
    # Filter for senders near me
    near_me = [s for s in target_spots 
               if s.sender_grid[:2] == my_grid[:2]]
    
    if len(near_me) >= 2:
        return {'status': 'open', 'icon': '🟢', 'count': len(near_me)}
    elif len(near_me) == 1:
        return {'status': 'marginal', 'icon': '🟡', 'count': 1}
    else:
        return {'status': 'no_path', 'icon': '🔴'}
```

### On-Demand Details

Clicking `[Analyze]` on a hunt item:
1. Expands to show the near-me stations
2. Runs Phase 2 analysis on each
3. Shows actionable insights

---

## Caching Strategy

```python
class PathIntelligenceCache:
    """
    Cache PSK Reporter API results to avoid rate limiting.
    """
    CACHE_TTL = 300          # 5 minutes
    MIN_REFRESH = 60         # 1 minute between refreshes
    
    def __init__(self):
        self._cache = {}      # key -> {data, timestamp}
        self._last_fetch = {} # key -> timestamp
    
    def get(self, key):
        if key in self._cache:
            age = time.time() - self._cache[key]['timestamp']
            if age < self.CACHE_TTL:
                return self._cache[key]['data'], age
        return None, None
    
    def set(self, key, data):
        self._cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
        self._last_fetch[key] = time.time()
    
    def can_refresh(self, key):
        if key not in self._last_fetch:
            return True
        return (time.time() - self._last_fetch[key]) > self.MIN_REFRESH
```

---

## API Budget

| Action | API Calls | Frequency |
|--------|-----------|-----------|
| Phase 1 (near-me count) | 0 | Passive/continuous |
| Phase 2 (single station) | 1 | On-demand |
| Phase 2 (3 stations) | 3 | On-demand |
| Phase 3 (check unknown) | 1-3 | On-demand |

**PSK Reporter limit:** ~100 requests/hour

**Worst case user behavior:** 
- Click analyze every minute = 60 calls/hour
- Well within limits

---

## Files to Modify

| File | Changes |
|------|---------|
| `analyzer.py` | `find_near_me_stations()` method |
| `psk_reporter_api.py` | New file — reverse lookup queries |
| `path_intelligence.py` | New file — analysis engine |
| `insights_panel.py` | New "Near Me" section, analyze button |
| `hunt_dialog.py` | Path status per hunt item |

---

## Success Metrics

1. User can see "2 stations near you getting through" in < 1 second (passive MQTT)
2. Full analysis completes in < 5 seconds (API fetch)
3. Insights are actionable ("try their frequency") not just data
4. No rate limiting issues with PSK Reporter

---

## Open Questions

1. **Where in Insights Panel?** New section? Replace something?
2. **Hunt dialog or separate panel?** For hunt path status
3. **How prominent?** Always visible or collapsed by default?
4. **Notification?** Alert when path opens to a hunt target?

---

**73 de WU2C**
