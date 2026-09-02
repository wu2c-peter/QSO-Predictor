# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Path-label semantics that changed when the reception cache went
per-band (v2.7.0). "Not Transmitting" used to mean "no spots of me
anywhere"; with the cache cleared on every QSY that was also what the
first minutes on a new band looked like while calling — and the string
is persisted as `path_at_select` in the outcome JSONL.
"""

import time

from analyzer.core import QSOAnalyzer


def _bare_analyzer():
    """An analyzer without __init__ (no MQTT client, no threads)."""
    a = QSOAnalyzer.__new__(QSOAnalyzer)
    a._tx_on = False
    a._last_tx_time = 0.0
    return a


def test_not_transmitting_requires_being_off_the_air():
    a = _bare_analyzer()
    assert a._no_path_label(True, []) == "Not Transmitting"


def test_on_the_air_but_unheard_is_not_reported_in_region():
    a = _bare_analyzer()
    a.set_tx_state(True)
    assert a._no_path_label(True, []) == "Not Reported in Region"


def test_recent_tx_still_counts_as_on_the_air():
    a = _bare_analyzer()
    a.set_tx_state(True)
    a.set_tx_state(False)          # TX just ended
    assert a.transmitting_recently()
    assert a._no_path_label(True, []) == "Not Reported in Region"
    a._last_tx_time = time.time() - QSOAnalyzer.TX_RECENT_WINDOW_S - 1
    assert a._no_path_label(True, []) == "Not Transmitting"


def test_spotted_elsewhere_is_not_reported_in_region():
    a = _bare_analyzer()
    assert a._no_path_label(True, [{'receiver': 'K1ABC'}]) == "Not Reported in Region"


def test_no_reporters_wins_regardless_of_tx():
    a = _bare_analyzer()
    a.set_tx_state(True)
    assert a._no_path_label(False, []) == "No Reporters in Region"
