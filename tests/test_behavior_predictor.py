# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""BehaviorPredictor persistence and counter semantics (2026-09 audit).

- update_observations added picking observations to total_qsos, which
  feeds the persona traits; every bootstrapped station's completion
  rate decayed toward zero and into the dx_hunter persona.
- The periodic live-session save was keyed on len(history) % 10, so it
  stopped firing once the dict settled on a non-multiple of ten.
- History was written truncate-then-write; a crash mid-dump left a
  file the loader silently treated as "no history".
"""

import json
import threading

import pytest

from local_intel.behavior_predictor import BehaviorPredictor, BehaviorPrior, HistoricalRecord


@pytest.fixture
def predictor(tmp_path):
    return BehaviorPredictor(model_manager=None,
                             history_path=tmp_path / 'behavior_history.json')


def test_picking_observations_do_not_inflate_total_qsos(predictor):
    predictor._history['OH0ERF'] = HistoricalRecord(
        callsign='OH0ERF', sessions_seen=2, total_qsos=10, completed_qsos=9,
        total_session_seconds=600)
    before = predictor._history['OH0ERF'].completion_rate
    predictor.update_observations('OH0ERF', [(True, 'K1ABC'), (False, 'W1XYZ')] * 10)
    rec = predictor._history['OH0ERF']
    assert rec.observations == 20
    assert rec.total_qsos == 10
    assert rec.completion_rate == before


def test_live_history_saves_every_n_updates(predictor):
    belief = BehaviorPrior(style_probs={'loudest_first': 0.8, 'methodical': 0.1,
                                        'random': 0.1}, confidence=0.7, source='bayesian')
    # 47 stations — the old `len % 10 == 0` test could never fire again
    for i in range(47):
        predictor._history[f"K{i}ABC"] = HistoricalRecord(callsign=f"K{i}ABC")
    assert not predictor.history_path.exists()
    for _ in range(predictor.SAVE_EVERY_N_UPDATES):
        predictor._update_history('K1ABC', belief)
    assert predictor.history_path.exists()
    saved = json.loads(predictor.history_path.read_text(encoding='utf-8'))
    assert saved['records']['K1ABC']['loudest_first_count'] == predictor.SAVE_EVERY_N_UPDATES


def test_save_is_atomic_and_reload_matches(predictor):
    predictor._history['JA1XYZ'] = HistoricalRecord(callsign='JA1XYZ', observations=5)
    predictor._save_history()
    assert not predictor.history_path.with_suffix('.json.tmp').exists()
    fresh = BehaviorPredictor(model_manager=None, history_path=predictor.history_path)
    assert fresh._history['JA1XYZ'].observations == 5


def test_corrupt_history_is_quarantined_not_ignored(tmp_path):
    path = tmp_path / 'behavior_history.json'
    path.write_text('{"records": {"K1ABC": {"callsign": "K1A', encoding='utf-8')
    p = BehaviorPredictor(model_manager=None, history_path=path)
    assert p._history == {}
    assert path.with_suffix('.json.corrupt').exists()


def test_concurrent_updates_and_saves_do_not_corrupt(predictor):
    """Scanner thread saving while the main thread inserts used to raise
    'dictionary changed size during iteration' inside the save."""
    errors = []

    def writer():
        try:
            for i in range(300):
                predictor.update_observations(f"W{i}AAA", [(True, 'X')])
        except Exception as e:  # pragma: no cover
            errors.append(e)

    def saver():
        try:
            for _ in range(30):
                predictor._save_history()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer), threading.Thread(target=saver)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    predictor._save_history()
    assert errors == []
    saved = json.loads(predictor.history_path.read_text(encoding='utf-8'))
    assert len(saved['records']) == 300


def test_bootstrap_watermark_round_trip(predictor):
    from datetime import datetime
    ts = datetime(2026, 8, 30, 12, 34, 56)
    assert predictor._read_bootstrap_watermark() is None
    predictor._write_bootstrap_watermark(ts)
    assert predictor._read_bootstrap_watermark() == ts
