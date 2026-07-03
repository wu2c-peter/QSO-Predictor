# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Great-circle bearing math in psk_reporter_api — feeds path
classification (sector_distribution) and region binning."""

import pytest

from psk_reporter_api import calculate_bearing


def assert_bearing_near(actual, expected, tol=12):
    assert actual is not None
    # Circular difference so 359 vs 1 counts as 2 degrees, not 358
    diff = abs((actual - expected + 180) % 360 - 180)
    assert diff <= tol, f"bearing {actual:.1f} not within {tol}deg of {expected}"


def test_cardinal_directions():
    assert_bearing_near(calculate_bearing("FN30", "FN31"), 0)     # due north
    assert_bearing_near(calculate_bearing("FN31", "FN30"), 180)   # due south
    assert_bearing_near(calculate_bearing("FN30", "FN50"), 90)    # east
    assert_bearing_near(calculate_bearing("FN50", "FN30"), 270)   # west


def test_transatlantic_path():
    # NYC area -> Berlin area: the classic 40-55 degree NE path
    assert_bearing_near(calculate_bearing("FN30", "JO62"), 50, tol=15)


def test_range_is_0_360():
    for pair in [("FN30", "FN31"), ("FN31", "FN30"),
                 ("FN30", "PM95"), ("PM95", "FN30")]:
        b = calculate_bearing(*pair)
        assert b is not None and 0 <= b < 360


def test_missing_grids_return_none():
    assert calculate_bearing("", "FN30") is None
    assert calculate_bearing("FN30", "") is None
    assert calculate_bearing("Z", "FN30") is None


def test_junk_grids_return_none():
    """grid_to_latlon range-checks characters — junk that passes length
    checks (a malformed 4-char grid in a PSK Reporter spot) must be
    rejected, not converted to impossible coordinates."""
    assert calculate_bearing("!!", "FN30") is None
    assert calculate_bearing("ZZ99", "FN30") is None
    assert calculate_bearing("FN30", "ZZ99") is None
    assert calculate_bearing("FNAA", "FN30") is None    # letters where digits go
    assert calculate_bearing("FN30ZZ", "FN30") is None  # subsquare past 'X'


def test_valid_grids_still_accepted():
    """Guard against over-tightening: all real locator shapes must pass."""
    assert_bearing_near(calculate_bearing("fn30", "FN31"), 0)       # lowercase
    assert_bearing_near(calculate_bearing("FN30as", "FN31as"), 0)   # 6-char
    assert calculate_bearing("FN", "JO") is not None              # 2-char field
    assert calculate_bearing("RR73", "FN30") is not None  # valid grid (Siberia)
                                                          # despite doubling as
                                                          # the FT8 ack token
