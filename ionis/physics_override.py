# QSO Predictor — IONIS Physics Override Layer
# Copyright (C) 2025-2026 Peter Hirst (WU2C)
#
# Physics override ported from IONIS V22-gamma by Greg Beam (KI7MT)
# Original source: github.com/IONIS-AI/ionis-validate (GPLv3)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Deterministic physics override for IONIS predictions.

Applied after model inference to clamp physically impossible predictions.
The neural network occasionally predicts viable signals on paths that
physics says are dead. These rules catch those cases.

Rule A (both dark — F-layer collapse):
    freq >= 21 MHz AND tx_solar < -6° AND rx_solar < -6°
    → clamp to -2.0σ

Rule B (TX deep darkness — F-layer collapse):
    freq >= 21 MHz AND tx_solar < -18°
    → clamp to -2.0σ

Rule C (D-layer daytime absorption — two tiers):
    Severe (freq <= 4.0 MHz, 80m/160m):
        EITHER endpoint above horizon AND distance > 1500 km
        → clamp to -2.0σ
    Moderate (freq 4.0–7.5 MHz, 40m/60m):
        BOTH endpoints above horizon AND distance > 1500 km
        → clamp to -2.0σ

The -2.0σ clamp = approximately -31 dB, well below all decode floors.
"""

# ── Constants ────────────────────────────────────────────────────────────────

# Rules A/B: High-band night closure (F-layer collapse)
FREQ_THRESHOLD_MHZ = 21.0          # 15m and above
SOLAR_THRESHOLD_DEG = -6.0         # Civil twilight (Rule A: both endpoints)
DEEP_DARK_THRESHOLD_DEG = -18.0    # Astronomical twilight (Rule B: TX only)

# Rule C: Low-band day closure (D-layer absorption)
LOW_FREQ_THRESHOLD_MHZ = 7.5      # 40m and below
SEVERE_DLAYER_FREQ_MHZ = 4.0      # 80m/160m — severe 1/f² absorption
DLAYER_SOLAR_THRESHOLD_DEG = 0.0   # Endpoint above horizon
DLAYER_DISTANCE_KM = 1500.0       # Clears max NVIS range for 40m

CLAMP_SIGMA = -2.0                # ~-31 dB, below all decode floors


# ── Single Prediction ────────────────────────────────────────────────────────

def apply_override(sigma: float, freq_mhz: float,
                   tx_solar_deg: float, rx_solar_deg: float,
                   distance_km: float = None) -> tuple[float, bool]:
    """Apply physics override to a single prediction.

    Args:
        sigma: Model prediction in z-score (sigma) units
        freq_mhz: Operating frequency in MHz
        tx_solar_deg: TX solar elevation in degrees (negative = night)
        rx_solar_deg: RX solar elevation in degrees
        distance_km: Great-circle distance in km (needed for Rule C)

    Returns:
        (clamped_sigma, was_overridden) tuple
    """
    if sigma <= CLAMP_SIGMA:
        # Already below clamp — nothing to override
        return sigma, False

    # Rules A/B: High-band night closure (F-layer collapse)
    if freq_mhz >= FREQ_THRESHOLD_MHZ:
        both_dark = (tx_solar_deg < SOLAR_THRESHOLD_DEG and
                     rx_solar_deg < SOLAR_THRESHOLD_DEG)
        tx_deep_dark = (tx_solar_deg < DEEP_DARK_THRESHOLD_DEG)
        if both_dark or tx_deep_dark:
            return CLAMP_SIGMA, True

    # Rule C: Low-band day closure (D-layer absorption)
    if (distance_km is not None and
            freq_mhz <= LOW_FREQ_THRESHOLD_MHZ and
            distance_km > DLAYER_DISTANCE_KM):
        if freq_mhz <= SEVERE_DLAYER_FREQ_MHZ:
            # 80m/160m: EITHER endpoint in daylight kills signal
            if (tx_solar_deg > DLAYER_SOLAR_THRESHOLD_DEG or
                    rx_solar_deg > DLAYER_SOLAR_THRESHOLD_DEG):
                return CLAMP_SIGMA, True
        else:
            # 40m/60m: BOTH endpoints in daylight kills signal
            if (tx_solar_deg > DLAYER_SOLAR_THRESHOLD_DEG and
                    rx_solar_deg > DLAYER_SOLAR_THRESHOLD_DEG):
                return CLAMP_SIGMA, True

    return sigma, False
