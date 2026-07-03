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


@pytest.mark.xfail(reason="grid_to_latlon length-checks but does not "
                          "range-check characters: 'ZZ99' yields lat 169.5. "
                          "Known gap — see the range-check follow-up task.",
                   strict=True)
def test_junk_grids_would_ideally_return_none():
    assert calculate_bearing("!!", "FN30") is None
    assert calculate_bearing("ZZ99", "FN30") is None
