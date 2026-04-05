# Release Notes — v2.4.0

**Date:** April 2026  
**Theme:** Path Prediction (IONIS Integration)

---

## New Feature: Path Prediction

QSO Predictor now includes embedded HF propagation predictions powered by the
[IONIS](https://ionis-ai.com) model by Greg Beam (KI7MT). IONIS is a 
physics-constrained neural network trained on 20 million WSPR observations that 
predicts whether an FT8 signal can travel a given path under current conditions.

### What You'll See

A new **"Path Prediction (IONIS)"** section appears at the bottom of the 
Insights Panel when you select a target. It shows:

- **Current prediction:** Band, path (your grid → target grid), status (OPEN / 
  MARGINAL / CLOSED), and predicted SNR in dB
- **12-hour forecast strip:** Color-coded bar showing how the path is expected 
  to change over the next 12 hours based on sun position. Green = open, 
  yellow = marginal, red = closed. Tick marks every hour, labels every 3 hours.
- **vs-Reality check:** Compares what IONIS predicts against what PSK Reporter 
  is actually observing. Flags unusual conditions:
  - "✓ Confirmed by spots" — prediction matches reality
  - "★ Unexpected opening!" — path is open when physics says it shouldn't be
  - "★ Better than expected" — conditions are beating the prediction
- **Current conditions:** SFI and Kp values used for the prediction

### How It Works

The prediction updates automatically when you:
- Select a new target station
- Change bands
- Solar conditions refresh (every 15 minutes)

No internet connection required — the model runs entirely locally using current
SFI and Kp values. The prediction is purely physics-based: sun position at both
endpoints, path geometry, solar flux, and geomagnetic activity.

### Enable / Disable

Go to **Edit → Settings → Features** to toggle IONIS predictions on or off.
Enabled by default. Independent of Purist Mode (IONIS is local computation, 
not internet-dependent).

### Technical Details

- IONIS V22-gamma model: 205,621 parameters, 806 KB checkpoint
- Pure numpy inference — no PyTorch dependency
- Inference time: ~0.1 ms per prediction, ~1.5 ms for 12-hour forecast
- New dependency: `safetensors>=0.4.0` (model weight loading)

### Credit

Propagation model by Greg Beam, KI7MT — [ionis-ai.com](https://ionis-ai.com)  
GPLv3 · [github.com/IONIS-AI](https://github.com/IONIS-AI)

---

## Bug Fix: Target Grid Backfill

When a target was set from a WSJT-X/JTDX status message (before decodes 
arrived), the target grid could remain empty. This affected perspective 
accuracy for PSK Reporter analysis. The grid is now backfilled from the decode 
table on the next refresh cycle.

---

## Files Changed

### New
- `ionis/` — Complete propagation prediction engine (4 Python files + model data)
- `docs/DESIGN_IONIS_INTEGRATION.md` — Design document

### Modified
- `main_v2.py` — IONIS integration, grid backfill fix
- `insights_panel.py` — PropagationWidget, ForecastStrip
- `settings_dialog.py` — Features tab
- `config_manager.py` — IONIS config defaults
- `requirements.txt` — safetensors dependency
- `qso_predictor.spec` — PyInstaller bundling

---

## Upgrade Notes

- Install new dependency: `pip install safetensors`
- No configuration changes required — IONIS is enabled by default
- Existing settings are preserved

---

**73 de WU2C**
