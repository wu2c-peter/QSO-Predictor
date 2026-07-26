# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Clock Doctor tests: pure SNTP reply parsing (crafted packets) and the
doctor's checks over fixture snapshots. No network I/O anywhere."""

import struct

import pytest

from diagnostics.doctors.clock import (ClockDoctor, OFFSET_FAIL_S,
                                       OFFSET_WARN_S)
from diagnostics.models import (ClockSnapshot, SNAPSHOT_SCHEMA_VERSION,
                                Severity, StationSnapshot)
from diagnostics.probe_clock import _NTP_EPOCH_OFFSET, _parse_ntp_reply


# ---------------------------------------------------------------------------
# _parse_ntp_reply — crafted server packets
# ---------------------------------------------------------------------------

def _reply(t2: float, t3: float, mode: int = 4, stratum: int = 2) -> bytes:
    data = bytearray(48)
    data[0] = (4 << 3) | mode          # LI=0, VN=4
    data[1] = stratum
    for offset, t in ((32, t2), (40, t3)):
        sec = (int(t) + _NTP_EPOCH_OFFSET) % 2**32   # wraps in 2036, like
        frac = int((t - int(t)) * 2**32)             # a real era-1 server
        struct.pack_into('!II', data, offset, sec, frac)
    return bytes(data)


def test_parse_reply_slow_clock_reads_negative():
    """Server 5 s ahead of us -> our clock is slow -> offset_s -5."""
    offset, delay = _parse_ntp_reply(_reply(t2=1005.1, t3=1005.1),
                                     t1=1000.0, t4=1000.2)
    assert offset == pytest.approx(-5.0, abs=0.01)
    assert delay == pytest.approx(0.2, abs=0.01)


def test_parse_reply_fast_clock_reads_positive():
    offset, _ = _parse_ntp_reply(_reply(t2=995.1, t3=995.1),
                                 t1=1000.0, t4=1000.2)
    assert offset == pytest.approx(5.0, abs=0.01)


def test_parse_reply_rejects_garbage():
    with pytest.raises(ValueError):
        _parse_ntp_reply(b'\x00' * 20, 0, 0)          # short
    with pytest.raises(ValueError):
        _parse_ntp_reply(_reply(0, 0, mode=3), 0, 0)  # not a server reply
    with pytest.raises(ValueError):
        _parse_ntp_reply(_reply(0, 0, stratum=0), 0, 0)  # kiss-of-death


# ---------------------------------------------------------------------------
# ClockDoctor checks
# ---------------------------------------------------------------------------

def _snap(clock):
    return StationSnapshot(schema_version=SNAPSHOT_SCHEMA_VERSION,
                           taken_at_utc='2026-07-26T12:00:00Z',
                           platform='macos', clock=clock)


def _offset_check(clock):
    results = ClockDoctor().run(_snap(clock))
    return next(r for r in results if r.check_id == 'clock/ntp-offset')


def test_offset_unreachable_is_unknown_not_failure():
    r = _offset_check(ClockSnapshot(offset_s=None))
    assert r.severity == Severity.UNKNOWN
    assert 'offline' in r.detail


@pytest.mark.parametrize("offset_s,expected", [
    (0.2, Severity.OK),
    (-0.9, Severity.OK),
    (OFFSET_WARN_S, Severity.WARNING),      # boundary: 1.0 s warns
    (-1.5, Severity.WARNING),
    (OFFSET_FAIL_S, Severity.FAIL),         # boundary: 2.0 s fails
    (30.0, Severity.FAIL),
])
def test_offset_thresholds(offset_s, expected):
    r = _offset_check(ClockSnapshot(offset_s=offset_s,
                                    ntp_server='pool.ntp.org'))
    assert r.severity == expected
    assert 'pool.ntp.org' in r.detail


def test_offset_detail_states_direction():
    assert 'fast' in _offset_check(
        ClockSnapshot(offset_s=3.0, ntp_server='x')).detail
    assert 'slow' in _offset_check(
        ClockSnapshot(offset_s=-3.0, ntp_server='x')).detail


def test_timezone_is_informational():
    results = ClockDoctor().run(_snap(
        ClockSnapshot(offset_s=0.1, ntp_server='x',
                      timezone_name='EDT', utc_offset_min=-240)))
    tz = next(r for r in results if r.check_id == 'clock/timezone')
    assert tz.severity == Severity.INFO
    assert 'UTC-04:00' in tz.detail


def test_missing_clock_domain_is_unknown():
    results = ClockDoctor().run(_snap(None))
    assert [r.check_id for r in results] == ['clock/snapshot-missing']
    assert results[0].severity == Severity.UNKNOWN


def test_clock_doctor_declares_all_platforms():
    d = ClockDoctor()
    assert d.platforms == frozenset({'windows', 'macos', 'linux'})
    assert d.domains == frozenset({'clock'})


# ---------------------------------------------------------------------------
# Review-driven hardening (step-4 adversarial review findings)
# ---------------------------------------------------------------------------

def test_parse_reply_rejects_unsynchronized_servers():
    """RFC 4330 §5: LI=3 (alarm), stratum >15, and a zero transmit stamp
    all mean the server's answer is unusable — accepting one turned a
    booting pool member into a confident false FAIL."""
    li3 = bytearray(_reply(1005.0, 1005.0))
    li3[0] |= 0xC0                                    # LI = 3
    with pytest.raises(ValueError):
        _parse_ntp_reply(bytes(li3), 1000.0, 1000.2)
    with pytest.raises(ValueError):
        _parse_ntp_reply(_reply(1005.0, 1005.0, stratum=16), 1000.0, 1000.2)
    zero_t3 = bytearray(_reply(1005.0, 1005.0))
    zero_t3[40:48] = b'\x00' * 8
    with pytest.raises(ValueError):
        _parse_ntp_reply(bytes(zero_t3), 1000.0, 1000.2)


def test_parse_reply_handles_ntp_era_rollover():
    """After 2036-02-07 the 32-bit NTP seconds wrap; a correct clock must
    not read as 136 years fast. Simulates a checkup run shortly after
    the rollover with a perfectly synced local clock."""
    import time as time_mod
    rollover_unix = 2**32 - _NTP_EPOCH_OFFSET       # 2036-02-07T06:28:16Z
    t_real = rollover_unix + 100.0
    offset, _ = _parse_ntp_reply(_reply(t2=t_real, t3=t_real),
                                 t1=t_real - 0.1, t4=t_real + 0.1)
    assert abs(offset) < 0.2


def test_ok_wording_never_contradicts_the_threshold():
    """999.6 ms used to render as '1000 ms ... inside the ~1 s
    tolerance'. One decimal place keeps the frozen wording honest."""
    r = _offset_check(ClockSnapshot(offset_s=0.9996, ntp_server='x'))
    assert r.severity == Severity.OK
    assert '999.6 ms' in r.detail
    assert '1000 ms' not in r.detail
