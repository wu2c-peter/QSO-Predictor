# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""IONIS propagation engine — the first tests for ~800 lines of pure,
deterministic numeric code (2026-09 audit).

- Golden vectors pin the forward pass for the committed V22-gamma
  checkpoint so a silent architecture/weight drift shows up here.
- Input validation: an invalid grid used to resolve to JJ00 (the Gulf
  of Guinea), SFI 0 / Kp 0 from a failed NOAA fetch went straight into
  the model (and came out slightly MORE optimistic than real data),
  and a NaN fell through the status ladder as a confident "CLOSED".
- predict_range's first column used the truncated hour while the
  headline used the fractional hour, and its day-of-year wrap skipped
  1 January after a leap-year 31 December.
"""

import math

import pytest

from ionis import IonisEngine
from ionis.features import grid4_to_latlon, freq_to_band
from ionis.physics_override import apply_override


@pytest.fixture(scope='module')
def engine():
    e = IonisEngine()
    if not e.is_available():
        pytest.skip("IONIS checkpoint not available")
    return e


# ---------------------------------------------------------------------------
# Grid handling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("grid, lat, lon", [
    ('FN42', 42.5, -71.0),
    ('fn42', 42.5, -71.0),
    ('JN48ab', 48.5, 9.0),      # 6-char input → its 4-char square
    ('JJ00', 0.5, 1.0),
    ('AA00', -89.5, -179.0),
    ('RR99', 89.5, 179.0),
])
def test_grid4_to_latlon(grid, lat, lon):
    assert grid4_to_latlon(grid) == pytest.approx((lat, lon))


@pytest.mark.parametrize("bad", ['', None, 'FN', 'Ohio', 'ZZ12', '73', '1234', 'xFN42'])
def test_invalid_grid_is_none_not_gulf_of_guinea(bad):
    assert grid4_to_latlon(bad) is None


def test_rr73_is_a_real_grid_square():
    """RR73 is syntactically (and geographically) a valid grid; the
    "it's an FT8 ack token, not a grid" rule belongs to the decode
    parser upstream, which is where it lives (parse_decode_message)."""
    assert grid4_to_latlon('RR73') == pytest.approx((83.5, 175.0))


def test_freq_to_band():
    assert freq_to_band(14_074_000) == '20m'
    assert freq_to_band(144_174_000) is None


# ---------------------------------------------------------------------------
# Engine input validation
# ---------------------------------------------------------------------------

def test_engine_refuses_unresolvable_grid(engine):
    assert engine.predict('FN', 'JN48', '20m', 142, 2) is None
    assert engine.predict('FN42', 'Ohio', '20m', 142, 2) is None


@pytest.mark.parametrize("sfi, kp", [
    (0, 0), (float('nan'), 2), (142, float('nan')), (142, 12), (-5, 2),
    (None, 2), ('abc', 2), (float('inf'), 2),
])
def test_engine_refuses_impossible_solar_inputs(engine, sfi, kp):
    assert engine.predict('FN42', 'JN48', '20m', sfi, kp,
                          hour_utc=14.0, month=6, day_of_year=170) is None


def test_engine_refuses_unknown_band(engine):
    assert engine.predict('FN42', 'JN48', '2m', 142, 2) is None


# ---------------------------------------------------------------------------
# Golden vectors (V22-gamma checkpoint, FN42 → JN48, 14:00 UTC, day 170)
# ---------------------------------------------------------------------------

GOLDEN = [
    # sfi, kp, band, hour, month, doy, snr_db, status
    (142, 2, '20m', 14.0, 6, 170, -18.471, 'OPEN'),
    (80, 5, '20m', 14.0, 6, 170, -22.448, 'MARGINAL'),
    (200, 0, '20m', 14.0, 6, 170, -15.459, 'OPEN'),
    (142, 2, '40m', 14.0, 6, 170, -30.540, 'CLOSED'),
    (142, 2, '20m', 3.0, 12, 350, -21.242, 'MARGINAL'),
]


@pytest.mark.parametrize("sfi, kp, band, hour, month, doy, snr_db, status", GOLDEN)
def test_forward_pass_golden(engine, sfi, kp, band, hour, month, doy, snr_db, status):
    r = engine.predict('FN42', 'JN48', band, sfi, kp,
                       hour_utc=hour, month=month, day_of_year=doy)
    assert r is not None
    assert r['snr_db'] == pytest.approx(snr_db, abs=0.01)
    assert r['ft8_status'] == status
    assert r['ft8_open'] == (status in ('OPEN', 'STRONG'))
    assert math.isfinite(r['sigma'])
    assert r['band'] == band


def test_more_flux_is_never_worse(engine):
    """The sun sidecar is a monotonic MLP: higher SFI, same everything
    else, must not lower the predicted SNR."""
    kw = dict(hour_utc=14.0, month=6, day_of_year=170)
    a = engine.predict('FN42', 'JN48', '20m', 90, 2, **kw)['snr_db']
    b = engine.predict('FN42', 'JN48', '20m', 180, 2, **kw)['snr_db']
    assert b >= a


def test_storm_is_never_better(engine):
    kw = dict(hour_utc=14.0, month=6, day_of_year=170)
    quiet = engine.predict('FN42', 'JN48', '20m', 142, 0, **kw)['snr_db']
    storm = engine.predict('FN42', 'JN48', '20m', 142, 8, **kw)['snr_db']
    assert storm <= quiet


# ---------------------------------------------------------------------------
# Forecast consistency
# ---------------------------------------------------------------------------

def test_forecast_first_column_matches_headline_prediction(engine):
    """Both default to the SAME fractional 'now' — they used to differ
    by up to an hour of solar elevation at :59."""
    head = engine.predict('FN42', 'JN48', '20m', 142, 2)
    fc = engine.predict_range('FN42', 'JN48', '20m', 142, 2, hours=3)
    assert fc and fc[0]['hour_utc'] == pytest.approx(head['hour_utc'], abs=1 / 60)


def test_forecast_wraps_year_end_correctly(engine):
    """The last day of the CURRENT year (366 in a leap year, where the
    old `> 365` wrap jumped to 2 January) + 2 h must land on day 1."""
    import calendar
    from datetime import datetime, timezone
    last_day = 366 if calendar.isleap(datetime.now(timezone.utc).year) else 365
    fc = engine.predict_range('FN42', 'JN48', '20m', 142, 2, hours=3,
                              start_hour=23.0, month=12, day_of_year=last_day)
    assert fc and len(fc) == 3
    assert fc[1]['hour_utc'] == 0.0 and fc[2]['hour_utc'] == 1.0
    jan1 = engine.predict('FN42', 'JN48', '20m', 142, 2,
                          hour_utc=0.0, month=12, day_of_year=1)
    assert fc[1]['snr_db'] == pytest.approx(jan1['snr_db'], abs=1e-6)
    jan2 = engine.predict('FN42', 'JN48', '20m', 142, 2,
                          hour_utc=0.0, month=12, day_of_year=2)
    assert fc[1]['snr_db'] != pytest.approx(jan2['snr_db'], abs=1e-9) or \
        jan1['snr_db'] == jan2['snr_db']


# ---------------------------------------------------------------------------
# Physics override contract (pure function)
# ---------------------------------------------------------------------------

def test_physics_override_returns_tuple_and_flags():
    sigma, flagged = apply_override(0.5, 14.074, 30.0, 30.0, 6000.0)
    assert isinstance(flagged, bool)
    assert math.isfinite(sigma)
