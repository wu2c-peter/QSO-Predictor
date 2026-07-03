# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""freq_to_band is duplicated across modules (see CLAUDE.md "Known
follow-ups"). Until the copies are consolidated onto
analyzer.geometry.freq_to_band, this guards that they at least agree for
in-band frequencies — a band-table edit that only lands in one copy fails
here.

Out-of-band fallbacks intentionally differ per copy ('??m', '?', '20m',
None) and are NOT asserted; consolidating those is part of the cleanup.
"""

import pytest

from analyzer.geometry import freq_to_band as canonical

# Test frequencies: low edge / FT8 sub-band / high edge for every HF+6m band
IN_BAND_HZ = [
    1_800_000, 1_840_000, 2_000_000,        # 160m
    3_500_000, 3_573_000, 4_000_000,        # 80m
    5_300_000, 5_357_000, 5_400_000,        # 60m
    7_000_000, 7_074_000, 7_300_000,        # 40m
    10_100_000, 10_136_000, 10_150_000,     # 30m
    14_000_000, 14_074_000, 14_350_000,     # 20m
    18_068_000, 18_100_000, 18_168_000,     # 17m
    21_000_000, 21_074_000, 21_450_000,     # 15m
    24_890_000, 24_915_000, 24_990_000,     # 12m
    28_000_000, 28_074_000, 29_700_000,     # 10m
    50_000_000, 50_313_000, 54_000_000,     # 6m
]


@pytest.mark.parametrize("freq_hz", IN_BAND_HZ)
def test_hunt_manager_copy_agrees(freq_hz):
    from hunt_manager import HuntManager
    # The private copies don't touch self — call unbound
    assert HuntManager._freq_to_band(None, freq_hz) == canonical(freq_hz)


@pytest.mark.parametrize("freq_hz", IN_BAND_HZ)
def test_mqtt_client_copy_agrees(freq_hz):
    from mqtt_client import MQTTClient
    assert MQTTClient._freq_to_band(None, freq_hz) == canonical(freq_hz)


@pytest.mark.parametrize("freq_hz", IN_BAND_HZ)
def test_log_parser_copy_agrees(freq_hz):
    from local_intel.log_parser import LogParser
    # This copy takes MHz, not Hz
    assert LogParser._freq_to_band(freq_hz / 1e6) == canonical(freq_hz)


@pytest.mark.parametrize("freq_hz", IN_BAND_HZ)
def test_ionis_copy_agrees_in_band(freq_hz):
    from ionis.features import freq_to_band as ionis_freq_to_band
    result = ionis_freq_to_band(freq_hz)
    # IONIS band ranges come from its training config and may not span
    # the full amateur allocation — only compare when it recognizes the
    # frequency at all.
    if result is not None:
        assert result == canonical(freq_hz)


def test_ionis_recognizes_ft8_subbands():
    """The FT8 calling frequencies must be classified by IONIS —
    they're where predictions actually get requested."""
    from ionis.features import freq_to_band as ionis_freq_to_band
    for freq_hz in [3_573_000, 7_074_000, 10_136_000, 14_074_000,
                    18_100_000, 21_074_000, 24_915_000, 28_074_000]:
        assert ionis_freq_to_band(freq_hz) == canonical(freq_hz)
