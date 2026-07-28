# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Status-bar reporter counting (analyzer.core free functions).

Field report 2026-07-27: while running frequency on 20m, the status
bar claimed "233 reporting WU2C" — the raw length of the 3-minute
reception-report list. A receiver that copies you every TX cycle
appears up to ~6 times in that window, so the display overstated the
distinct-receiver count 3-6x. Same bug class as the v2.0.4 "count
unique callsigns, not total spots" fix on the Tracking side.
"""

from analyzer.core import (count_unique_reporters,
                           count_unique_reporters_near)


def _report(receiver, grid='FN31', t=1000.0):
    return {'receiver': receiver, 'grid': grid, 'time': t,
            'sender': 'WU2C', 'snr': -10}


def test_repeat_reports_from_one_receiver_count_once():
    """Six TX cycles heard by the same station = one reporter."""
    reports = [_report('K1ABC', t=1000 + i * 30) for i in range(6)]
    assert count_unique_reporters(reports) == 1


def test_running_frequency_scenario_counts_receivers_not_reports():
    """The field case: ~6 TX cycles x ~40 receivers = ~240 reports,
    but the honest number is the 40 distinct receivers."""
    reports = [_report(f'K{n}ABC', t=1000 + cycle * 30)
               for cycle in range(6) for n in range(40)]
    assert len(reports) == 240
    assert count_unique_reporters(reports) == 40


def test_receiver_case_is_normalized():
    assert count_unique_reporters(
        [_report('k1abc'), _report('K1ABC')]) == 1


def test_reports_without_receiver_are_ignored():
    reports = [_report('K1ABC'), {'grid': 'FN31', 'time': 1000.0},
               {'receiver': '', 'grid': 'FN31', 'time': 1000.0}]
    assert count_unique_reporters(reports) == 1
    assert count_unique_reporters([]) == 0


def test_near_target_counts_unique_receivers_in_field():
    reports = ([_report('GN1AA', grid='GN28', t=1000 + i * 30)
                for i in range(6)]           # one near-target receiver, 6x
               + [_report('GN2BB', grid='GN37')]   # same field, once
               + [_report('K1ABC', grid='FN31')])  # elsewhere
    assert count_unique_reporters_near(reports, 'GN') == 2


def test_near_target_handles_missing_or_short_grids():
    reports = [_report('K1ABC', grid=''), _report('K2DEF', grid='F'),
               {'receiver': 'K3GHI', 'time': 1000.0}]
    assert count_unique_reporters_near(reports, 'GN') == 0


# ---------------------------------------------------------------------------
# Band gating (v2.7.0 field report: Mac on 10m displayed "12 reporting
# WU2C" — live 20m receptions of the OTHER same-call station, because
# the self-spot MQTT subscription is band-wildcarded and the reception
# cache had no band gate)
# ---------------------------------------------------------------------------

from analyzer.core import spot_is_on_dial_band


def test_reception_band_gate_matches_the_band_map_rule():
    dial = 14_074_000
    # In the FT8 passband above dial: on band.
    assert spot_is_on_dial_band(14_074_000, dial)
    assert spot_is_on_dial_band(14_075_500, dial)
    assert spot_is_on_dial_band(14_078_000, dial)
    # The field case: 10m dial, 20m spots of the same callsign.
    assert not spot_is_on_dial_band(14_075_000, 28_074_000)
    # Another band, another sub-band, adjacent FT4 slot.
    assert not spot_is_on_dial_band(28_074_000, 14_074_000)
    assert not spot_is_on_dial_band(14_080_000, 14_074_000)
