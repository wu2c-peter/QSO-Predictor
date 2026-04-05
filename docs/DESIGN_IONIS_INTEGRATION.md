# IONIS Integration Design — QSO Predictor

**Date:** April 4, 2026  
**Status:** Design — pre-implementation  
**Author:** Peter WU2C + Claude  
**IONIS Version:** V22-gamma (production checkpoint)  
**Target QSOP Version:** v2.4.0

---

## 1. Overview

Embed KI7MT's IONIS propagation prediction model directly into QSO Predictor.
IONIS predicts HF path viability using a 205K-parameter neural network trained
on 20 million WSPR observations. The model takes two grid squares, band,
time, SFI, and Kp — all inputs QSOP already has — and outputs predicted SNR.

**Key properties:**
- Pure numpy inference (no PyTorch dependency)
- 806 KB model checkpoint (safetensors format)
- ~1ms inference time per prediction
- Zero network dependency — runs entirely offline
- GPLv3 license — compatible with QSOP's GPLv3

**New dependency:** `safetensors` (pip package, ~500 KB, pure Python reader
available via `safetensors.numpy`). Already a dependency of the IONIS project.

---

## 2. User-Facing Features

### 2.1 Propagation Outlook (Insights Panel)

New section in the Insights Panel, below the existing Strategy widget:

```
┌─ Propagation Outlook (IONIS) ──────────────────┐
│                                                  │
│  20m FN42 → JN48:  OPEN  (SNR ≈ -12 dB)        │
│                                                  │
│  12-Hour Forecast:                               │
│  ▐██████████▌░░░░░░░░░░░░▐                      │
│  14  16  18  20  22  00  02  UTC                 │
│  ←── now                                         │
│                                                  │
│  Conditions: SFI 142, Kp 2                       │
│  ⚠ Forecast assumes current conditions hold      │
└──────────────────────────────────────────────────┘
```

**Behavior:**
- Updates when target changes (new grid → new path → new prediction)
- Updates when band changes (UDP status message)
- Updates when solar data refreshes (SFI/Kp change)
- The 12-hour strip computes predictions for each hour from now → now+12
- Color gradient: green (OPEN, strong) → yellow (marginal) → red (CLOSED)
- Strip implemented as a simple painted QWidget (like the existing band map bars)

**When no target selected:** Section shows "Select a target to see propagation forecast"
**When IONIS disabled:** Section does not render at all

### 2.2 IONIS vs Reality (Target Dashboard / Insights Panel)

A compact indicator comparing what IONIS predicts vs what PSK Reporter shows:

| IONIS says | PSK Reporter shows | Display |
|---|---|---|
| Open | Spots confirm (Tier 1-3 data for this path corridor) | "✓ Confirmed" (green) |
| Open | No spots on this path | "⚠ Predicted open, unconfirmed" (yellow) |
| Marginal | Spots seen | "★ Better than expected" (cyan) |
| Closed | No spots | "— Closed" (gray) |
| Closed | Spots seen! | "★ Unexpected opening!" (bright cyan) |

**"Path corridor"** = spots from our field (first 2 chars of grid) to target's
field. This averages out individual station variation — Peter's key insight
that local station performance is a variable.

**Placement:** Inside the PropagationWidget, below the forecast strip.

### 2.3 Settings Toggle

New checkbox in Settings dialog:
- "Enable IONIS propagation predictions"
- Default: enabled
- Config: `[IONIS] enabled = true`
- Independent of Purist Mode (IONIS is purely local computation)

---

## 3. Architecture

### 3.1 New Files

```
qso-predictor/
├── ionis/                          # NEW directory
│   ├── __init__.py                 # Package init
│   ├── engine.py                   # Numpy inference engine (~250 lines)
│   ├── features.py                 # Feature builder + geo helpers (~150 lines)
│   ├── physics_override.py         # Post-inference clamp (~80 lines)
│   └── data/                       # Bundled model data
│       ├── ionis_v22_gamma.safetensors  # 806 KB checkpoint
│       └── config_v22.json              # Architecture + norm constants
```

### 3.2 Module Responsibilities

**`ionis/engine.py`** — The core inference engine
- `IonisEngine` class
  - `__init__(config_path, checkpoint_path)` — loads weights into numpy arrays
  - `predict(tx_grid, rx_grid, band, sfi, kp, hour_utc, month, day_of_year)` → dict
    - Returns: `{sigma, snr_db, ft8_open, overridden, tx_solar, rx_solar}`
  - `predict_range(tx_grid, rx_grid, band, sfi, kp, hours, month, day_of_year)` → list[dict]
    - Batch prediction for forecast strip (12 hours)
  - `is_available()` → bool (True if model loaded successfully)
- Pure numpy forward pass (no PyTorch)
- Loads weights once at startup, holds in memory (~800 KB)

**`ionis/features.py`** — Feature engineering
- `build_features()` — grid/freq/time/solar → 17-element feature vector
- `grid4_to_latlon()` — Maidenhead to lat/lon
- `haversine_km()` — great circle distance
- `azimuth_deg()` — bearing calculation
- `vertex_lat_deg()` — great circle vertex
- `solar_elevation_deg()` — sun position

All ported from KI7MT's model.py — pure math, already numpy.

**`ionis/physics_override.py`** — Deterministic clamp
- `apply_override(sigma, freq_mhz, tx_solar, rx_solar, distance_km)` → (sigma, bool)
- Rules A/B (high-band night closure) and Rule C (low-band day absorption)
- Already pure numpy in IONIS source — copy with attribution

### 3.3 Modified Files

**`insights_panel.py`**
- New `PropagationWidget(QGroupBox)` class (~200 lines)
  - Contains: current prediction label, 12-hour forecast strip, vs-reality indicator
  - `ForecastStrip` inner widget for the painted color bar
  - `update_display(prediction_data)` / `clear()` following existing pattern

**`main_v2.py`**
- Import and instantiate `IonisEngine` at startup (if enabled)
- Call `predict()` on target change, band change, solar data refresh
- Call `predict_range()` for the 12-hour strip
- Wire results to `PropagationWidget.update_display()`
- Compare IONIS prediction with existing PSK Reporter path data for vs-reality

**`settings_dialog.py`**
- New "Propagation" tab or section with IONIS enable/disable checkbox

**`config_manager.py`**
- Add `[IONIS] enabled = true` default

**`requirements.txt`**
- Add `safetensors>=0.4.0`

**`qso_predictor.spec`** (PyInstaller)
- Add `ionis/data/` to data files for bundling

---

## 4. Data Flow

```
Target selected (or band/solar change)
    │
    ├─► IonisEngine.predict(my_grid, target_grid, band, sfi, kp, hour, month, doy)
    │       │
    │       ├─ build_features() → 17 floats
    │       ├─ numpy forward pass → raw sigma
    │       ├─ physics_override() → clamped sigma
    │       └─ denormalize (per-band mean/std) → snr_db, ft8_open
    │
    ├─► IonisEngine.predict_range(..., hours=[now..now+12])
    │       │
    │       └─ 12 predictions → forecast strip data
    │
    ├─► Compare ft8_open vs PSK Reporter path data
    │       │
    │       └─ vs_reality = {confirmed, unconfirmed, better_than_expected, closed, unexpected}
    │
    └─► PropagationWidget.update_display({
            current: {snr_db, ft8_open, overridden},
            forecast: [{hour, snr_db, ft8_open}, ...],
            vs_reality: str,
            conditions: {sfi, kp}
        })
```

---

## 5. Denormalization and Thresholds

The model outputs in **sigma units** (z-scores of per-band WSPR SNR distribution).

**Per-band normalization constants** (from config_v22.json):

| Band | WSPR Mean (dB) | WSPR Std (dB) |
|------|----------------|----------------|
| 160m | -18.04 | 6.9 |
| 80m  | -17.90 | 6.9 |
| 60m  | -17.60 | 7.1 |
| 40m  | -17.34 | 6.6 |
| 30m  | -18.07 | 6.5 |
| 20m  | -17.53 | 6.7 |
| 17m  | -18.35 | 7.0 |
| 15m  | -18.32 | 6.6 |
| 12m  | -18.76 | 6.6 |
| 10m  | -17.86 | 6.5 |

**Conversion:** `snr_db = sigma * std + mean`

**FT8 decode threshold:** -21.0 dB (from IONIS MODE_THRESHOLDS_DB)

**Display thresholds for forecast strip:**
- Strong open:  snr_db >= -10 dB  → bright green
- Open:         snr_db >= -21 dB  → green
- Marginal:     snr_db >= -25 dB  → yellow
- Closed:       snr_db <  -25 dB  → red/gray

---

## 6. FT8 Frequency Mapping

IONIS was trained on WSPR dial frequencies. For QSOP we use FT8 dial
frequencies. The difference is negligible in log-frequency space:

| Band | WSPR Hz | FT8 Hz | log10 ratio |
|------|---------|--------|-------------|
| 20m | 14,097,100 | 14,074,000 | 0.00007 |
| 15m | 21,094,600 | 21,074,000 | 0.00004 |

Using FT8 frequencies directly is fine — the feature is log10(freq)/8.0
and the difference vanishes.

**Band detection from UDP frequency:**
```python
BAND_RANGES_HZ = {
    "160m": (1_800_000, 2_000_000),
    "80m":  (3_500_000, 4_000_000),
    "60m":  (5_250_000, 5_450_000),
    "40m":  (7_000_000, 7_300_000),
    "30m":  (10_100_000, 10_150_000),
    "20m":  (14_000_000, 14_350_000),
    "17m":  (18_068_000, 18_168_000),
    "15m":  (21_000_000, 21_450_000),
    "12m":  (24_890_000, 24_990_000),
    "10m":  (28_000_000, 29_700_000),
}
```

---

## 7. Performance

- Model loading: ~50ms (read 806KB file, parse into numpy arrays)
- Single prediction: ~1ms (17 features → matmul chain → scalar)
- 12-hour forecast: ~12ms (12 predictions)
- Memory: ~1 MB (weights + working arrays)

No threading needed — this is fast enough for main thread.

---

## 8. vs-Reality Comparison Logic

```python
def compute_vs_reality(ionis_open: bool, ionis_snr_db: float,
                       psk_has_spots: bool) -> str:
    """
    Compare IONIS prediction against PSK Reporter observations.
    
    psk_has_spots: True if we have Tier 1-3 spots from our field
                   to the target's field on this band within last 15 min.
    """
    MARGINAL_THRESHOLD = -25.0  # dB
    
    if ionis_open and psk_has_spots:
        return "confirmed"          # ✓ Confirmed
    elif ionis_open and not psk_has_spots:
        return "unconfirmed"        # ⚠ Predicted open, unconfirmed
    elif not ionis_open and ionis_snr_db >= MARGINAL_THRESHOLD and psk_has_spots:
        return "better_than_expected"  # ★ Better than expected
    elif not ionis_open and not psk_has_spots:
        return "closed"             # — Closed
    elif not ionis_open and psk_has_spots:
        return "unexpected_opening" # ★ Unexpected opening!
    return "unknown"
```

**PSK spot check:** Reuse existing MQTT spot data. For vs-reality, check:
"Do we have spots where sender is in our field (FN) and receiver is in 
target's field, on current band, within last 15 minutes?"

This is a subset of data we already collect and filter.

---

## 9. Settings & Configuration

### Config file (qso_predictor.ini)

```ini
[IONIS]
enabled = true
```

Future options (not in MVP):
- `model_version = v22_gamma` (for swapping checkpoints)
- `forecast_hours = 12`
- `show_forecast_strip = true`

### Settings Dialog

New section or tab "Propagation":
- Checkbox: "Enable IONIS propagation predictions"
- Label: "IONIS V22-gamma by KI7MT — physics-informed HF propagation model"
- Small text: "Uses current SFI and Kp to predict band openings. No internet required."

---

## 10. Attribution

IONIS is developed by Greg Beam (KI7MT). GPLv3 license.
- GitHub: github.com/IONIS-AI
- Reference: ionis-training, ionis-validate repos

**In QSOP:**
- Settings dialog: credit line with callsign and link
- About dialog: add to "Powered by" section
- README: document IONIS integration with link
- Source files: header comment with attribution

---

## 11. Implementation Order

### Phase 1: Engine (standalone, testable)
1. Create `ionis/` package with engine.py, features.py, physics_override.py
2. Bundle checkpoint + config in ionis/data/
3. Write standalone test script (verify against known IONIS outputs)
4. Add `safetensors` to requirements.txt

### Phase 2: Insights Panel Widget
5. Create PropagationWidget class in insights_panel.py
6. Implement ForecastStrip painted widget
7. Wire to InsightsPanel layout (below StrategyWidget)

### Phase 3: Integration
8. Instantiate IonisEngine in main_v2.py
9. Trigger predictions on target change / band change / solar refresh
10. Implement vs-reality comparison using existing MQTT spot data
11. Add IONIS enable/disable to settings dialog + config

### Phase 4: Build & Package
12. Update qso_predictor.spec for PyInstaller bundling
13. Update build.bat / GitHub Actions
14. Test Windows .exe with bundled model
15. Update README and release notes

---

## 12. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| safetensors adds too much to .exe size | Low | Low | Pure Python reader is ~50KB |
| Model predictions are wrong for edge cases | Medium | Low | Physics override catches worst cases; vs-reality shows disagreement |
| KI7MT objects to embedding | Low | High | Reach out first; GPL explicitly allows this; attribution is respectful |
| Users confused by IONIS predictions | Medium | Medium | Clear labeling, tooltip explanations, disable option |
| v22-gamma becomes outdated | Low | Low | Architecture is stable; checkpoint is hot-swappable |

---

## 13. Open Questions

1. **Reach out to KI7MT before or after implementation?**
   Recommendation: before. Courtesy, and he may have opinions on best practices.

2. **Should we show raw sigma or only dB?**
   Recommendation: dB only for users. Sigma is meaningless to operators.

3. **FT4 support?**
   FT4 threshold would be similar to FT8 (-21 dB). Same model, just a 
   different threshold comparison. Easy to add.

4. **Multi-band forecast?**
   "Check all bands" button that runs predictions for 160m-10m and shows
   which bands are open/opening. Future enhancement, not MVP.

---

*73 de WU2C*
