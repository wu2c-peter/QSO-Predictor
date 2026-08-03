# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Click-to-call: outgoing Reply/Configure requests to WSJT-X.

Wire format checked field-by-field against the WSJT-X NetworkMessage
QDataStream spec, independent of the builders (same philosophy as
wsjtx_packets.py on the receive side). Reply is CQ/QRZ-only by WSJT-X's
design; Configure (added in WSJT-X 2.3) sets any DX Call.
"""

import socket
import struct

import pytest

from tests import wsjtx_packets as pkt
from tests.conftest import StubConfig
from udp_handler import UDPHandler
from utils import wsjtx_protocol

MAGIC = 0xADBCCBDA


def read_utf8(data, idx):
    n = struct.unpack('>I', data[idx:idx + 4])[0]
    idx += 4
    if n == 0xFFFFFFFF:
        return None, idx
    return data[idx:idx + n].decode(), idx + n


def read_header(data, expected_type):
    magic, schema, msg_type = struct.unpack('>III', data[:12])
    assert magic == MAGIC
    assert schema == 2
    assert msg_type == expected_type
    return read_utf8(data, 12)


def test_build_reply_wire_format():
    p = wsjtx_protocol.build_reply(
        'WSJT-X - rig1', time_ms=66615000, snr=-12, dt=0.3, freq=1687,
        mode_code='~', message='CQ JA1XYZ PM95')
    client_id, idx = read_header(p, 4)
    assert client_id == 'WSJT-X - rig1'
    assert struct.unpack('>I', p[idx:idx + 4])[0] == 66615000  # exact ms
    idx += 4
    assert struct.unpack('>i', p[idx:idx + 4])[0] == -12
    idx += 4
    assert struct.unpack('>d', p[idx:idx + 8])[0] == pytest.approx(0.3)
    idx += 8
    assert struct.unpack('>I', p[idx:idx + 4])[0] == 1687
    idx += 4
    mode, idx = read_utf8(p, idx)
    assert mode == '~'
    message, idx = read_utf8(p, idx)
    assert message == 'CQ JA1XYZ PM95'
    assert p[idx] == 0          # low confidence
    assert p[idx + 1] == 0      # keyboard modifiers
    assert idx + 2 == len(p)


def test_build_configure_wire_format():
    p = wsjtx_protocol.build_configure('WSJT-X', 'V31DL', 'EK57')
    client_id, idx = read_header(p, 15)
    assert client_id == 'WSJT-X'
    mode, idx = read_utf8(p, idx)
    assert mode == ''                                     # no change
    assert struct.unpack('>I', p[idx:idx + 4])[0] == 0xFFFFFFFF  # freq tol
    idx += 4
    submode, idx = read_utf8(p, idx)
    assert submode == ''
    assert p[idx] == 0                                    # fast mode
    idx += 1
    assert struct.unpack('>I', p[idx:idx + 4])[0] == 0xFFFFFFFF  # T/R period
    idx += 4
    assert struct.unpack('>I', p[idx:idx + 4])[0] == 0xFFFFFFFF  # RX DF
    idx += 4
    dx_call, idx = read_utf8(p, idx)
    assert dx_call == 'V31DL'
    dx_grid, idx = read_utf8(p, idx)
    assert dx_grid == 'EK57'
    assert p[idx] == 1                                    # generate messages
    assert idx + 1 == len(p)


# ---------------------------------------------------------------------------
# Decode parsing must retain the raw fields a Reply echoes
# ---------------------------------------------------------------------------

def test_decode_retains_raw_reply_fields(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(pkt.decode("CQ JA1XYZ PM95", h=18, m=30, s=15,
                                     snr=-12, dt=0.3, freq=1687))
    d = received['decode'][0]
    assert d['time_ms'] == ((18 * 60 + 30) * 60 + 15) * 1000
    assert d['raw_dt'] == pytest.approx(0.3)
    assert d['received_at'] > 0


def test_client_id_captured_from_packets(udp_handler):
    """Requests must echo the sending instance's id or WSJT-X drops them."""
    handler, _ = udp_handler
    assert handler._last_client_id == 'WSJT-X'   # default
    handler._parse_packet(pkt.decode("CQ JA1XYZ PM95"))
    assert handler._last_client_id == pkt.CLIENT_ID


# ---------------------------------------------------------------------------
# Request routing
# ---------------------------------------------------------------------------

def test_no_destination_before_any_packet(udp_handler):
    handler, _ = udp_handler
    assert handler.request_destination() is None
    assert handler.send_configure('K1ABC') is False
    assert handler.send_reply({'time_ms': 0, 'snr': 0, 'freq': 1500,
                               'message': 'CQ K1ABC'}) is False


def test_reply_requires_raw_time(udp_handler):
    """FT8web-sourced decodes lack time_ms and must never produce a
    malformed Reply."""
    handler, _ = udp_handler
    handler._last_source_addr = ('127.0.0.1', 1)
    assert handler.send_reply({'snr': 0, 'freq': 1500,
                               'message': 'CQ K1ABC'}) is False


def test_multicast_requests_still_reply_to_source():
    """2026-08-02, learned live twice over: WSJT-X does NOT listen on its
    configured UDP server port (wsjtx.exe held no 2237 socket) — it
    accepts requests only on the ephemeral socket it transmits from.
    Group-addressed requests reached only the other listeners, which
    ignored them. Requests therefore go to the packet source in EVERY
    mode, multicast included."""
    handler = UDPHandler(StubConfig(
        overrides={('NETWORK', 'udp_ip'): '239.255.0.0',
                   ('NETWORK', 'udp_port'): '2237'}))
    try:
        assert handler.request_destination() is None    # nothing heard yet
        handler._last_source_addr = ('192.168.160.60', 53749)
        assert handler.request_destination() == ('192.168.160.60', 53749)
    finally:
        handler.stop()


def test_unicast_request_goes_to_packet_source(udp_handler):
    """End-to-end over real sockets: the request must land on the socket
    the decodes came from (WSJT-X's, on a direct connection)."""
    handler, _ = udp_handler
    wsjtx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    wsjtx_sock.bind(('127.0.0.1', 0))
    wsjtx_sock.settimeout(1.0)
    try:
        handler._last_source_addr = wsjtx_sock.getsockname()
        assert handler.send_configure('V31DL', 'EK57') is True
        data, _ = wsjtx_sock.recvfrom(4096)
        client_id, idx = read_header(data, 15)
        assert client_id == 'WSJT-X'
    finally:
        wsjtx_sock.close()
