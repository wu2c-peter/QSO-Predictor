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

"""WSJT-X UDP protocol packet builders (pure stdlib, no Qt).

Used to synthesize WSJT-X-format datagrams from non-WSJT-X sources
(e.g. the FT8web WebSocket stream) so downstream consumers on the
forward ports — GridTracker, JTAlert, loggers — receive a stream they
already understand. Field order and encoding follow the QDataStream
wire format that udp_handler.py parses on the receive side.
"""

import datetime
import struct

MAGIC = 0xADBCCBDA
SCHEMA = 2

# WSJT-X Decode packets carry a one-character mode code.
MODE_CODES = {"FT8": "~", "FT4": "+"}


def _utf8(s):
    b = (s or "").encode("utf-8")
    return struct.pack('>I', len(b)) + b


def _header(msg_type, client_id):
    return struct.pack('>III', MAGIC, SCHEMA, msg_type) + _utf8(client_id)


def _time_ms(hhmmss):
    """'HHMMSS' (or 'HHMM') -> milliseconds since UTC midnight."""
    hhmmss = (hhmmss or "").ljust(6, "0")
    h, m, s = int(hhmmss[0:2]), int(hhmmss[2:4]), int(hhmmss[4:6])
    return ((h * 60 + m) * 60 + s) * 1000


def _qdatetime_now():
    """QDateTime: julian day (i64) + ms since midnight (u32) + timespec (u8=UTC)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    julian_day = now.date().toordinal() + 1721425
    ms = ((now.hour * 60 + now.minute) * 60 + now.second) * 1000
    return struct.pack('>qIB', julian_day, ms, 1)


def build_heartbeat(client_id):
    """Type 0: Heartbeat. Some consumers use it for client discovery."""
    return _header(0, client_id) + struct.pack('>I', 3) + _utf8("2.6.1") + _utf8(client_id)


def build_status(client_id, dial_freq, mode, dx_call="", tx_df=0,
                 tx_enabled=False, transmitting=False, de_call="", de_grid="",
                 dx_grid=""):
    """Type 1: Status."""
    p = _header(1, client_id)
    p += struct.pack('>Q', int(dial_freq))
    p += _utf8(mode)
    p += _utf8(dx_call)
    p += _utf8("")                                  # report
    p += _utf8(mode)                                # TX mode
    p += struct.pack('>?', bool(tx_enabled))
    p += struct.pack('>?', bool(transmitting))
    p += struct.pack('>?', False)                   # decoding
    p += struct.pack('>I', int(tx_df))              # RX DF
    p += struct.pack('>I', int(tx_df))              # TX DF
    p += _utf8(de_call)
    p += _utf8(de_grid)
    p += _utf8(dx_grid)
    p += struct.pack('>?', False)                   # TX watchdog
    p += _utf8("")                                  # submode
    p += struct.pack('>?', False)                   # fast mode
    p += struct.pack('>B', 0)                       # special op mode
    return p


def build_decode(client_id, time_hhmmss, snr, freq, message, mode="FT8", dt=0.0):
    """Type 2: Decode. `freq` is the audio offset (delta frequency) in Hz."""
    p = _header(2, client_id)
    p += struct.pack('>?', True)                    # is new
    p += struct.pack('>I', _time_ms(time_hhmmss))
    p += struct.pack('>i', int(snr))
    p += struct.pack('>d', float(dt))
    p += struct.pack('>I', int(freq))
    p += _utf8(MODE_CODES.get(mode, "~"))
    p += _utf8(message)
    p += struct.pack('>?', False)                   # low confidence
    p += struct.pack('>?', False)                   # off air
    return p


def build_qso_logged(client_id, dx_call, dx_grid="", dial_freq=0, mode="FT8",
                     rst_sent="", rst_rcvd=""):
    """Type 5: QSO Logged."""
    p = _header(5, client_id)
    p += _qdatetime_now()                           # date/time off
    p += _utf8(dx_call)
    p += _utf8(dx_grid)
    p += struct.pack('>Q', int(dial_freq))          # TX frequency
    p += _utf8(mode)
    p += _utf8(rst_sent)
    p += _utf8(rst_rcvd)
    p += _utf8("")                                  # TX power
    p += _utf8("")                                  # comments
    p += _utf8("")                                  # name
    p += _qdatetime_now()                           # date/time on
    return p
