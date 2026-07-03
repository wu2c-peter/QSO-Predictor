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

"""Validation harness for the FT8web External Data Stream listener.

Run after rebasing feat/ft8web-stream-listener (or after any change that
touches ft8web_handler.py, udp_handler.py, utils/wsjtx_protocol.py, or the
MainWindow signal wiring):

    ./venv/bin/python3 tests/test_ft8web_handler.py

Self-contained: includes a minimal RFC 6455 client (masked frames, like a
browser) so no third-party packages are needed. Covers:

  1. Signal payloads match UDPHandler's dict shapes exactly.
  2. FT4 mode code mapping, callsign/grid extraction via the shared parser.
  3. Junk (non-JSON) frames are dropped without killing the stream.
  4. Disconnect / reconnect cycle.
  5. Ping -> pong.
  6. WSJT-X re-broadcast on the forward port round-trips through
     UDPHandler's own parser (GridTracker compatibility proxy).
"""

import base64
import hashlib
import json
import os
import secrets
import socket
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WS_PORT = 2443   # avoid clashing with a live app on 2442
FWD_PORT = 2244


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
        assert len(header) == 2 and header[0] & 0x0F == 0xA, "expected pong"
        length = header[1] & 0x7F
        if length:
            self.sock.recv(length)

    def close(self):
        try:
            self._send_frame(0x8, struct.pack(">H", 1000))
            self.sock.close()
        except OSError:
            pass


class StubConfig:
    def get(self, section, key, fallback=None):
        vals = {
            ('FT8WEB', 'enabled'): 'true',
            ('FT8WEB', 'ws_port'): str(WS_PORT),
            ('NETWORK', 'udp_port'): '2237',
            ('NETWORK', 'udp_ip'): '127.0.0.1',
        }
        return vals.get((section, key), fallback)

    def get_forward_ports(self):
        return [FWD_PORT]


def main():
    from PyQt6.QtCore import Qt
    from ft8web_handler import FT8WebHandler
    from udp_handler import UDPHandler

    DIRECT = Qt.ConnectionType.DirectConnection  # no Qt event loop here

    fwd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fwd_sock.bind(("127.0.0.1", FWD_PORT))
    fwd_sock.settimeout(0.2)

    handler = FT8WebHandler(StubConfig())
    received = {"decode": [], "status": [], "qso_logged": [], "state": []}
    handler.new_decode.connect(lambda d: received["decode"].append(d), DIRECT)
    handler.status_update.connect(lambda d: received["status"].append(d), DIRECT)
    handler.qso_logged.connect(lambda d: received["qso_logged"].append(d), DIRECT)
    handler.client_state_changed.connect(lambda c: received["state"].append(c), DIRECT)
    handler.start()
    time.sleep(0.5)

    envelope = {"src": "FT8web", "ver": 1, "utc": "2026-07-03T18:30:00Z"}

    # --- Session 1: all three message types + ping/pong ---
    ws = MiniWSClient("localhost", WS_PORT)
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
    ws.ping_and_wait_pong()
    time.sleep(0.5)
    ws.close()
    time.sleep(0.5)

    # --- Session 2: reconnect works; junk frame is dropped harmlessly ---
    ws = MiniWSClient("localhost", WS_PORT)
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

    # --- Assertions: signal payloads (must stay identical to UDPHandler's) ---
    assert received["state"][:3] == [True, False, True], received["state"]
    st = received["status"][0]
    assert st == {'dial_freq': 14074000, 'dx_call': 'JA1XYZ', 'dx_grid': '',
                  'tx_df': 1512, 'tx_enabled': True, 'transmitting': False,
                  'de_call': 'WU2C', 'de_grid': 'FN30', 'special_mode': 0}, st
    assert len(received["decode"]) == 4, received["decode"]
    d0 = received["decode"][0]
    assert d0 == {'time': '1830', 'snr': -12, 'dt': 0.0, 'freq': 1687,
                  'mode': '~', 'message': 'CQ JA1XYZ PM95',
                  'call': 'JA1XYZ', 'grid': 'PM95'}, d0
    assert received["decode"][1]['call'] == 'K1ABC'
    assert received["decode"][2]['mode'] == '+'       # FT4 code
    assert received["decode"][3]['call'] == 'F4XYZ'   # survived the junk frame
    assert received["qso_logged"] == [{'dx_call': 'JA1XYZ', 'dx_grid': 'PM95'}]

    # --- Assertions: forward-port re-broadcast parses via UDPHandler ---
    packets = []
    while True:
        try:
            data, _ = fwd_sock.recvfrom(4096)
            packets.append(data)
        except socket.timeout:
            break

    udp = UDPHandler(StubConfig())
    rt = {"decode": [], "status": [], "qso_logged": []}
    udp.new_decode.connect(lambda d: rt["decode"].append(d), DIRECT)
    udp.status_update.connect(lambda d: rt["status"].append(d), DIRECT)
    udp.qso_logged.connect(lambda d: rt["qso_logged"].append(d), DIRECT)
    for pkt in packets:
        udp._parse_packet(pkt)

    assert len(rt["status"]) == 1 and rt["status"][0]["dial_freq"] == 14074000
    assert len(rt["decode"]) == 4
    assert {d["message"] for d in rt["decode"]} == {
        "CQ JA1XYZ PM95", "WU2C K1ABC -07", "CQ DL1ABC JO62", "CQ F4XYZ JN18"}
    assert rt["qso_logged"] == [{'dx_call': 'JA1XYZ', 'dx_grid': 'PM95'}]

    handler.stop()
    assert not handler.running
    fwd_sock.close()
    print(f"OK: {len(received['decode'])} decodes, 1 status, 1 qso_logged, "
          f"{len(packets)} re-broadcast datagrams — all assertions passed")


if __name__ == "__main__":
    main()
