# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""OutcomeRecorder: the persisted JSONL event format is an external contract.

Existing outcome_history.jsonl files must stay readable across releases —
these tests freeze schema v1's field set and the recording/filtering rules
(browsing produces nothing, churn is skipped, QSO_LOGGED always records).
The `outcome_recorder_home` fixture redirects HOME so no test ever touches
the real ~/.qso-predictor.
"""

import json
from datetime import datetime, timedelta

import pytest

from outcome_recorder import OutcomeRecorder, SCHEMA_VERSION
from local_intel.models import PathStatus


SNAPSHOT = {
    'rec_freq': 1687, 'rec_score': 82.0, 'tx_freq': 1690, 'tx_score': 81.5,
    'score_reason': 3, 'path': 'Heard by Target', 'competition': 4,
    'reporters': 12, 'ionis': 'OPEN', 'fh_mode': 'normal',
    'band': '20m', 'sfi': 155, 'k': 2,
}

# Schema v1 field set — a superset breaks nothing, but a missing or renamed
# key breaks every analysis script that reads historic files.
OUTCOME_FIELDS = {
    'v', 'type', 'ts', 'band', 'outcome',
    'rec_freq', 'rec_score', 'tx_freq', 'tx_score', 'followed',
    'score_delta', 'score_reason',
    'path', 'path_at_select', 'competition', 'reporters', 'ionis', 'fh_mode',
    'sfi', 'k', 'a', 'tx_cycles', 'elapsed_s',
    'hour_utc', 'dow', 'distance_km', 'target_continent',
}


def read_events(filepath):
    if not filepath.exists():
        return []
    return [json.loads(line) for line in filepath.read_text().splitlines()]


def make_attempt(recorder, call='JA1XYZ', grid='PM95', path=''):
    """Select a target and simulate one full TX cycle, backdated so the
    15-second churn filter doesn't discard the attempt."""
    recorder.on_target_selected(call, grid, band='20m', sfi=155, k=2,
                                path_at_select=path)
    recorder.on_status_update(True)    # TX rising edge
    recorder.on_status_update(False)
    if recorder._target_selected_at is not None:   # None when disabled
        recorder._target_selected_at -= timedelta(seconds=60)


def test_qso_logged_event_schema(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec)
    rec.record_outcome('QSO_LOGGED', SNAPSHOT)

    events = read_events(outcome_recorder_home)
    types = [e['type'] for e in events]
    assert types == ['session_start', 'outcome']

    ev = events[1]
    assert set(ev.keys()) == OUTCOME_FIELDS
    assert ev['v'] == SCHEMA_VERSION
    assert ev['outcome'] == 'QSO_LOGGED'
    assert ev['band'] == '20m'
    assert ev['tx_cycles'] == 1
    assert ev['followed'] is True          # |1690-1687| < 100 Hz
    assert ev['score_delta'] == 0.5
    assert ev['target_continent'] == 'AS'  # PM95 = Japan
    assert 9000 < ev['distance_km'] < 12000  # FN30 (NY) -> PM95 (Tokyo)


def test_path_status_labels_persist_byte_identical(outcome_recorder_home):
    """The JSONL 'path' fields carry PathStatus.display_label strings —
    the reason those labels are frozen (see test_path_status.py)."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec, path=PathStatus.REPORTED_IN_REGION.display_label)
    rec.record_outcome(
        'QSO_LOGGED',
        dict(SNAPSHOT, path=PathStatus.HEARD_BY_TARGET.display_label))

    raw = outcome_recorder_home.read_text()
    assert '"path":"Heard by Target"' in raw
    assert '"path_at_select":"Reported in Region"' in raw


def test_browsing_records_nothing(outcome_recorder_home):
    """Selecting a target and never transmitting = browsing. No outcome,
    and — because session start is deferred to first TX — no session."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    rec.on_target_selected('JA1XYZ', 'PM95', band='20m')
    rec._target_selected_at -= timedelta(seconds=60)
    rec.record_outcome('CLEARED', SNAPSHOT)
    rec.on_app_close()

    assert read_events(outcome_recorder_home) == []


def test_churn_is_skipped(outcome_recorder_home):
    """Elapsed < 15s can't be a real FT8 attempt (band-change churn)."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    rec.on_target_selected('JA1XYZ', 'PM95', band='20m')
    rec.on_status_update(True)
    rec.record_outcome('CLEARED', SNAPSHOT)   # no backdating: elapsed ~0s

    events = read_events(outcome_recorder_home)
    assert all(e['type'] != 'outcome' for e in events)


def test_responded_outcome_via_decode(outcome_recorder_home):
    """A decode FROM the target containing MY call upgrades the outcome
    tier from NO_RESPONSE to RESPONDED."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec)
    rec.on_decode('JA1XYZ', 'WU2C JA1XYZ -07')
    rec.record_outcome('CLEARED', SNAPSHOT)

    outcome = [e for e in read_events(outcome_recorder_home)
               if e['type'] == 'outcome'][0]
    assert outcome['outcome'] == 'RESPONDED'


def test_no_response_outcome(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec)
    # Decodes from other stations, or from target not mentioning us,
    # must NOT count as a response
    rec.on_decode('K1ABC', 'WU2C K1ABC -07')
    rec.on_decode('JA1XYZ', 'CQ JA1XYZ PM95')
    rec.record_outcome('CLEARED', SNAPSHOT)

    outcome = [e for e in read_events(outcome_recorder_home)
               if e['type'] == 'outcome'][0]
    assert outcome['outcome'] == 'NO_RESPONSE'


def test_disabled_recorder_writes_nothing(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30', enabled=False)
    make_attempt(rec)
    rec.record_outcome('QSO_LOGGED', SNAPSHOT)
    rec.on_app_close()
    assert not outcome_recorder_home.exists()


def test_session_end_written_on_app_close(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec)
    rec.record_outcome('QSO_LOGGED', SNAPSHOT)
    rec.on_app_close()

    events = read_events(outcome_recorder_home)
    assert [e['type'] for e in events] == \
        ['session_start', 'outcome', 'session_end']
    assert events[2]['outcomes'] == 1


def test_followed_false_when_far_from_recommendation(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec)
    rec.record_outcome('QSO_LOGGED', dict(
        SNAPSHOT, tx_freq=500, tx_score=40.0))  # 1187 Hz off, score -42

    outcome = [e for e in read_events(outcome_recorder_home)
               if e['type'] == 'outcome'][0]
    assert outcome['followed'] is False
    assert outcome['score_delta'] == 42.0
