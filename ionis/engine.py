# QSO Predictor — IONIS Inference Engine
# Copyright (C) 2025-2026 Peter Hirst (WU2C)
#
# Pure numpy reimplementation of IonisGate V22-gamma by Greg Beam (KI7MT)
# Original PyTorch model: github.com/IONIS-AI/ionis-training (GPLv3)
#
# This implementation loads the original safetensors checkpoint and
# reproduces the forward pass using only numpy — no PyTorch dependency.
# The model architecture (IonisGate with MonotonicMLP sidecars) is
# documented in the IONIS project.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
IONIS propagation prediction engine for QSO Predictor.

Predicts HF path viability using a 205K-parameter neural network trained
on 20 million WSPR observations. Takes two grid squares, band, time,
SFI, and Kp — outputs predicted SNR and band open/closed status.

Usage:
    engine = IonisEngine()
    if engine.is_available():
        result = engine.predict('FN42', 'JN48', '20m', sfi=142, kp=2)
        print(f"SNR: {result['snr_db']:.1f} dB, FT8: {result['ft8_status']}")
"""

import json
import logging
import os
from datetime import datetime, timezone

import numpy as np

from .features import (
    build_features, grid4_to_latlon, haversine_km,
    solar_elevation_deg, freq_to_band,
    BAND_FREQ_HZ, BAND_NORM, MODE_THRESHOLDS_DB,
)
from .physics_override import apply_override

logger = logging.getLogger(__name__)


# ── Activation Functions ─────────────────────────────────────────────────────

def _mish(x: np.ndarray) -> np.ndarray:
    """Mish activation: x * tanh(softplus(x))"""
    sp = np.log1p(np.exp(np.clip(x, -20, 20)))
    return x * np.tanh(sp)


def _softplus(x: np.ndarray) -> np.ndarray:
    """Softplus activation: log(1 + exp(x))"""
    return np.log1p(np.exp(np.clip(x, -20, 20)))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Sigmoid activation: 1 / (1 + exp(-x))"""
    return 1.0 / (1.0 + np.exp(-np.clip(x, -20, 20)))


def _gate(x: np.ndarray) -> np.ndarray:
    """IonisGate gate function: range 0.5 to 2.0"""
    return 0.5 + 1.5 * _sigmoid(x)


# ── Model Loading ────────────────────────────────────────────────────────────

def _load_weights(checkpoint_path: str) -> dict[str, np.ndarray] | None:
    """Load model weights from safetensors file using numpy backend.

    Uses safetensors.numpy to avoid PyTorch dependency entirely.
    Returns None if loading fails.
    """
    try:
        from safetensors.numpy import load_file
        return load_file(checkpoint_path)
    except ImportError:
        logger.error(
            "safetensors package not installed. "
            "Install with: pip install safetensors"
        )
        return None
    except Exception as e:
        logger.error(f"Failed to load IONIS checkpoint: {e}")
        return None


# ── Forward Pass ─────────────────────────────────────────────────────────────

def _forward(features: np.ndarray, W: dict[str, np.ndarray]) -> float:
    """Pure numpy forward pass of IonisGate.

    Architecture:
        Trunk: features[0:15] → Linear(15,512) + Mish → Linear(512,256) + Mish
        Base head: 256 → 128 + Mish → 1
        Sun scaler: 256 → 64 + Mish → 1 → gate(0.5-2.0)
        Storm scaler: 256 → 64 + Mish → 1 → gate(0.5-2.0)
        Sun sidecar (monotonic): features[15] → 8 + Softplus → 1
        Storm sidecar (monotonic): features[16] → 8 + Softplus → 1

        Output = base_snr + sun_gate * sun_sidecar + storm_gate * storm_sidecar

    Args:
        features: 17-element feature vector (float32)
        W: dict of weight tensors loaded from safetensors

    Returns:
        Predicted SNR in sigma (z-score) units
    """
    x = np.asarray(features, dtype=np.float32)

    # Split inputs (V22: dnn_dim=15, sfi_idx=15, kp_penalty_idx=16)
    x_deep = x[:15]
    x_sfi = x[15:16]
    x_kp = x[16:17]

    # ── Trunk: geography/time → 256-dim representation ──
    h = x_deep @ W['trunk.0.weight'].T + W['trunk.0.bias']
    h = _mish(h)
    h = h @ W['trunk.2.weight'].T + W['trunk.2.bias']
    h = _mish(h)

    # ── Base head: trunk → SNR prediction ──
    base = h @ W['base_head.0.weight'].T + W['base_head.0.bias']
    base = _mish(base)
    base_snr = base @ W['base_head.2.weight'].T + W['base_head.2.bias']

    # ── Sun scaler: trunk → gate logit → gate(0.5-2.0) ──
    sun_h = h @ W['sun_scaler_head.0.weight'].T + W['sun_scaler_head.0.bias']
    sun_h = _mish(sun_h)
    sun_logit = (sun_h @ W['sun_scaler_head.2.weight'].T +
                 W['sun_scaler_head.2.bias'])
    sun_gate = _gate(sun_logit)

    # ── Storm scaler: trunk → gate logit → gate(0.5-2.0) ──
    storm_h = (h @ W['storm_scaler_head.0.weight'].T +
               W['storm_scaler_head.0.bias'])
    storm_h = _mish(storm_h)
    storm_logit = (storm_h @ W['storm_scaler_head.2.weight'].T +
                   W['storm_scaler_head.2.bias'])
    storm_gate = _gate(storm_logit)

    # ── Sun sidecar (monotonic MLP): abs(weights) enforces monotonicity ──
    sun_w1 = np.abs(W['sun_sidecar.fc1.weight'])
    sun_w2 = np.abs(W['sun_sidecar.fc2.weight'])
    sun_s = _softplus(x_sfi @ sun_w1.T + W['sun_sidecar.fc1.bias'])
    sun_boost = sun_s @ sun_w2.T + W['sun_sidecar.fc2.bias']

    # ── Storm sidecar (monotonic MLP): abs(weights) enforces monotonicity ──
    storm_w1 = np.abs(W['storm_sidecar.fc1.weight'])
    storm_w2 = np.abs(W['storm_sidecar.fc2.weight'])
    storm_s = _softplus(x_kp @ storm_w1.T + W['storm_sidecar.fc1.bias'])
    storm_boost = storm_s @ storm_w2.T + W['storm_sidecar.fc2.bias']

    # ── Final output ──
    return (base_snr + sun_gate * sun_boost + storm_gate * storm_boost).item()


# ── Engine Class ─────────────────────────────────────────────────────────────

class IonisEngine:
    """IONIS propagation prediction engine.

    Loads the V22-gamma checkpoint once and provides prediction methods
    for use by QSO Predictor.

    The engine is designed to fail gracefully — if the model can't be
    loaded (missing safetensors, missing checkpoint), is_available()
    returns False and all predictions return None.
    """

    def __init__(self, data_dir: str = None):
        """Initialize the engine, loading model weights.

        Args:
            data_dir: Path to directory containing config_v22.json and
                      ionis_v22_gamma.safetensors. If None, uses the
                      bundled data directory.
        """
        self._weights = None
        self._config = None
        self._available = False

        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), 'data')

        config_path = os.path.join(data_dir, 'config_v22.json')
        checkpoint_path = os.path.join(data_dir, 'ionis_v22_gamma.safetensors')

        if not os.path.exists(config_path):
            logger.warning(f"IONIS config not found: {config_path}")
            return

        if not os.path.exists(checkpoint_path):
            logger.warning(f"IONIS checkpoint not found: {checkpoint_path}")
            return

        try:
            with open(config_path) as f:
                self._config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read IONIS config: {e}")
            return

        self._weights = _load_weights(checkpoint_path)
        if self._weights is not None:
            self._available = True
            param_count = sum(w.size for w in self._weights.values())
            logger.info(
                f"IONIS engine loaded: V{self._config.get('version', '?')}-"
                f"{self._config.get('variant', '?')}, "
                f"{param_count:,} parameters"
            )

    def is_available(self) -> bool:
        """Check if the engine loaded successfully."""
        return self._available

    def predict(self, tx_grid: str, rx_grid: str, band: str,
                sfi: float, kp: float,
                hour_utc: float = None, month: int = None,
                day_of_year: int = None) -> dict | None:
        """Predict path viability for a single TX→RX path.

        If time parameters are omitted, uses current UTC time.

        Args:
            tx_grid: Transmitter Maidenhead grid (4-char, e.g. 'FN42')
            rx_grid: Receiver Maidenhead grid (4-char, e.g. 'JN48')
            band: Band name (e.g. '20m', '15m')
            sfi: Solar Flux Index (65-300)
            kp: Kp geomagnetic index (0-9)
            hour_utc: Hour of day UTC (0-23). None = current hour.
            month: Month (1-12). None = current month.
            day_of_year: Day of year (1-366). None = current day.

        Returns:
            dict with prediction results, or None if engine unavailable.
            Keys:
                sigma: Raw model output in z-score units
                snr_db: Predicted SNR in dB (denormalized for band)
                ft8_open: bool — is FT8 predicted decodable?
                ft8_status: str — 'OPEN', 'MARGINAL', or 'CLOSED'
                overridden: bool — was physics override applied?
                tx_solar_deg: TX solar elevation
                rx_solar_deg: RX solar elevation
                distance_km: Great-circle distance
                band: Band name used
                hour_utc: Hour used for prediction
        """
        if not self._available:
            return None

        if band not in BAND_FREQ_HZ:
            logger.warning(f"IONIS: unknown band '{band}'")
            return None

        # Default to current UTC time
        now = datetime.now(timezone.utc)
        if hour_utc is None:
            hour_utc = now.hour + now.minute / 60.0
        if month is None:
            month = now.month
        if day_of_year is None:
            day_of_year = now.timetuple().tm_yday

        # Resolve grids to coordinates
        tx_lat, tx_lon = grid4_to_latlon(tx_grid)
        rx_lat, rx_lon = grid4_to_latlon(rx_grid)

        freq_hz = BAND_FREQ_HZ[band]
        freq_mhz = freq_hz / 1e6

        # Build feature vector
        features = build_features(
            tx_lat, tx_lon, rx_lat, rx_lon,
            freq_hz, sfi, kp, hour_utc, month, day_of_year
        )

        # Run inference
        raw_sigma = _forward(features, self._weights)

        # Solar info for physics override and display
        tx_solar = solar_elevation_deg(tx_lat, tx_lon, hour_utc, day_of_year)
        rx_solar = solar_elevation_deg(rx_lat, rx_lon, hour_utc, day_of_year)
        distance_km = haversine_km(tx_lat, tx_lon, rx_lat, rx_lon)

        # Physics override
        sigma, overridden = apply_override(
            raw_sigma, freq_mhz, tx_solar, rx_solar, distance_km
        )

        # Denormalize to dB
        norm = BAND_NORM[band]
        snr_db = sigma * norm["std"] + norm["mean"]

        # FT8 status
        ft8_threshold = MODE_THRESHOLDS_DB["FT8"]
        ft8_open = snr_db >= ft8_threshold
        if snr_db >= ft8_threshold:
            ft8_status = "OPEN"
        elif snr_db >= ft8_threshold - 4.0:  # Within 4 dB of threshold
            ft8_status = "MARGINAL"
        else:
            ft8_status = "CLOSED"

        return {
            "sigma": float(sigma),
            "raw_sigma": float(raw_sigma),
            "snr_db": float(snr_db),
            "ft8_open": ft8_open,
            "ft8_status": ft8_status,
            "overridden": overridden,
            "tx_solar_deg": float(tx_solar),
            "rx_solar_deg": float(rx_solar),
            "distance_km": float(distance_km),
            "band": band,
            "hour_utc": float(hour_utc),
        }

    def predict_range(self, tx_grid: str, rx_grid: str, band: str,
                      sfi: float, kp: float,
                      hours: int = 12,
                      start_hour: float = None,
                      month: int = None,
                      day_of_year: int = None) -> list[dict] | None:
        """Predict path viability across a range of hours.

        Sweeps from start_hour through start_hour + hours, computing
        a prediction for each hour. SFI and Kp are held constant
        (reasonable assumption for 12-hour lookahead).

        Args:
            tx_grid, rx_grid, band, sfi, kp: Same as predict()
            hours: Number of hours to forecast (default 12)
            start_hour: Starting hour UTC. None = current hour.
            month: Month (1-12). None = current month.
            day_of_year: Day of year (1-366). None = current day.

        Returns:
            List of prediction dicts (one per hour), or None.
        """
        if not self._available:
            return None

        now = datetime.now(timezone.utc)
        if start_hour is None:
            start_hour = now.hour
        if month is None:
            month = now.month
        if day_of_year is None:
            day_of_year = now.timetuple().tm_yday

        results = []
        for offset in range(hours):
            hour = (start_hour + offset) % 24
            # Day of year advances when we wrap past midnight
            doy = day_of_year
            if start_hour + offset >= 24:
                doy = day_of_year + (start_hour + offset) // 24
                # Crude wrap — good enough for 12-hour forecasts
                if doy > 365:
                    doy = doy - 365

            result = self.predict(
                tx_grid, rx_grid, band, sfi, kp,
                hour_utc=hour, month=month, day_of_year=doy
            )
            if result is not None:
                results.append(result)

        return results if results else None
