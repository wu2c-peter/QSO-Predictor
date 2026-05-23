"""Pure geometry / classification helpers for the analyzer.

Lifted out of QSOAnalyzer so they can be reused (and tested) without
touching the analyzer's locked caches. These functions take their inputs
explicitly — no MainWindow or self state.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

from typing import List


def sector_distribution(spots: list, from_grid: str) -> List[int]:
    """Distribute spots across 8 compass sectors (N, NE, E, ..., NW).

    Returns a list of 8 counts keyed by 45° sector index from north.
    """
    # Lazy import — psk_reporter_api pulls in requests which we don't want
    # paid at module-import time for this geometry module.
    from psk_reporter_api import calculate_bearing

    sectors = [0] * 8  # N, NE, E, SE, S, SW, W, NW

    for spot in spots:
        receiver_grid = spot.get('grid', '')
        if receiver_grid and len(receiver_grid) >= 4 and from_grid and len(from_grid) >= 4:
            bearing = calculate_bearing(from_grid, receiver_grid)
            if bearing is not None:
                sector = int(bearing / 45) % 8
                sectors[sector] += 1

    return sectors


def max_concentration(sectors: List[int]) -> int:
    """Return the highest percentage of spots in any 3 adjacent sectors (135° arc)."""
    total = sum(sectors)
    if total == 0:
        return 0

    max_conc = 0
    for i in range(8):
        # 3 adjacent sectors (wrap-around)
        left = (i - 1) % 8
        right = (i + 1) % 8
        concentrated = sectors[left] + sectors[i] + sectors[right]
        conc_pct = int(100 * concentrated / total)
        if conc_pct > max_conc:
            max_conc = conc_pct

    return max_conc


def bearing_to_region(bearing: float) -> str:
    """Bin a bearing (degrees from north) into a coarse DXCC region code."""
    bearing = bearing % 360
    if 20 <= bearing < 70:
        return "EU"
    elif 70 <= bearing < 120:
        return "AF/ME"
    elif 120 <= bearing < 180:
        return "AS"
    elif 180 <= bearing < 240:
        return "OC"
    elif 240 <= bearing < 300:
        return "SA"
    elif 300 <= bearing < 340:
        return "CA"
    else:
        return "NA"


def freq_to_band(freq_hz: int) -> str:
    """Convert frequency in Hz to ham-band name ('20m', '40m', etc.).

    Returns '??m' for frequencies that don't fall within a recognized band.
    """
    f = freq_hz / 1_000_000
    if 1.8 <= f <= 2.0: return "160m"
    if 3.5 <= f <= 4.0: return "80m"
    if 5.3 <= f <= 5.4: return "60m"
    if 7.0 <= f <= 7.3: return "40m"
    if 10.1 <= f <= 10.15: return "30m"
    if 14.0 <= f <= 14.35: return "20m"
    if 18.068 <= f <= 18.168: return "17m"
    if 21.0 <= f <= 21.45: return "15m"
    if 24.89 <= f <= 24.99: return "12m"
    if 28.0 <= f <= 29.7: return "10m"
    if 50.0 <= f <= 54.0: return "6m"
    return "??m"


def is_callsign(s: str) -> bool:
    """Loose heuristic: does this string look like an amateur radio callsign?"""
    if not s or len(s) < 3 or len(s) > 10:
        return False
    s = s.strip('<>')
    return any(c.isdigit() for c in s) and all(c.isalnum() or c == '/' for c in s)
