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
    'rec_freq': 1687, 'rec_score': 82.0, 'rec_reason': 4,
    'tx_freq': 1690, 'tx_score': 81.5,
    'score_reason': 3, 'tier1_count_at_tx_bucket': 2,
    'path': 'Heard by Target', 'competition': 4,
    'reporters': 12, 'ionis': 'OPEN', 'fh_mode': 'normal',
    'band': '20m', 'sfi': 155, 'k': 2,
}

TACTICAL = {
    'competition_at_select': 3, 'competition_src': 'target',
    'local_callers_at_select': 2, 'my_rank_at_select': 2,
    'my_snr_at_target': -11, 'best_rival_snr_at_target': -4,
    'near_me_heard': 1,
    'behavior_pattern': 'loudest_first', 'behavior_confidence': 62,
    'behavior_source': 'historical', 'persona': None,
}

CYCLE_CTX = {
    'rank': 3, 'comp': 4, 'lcall': 2, 'path': 'R', 't1': 1, 'txf': 1831,
    'success_prob': 41, 'strategy': 'call_now', 'target_state': 'cq',
}

# Schema v2 field set — a superset breaks nothing, but a missing or renamed
# key breaks every analysis script that reads historic files. The v1 subset
# must never shrink (v1 events remain valid for the fields they have).
OUTCOME_FIELDS = {
    # v1
    'v', 'type', 'ts', 'band', 'outcome',
    'rec_freq', 'rec_score', 'tx_freq', 'tx_score', 'followed',
    'score_delta', 'score_reason',
    'path', 'path_at_select', 'competition', 'reporters', 'ionis', 'fh_mode',
    'sfi', 'k', 'a', 'tx_cycles', 'elapsed_s',
    'hour_utc', 'dow', 'distance_km', 'target_continent',
    # v2: at-select tactical snapshot
    'success_prob', 'strategy',
    'competition_at_select', 'competition_src', 'competition_max',
    'local_callers_at_select', 'my_rank_at_select',
    'my_snr_at_target', 'best_rival_snr_at_target', 'near_me_heard',
    'behavior_pattern', 'behavior_confidence', 'behavior_source',
    'persona', 'target_state',
    # v2: terminal additions + per-cycle trace
    'rec_reason', 'tier1_count_at_tx_bucket', 'trace',
}


def read_events(filepath):
    if not filepath.exists():
        return []
    return [json.loads(line) for line in filepath.read_text().splitlines()]


def make_attempt(recorder, call='JA1XYZ', grid='PM95', path='',
                 tactical=None, cycle_ctx=None, cycles=1):
    """Select a target and simulate TX cycles, backdated so the
    15-second churn filter doesn't discard the attempt."""
    recorder.on_target_selected(call, grid, band='20m', sfi=155, k=2,
                                path_at_select=path, tactical=tactical)
    fn = (lambda: dict(cycle_ctx)) if cycle_ctx else None
    for _ in range(cycles):
        recorder.on_status_update(True, cycle_context_fn=fn)   # rising edge
        recorder.on_status_update(False, cycle_context_fn=fn)
    if recorder._target_selected_at is not None:   # None when disabled
        recorder._target_selected_at -= timedelta(seconds=60)


def test_qso_logged_event_schema(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec, tactical=TACTICAL, cycle_ctx=CYCLE_CTX, cycles=2)
    rec.record_outcome('QSO_LOGGED', SNAPSHOT)

    events = read_events(outcome_recorder_home)
    types = [e['type'] for e in events]
    assert types == ['session_start', 'outcome']

    ev = events[1]
    assert set(ev.keys()) == OUTCOME_FIELDS
    assert ev['v'] == SCHEMA_VERSION == 2
    assert ev['outcome'] == 'QSO_LOGGED'
    assert ev['band'] == '20m'
    assert ev['tx_cycles'] == 2
    assert ev['followed'] is True          # |1690-1687| < 100 Hz
    assert ev['score_delta'] == 0.5
    assert ev['target_continent'] == 'AS'  # PM95 = Japan
    assert 9000 < ev['distance_km'] < 12000  # FN30 (NY) -> PM95 (Tokyo)

    # v2: at-select tactical fields pass through verbatim
    for key, expected in TACTICAL.items():
        assert ev[key] == expected, key
    # v2: terminal additions
    assert ev['rec_reason'] == 4
    assert ev['tier1_count_at_tx_bucket'] == 2
    # v2: first-TX promotion — lifted from cycle context, NOT in trace
    assert ev['success_prob'] == 41
    assert ev['strategy'] == 'call_now'
    assert ev['target_state'] == 'cq'
    # v2: trace — one entry per cycle, promotion keys absent, c increments
    assert [t['c'] for t in ev['trace']] == [1, 2]
    for entry in ev['trace']:
        assert set(entry.keys()) == {'c', 'rank', 'comp', 'lcall',
                                     'path', 't1', 'txf'}
    # v2: competition_max = max(at-select 3, per-cycle 4)
    assert ev['competition_max'] == 4


def test_v2_fields_null_without_tactical_data(outcome_recorder_home):
    """A bare attempt (no tactical snapshot, no cycle context) must still
    record — every v2 field degrades to null/0/[] per graceful-absence."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec)
    rec.record_outcome('QSO_LOGGED', SNAPSHOT)

    ev = [e for e in read_events(outcome_recorder_home)
          if e['type'] == 'outcome'][0]
    assert set(ev.keys()) == OUTCOME_FIELDS
    assert ev['success_prob'] is None
    assert ev['strategy'] is None
    assert ev['my_rank_at_select'] is None
    assert ev['behavior_pattern'] is None
    assert ev['competition_at_select'] == 0
    assert ev['competition_src'] is None
    assert ev['trace'] == []


def test_trace_promotion_only_first_non_null(outcome_recorder_home):
    """Promotion keys are lifted on the first cycle that has a non-null
    value and never overwritten by later cycles."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    contexts = iter([
        {'comp': 2, 'success_prob': None, 'strategy': None, 'target_state': None},
        {'comp': 5, 'success_prob': 38, 'strategy': 'wait', 'target_state': 'in_qso'},
        {'comp': 1, 'success_prob': 70, 'strategy': 'call_now', 'target_state': 'cq'},
    ])
    rec.on_target_selected('JA1XYZ', 'PM95', band='20m',
                           tactical={'competition_at_select': 1})
    for _ in range(3):
        rec.on_status_update(True, cycle_context_fn=lambda: next(contexts))
        rec.on_status_update(False)
    rec._target_selected_at -= timedelta(seconds=60)
    rec.record_outcome('CLEARED', SNAPSHOT)

    ev = [e for e in read_events(outcome_recorder_home)
          if e['type'] == 'outcome'][0]
    assert ev['success_prob'] == 38          # cycle 2 wins, cycle 3 ignored
    assert ev['strategy'] == 'wait'
    assert ev['target_state'] == 'in_qso'
    assert ev['competition_max'] == 5        # running max across cycles
    assert len(ev['trace']) == 3
    assert all('success_prob' not in t for t in ev['trace'])


def test_trace_cap_halves_rate_beyond_40(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    rec.on_target_selected('JA1XYZ', 'PM95', band='20m')
    for _ in range(50):
        rec.on_status_update(True, cycle_context_fn=lambda: {'comp': 1})
        rec.on_status_update(False)
    cycles = [t['c'] for t in rec._trace]
    assert cycles[:40] == list(range(1, 41))
    # Beyond the cap only even cycles are kept; gaps stay explicit
    assert cycles[40:] == [42, 44, 46, 48, 50]


def test_trace_capture_failure_never_breaks_cycle_counting(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    def boom():
        raise RuntimeError("widget went away")
    rec.on_target_selected('JA1XYZ', 'PM95', band='20m')
    rec.on_status_update(True, cycle_context_fn=boom)
    rec.on_status_update(False)
    assert rec._tx_cycle_count == 1
    assert rec._trace == []


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


def test_rapid_reselects_after_idle_gap_write_no_stale_session_end(outcome_recorder_home):
    """Regression: field data (2026-04-21T23:15) showed that clicking through
    targets shortly after an idle gap wrote one session_end PER CLICK, each
    stamped with the OLD session's last-activity time and a negative
    elapsed_s. Root cause: _last_activity_time was only updated by
    record_outcome, so every select after the first still saw the stale gap
    and re-ended the freshly started session."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec, cycles=2)
    rec.record_outcome('QSO_LOGGED', dict(SNAPSHOT))

    # Idle for 2 hours: shift everything that happened into the past
    idle = timedelta(hours=2)
    rec._last_activity_time -= idle
    rec._session_start_time -= idle

    # Operator returns and clicks through three targets, transmitting
    # briefly on each (TX is what activates the deferred session)
    make_attempt(rec, call='K1ABC', grid='FN42')
    make_attempt(rec, call='DL1ABC', grid='JO62')
    make_attempt(rec, call='F4XYZ', grid='JN18')

    events = read_events(outcome_recorder_home)
    ends = [e for e in events if e['type'] == 'session_end']
    assert all(e['elapsed_s'] >= 0 for e in ends), ends
    # Only the idle session ends; re-selects continue the new session
    assert len(ends) == 1, [e['type'] for e in events]


def test_session_end_never_predates_session_start(outcome_recorder_home):
    """Even with pathological internal state (stale activity timestamp from
    before the current session), the persisted session_end must not carry a
    ts earlier than its session_start or a negative elapsed_s."""
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec, cycles=2)
    rec._last_activity_time = rec._session_start_time - timedelta(hours=4)
    rec._end_session()

    end = read_events(outcome_recorder_home)[-1]
    assert end['type'] == 'session_end'
    assert end['elapsed_s'] >= 0
    starts = [e for e in read_events(outcome_recorder_home)
              if e['type'] == 'session_start']
    assert end['ts'] >= starts[-1]['ts']


def test_junk_grid_yields_no_distance():
    """_grid_to_latlon range-checks characters; _haversine_km maps the
    rejection to its -1 sentinel (persisted as distance_km: null)."""
    from outcome_recorder import _haversine_km
    assert _haversine_km('FN30', 'ZZ99') == -1
    assert _haversine_km('!!!!', 'FN30') == -1
    assert _haversine_km('FN30', 'PM95') > 0   # valid pair unaffected


def test_followed_false_when_far_from_recommendation(outcome_recorder_home):
    rec = OutcomeRecorder('WU2C', 'FN30')
    make_attempt(rec)
    rec.record_outcome('QSO_LOGGED', dict(
        SNAPSHOT, tx_freq=500, tx_score=40.0))  # 1187 Hz off, score -42

    outcome = [e for e in read_events(outcome_recorder_home)
               if e['type'] == 'outcome'][0]
    assert outcome['followed'] is False
    assert outcome['score_delta'] == 42.0
