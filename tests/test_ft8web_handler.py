# QSO Predictor
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

"""Tests for the FT8web External Data Stream listener.

Self-contained: includes a minimal RFC 6455 client (masked frames, like a
browser) so no third-party packages are needed. The module-scoped
`stream_scenario` fixture drives one full client lifecycle against a live
FT8WebHandler — connect, all three message types, ping, disconnect,
reconnect, junk frame, disconnect, stop — and the tests assert on the
collected signals and re-broadcast datagrams. Covers:

  1. Signal payloads match UDPHandler's dict shapes exactly.
  2. FT4 mode code mapping, callsign/grid extraction via the shared parser.
  3. Junk (non-JSON) frames are dropped without killing the stream.
  4. Disconnect / reconnect cycle.
  5. Ping -> pong.
  6. WSJT-X re-broadcast on the forward port round-trips through
     UDPHandler's own parser (GridTracker compatibility proxy).
"""

import base64
import json
import secrets
import socket
import struct
import time

import pytest

from tests.conftest import StubConfig


def _free_port():
    """Ask the OS for a currently-free TCP port (avoids a live app on 2442)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MiniWSClient:
    """Just enough RFC 6455 client to act like a browser: masked text frames."""

    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=5)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        self.sock.sendall(
            f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            .encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise ConnectionError("handshake failed")
            response += chunk
        if b"101" not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"handshake rejected: {response[:80]!r}")

    def _send_frame(self, opcode, payload):
        mask = secrets.token_bytes(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 1 << 16:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(header + mask + masked)

    def send_text(self, text):
        self._send_frame(0x1, text.encode("utf-8"))

    def ping_and_wait_pong(self):
        self._send_frame(0x9, b"hb")
        header = self.sock.recv(2)
        if len(header) != 2 or header[0] & 0x0F != 0xA:
            return False
        length = header[1] & 0x7F
        if length:
            self.sock.recv(length)
        return True

    def close(self):
        try:
            self._send_frame(0x8, struct.pack(">H", 1000))
            self.sock.close()
        except OSError:
            pass


@pytest.fixture(scope="module")
def stream_scenario():
    """Run the full client lifecycle once; yield everything the tests assert on.

    Signals are connected DirectConnection because there is no Qt event loop
    in the test process. The sleeps let the handler's serve thread keep up.
    """
    from PyQt6.QtCore import Qt
    from ft8web_handler import FT8WebHandler
    from udp_handler import UDPHandler

    direct = Qt.ConnectionType.DirectConnection

    fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fwd_sock.bind(("127.0.0.1", 0))
    fwd_sock.settimeout(0.2)
    fwd_port = fwd_sock.getsockname()[1]
    ws_port = _free_port()

    handler = FT8WebHandler(StubConfig(
        overrides={('FT8WEB', 'enabled'): 'true',
                   ('FT8WEB', 'ws_port'): str(ws_port)},
        forward_ports=[fwd_port]))
    received = {"decode": [], "status": [], "qso_logged": [], "state": []}
    handler.new_decode.connect(lambda d: received["decode"].append(d), direct)
    handler.status_update.connect(lambda d: received["status"].append(d), direct)
    handler.qso_logged.connect(lambda d: received["qso_logged"].append(d), direct)
    handler.client_state_changed.connect(lambda c: received["state"].append(c), direct)
    handler.start()
    time.sleep(0.5)

    envelope = {"src": "FT8web", "ver": 1, "utc": "2026-07-03T18:30:00Z"}

    # --- Session 1: all three message types + ping/pong ---
    ws = MiniWSClient("localhost", ws_port)
    ws.send_text(json.dumps({
        **envelope, "type": "status",
        "dialFreqHz": 14074000, "mode": "FT8", "myCall": "WU2C",
        "myGrid": "FN30", "txFreqHz": 1512, "txEnabled": True,
        "transmitting": False, "dxCall": "ja1xyz",
    }))
    ws.send_text(json.dumps({
        **envelope, "type": "decode",
        "dialFreqHz": 14074000, "mode": "FT8",
        "decodes": [
            {"time": "183000", "snr": -12, "freq": 1687, "message": "CQ JA1XYZ PM95"},
            {"time": "183000", "snr": 3, "freq": 2450, "message": "WU2C K1ABC -07"},
        ],
    }))
    ws.send_text(json.dumps({
        **envelope, "type": "qso_logged",
        "call": "JA1XYZ", "grid": "PM95", "rstSent": "-12", "rstRcvd": "-07",
        "dialFreqHz": 14074000, "mode": "FT8", "band": "20m",
    }))
    pong_ok = ws.ping_and_wait_pong()
    time.sleep(0.5)
    ws.close()
    time.sleep(0.5)

    # --- Session 2: reconnect works; junk frame is dropped harmlessly ---
    ws = MiniWSClient("localhost", ws_port)
    ws.send_text(json.dumps({
        **envelope, "type": "decode", "dialFreqHz": 7047500, "mode": "FT4",
        "decodes": [{"time": "1831", "snr": 5, "freq": 800, "message": "CQ DL1ABC JO62"}],
    }))
    ws.send_text("this is not json")
    ws.send_text(json.dumps({
        **envelope, "type": "decode", "dialFreqHz": 7047500, "mode": "FT4",
        "decodes": [{"time": "1831", "snr": -3, "freq": 900, "message": "CQ F4XYZ JN18"}],
    }))
    time.sleep(0.5)
    ws.close()
    time.sleep(0.3)

    # --- Drain the forward port, round-trip through UDPHandler's parser ---
    packets = []
    while True:
        try:
            data, _ = fwd_sock.recvfrom(4096)
            packets.append(data)
        except socket.timeout:
            break

    udp = UDPHandler(StubConfig())
    roundtrip = {"decode": [], "status": [], "qso_logged": []}
    udp.new_decode.connect(lambda d: roundtrip["decode"].append(d), direct)
    udp.status_update.connect(lambda d: roundtrip["status"].append(d), direct)
    udp.qso_logged.connect(lambda d: roundtrip["qso_logged"].append(d), direct)
    for pkt in packets:
        udp._parse_packet(pkt)
    udp.sock.close()

    handler.stop()
    stopped = not handler.running
    fwd_sock.close()

    yield {"received": received, "pong_ok": pong_ok, "packets": packets,
           "roundtrip": roundtrip, "stopped": stopped}


def test_client_state_transitions(stream_scenario):
    # connect, disconnect, reconnect across the two sessions
    assert stream_scenario["received"]["state"][:3] == [True, False, True]


def test_ping_gets_pong(stream_scenario):
    assert stream_scenario["pong_ok"]


def test_status_payload_matches_udp_shape(stream_scenario):
    st = stream_scenario["received"]["status"][0]
    assert st == {'dial_freq': 14074000, 'dx_call': 'JA1XYZ', 'dx_grid': '',
                  'tx_df': 1512, 'tx_enabled': True, 'transmitting': False,
                  'de_call': 'WU2C', 'de_grid': 'FN30', 'special_mode': 0}


def test_decode_payload_matches_udp_shape(stream_scenario):
    decodes = stream_scenario["received"]["decode"]
    assert decodes[0] == {'time': '1830', 'snr': -12, 'dt': 0.0, 'freq': 1687,
                          'mode': '~', 'message': 'CQ JA1XYZ PM95',
                          'call': 'JA1XYZ', 'grid': 'PM95'}
    assert decodes[1]['call'] == 'K1ABC'


def test_ft4_mode_code(stream_scenario):
    assert stream_scenario["received"]["decode"][2]['mode'] == '+'


def test_junk_frame_does_not_kill_stream(stream_scenario):
    decodes = stream_scenario["received"]["decode"]
    assert len(decodes) == 4
    assert decodes[3]['call'] == 'F4XYZ'   # arrived after the non-JSON frame


def test_qso_logged_payload(stream_scenario):
    assert stream_scenario["received"]["qso_logged"] == [
        {'dx_call': 'JA1XYZ', 'dx_grid': 'PM95'}]


def test_rebroadcast_roundtrips_through_udp_parser(stream_scenario):
    rt = stream_scenario["roundtrip"]
    assert len(rt["status"]) == 1
    assert rt["status"][0]["dial_freq"] == 14074000
    assert len(rt["decode"]) == 4
    assert {d["message"] for d in rt["decode"]} == {
        "CQ JA1XYZ PM95", "WU2C K1ABC -07", "CQ DL1ABC JO62", "CQ F4XYZ JN18"}
    assert rt["qso_logged"] == [{'dx_call': 'JA1XYZ', 'dx_grid': 'PM95'}]


def test_stop_terminates_listener(stream_scenario):
    assert stream_scenario["stopped"]
