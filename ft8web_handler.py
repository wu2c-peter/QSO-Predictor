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

"""FT8web External Data Stream listener.

Accepts FT8web's browser-originated WebSocket connection (JSON, schema v1
— see https://github.com/ok1cdj/FT8web/pull/10) and emits the same Qt
signals as UDPHandler, so MainWindow wires both sources to the same slots.

Also optionally re-broadcasts each message as a WSJT-X-format UDP datagram
to the configured forward ports, so downstream apps (GridTracker, JTAlert,
loggers) work while QSOP runs — no separate bridge process needed.

The WebSocket server is pure stdlib (RFC 6455 server handshake + frame
parsing) to avoid adding a dependency to the packaged builds. The browser
always initiates the connection; nothing here dials out. Binds localhost
only. The stream is one-way: nothing is ever sent back to FT8web except
protocol-level pong/close frames.
"""

import base64
import hashlib
import json
import logging
import socket
import struct
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

from udp_handler import parse_decode_message
from utils import wsjtx_protocol

logger = logging.getLogger(__name__)

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
CLIENT_ID = "FT8web"
HEARTBEAT_INTERVAL = 15  # seconds, matches WSJT-X


class FT8WebHandler(QObject):
    """WebSocket listener for the FT8web External Data Stream."""

    new_decode = pyqtSignal(dict)
    status_update = pyqtSignal(dict)
    qso_logged = pyqtSignal(dict)
    client_state_changed = pyqtSignal(bool)  # True = FT8web connected

    def __init__(self, config):
        super().__init__()
        self.enabled = str(config.get('FT8WEB', 'enabled', fallback='false')).lower() == 'true'
        try:
            self.port = int(config.get('FT8WEB', 'ws_port', fallback='2442'))
        except (TypeError, ValueError):
            self.port = 2442
        self.forward_ports = config.get_forward_ports()

        self.running = False
        self._server_sock = None
        self._thread = None
        self._client_connected = False
        self.messages_received = 0
        self._decodes_received = 0
        self._last_message_time = None
        self._forward_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._forward_errors_logged = set()

    # ------------------------------------------------------------------ #
    # Lifecycle (mirrors UDPHandler.start/stop)
    # ------------------------------------------------------------------ #

    def start(self):
        if not self.enabled:
            logger.info("FT8web: listener disabled in settings")
            return
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._serve_loop, daemon=True,
                                        name="FT8WebListener")
        self._thread.start()

    def stop(self):
        self.running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def is_client_connected(self):
        return self._client_connected

    def get_diagnostics(self) -> dict:
        return {
            'enabled': self.enabled,
            'port': self.port,
            'running': self.running,
            'client_connected': self._client_connected,
            'messages_received': self.messages_received,
            'decodes_received': self._decodes_received,
            'last_message_age': (time.time() - self._last_message_time)
                                if self._last_message_time else None,
            'forward_ports': self.forward_ports,
        }

    # ------------------------------------------------------------------ #
    # Server loop
    # ------------------------------------------------------------------ #

    def _serve_loop(self):
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(('127.0.0.1', self.port))
            srv.listen(1)
            srv.settimeout(1.0)
            self._server_sock = srv
            logger.info(f"FT8web: listening on ws://localhost:{self.port}")
        except OSError as e:
            logger.error(f"FT8web: could not bind port {self.port}: {e}")
            self.running = False
            return

        while self.running:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed by stop()
            try:
                self._handle_connection(conn, addr)
            except Exception as e:
                logger.warning(f"FT8web: connection error: {e}")
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                if self._client_connected:
                    self._client_connected = False
                    self.client_state_changed.emit(False)
                    logger.info("FT8web: client disconnected")

    def _handle_connection(self, conn, addr):
        conn.settimeout(1.0)
        if not self._ws_handshake(conn):
            return
        logger.info(f"FT8web: client connected from {addr[0]}")
        self._client_connected = True
        self.client_state_changed.emit(True)

        buf = bytearray()
        fragments = bytearray()
        last_heartbeat = 0.0
        while self.running:
            now = time.time()
            if self.forward_ports and now - last_heartbeat >= HEARTBEAT_INTERVAL:
                self._forward(wsjtx_protocol.build_heartbeat(CLIENT_ID))
                last_heartbeat = now

            frame = self._read_frame(conn, buf)
            if frame is None:
                continue  # timeout tick; loop for running/heartbeat checks
            fin, opcode, payload = frame
            if opcode == 0x8:  # close
                self._send_frame(conn, 0x8, payload[:2])
                return
            if opcode == 0x9:  # ping -> pong
                self._send_frame(conn, 0xA, payload)
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode in (0x1, 0x0):  # text / continuation
                fragments.extend(payload)
                if not fin:
                    continue
                text = fragments.decode('utf-8', errors='replace')
                fragments = bytearray()
                self._dispatch(text)

    # ------------------------------------------------------------------ #
    # RFC 6455 plumbing
    # ------------------------------------------------------------------ #

    def _ws_handshake(self, conn):
        """Read the HTTP upgrade request, reply 101. Returns True on success."""
        request = bytearray()
        deadline = time.time() + 5.0
        while b'\r\n\r\n' not in request:
            if time.time() > deadline or len(request) > 8192:
                return False
            try:
                chunk = conn.recv(1024)
            except socket.timeout:
                continue
            if not chunk:
                return False
            request.extend(chunk)

        key = None
        for line in request.split(b'\r\n'):
            if line.lower().startswith(b'sec-websocket-key:'):
                key = line.split(b':', 1)[1].strip().decode('ascii')
                break
        if not key:
            conn.sendall(b'HTTP/1.1 400 Bad Request\r\n\r\n')
            return False

        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode('ascii')).digest()
        ).decode('ascii')
        conn.sendall(
            b'HTTP/1.1 101 Switching Protocols\r\n'
            b'Upgrade: websocket\r\n'
            b'Connection: Upgrade\r\n'
            b'Sec-WebSocket-Accept: ' + accept.encode('ascii') + b'\r\n\r\n'
        )
        return True

    def _read_exact(self, conn, buf, n):
        """Read exactly n bytes into/from buf. Returns bytes or None on timeout."""
        while len(buf) < n:
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                return None
            if not chunk:
                raise ConnectionError("peer closed")
            buf.extend(chunk)
        out = bytes(buf[:n])
        del buf[:n]
        return out

    def _read_frame(self, conn, buf):
        """Read one WebSocket frame. Returns (fin, opcode, payload) or None on timeout.

        A timeout mid-frame leaves consumed bytes stashed back at the front of
        buf so the next call resumes cleanly.
        """
        header = self._read_exact(conn, buf, 2)
        if header is None:
            return None
        fin = bool(header[0] & 0x80)
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F

        consumed = bytearray(header)

        def read_more(n):
            data = self._read_exact(conn, buf, n)
            if data is None:
                # Timeout mid-frame: un-consume and retry next tick
                buf[:0] = consumed
                return None
            consumed.extend(data)
            return data

        if length == 126:
            ext = read_more(2)
            if ext is None:
                return None
            length = struct.unpack('>H', ext)[0]
        elif length == 127:
            ext = read_more(8)
            if ext is None:
                return None
            length = struct.unpack('>Q', ext)[0]
        if length > 1 << 20:
            raise ConnectionError(f"frame too large ({length} bytes)")

        mask = b''
        if masked:
            mask = read_more(4)
            if mask is None:
                return None

        payload = read_more(length) if length else b''
        if payload is None:
            return None
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return fin, opcode, payload

    def _send_frame(self, conn, opcode, payload):
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([n])
        elif n < 1 << 16:
            header += bytes([126]) + struct.pack('>H', n)
        else:
            header += bytes([127]) + struct.pack('>Q', n)
        try:
            conn.sendall(header + payload)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Stream dispatch (schema v1)
    # ------------------------------------------------------------------ #

    def _dispatch(self, text):
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("FT8web: dropped non-JSON frame")
            return
        if not isinstance(msg, dict):
            return

        self.messages_received += 1
        self._last_message_time = time.time()
        mtype = msg.get('type')
        try:
            if mtype == 'decode':
                self._on_decode(msg)
            elif mtype == 'status':
                self._on_status(msg)
            elif mtype == 'qso_logged':
                self._on_qso_logged(msg)
        except Exception as e:
            logger.warning(f"FT8web: error processing '{mtype}' message: {e}")

    def _on_decode(self, msg):
        mode = msg.get('mode', 'FT8')
        # Match UDPHandler's decode dict exactly, including the WSJT-X
        # single-char mode code and HHMM time, so downstream treats both
        # sources identically.
        mode_code = wsjtx_protocol.MODE_CODES.get(mode, '~')
        for d in msg.get('decodes', []):
            time_hhmmss = str(d.get('time', ''))
            message = d.get('message', '')
            call, grid = parse_decode_message(message)
            self._decodes_received += 1
            if self._decodes_received == 1:
                logger.info(f"FT8web: first decode received - {call} "
                            f"{d.get('snr')}dB {d.get('freq')}Hz")
            self.new_decode.emit({
                'time': time_hhmmss[:4], 'snr': int(d.get('snr', 0)), 'dt': 0.0,
                'freq': int(d.get('freq', 0)), 'mode': mode_code,
                'message': message, 'call': call, 'grid': grid
            })
            self._forward(wsjtx_protocol.build_decode(
                CLIENT_ID, time_hhmmss, d.get('snr', 0), d.get('freq', 0),
                message, mode=mode))

    def _on_status(self, msg):
        self.status_update.emit({
            'dial_freq': int(msg.get('dialFreqHz', 0)),
            'dx_call': (msg.get('dxCall') or '').upper(),
            'dx_grid': '',
            'tx_df': int(msg.get('txFreqHz', 0)),
            'tx_enabled': bool(msg.get('txEnabled', False)),
            'transmitting': bool(msg.get('transmitting', False)),
            'de_call': (msg.get('myCall') or '').upper(),
            'de_grid': msg.get('myGrid') or '',
            'special_mode': 0,
        })
        self._forward(wsjtx_protocol.build_status(
            CLIENT_ID, msg.get('dialFreqHz', 0), msg.get('mode', 'FT8'),
            dx_call=msg.get('dxCall', ''), tx_df=msg.get('txFreqHz', 0),
            tx_enabled=msg.get('txEnabled', False),
            transmitting=msg.get('transmitting', False),
            de_call=msg.get('myCall', ''), de_grid=msg.get('myGrid', '')))

    def _on_qso_logged(self, msg):
        dx_call = (msg.get('call') or '').upper()
        if not dx_call:
            return
        logger.info(f"FT8web: QSO Logged - {dx_call} ({msg.get('grid', '')})")
        self.qso_logged.emit({
            'dx_call': dx_call,
            'dx_grid': msg.get('grid') or '',
        })
        self._forward(wsjtx_protocol.build_qso_logged(
            CLIENT_ID, dx_call, dx_grid=msg.get('grid', ''),
            dial_freq=msg.get('dialFreqHz', 0), mode=msg.get('mode', 'FT8'),
            rst_sent=msg.get('rstSent', ''), rst_rcvd=msg.get('rstRcvd', '')))

    # ------------------------------------------------------------------ #
    # WSJT-X UDP re-broadcast (same semantics as UDPHandler._forward_packet)
    # ------------------------------------------------------------------ #

    def _forward(self, packet):
        for port in self.forward_ports:
            try:
                self._forward_sock.sendto(packet, ('127.0.0.1', port))
            except OSError as e:
                if port not in self._forward_errors_logged:
                    self._forward_errors_logged.add(port)
                    logger.warning(f"FT8web: forward to port {port} failed: {e}")

    def check_data_health(self) -> tuple:
        """FT8web is an optional source — its absence is never a warning."""
        return (True, "")
