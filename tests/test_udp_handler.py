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


# ---------------------------------------------------------------------------
# Multicast membership: join on loopback + every interface, not only
# INADDR_ANY. A lone INADDR_ANY join attaches to the lowest-metric
# multicast route — observed live 2026-08-02: an idle NordVPN adapter
# (metric 261) beat Ethernet (281), leaving QSOP deaf on a group that
# GridTracker and JTAlert received fine.
# ---------------------------------------------------------------------------

import socket
import struct

import udp_handler as udp_mod


def test_membership_requests_include_inaddr_any_and_each_addr():
    reqs = udp_mod.multicast_membership_requests(
        '239.255.0.0', ['127.0.0.1', '192.168.1.10'])
    labels = [label for label, _ in reqs]
    assert labels == ['default', '127.0.0.1', '192.168.1.10']
    group = socket.inet_aton('239.255.0.0')
    assert reqs[0][1] == struct.pack('4sl', group, socket.INADDR_ANY)
    assert reqs[1][1] == struct.pack('4s4s', group,
                                     socket.inet_aton('127.0.0.1'))
    assert reqs[2][1] == struct.pack('4s4s', group,
                                     socket.inet_aton('192.168.1.10'))


def test_join_addrs_loopback_first_and_deduped(monkeypatch):
    monkeypatch.setattr(udp_mod.socket, 'gethostname', lambda: 'shack-pc')
    fake_infos = [
        (socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('192.168.160.60', 0)),
        (socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('192.168.160.60', 0)),
        (socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('10.5.0.2', 0)),
        (socket.AF_INET, socket.SOCK_DGRAM, 17, '', ('127.0.0.1', 0)),
    ]
    monkeypatch.setattr(udp_mod.socket, 'getaddrinfo',
                        lambda *a, **k: fake_infos)
    assert udp_mod.multicast_join_addrs() == \
        ['127.0.0.1', '192.168.160.60', '10.5.0.2']


def test_join_addrs_survives_unresolvable_hostname(monkeypatch):
    """Loopback must still be joined when the hostname doesn't resolve."""
    def boom(*a, **k):
        raise socket.gaierror("nodename nor servname provided")
    monkeypatch.setattr(udp_mod.socket, 'getaddrinfo', boom)
    assert udp_mod.multicast_join_addrs() == ['127.0.0.1']


def test_multicast_handler_joins_multiple_interfaces():
    """End-to-end: a multicast-configured handler must hold at least the
    loopback membership (not just INADDR_ANY) and drop them all on stop."""
    from tests.conftest import StubConfig
    handler = udp_mod.UDPHandler(StubConfig(
        overrides={('NETWORK', 'udp_ip'): '239.255.0.0'}))
    try:
        assert handler.is_multicast
        assert handler._bind_ok
        group = socket.inet_aton('239.255.0.0')
        loopback_mreq = struct.pack('4s4s', group,
                                    socket.inet_aton('127.0.0.1'))
        assert loopback_mreq in handler._joined_memberships
    finally:
        handler.stop()
    assert handler._joined_memberships == []


# ---------------------------------------------------------------------------
# 2026-09 audit: stray datagrams must not hijack click-to-call routing
# or make the health check believe WSJT-X is talking
# ---------------------------------------------------------------------------

def test_non_wsjtx_datagram_is_ignored_for_routing_and_health(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(b'\x00' * 40, ('192.168.1.99', 51000))
    assert handler.request_destination() is None
    assert handler.messages_received == 0
    assert handler._last_packet_time is None
    assert received['decode'] == []


def test_wsjtx_datagram_sets_routing_and_health(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.status(dx_call='JA1XYZ'), ('127.0.0.1', 61234))
    assert handler.request_destination() == ('127.0.0.1', 61234)
    assert handler.messages_received == 1
    assert handler._last_packet_time is not None
    # A later stray packet does not repoint the destination
    handler._parse_packet(b'JUNK' * 10, ('10.0.0.5', 2237))
    assert handler.request_destination() == ('127.0.0.1', 61234)


def test_status_carries_mode(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.status(mode='FT4'))
    assert received['status'][0]['mode'] == 'FT4'


def test_get_diagnostics_does_not_raise(udp_handler):
    """Referenced a renamed attribute (forward_ports) for two releases."""
    handler, _ = udp_handler
    diag = handler.get_diagnostics()
    assert diag['forward_targets'] == []
    assert diag['loop_packets_dropped'] == 0


def test_own_forward_loop_is_detected(udp_handler):
    handler, _ = udp_handler
    assert handler._is_own_forward(('127.0.0.1', handler.port))
    assert not handler._is_own_forward(('127.0.0.1', handler.port + 1))
    assert not handler._is_own_forward(('192.0.2.1', handler.port))
    assert not handler._is_own_forward(None)


def test_udp_port_missing_from_config_does_not_crash():
    """int(None) used to kill the app inside MainWindow.__init__."""
    from tests.conftest import StubConfig
    cfg = StubConfig()
    del cfg.values[('NETWORK', 'udp_port')]
    handler = udp_mod.UDPHandler(cfg)
    try:
        assert handler.port == 2237
    finally:
        handler.sock.close()
