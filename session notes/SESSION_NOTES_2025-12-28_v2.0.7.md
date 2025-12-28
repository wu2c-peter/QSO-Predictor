# QSO Predictor Session Notes
**Date:** December 28, 2025  
**Version:** 2.0.7 released, 2.0.8 planned  
**Session:** UI freeze fix, UDP flooding discovery, Local Intelligence debugging

---

## Summary

Major debugging session that fixed critical UI responsiveness issues and diagnosed why Local Intelligence bootstrap was failing with large log files.

---

## v2.0.7 Released — UI Responsiveness Fixes

### Problem 1: UI Freeze on Station Click (45+ seconds)

**Root cause:** `session_tracker.py` called `lookup_station()` synchronously on every target click, scanning entire ALL.TXT files (168MB).

**Fix:** Replace blocking lookup with cache-only check.

**Files changed:**
- `local_intel/session_tracker.py` — removed `lookup_station()` call
- `local_intel/behavior_predictor.py` — added `has_cached_history()` method

```python
# session_tracker.py (BEFORE)
self._behavior_predictor.lookup_station(callsign)  # Blocks 45s

# AFTER
if self._behavior_predictor.has_cached_history(callsign):
    print(f"[SessionTracker] {callsign}: found in behavior cache")
else:
    print(f"[SessionTracker] {callsign}: not in cache, will observe live")
```

### Problem 2: UDP Status Flooding

**Symptom:** After Phase 1 fix, console spam appeared — hundreds of `[TX] Calling...` per second, rapid table refresh, yellow TX line flickering.

**Root cause:** JTDX sends UDP status messages many times per second on localhost. The 45-second blocking lookup was accidentally throttling the entire UI. With instant cache lookup, the flooding became visible.

**Fix:** Throttle `handle_status_update()` to max 2Hz.

```python
def handle_status_update(self, status):
    now = time.time()
    if hasattr(self, '_last_status_time') and (now - self._last_status_time) < 0.5:
        return
    self._last_status_time = now
    # ... rest of function
```

### Problem 3: Table Re-sorting Jitter

**Symptom:** Decode table constantly re-sorting during updates.

**Root cause:** `setSortingEnabled(True)` makes Qt re-sort on every `dataChanged` signal.

**Fix:** 
1. Throttle `refresh_paths()` to max once per 2 seconds
2. Disable sorting during batch updates

```python
def refresh_paths(self):
    now = time.time()
    if hasattr(self, '_last_path_refresh') and (now - self._last_path_refresh) < 2.0:
        return
    self._last_path_refresh = now
    
    self.table_view.setSortingEnabled(False)
    self.model.update_data_in_place(self.analyzer.update_path_only)
    self.table_view.setSortingEnabled(True)
```

---

## Local Intelligence Bootstrap Investigation

### Symptom
```
[bootstrap] Found 4008 DX stations
[bootstrap] Complete: 0 stations in 48.7s
```

Parses 500,000 decodes, finds 4008 DX stations, but saves 0.

### Investigation Path

1. **Checked behavior_history.json** — only 1 station (W4SEJ)
2. **Checked for ML models** — none present
3. **Reviewed bootstrap code** — filtering requires `total_qsos >= 2`
4. **Suspected log format issue** — JTDX dated files have trailing markers (`^`, `*`)

### Key Discovery: Timeout, Not Corruption

**Test:** Renamed old log files, let JTDX create fresh ones, ran bootstrap:
```
[bootstrap] Parsed 702 decodes in 0.0s
[bootstrap] Found 63 DX stations
[bootstrap] Complete: 14 stations in 0.0s
[bootstrap] 4 stations have persona traits
```

**Conclusion:** With small files, bootstrap works perfectly. The issue is the timeout:

```python
# Line 1242 - stops at 70% of timeout
if time.time() - start_time > timeout_seconds * 0.7:
    break
```

With 500,000 decodes:
1. First pass finds 4008 DX stations ✅
2. Second pass (activity tracking) times out before finishing ❌
3. Third pass finds no QSOs recorded → all stations filtered out

### Log Format Fix (Still Valid)

JTDX dated files have trailing markers that weren't being stripped:

```python
# BEFORE
r'(.+?)\s*[*d]?\s*$'      # Only strips * or d

# AFTER  
r'(.+?)\s*[*d^.&]?\s*$'   # Strips ^ * . d &
```

**File:** `local_intel/log_parser.py` line 240

---

## Log Format Reference

| Source | Format | Trailing markers |
|--------|--------|------------------|
| WSJT-X / WSJT-X Improved | `YYMMDD_HHMMSS freq Rx FT8 ...` | None |
| JTDX standard | `YYYY-MM-DD HH:MM:SS freq Rx ...` | None |
| JTDX dated (YYYYMM_ALL.TXT) | `YYYYMMDD_HHMMSS snr dt freq ~ msg` | `^ * . d` |

JTDX trailing markers:
- `^` = decoded using a priori (AP) info
- `*` = low confidence decode
- Others = unknown

---

## Bayesian Architecture Discussion

### Current State
Counts stored in JSON are sufficient statistics:
```json
"IW4DV": {
  "observations": 4,
  "loudest_first_count": 4,
  "methodical_count": 0,
  "random_count": 0
}
```

### Key Insight
No need to re-scan history. Just increment counts on new observations:
```python
# New observation: IW4DV picks loudest
loudest_first_count += 1
observations += 1
# Belief updates automatically: P(loudest) = 4/5 = 80%
```

### UI for Mixed/Spread Behaviors
Proposed display for stations with no clear pattern:
```
Behavior: Unpredictable
[███ ▒▒▒ ░░] L:40% M:35% R:25%
Tip: No clear pattern — be patient
```

---

## v2.0.8 Planned Scope

| Item | Description |
|------|-------------|
| `^` marker fix | log_parser.py regex fix |
| Background scanner | QThread, no timeout |
| Incremental processing | Track file positions, only scan new data |
| Bayesian updates | Increment counts, no re-scan |
| Behavior distribution display | Show spread when mixed |

**v2.1.0** reserved for new features (Hunt Mode, Band filtering, etc.)

---

## Files Modified in v2.0.7

| File | Changes |
|------|---------|
| `main_v2.py` | Version header, throttle status updates (2Hz), throttle refresh_paths (2s), disable sort during updates |
| `local_intel/session_tracker.py` | Remove blocking lookup_station call |
| `local_intel/behavior_predictor.py` | Add has_cached_history() method |
| `README.md` | Version 2.0.7, changelog, contributors |

## Files Ready for v2.0.8

| File | Changes |
|------|---------|
| `local_intel/log_parser.py` | Fix `^` marker regex |

---

## Key Learnings

### Human Intuition vs AI Analysis (Again)
Peter correctly identified: "could be the size? timeout or too much memory?" — cutting through my incorrect "corruption" theory.

### Accidental Throttling
The 45-second blocking lookup was masking the UDP flooding problem. Fixing one bug revealed another.

### Sufficient Statistics
The counts in behavior_history.json ARE the accumulated evidence. Bayesian updates just increment them — no need to re-analyze history.

### Format vs Scale
WSJT-X Improved format is fine. The `^` marker fix is valid but the main bootstrap issue was timeout with large files, not format.

---

## Next Session Priorities

1. Implement BackgroundScanner (QThread)
2. File position tracking for incremental processing
3. Remove/adjust timeout for background processing
4. Behavior distribution UI in Insights panel
5. Test with large log files

---

**73 de WU2C**
