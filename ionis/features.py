# QSO Predictor — IONIS Feature Engineering
# Copyright (C) 2025-2026 Peter Hirst (WU2C)
#
# Feature engineering ported from IONIS V22-gamma by Greg Beam (KI7MT)
# Original source: github.com/IONIS-AI/ionis-training (GPLv3)
# Adapted for pure-numpy inference without PyTorch dependency.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Feature engineering for IONIS propagation prediction.

Converts human-friendly inputs (grid squares, band, time, SFI, Kp) into
the 17-element normalized feature vector expected by IonisGate V22.

All functions are pure numpy/math — no PyTorch, no external dependencies.
"""

import math
import re

import numpy as np


# ── Grid Utilities ───────────────────────────────────────────────────────────

_GRID_RE = re.compile(r'[A-Ra-r]{2}[0-9]{2}')


def grid4_to_latlon(grid: str) -> tuple[float, float]:
    """Convert a 4-char Maidenhead grid to (lat, lon) centroid.

    Returns the center of the grid square. Falls back to JJ00 (equator)
    if the grid is invalid.

    Args:
        grid: 4-character Maidenhead grid (e.g. 'FN42', 'JN48')

    Returns:
        (latitude, longitude) in degrees
    """
    s = str(grid).strip().rstrip('\x00').upper()
    m = _GRID_RE.search(s)
    g4 = m.group(0) if m else 'JJ00'
    lon = (ord(g4[0]) - ord('A')) * 20.0 - 180.0 + int(g4[2]) * 2.0 + 1.0
    lat = (ord(g4[1]) - ord('A')) * 10.0 - 90.0 + int(g4[3]) * 1.0 + 0.5
    return lat, lon


# ── Geo Helpers ──────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float,
                 lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/lon points."""
    R = 6371.0
    lat1_r, lat2_r = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = (np.sin(dlat / 2) ** 2 +
         np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2)
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def azimuth_deg(lat1: float, lon1: float,
                lat2: float, lon2: float) -> float:
    """Initial bearing (azimuth) in degrees from point 1 to point 2."""
    lat1_r, lat2_r = np.radians(lat1), np.radians(lat2)
    dlon = np.radians(lon2 - lon1)
    x = np.sin(dlon) * np.cos(lat2_r)
    y = (np.cos(lat1_r) * np.sin(lat2_r) -
         np.sin(lat1_r) * np.cos(lat2_r) * np.cos(dlon))
    return (np.degrees(np.arctan2(x, y)) + 360) % 360


def vertex_lat_deg(tx_lat: float, tx_lon: float,
                   rx_lat: float, rx_lon: float) -> float:
    """Compute vertex latitude — highest point on the great circle path.

    The vertex indicates polar exposure for geomagnetic storm sensitivity.
    Inspired by WsprDaemon schema (Rob Robinett AI6VN).

    Returns:
        Vertex latitude in degrees (always positive, 0-90)
    """
    bearing_rad = np.radians(azimuth_deg(tx_lat, tx_lon, rx_lat, rx_lon))
    tx_lat_rad = np.radians(tx_lat)
    vertex_lat_rad = np.arccos(
        np.abs(np.sin(bearing_rad) * np.cos(tx_lat_rad)))
    return np.degrees(vertex_lat_rad)


# ── Solar Position ───────────────────────────────────────────────────────────

def solar_elevation_deg(lat: float, lon: float,
                        hour_utc: float, day_of_year: int) -> float:
    """Compute solar elevation angle in degrees.

    Positive = sun above horizon (daylight)
    Negative = sun below horizon (night)

    Physical thresholds the model has learned:
        > 0°:       Daylight — D-layer absorbing, F-layer ionized
        0° to -6°:  Civil twilight — D-layer weakening
        -6° to -12°: Nautical twilight — D-layer collapsed (greyline)
        -12° to -18°: Astronomical twilight — F-layer fading
        < -18°:     Night — F-layer decayed

    Accuracy ~1°, sufficient for ionospheric modeling.
    """
    # Solar declination (simplified)
    dec = -23.44 * math.cos(math.radians(360.0 / 365.0 * (day_of_year + 10)))
    dec_r = math.radians(dec)
    lat_r = math.radians(lat)

    # Hour angle: degrees from solar noon
    solar_hour = hour_utc + lon / 15.0
    ha_r = math.radians((solar_hour - 12.0) * 15.0)

    # Solar elevation formula
    sin_elev = (math.sin(lat_r) * math.sin(dec_r) +
                math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r))
    sin_elev = max(-1.0, min(1.0, sin_elev))

    return math.degrees(math.asin(sin_elev))


# ── Band Lookup ──────────────────────────────────────────────────────────────

# FT8 dial frequencies in Hz, keyed by band name
# Note: IONIS was trained on WSPR frequencies but the difference is
# negligible in log-frequency space (< 0.01% for all bands).
BAND_FREQ_HZ = {
    "160m":  1_840_000,
    "80m":   3_573_000,
    "60m":   5_357_000,
    "40m":   7_074_000,
    "30m":  10_136_000,
    "20m":  14_074_000,
    "17m":  18_100_000,
    "15m":  21_074_000,
    "12m":  24_915_000,
    "10m":  28_074_000,
}

# Band detection from raw frequency (Hz)
BAND_RANGES_HZ = {
    "160m": (1_800_000,   2_000_000),
    "80m":  (3_500_000,   4_000_000),
    "60m":  (5_250_000,   5_450_000),
    "40m":  (7_000_000,   7_300_000),
    "30m":  (10_100_000, 10_150_000),
    "20m":  (14_000_000, 14_350_000),
    "17m":  (18_068_000, 18_168_000),
    "15m":  (21_000_000, 21_450_000),
    "12m":  (24_890_000, 24_990_000),
    "10m":  (28_000_000, 29_700_000),
}


def freq_to_band(freq_hz: float) -> str | None:
    """Convert a frequency in Hz to a band name, or None if out of range."""
    for band, (lo, hi) in BAND_RANGES_HZ.items():
        if lo <= freq_hz <= hi:
            return band
    return None


# Per-band normalization constants for denormalizing model output.
# Source: config_v22.json, WSPR statistics.
# The model outputs in sigma (z-score) units. To get dB:
#   snr_db = sigma * std + mean
BAND_NORM = {
    "160m": {"mean": -18.04, "std": 6.9},
    "80m":  {"mean": -17.90, "std": 6.9},
    "60m":  {"mean": -17.60, "std": 7.1},
    "40m":  {"mean": -17.34, "std": 6.6},
    "30m":  {"mean": -18.07, "std": 6.5},
    "20m":  {"mean": -17.53, "std": 6.7},
    "17m":  {"mean": -18.35, "std": 7.0},
    "15m":  {"mean": -18.32, "std": 6.6},
    "12m":  {"mean": -18.76, "std": 6.6},
    "10m":  {"mean": -17.86, "std": 6.5},
}

# Mode decode thresholds in dB (from IONIS ionis-validate)
MODE_THRESHOLDS_DB = {
    "WSPR": -28.0,
    "FT8":  -21.0,
    "FT4":  -21.0,  # Similar to FT8
    "CW":   -15.0,
    "RTTY":  -5.0,
    "SSB":    3.0,
}


# ── Feature Builder ─────────────────────────────────────────────────────────

def build_features(tx_lat: float, tx_lon: float,
                   rx_lat: float, rx_lon: float,
                   freq_hz: float, sfi: float, kp: float,
                   hour_utc: float, month: int,
                   day_of_year: int) -> np.ndarray:
    """Build a normalized 17-element feature vector for V22 inference.

    This is the V22 feature set with solar depression angles and
    band×darkness cross-products.

    Args:
        tx_lat, tx_lon: Transmitter coordinates in degrees
        rx_lat, rx_lon: Receiver coordinates in degrees
        freq_hz: Operating frequency in Hz
        sfi: Solar Flux Index (65-300)
        kp: Kp geomagnetic index (0-9)
        hour_utc: Hour of day in UTC (0-23, can be float)
        month: Month of year (1-12)
        day_of_year: Day of year (1-366)

    Returns:
        np.ndarray of shape (17,), dtype float32

    Feature indices:
        0: distance       1: freq_log       2: hour_sin      3: hour_cos
        4: az_sin          5: az_cos          6: lat_diff       7: midpoint_lat
        8: season_sin     9: season_cos     10: vertex_lat
       11: tx_solar_dep  12: rx_solar_dep
       13: freq_x_tx_dark 14: freq_x_rx_dark
       15: sfi            16: kp_penalty
    """
    # Geometry
    distance_km = haversine_km(tx_lat, tx_lon, rx_lat, rx_lon)
    az = azimuth_deg(tx_lat, tx_lon, rx_lat, rx_lon)
    midpoint_lat = (tx_lat + rx_lat) / 2.0
    v_lat = vertex_lat_deg(tx_lat, tx_lon, rx_lat, rx_lon)

    # Solar elevation at each endpoint
    tx_solar = solar_elevation_deg(tx_lat, tx_lon, hour_utc, day_of_year)
    rx_solar = solar_elevation_deg(rx_lat, rx_lon, hour_utc, day_of_year)
    tx_solar_norm = tx_solar / 90.0
    rx_solar_norm = rx_solar / 90.0

    # Band × darkness cross-products (asymmetric scaling, V22-gamma)
    # Below 10 MHz: darkness helps (D-layer absorption vanishes)
    # Above 10 MHz: darkness kills (F-layer refraction vanishes)
    freq_mhz = freq_hz / 1e6
    if freq_mhz >= 10.0:
        freq_centered = (freq_mhz - 10.0) / 18.0    # 28 MHz → +1.0
    else:
        freq_centered = (freq_mhz - 10.0) / 8.2     # 1.8 MHz → -1.0

    return np.array([
        distance_km / 20000.0,                        #  0: distance
        np.log10(freq_hz) / 8.0,                      #  1: freq_log
        np.sin(2.0 * np.pi * hour_utc / 24.0),        #  2: hour_sin
        np.cos(2.0 * np.pi * hour_utc / 24.0),        #  3: hour_cos
        np.sin(2.0 * np.pi * az / 360.0),             #  4: az_sin
        np.cos(2.0 * np.pi * az / 360.0),             #  5: az_cos
        abs(tx_lat - rx_lat) / 180.0,                 #  6: lat_diff
        midpoint_lat / 90.0,                           #  7: midpoint_lat
        np.sin(2.0 * np.pi * month / 12.0),           #  8: season_sin
        np.cos(2.0 * np.pi * month / 12.0),           #  9: season_cos
        v_lat / 90.0,                                  # 10: vertex_lat
        tx_solar_norm,                                 # 11: tx_solar_dep
        rx_solar_norm,                                 # 12: rx_solar_dep
        freq_centered * tx_solar_norm,                 # 13: freq_x_tx_dark
        freq_centered * rx_solar_norm,                 # 14: freq_x_rx_dark
        sfi / 300.0,                                   # 15: sfi
        1.0 - kp / 9.0,                               # 16: kp_penalty
    ], dtype=np.float32)


def get_solar_info(tx_lat: float, tx_lon: float,
                   rx_lat: float, rx_lon: float,
                   freq_hz: float,
                   hour_utc: float, day_of_year: int) -> dict:
    """Get solar and path info for display purposes.

    Returns a dict with human-readable path metadata that can be
    shown alongside the prediction in the UI.
    """
    return {
        "tx_solar_deg": solar_elevation_deg(tx_lat, tx_lon,
                                            hour_utc, day_of_year),
        "rx_solar_deg": solar_elevation_deg(rx_lat, rx_lon,
                                            hour_utc, day_of_year),
        "distance_km": haversine_km(tx_lat, tx_lon, rx_lat, rx_lon),
        "azimuth_deg": azimuth_deg(tx_lat, tx_lon, rx_lat, rx_lon),
        "freq_mhz": freq_hz / 1e6,
    }
