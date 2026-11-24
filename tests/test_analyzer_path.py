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


# --- Evidence behind "Reported in Region" -----------------------------
# Reported by a user (2026-11): Path Intelligence said "Your signal
# reported nearby / Spotted by receiver in target's region" while PSK
# Reporter showed nobody hearing him. The status had come from local
# decodes — the target answering some other station in his grid field —
# and the UI could not tell that apart from a real spot of his signal.
# The label string is persisted, so it stays; the evidence kind rides
# alongside it.

import threading


def _decode_analyzer():
    a = _bare_analyzer()
    a.lock = threading.RLock()
    a.my_call = "KB1AAA"
    a.my_grid = "FN42"
    a.decode_evidence = {}
    a.responded_to_me = {}
    a.call_grid_map = {}
    return a


def test_target_answering_my_neighbour_is_tagged_as_such():
    a = _decode_analyzer()
    a.decode_evidence["3B8XX"] = {"responded_to": {"W2ZZZ"}, "last_seen": time.time()}
    a.call_grid_map["W2ZZZ"] = "FN30"
    path, _, kind = a._check_decode_path("3B8XX", "LG89")
    assert path == "Reported in Region"
    assert kind == "target_working_my_area"


def test_station_near_target_answering_me_is_tagged_as_such():
    a = _decode_analyzer()
    a.responded_to_me["FR4QQ"] = time.time()
    a.call_grid_map["FR4QQ"] = "LG78"
    path, _, kind = a._check_decode_path("3B8XX", "LG89")
    assert path == "Reported in Region"
    assert kind == "near_target_answered_me"


def test_target_answering_me_and_no_evidence_kinds():
    a = _decode_analyzer()
    assert a._check_decode_path("3B8XX", "LG89") == (None, 0, None)
    a.decode_evidence["3B8XX"] = {"responded_to": {"KB1AAA"}, "last_seen": time.time()}
    path, _, kind = a._check_decode_path("3B8XX", "LG89")
    assert (path, kind) == ("Heard by Target", "target_answered_me")
