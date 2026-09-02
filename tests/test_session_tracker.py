# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Live pileup tracking: sweep detection, cycle clock, target lifecycle.

2026-09 audit findings encoded here:
- The Spearman correlation imported scipy, which the frozen builds
  deliberately exclude; the ImportError fallback returned 0.0, so no
  exe/DMG/MSIX could ever classify a methodical sweep — the sweep-bias
  feature (commit 0c41e87) was inert for every packaged user.
- FT4 (7.5 s) was clocked as FT8 (15 s).
- Clear Target left `target_session` in place (the old integration
  wrote attributes the tracker never had), so the cleared station's
  pileup kept updating and its pattern could re-arm the band map tilt.
- Sessions were never evicted; a station worked an hour ago replayed
  its stale sweep on the next answer.
"""

from datetime import datetime, timedelta

import pytest

from local_intel.models import Decode, PickingStyle, AnalysisConfig
from local_intel.session_tracker import SessionTracker, spearman_correlation


# ---------------------------------------------------------------------------
# stdlib Spearman
# ---------------------------------------------------------------------------

class TestSpearman:
    def test_perfect_ascending(self):
        assert spearman_correlation([300, 800, 1200, 1900, 2500]) == pytest.approx(1.0)

    def test_perfect_descending(self):
        assert spearman_correlation([2500, 1900, 1200, 800, 300]) == pytest.approx(-1.0)

    def test_ties_use_mean_rank(self):
        # scipy.stats.spearmanr([0,1,2,3], [1, 1, 2, 3]) == 0.9486832980505138
        assert spearman_correlation([1, 1, 2, 3]) == pytest.approx(0.94868, abs=1e-4)

    def test_known_value(self):
        # scipy.stats.spearmanr(range(6), [3, 1, 4, 1, 5, 9]) == 0.66674...
        assert spearman_correlation([3, 1, 4, 1, 5, 9]) == pytest.approx(0.6667, abs=1e-3)

    def test_degenerate_inputs(self):
        assert spearman_correlation([]) == 0.0
        assert spearman_correlation([5, 5]) == 0.0
        assert spearman_correlation([7, 7, 7, 7]) == 0.0   # constant → no correlation

    def test_oh0erf_high_to_low_sweep(self):
        # The 2026-08-06 session: the target worked its pileup from the
        # top of the passband downwards, with one out-of-order pick.
        assert spearman_correlation([2508, 2210, 1900, 2050, 1400, 1087]) < -0.5


# ---------------------------------------------------------------------------
# SessionTracker
# ---------------------------------------------------------------------------

def _decode(message, freq, snr=-10, ts=None, mode='FT8'):
    return Decode(timestamp=ts or datetime.now(), snr=snr, dt=0.1,
                  frequency=freq, mode=mode, message=message,
                  callsign=message.split()[1] if message.startswith('CQ') else message.split()[1])


def _feed(tracker, message, freq, snr=-10, ts=None, mode='FT8'):
    from local_intel.log_parser import MessageParser
    d = _decode(message, freq, snr, ts, mode)
    parsed = MessageParser.parse(message)
    d.callsign = parsed.caller
    d.grid = parsed.grid
    d.is_cq = parsed.is_cq
    d.is_reply = parsed.is_reply
    d.replying_to = parsed.callee
    tracker.process_decode(d)


@pytest.fixture
def tracker(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    return SessionTracker('WU2C', AnalysisConfig())


def _run_pileup(tracker, target, picks):
    """Callers call the target, target answers them in `picks` order.

    The weakest caller is answered first (SNR rises with pick order), so
    the pickup order is explained by FREQUENCY, not by signal strength —
    a loudest-first classification would be wrong here."""
    patterns = []
    tracker.on_pattern_detected(patterns.append)
    tracker.set_target(target)
    callers = {f"K{i}ABC": f for i, f in enumerate(picks)}
    for i, (call, freq) in enumerate(callers.items()):
        _feed(tracker, f"{target} {call} FN42", freq, snr=-20 + i)
    for call, freq in callers.items():
        _feed(tracker, f"{call} {target} -05", 1500)
    return patterns


def test_high_to_low_sweep_is_detected_without_scipy(tracker):
    patterns = _run_pileup(tracker, 'OH0ERF', [2508, 2210, 1900, 2050, 1400, 1087])
    assert patterns, "pattern callback never fired"
    assert patterns[-1].style is PickingStyle.METHODICAL_HIGH_LOW
    assert patterns[-1].style.sweep_direction() == +1
    assert patterns[-1].confidence > 0.5


def test_low_to_high_sweep(tracker):
    patterns = _run_pileup(tracker, 'JA1XYZ', [400, 700, 1100, 1600, 2100, 2600])
    assert patterns[-1].style is PickingStyle.METHODICAL_LOW_HIGH


def test_clear_target_stops_tracking(tracker):
    tracker.set_target('OH0ERF')
    _feed(tracker, "OH0ERF K1ABC FN42", 1200)
    assert tracker.get_pileup_info()['size'] == 1
    tracker.clear_target()
    assert tracker.target_session is None
    assert tracker.get_pileup_info() is None
    _feed(tracker, "OH0ERF K2XYZ FN42", 1300)     # must be ignored now
    assert tracker.target_session is None


def test_pattern_callback_not_fired_after_clear(tracker):
    patterns = []
    tracker.on_pattern_detected(patterns.append)
    tracker.set_target('OH0ERF')
    for i, f in enumerate([2500, 2100, 1700, 1300, 900]):
        _feed(tracker, f"OH0ERF K{i}ABC FN42", f)
    tracker.clear_target()
    for i in range(5):
        _feed(tracker, f"K{i}ABC OH0ERF -05", 1500)
    assert patterns == []


def test_idle_sessions_are_evicted(tracker):
    tracker.config.session_timeout_minutes = 10
    tracker.set_target('OH0ERF')
    tracker.target_session.last_activity = datetime.now() - timedelta(minutes=30)
    tracker.set_target('JA1XYZ')
    assert 'OH0ERF' not in tracker.active_sessions


def test_resumed_session_drops_stale_answers(tracker):
    tracker.config.session_timeout_minutes = 10
    tracker.set_target('OH0ERF')
    for i, f in enumerate([2500, 2100, 1700, 1300, 900]):
        _feed(tracker, f"OH0ERF K{i}ABC FN42", f)
        _feed(tracker, f"K{i}ABC OH0ERF -05", 1500)
    session = tracker.target_session
    assert len(session.answered_calls) == 5
    for a in session.answered_calls:
        a.answered_at = datetime.now() - timedelta(minutes=45)
    session.last_activity = datetime.now()      # keep it from being evicted
    tracker.set_target('JA1XYZ')
    tracker.set_target('OH0ERF')
    assert tracker.target_session.answered_calls == []


class TestCycleClock:
    def test_ft8_is_15s(self, tracker):
        t0 = datetime(2026, 9, 1, 12, 0, 0)
        tracker._update_cycle(t0, 'FT8')
        tracker._update_cycle(t0 + timedelta(seconds=14), 'FT8')
        assert tracker.current_cycle == 0
        tracker._update_cycle(t0 + timedelta(seconds=15), 'FT8')
        assert tracker.current_cycle == 1

    def test_ft4_is_7_5s(self, tracker):
        t0 = datetime(2026, 9, 1, 12, 0, 0)
        tracker._update_cycle(t0, 'FT4')
        tracker._update_cycle(t0 + timedelta(seconds=15), 'FT4')
        assert tracker.current_cycle == 2

    def test_jitter_does_not_lose_cycles(self, tracker):
        """Decode bursts land ~0.2 s late; snapping the reference to the
        burst time used to drop about one boundary in two."""
        t0 = datetime(2026, 9, 1, 12, 0, 0)
        tracker._update_cycle(t0, 'FT8')
        for n in range(1, 21):
            tracker._update_cycle(t0 + timedelta(seconds=15 * n + 0.2 * (n % 3)), 'FT8')
        assert tracker.current_cycle == 20
