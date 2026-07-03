# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""WSJT-X UDP packet builders for parser tests.

Deliberately written against the WSJT-X NetworkMessage documentation
(QDataStream wire format), independent of udp_handler.py, so the tests
exercise the parser rather than mirroring it.
"""

import struct

MAGIC = 0xADBCCBDA
SCHEMA = 2
CLIENT_ID = "WSJT-X"


def utf8(s):
    b = s.encode('utf-8')
    return struct.pack('>I', len(b)) + b


def header(msg_type, client_id=CLIENT_ID):
    return struct.pack('>III', MAGIC, SCHEMA, msg_type) + utf8(client_id)


def time_ms(h, m, s=0):
    return ((h * 60 + m) * 60 + s) * 1000


def heartbeat():
    return header(0) + struct.pack('>I', 3) + utf8("2.6.1") + utf8("")


def decode(message, h=18, m=30, s=0, snr=-10, dt=0.2, freq=1500, mode='~'):
    p = header(2)
    p += struct.pack('>?', True)             # is new
    p += struct.pack('>I', time_ms(h, m, s))
    p += struct.pack('>i', snr)
    p += struct.pack('>d', dt)
    p += struct.pack('>I', freq)
    p += utf8(mode)
    p += utf8(message)
    p += struct.pack('>?', False)            # low confidence
    p += struct.pack('>?', False)            # off air
    return p


def status(dial_freq=14074000, mode='FT8', dx_call='', report='', tx_mode='FT8',
           tx_enabled=False, transmitting=False, decoding=False,
           rx_df=1500, tx_df=1500, de_call='WU2C', de_grid='FN30',
           dx_grid='', watchdog=False, submode='', fast_mode=False,
           special_mode=0, truncate_after_txdf=False):
    """Full WSJT-X 2.6-style Status. truncate_after_txdf=True emulates an
    older client that stops at field 11 (no DE call/grid, no special mode)."""
    p = header(1)
    p += struct.pack('>Q', dial_freq)
    p += utf8(mode)
    p += utf8(dx_call)
    p += utf8(report)
    p += utf8(tx_mode)
    p += struct.pack('>?', tx_enabled)
    p += struct.pack('>?', transmitting)
    p += struct.pack('>?', decoding)
    p += struct.pack('>I', rx_df)
    p += struct.pack('>I', tx_df)
    if truncate_after_txdf:
        return p
    p += utf8(de_call)
    p += utf8(de_grid)
    p += utf8(dx_grid)
    p += struct.pack('>?', watchdog)
    p += utf8(submode)
    p += struct.pack('>?', fast_mode)
    p += struct.pack('>B', special_mode)
    return p


def qdatetime(julian_day=2461500, ms=66600000, timespec=1, offset=None):
    """QDateTime: julian day (i64) + ms since midnight (u32) + timespec (u8).
    timespec=2 (OffsetFromUTC) appends a 4-byte offset -> 17 bytes total."""
    p = struct.pack('>qIB', julian_day, ms, timespec)
    if offset is not None:
        p += struct.pack('>i', offset)
    return p


def qso_logged(dx_call='K1ABC', dx_grid='FN42', tx_freq=14074000, mode='FT8',
               rst_sent='-05', rst_rcvd='-12', dt=None):
    """Type 5: QSO Logged. dt overrides the leading QDateTime bytes."""
    p = header(5)
    p += dt if dt is not None else qdatetime()
    p += utf8(dx_call)
    p += utf8(dx_grid)
    p += struct.pack('>Q', tx_freq)
    p += utf8(mode)
    p += utf8(rst_sent)
    p += utf8(rst_rcvd)
    p += utf8('')      # TX power
    p += utf8('')      # comments
    p += utf8('')      # name
    p += qdatetime()   # date/time on
    return p
