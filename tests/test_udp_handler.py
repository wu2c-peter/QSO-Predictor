# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""WSJT-X/JTDX UDP protocol parsing.

Most cases here encode a historical, user-reported regression — the comment
on each says which. If one of these goes red, a past bug is back.
"""

import pytest

from tests import wsjtx_packets as pkt


# ---------------------------------------------------------------------------
# Decode (Type 2): callsign / grid extraction from the message text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message, call, grid", [
    # Plain CQ with grid
    ("CQ JA1XYZ PM95", "JA1XYZ", "PM95"),
    # Directed CQ
    ("CQ DX K1ABC FN42", "K1ABC", "FN42"),
    ("CQ POTA K1ABC FN42", "K1ABC", "FN42"),
    # Reply with report — no grid
    ("WU2C K1ABC -07", "K1ABC", ""),
    ("WU2C K1ABC R-15", "K1ABC", ""),
    ("WU2C K1ABC +03", "K1ABC", ""),
    # v2.1.2: RR73 is an FT8 ack token, NOT a grid square (RR73 = valid
    # Maidenhead syntax but must be treated as suffix)
    ("WU2C K1ABC RR73", "K1ABC", ""),
    ("WU2C K1ABC RRR", "K1ABC", ""),
    ("WU2C K1ABC 73", "K1ABC", ""),
    # v2.1.3: AP (a priori) decode indicators a1-a7 must be stripped
    # before extraction (reported by Brian KB1OPD)
    ("WU2C K1ABC -07 a2", "K1ABC", ""),
    ("CQ JA1XYZ PM95 a7", "JA1XYZ", "PM95"),
    # Hashed (nonstandard) callsigns arrive in <angle brackets>
    ("WU2C <KH1/KH7Z> RR73", "KH1/KH7Z", ""),
    # Two-token messages: second token is the sender
    ("K1ABC WU2C", "WU2C", ""),
    ("CQ K1ABC", "K1ABC", ""),
])
def test_decode_extraction(udp_handler, message, call, grid):
    handler, received = udp_handler
    handler._parse_packet(pkt.decode(message))
    assert len(received['decode']) == 1
    d = received['decode'][0]
    assert d['call'] == call
    assert d['grid'] == grid
    assert d['message'] == message


def test_decode_fields(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(
        pkt.decode("CQ JA1XYZ PM95", h=18, m=30, s=15, snr=-12, dt=0.3,
                   freq=1687, mode='~'))
    d = received['decode'][0]
    assert d['time'] == '1830'   # HHMM (seconds dropped)
    assert d['snr'] == -12
    assert d['dt'] == 0.3
    assert d['freq'] == 1687
    assert d['mode'] == '~'


def test_decode_midnight_time(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.decode("CQ JA1XYZ PM95", h=0, m=5))
    assert received['decode'][0]['time'] == '0005'


# ---------------------------------------------------------------------------
# Status (Type 1)
# ---------------------------------------------------------------------------

def test_status_full(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.status(
        dial_freq=14074000, dx_call='JA1XYZ', tx_df=1512,
        tx_enabled=True, transmitting=True,
        de_call='WU2C', de_grid='FN30', dx_grid='PM95'))
    assert len(received['status']) == 1
    st = received['status'][0]
    assert st['dial_freq'] == 14074000
    assert st['dx_call'] == 'JA1XYZ'
    assert st['dx_grid'] == 'PM95'
    assert st['tx_df'] == 1512
    assert st['tx_enabled'] is True
    assert st['transmitting'] is True
    assert st['de_call'] == 'WU2C'
    assert st['de_grid'] == 'FN30'


def test_status_truncated_older_client(udp_handler):
    """v2.3.0: fields 12-18 may be absent in older WSJT-X/JTDX — the
    packet must still parse with empty defaults, not be dropped."""
    handler, received = udp_handler
    handler._parse_packet(pkt.status(
        dial_freq=7074000, dx_call='DL1ABC', tx_df=800,
        truncate_after_txdf=True))
    assert len(received['status']) == 1
    st = received['status'][0]
    assert st['dial_freq'] == 7074000
    assert st['dx_call'] == 'DL1ABC'
    assert st['tx_df'] == 800
    assert st['de_call'] == ''
    assert st['special_mode'] == 0


def test_status_fox_hound_special_mode(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.status(dx_call='3Y0J', special_mode=7))  # Hound
    assert received['status'][0]['special_mode'] == 7


# ---------------------------------------------------------------------------
# QSO Logged (Type 5): QDateTime width varies between implementations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dt_bytes", [
    pkt.qdatetime(timespec=1),               # 13 bytes: WSJT-X UTC
    pkt.qdatetime(timespec=2, offset=3600),  # 17 bytes: OffsetFromUTC
], ids=["qdatetime-13", "qdatetime-17"])
def test_qso_logged_qdatetime_variants(udp_handler, dt_bytes):
    """v2.0.3: the parser auto-detects the QDateTime width by validating
    the callsign that follows (suggested by Warren KC0GU)."""
    handler, received = udp_handler
    handler._parse_packet(pkt.qso_logged(dx_call='K1ABC', dx_grid='FN42',
                                         dt=dt_bytes))
    assert received['qso_logged'] == [{'dx_call': 'K1ABC', 'dx_grid': 'FN42'}]


def test_qso_logged_compound_call(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.qso_logged(dx_call='KH1/KH7Z', dx_grid=''))
    assert received['qso_logged'][0]['dx_call'] == 'KH1/KH7Z'


# ---------------------------------------------------------------------------
# Robustness: garbage in, nothing out (and no crash)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data", [
    b'',
    b'\x00',
    b'not a wsjtx packet at all',
    b'\xad\xbc\xcb\xda',                          # magic only, truncated
    pkt.header(2),                                # decode with no body
    b'\xde\xad\xbe\xef' + pkt.decode("CQ X1X")[4:],  # wrong magic
], ids=["empty", "one-byte", "text", "magic-only", "headerless", "bad-magic"])
def test_garbage_packets_ignored(udp_handler, data):
    handler, received = udp_handler
    handler._parse_packet(data)   # must not raise
    assert received['decode'] == []
    assert received['status'] == []
    assert received['qso_logged'] == []


def test_heartbeat_ignored(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.heartbeat())
    assert received == {'decode': [], 'status': [], 'qso_logged': []}


# ---------------------------------------------------------------------------
# Dual-source detection: has_recent_data() feeds the HealthMonitor's
# "Two data sources active" warning when FT8web is connected alongside
# WSJT-X/JTDX. Heartbeats must NOT count — an idle-but-open WSJT-X is fine.
# ---------------------------------------------------------------------------

def test_has_recent_data_false_initially(udp_handler):
    handler, _ = udp_handler
    assert not handler.has_recent_data()


def test_heartbeat_does_not_count_as_recent_data(udp_handler):
    handler, _ = udp_handler
    handler._parse_packet(pkt.heartbeat())
    assert not handler.has_recent_data()


@pytest.mark.parametrize("packet", [
    pkt.status(dx_call='JA1XYZ'),
    pkt.decode("CQ JA1XYZ PM95"),
    pkt.qso_logged(),
], ids=['status', 'decode', 'qso_logged'])
def test_data_bearing_packets_count_as_recent_data(udp_handler, packet):
    handler, _ = udp_handler
    handler._parse_packet(packet)
    assert handler.has_recent_data()


def test_has_recent_data_expires_outside_window(udp_handler):
    handler, _ = udp_handler
    handler._parse_packet(pkt.status(dx_call='JA1XYZ'))
    handler._last_data_time -= 120   # backdate beyond the 60 s default
    assert not handler.has_recent_data()
    assert handler.has_recent_data(window_seconds=300)
