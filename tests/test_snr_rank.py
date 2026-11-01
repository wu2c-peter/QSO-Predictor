# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Own SNR rank at the target's end (outcome schema v2 `my_rank_at_select`).

2026-10 analysis: the field was null in 100% of v2 events because it read
SessionTracker.get_your_status()['rank'], which is only ever None or '?'
(we can't hear our own signal locally). The rank that CAN be known is
at the target's end: our spotted SNR vs the rivals spotted near the
target's frequency.
"""

from analyzer.core import snr_rank_at_target


def test_loudest_is_rank_one():
    assert snr_rank_at_target(-5, [-10, -12, -20]) == 1


def test_rank_counts_strictly_louder_rivals():
    assert snr_rank_at_target(-11, [-4, -10, -11, -20]) == 3


def test_no_rivals_is_rank_one():
    assert snr_rank_at_target(-15, []) == 1


def test_unknown_own_snr_has_no_rank():
    assert snr_rank_at_target(None, [-4, -10]) is None


def test_rivals_without_snr_are_ignored():
    assert snr_rank_at_target(-8, [None, -2, None]) == 2
