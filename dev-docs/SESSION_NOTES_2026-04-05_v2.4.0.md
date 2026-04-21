# QSO Predictor Session Notes
**Date:** April 5, 2026  
**Version:** 2.4.0  
**Session:** IONIS Propagation Prediction Integration

---

## Summary

Embedded KI7MT's IONIS V22-gamma propagation model directly into QSO Predictor.
Pure numpy reimplementation of a 205K-parameter neural network that predicts HF
path viability. No PyTorch dependency, no network requirement — runs entirely
in-process.

---

## Research Phase

### IONIS Discovery
- Found IONIS-AI GitHub organization (Greg Beam, KI7MT)
- 10 repos, all GPLv3, zero external contributors, zero GitHub Discussions
- Greg is a WSJT Development Group member — created JTSDK (build system for WSJT-X)
- IONIS trained on 20M WSPR observations, 205K parameters, 806 KB checkpoint
- Published production model: V22-gamma with PhysicsOverrideLayer

### External Presence
- Searched Reddit, QRZ, eHam, Groups.io — zero community discussion of IONIS
- Only public-facing presence: ionis-ai.com, ham-stats.com (both Greg's own sites)
- Decided to build first, post courtesy message after shipping

### Integration Path Decision
Three options evaluated:
1. **ionis-mcp** (MCP server) — adds network dependency, rejected
2. **ionis-validate** (pip package) — requires PyTorch (~150-800 MB), rejected
3. **Pure numpy reimplementation** — zero new heavy dependencies, chosen

Key insight: the model is only 205K parameters with standard operations
(Linear, Mish, Softplus, Sigmoid). The forward pass is ~40 lines of numpy.

---

## Phase 1: Engine Module (Standalone)

### New Files Created
```
ionis/
├── __init__.py              (31 lines)  — clean public API
├── engine.py               (377 lines)  — IonisEngine class, numpy forward pass
├── features.py             (291 lines)  — grid conversion, solar, 17-feature builder
├── physics_override.py      (98 lines)  — deterministic post-inference clamp
└── data/
    ├── config_v22.json     (2.5 KB)     — architecture + normalization constants
    └── ionis_v22_gamma.safetensors (806 KB) — trained model weights
```

### Architecture (IonisGate V22-gamma)
```
Input (17 features) → split:
  ├─ features[0:15] → Trunk: Linear(15→512)+Mish → Linear(512→256)+Mish
  │   ├─ base_head: Linear(256→128)+Mish → Linear(128→1)
  │   ├─ sun_scaler: Linear(256→64)+Mish → Linear(64→1) → gate(0.5-2.0)
  │   └─ storm_scaler: Linear(256→64)+Mish → Linear(64→1) → gate(0.5-2.0)
  ├─ features[15] (SFI) → sun_sidecar: MonotonicMLP(1→8→1)
  └─ features[16] (Kp)  → storm_sidecar: MonotonicMLP(1→8→1)

Output = base_snr + sun_gate * sun_sidecar(SFI) + storm_gate * storm_sidecar(Kp)
```

### 17 Input Features (V22 with solar depression)
All derived from inputs QSOP already has: two grids, band, UTC time, SFI, Kp.

| # | Feature | Source |
|---|---------|--------|
| 0 | distance | Haversine from grids |
| 1 | freq_log | log10(freq_hz) / 8.0 |
| 2-3 | hour_sin/cos | UTC time |
| 4-5 | az_sin/cos | Azimuth between grids |
| 6 | lat_diff | Latitude difference |
| 7 | midpoint_lat | Path midpoint |
| 8-9 | season_sin/cos | Month |
| 10 | vertex_lat | Great circle vertex (storm exposure) |
| 11-12 | tx/rx_solar_dep | Solar elevation at each endpoint |
| 13-14 | freq_x_tx/rx_dark | Band × darkness cross-products |
| 15 | sfi | Solar flux / 300 |
| 16 | kp_penalty | 1 - Kp/9 |

### Performance
- Single prediction: **126 µs** (0.13 ms)
- 12-hour forecast: **1.5 ms**
- Memory: ~1 MB (weights + working arrays)
- Main-thread safe — no threading needed

### Physics Override Layer
Post-inference clamp for physically impossible predictions:
- Rule A: High bands (≥21 MHz) + both endpoints dark → CLOSED
- Rule B: High bands + TX past astronomical twilight → CLOSED  
- Rule C: Low bands (≤7.5 MHz) + daytime D-layer absorption → CLOSED
- Clamp value: -2.0σ ≈ -31 dB (below all decode floors)

### New Dependency
- `safetensors>=0.4.0` — loads model weights via numpy backend, ~500 KB

---

## Phase 2-3: UI Integration

### PropagationWidget (insights_panel.py)
New QGroupBox subclass: "Path Prediction (IONIS)"
- Main prediction line: `20m FN42→FF87 OPEN (-17 dB)`
- Solar context: `TX ☽ -41°  RX ☽ -71°  7,475 km`
- ForecastStrip: 12-hour color-coded bar (custom QPainter widget)
  - Tick marks every hour, labels every 3 hours
  - Green (strong open) → yellow (marginal) → red (closed)
- vs-Reality: compares IONIS prediction against PSK Reporter observations
- Conditions: `SFI 128 · Kp 3`

### vs-Reality Comparison
| IONIS | PSK Reporter | Display |
|-------|-------------|---------|
| Open | Spots confirm | ✓ Confirmed by spots |
| Open | No spots | ⚠ Predicted open, no spots |
| Marginal | Spots seen | ★ Better than expected |
| Closed | No spots | — Closed |
| Closed | Spots seen | ★ Unexpected opening! |

Uses existing Tier 1-3 spot data from MQTT — no new queries needed.
Averages out individual station variation (Peter's insight).

### Three Trigger Points (main_v2.py)
1. **Target change** — `_set_new_target()` step 10
2. **Band change** — after `self._current_band = new_band`
3. **Solar refresh** — in `update_solar_ui()` when SFI/Kp change

### Settings Toggle
- New "Features" tab in Settings dialog
- Checkbox: "Enable IONIS propagation predictions"
- Credit: "Propagation model by Greg Beam, KI7MT — ionis-ai.com · GPLv3"
- Config: `[IONIS] enabled = true`

---

## Bugs Found and Fixed

### 1. Grid Backfill (critical)
**Problem:** When target is set from UDP status handler, grid is often empty
(decode table hasn't populated yet). `_update_ionis_prediction()` silently
returned because `self.current_target_grid` was empty. Nothing re-triggered it.

**Root cause:** `current_target_grid` was only set in `_set_new_target()`.
The 3-second perspective refresh found the grid in the decode table but
never copied it back to `current_target_grid`.

**Fix:** Added grid backfill in `refresh_target_perspective()`:
```python
if not self.current_target_grid and row.get('grid'):
    self.current_target_grid = row['grid']
    self.analyzer.current_target_grid = row['grid']
```
Plus `_ionis_shown` flag to re-attempt prediction on next refresh cycle.

**Note:** This bug affects more than just IONIS — the analyzer's perspective
queries also use `current_target_grid`. The backfill benefits the whole app.

### 2. get_target_perspective() Missing Arguments
**Problem:** Called `self.analyzer.get_target_perspective()` with no arguments
in `_compute_ionis_vs_reality()`. Method requires `target_call` and `target_grid`.
Would have crashed at runtime.

**Fix:** Pass `self.current_target_call` and `self.current_target_grid`.

**Lesson:** Verify method signatures before calling — don't assume from
variable names. This is exactly what the Code Quality Checklist warns about.

### 3. np.float64 Leak
**Problem:** `distance_km` in the prediction result dict was `np.float64`
instead of plain Python `float`. Would display as `np.float64(5980.59...)`
in debug output.

**Fix:** Cast all result dict values to `float()` in `engine.py`.

---

## Files Modified

| File | Changes |
|------|---------|
| `ionis/__init__.py` | **NEW** — Package init, public API |
| `ionis/engine.py` | **NEW** — IonisEngine, numpy forward pass |
| `ionis/features.py` | **NEW** — Feature builder, geo/solar helpers |
| `ionis/physics_override.py` | **NEW** — Deterministic physics clamp |
| `ionis/data/config_v22.json` | **NEW** — Model config (from IONIS) |
| `ionis/data/ionis_v22_gamma.safetensors` | **NEW** — Model weights (from IONIS) |
| `main_v2.py` | IONIS import, init, prediction methods, 3 triggers, grid backfill, about dialog |
| `insights_panel.py` | PropagationWidget, ForecastStrip, QPainter imports |
| `settings_dialog.py` | Features tab with IONIS toggle + credit |
| `config_manager.py` | IONIS default config section |
| `requirements.txt` | safetensors>=0.4.0 |
| `qso_predictor.spec` | ionis/data bundling + hidden imports |
| `docs/DESIGN_IONIS_INTEGRATION.md` | **NEW** — Full design document |

---

## Design Decisions

### Why numpy, not PyTorch
PyTorch adds 150-800 MB to the install. The model is 205K parameters with
standard operations. The forward pass is ~40 lines of numpy. Zero new heavy
dependencies. Users don't even know it's there.

### Why V22-gamma, not V27
V22-gamma is the published production checkpoint. V27 is marked "alpha" —
fine-tunes V22 with physics-informed loss for one edge case. Same architecture.
Can hot-swap later if V27 is promoted.

### Why IONIS is independent of Purist Mode
IONIS runs entirely locally — pure math on a bundled model. No internet
required. A purist who rejects PSK Reporter data might still appreciate
physics-based propagation predictions.

### Why vs-Reality uses PSK Reporter tiers, not local SNR
Peter's insight: "Our own local station performance is a variable." Comparing
IONIS predicted SNR to what we locally decode is apples to oranges. Instead,
compare IONIS path prediction against aggregate PSK Reporter observations
for the same path corridor. This averages out individual station variation.

---

## KI7MT Outreach Plan

- Build first, post courtesy message after shipping
- GitHub Discussion on IONIS-AI org (first external engagement)
- Tone: peer-to-peer, show we read the code, don't ask permission (GPL)
- Draft message prepared (long and short versions)

---

## Session Statistics

- **Duration:** ~5 hours
- **New code:** 797 lines (ionis package)
- **Modified code:** ~150 lines across 6 files
- **Bugs found:** 3 (1 would have crashed at runtime)
- **Model parameters loaded:** 205,621
- **Inference verified against:** 6 test paths, all physically correct

---

**73 de WU2C**
