"""
Clock probe: measure the system clock's offset against NTP.

A minimal SNTP client (RFC 4330) — one UDP packet per server, stdlib
only. FT8's 15-second windows need the clock within about a second of
UTC, and a drifted clock is the mode's classic silent killer: everything
looks fine, nothing decodes.

The reply parsing is a pure function (`_parse_ntp_reply`) so it is
unit-testable with crafted packets; only `gather_clock()` touches the
network. No reachable server is a normal condition (field/off-grid
operation) — the offset stays None and checks report UNKNOWN.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import logging
import socket
import struct
import time
from datetime import datetime
from typing import Sequence, Tuple

from diagnostics.models import ClockSnapshot

logger = logging.getLogger(__name__)

# Seconds between the NTP epoch (1900) and the Unix epoch (1970).
_NTP_EPOCH_OFFSET = 2208988800

# LI=0, VN=4, Mode=3 (client)
_CLIENT_REQUEST = b'\x23' + 47 * b'\x00'

# NOT pool.ntp.org: the NTP Pool's vendor policy forbids shipping the
# default pool zones as an application default. These two are anycast
# services explicitly operated for public use; load here is one 48-byte
# query per user-initiated checkup.
DEFAULT_SERVERS = ('time.cloudflare.com', 'time.google.com')


def _ts(data: bytes, offset: int) -> float:
    """Decode one 64-bit NTP timestamp (32.32 fixed point) to Unix time.

    Era handling: NTP era 0's 32-bit seconds wrap on 2036-02-07. A
    decoded time more than ~68 years in the past means the stamp is from
    the next era — desktop installs live long enough for this to matter.
    """
    sec, frac = struct.unpack('!II', data[offset:offset + 8])
    t = sec - _NTP_EPOCH_OFFSET + frac / 2**32
    if t < time.time() - 2**31:
        t += 2**32
    return t


def _parse_ntp_reply(data: bytes, t1: float, t4: float) -> Tuple[float, float]:
    """Pure RFC 4330 offset/delay computation, with the §5 sanity checks.

    t1/t4 are our send/receive times (Unix seconds); the reply carries
    the server's receive (t2, byte 32) and transmit (t3, byte 40)
    stamps. Returns (offset, round_trip_delay) where offset is
    system-minus-NTP: positive = our clock is fast.
    """
    if len(data) < 48:
        raise ValueError(f'short NTP reply ({len(data)} bytes)')
    if data[0] >> 6 == 3:
        raise ValueError('server clock not synchronized (LI=3)')
    mode = data[0] & 0x07
    if mode != 4:
        raise ValueError(f'not a server reply (mode {mode})')
    stratum = data[1]
    if stratum == 0 or stratum > 15:      # kiss-of-death / unsynchronized
        raise ValueError(f'unusable reply (stratum {stratum})')
    if data[40:48] == b'\x00' * 8:
        raise ValueError('zero transmit timestamp')
    t2 = _ts(data, 32)
    t3 = _ts(data, 40)
    offset = ((t2 - t1) + (t3 - t4)) / 2
    delay = (t4 - t1) - (t3 - t2)
    # NTP offset convention is server-minus-system; flip so positive
    # reads as "your clock is fast", which is how operators say it.
    return -offset, delay


def gather_clock(servers: Sequence[str] = DEFAULT_SERVERS,
                 timeout: float = 2.0) -> ClockSnapshot:
    """Domain gatherer for 'clock'. Network I/O — worker thread only."""
    snap = ClockSnapshot()

    local = datetime.now().astimezone()
    snap.timezone_name = str(local.tzinfo)
    utc_off = local.utcoffset()
    if utc_off is not None:
        snap.utc_offset_min = int(utc_off.total_seconds() // 60)

    for server in servers:
        sock = None
        try:
            # Resolve BEFORE stamping t1 — DNS latency inside the timing
            # window would read as clock offset (~half the DNS delay),
            # exactly the false positive this probe exists to prevent.
            # (getaddrinfo is not bounded by the socket timeout; a dead
            # resolver can stall for the OS resolver timeout per server —
            # the checkup UI shows a busy status for this reason.)
            addr = socket.getaddrinfo(server, 123, socket.AF_INET,
                                      socket.SOCK_DGRAM)[0][4]
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            t1 = time.time()
            sock.sendto(_CLIENT_REQUEST, addr)
            data, _ = sock.recvfrom(512)
            t4 = time.time()
            offset, delay = _parse_ntp_reply(data, t1, t4)
            snap.offset_s = offset
            snap.round_trip_s = delay
            snap.ntp_server = server
            logger.debug(f"Clock probe: {server} says offset "
                         f"{offset * 1000:+.0f} ms (rtt {delay * 1000:.0f} ms)")
            break
        except (OSError, ValueError) as e:
            logger.debug(f"Clock probe: {server} failed: {e}")
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    return snap
