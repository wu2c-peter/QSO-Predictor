#!/usr/bin/env python3
"""FT8web -> WSJT-X UDP bridge.

Accepts FT8web's External Data Stream (JSON over WebSocket, schema v1) and
re-emits WSJT-X-protocol UDP datagrams (Heartbeat, Status, Decode,
QSO Logged), so existing ecosystem tools — GridTracker, JTAlert,
QSO Predictor, logging programs — work with FT8web unmodified.

Usage:
    pip install websockets
    python3 ft8web_udp_bridge.py                  # WS :2442 -> UDP 127.0.0.1:2237
    python3 ft8web_udp_bridge.py --udp-port 2238  # custom UDP target

Then in FT8web: Settings -> External Data Stream -> Enabled,
URL ws://localhost:2442.
"""

import argparse
import asyncio
import datetime
import json
import socket
import struct

MAGIC = 0xADBCCBDA
SCHEMA = 2
CLIENT_ID = "FT8web"

# WSJT-X Decode packets carry a one-character mode code.
MODE_CODES = {"FT8": "~", "FT4": "+"}


def qutf8(s: str) -> bytes:
    b = (s or "").encode("utf-8")
    return struct.pack(">I", len(b)) + b


def header(msg_type: int) -> bytes:
    return struct.pack(">III", MAGIC, SCHEMA, msg_type) + qutf8(CLIENT_ID)


def qtime_ms(hhmmss: str) -> int:
    """'HHMMSS' (or 'HHMM') -> milliseconds since UTC midnight."""
    hhmmss = (hhmmss or "").ljust(6, "0")
    h, m, s = int(hhmmss[0:2]), int(hhmmss[2:4]), int(hhmmss[4:6])
    return ((h * 60 + m) * 60 + s) * 1000


def qdatetime_now() -> bytes:
    """QDateTime: julian day (i64) + ms since midnight (u32) + timespec (u8=UTC)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    julian_day = now.date().toordinal() + 1721425
    ms = ((now.hour * 60 + now.minute) * 60 + now.second) * 1000
    return struct.pack(">qIB", julian_day, ms, 1)


def heartbeat_pkt() -> bytes:
    return header(0) + struct.pack(">I", 3) + qutf8("2.6.1") + qutf8("FT8web-bridge")


def status_pkt(msg: dict) -> bytes:
    mode = msg.get("mode", "FT8")
    p = header(1)
    p += struct.pack(">Q", int(msg.get("dialFreqHz", 0)))   # dial frequency
    p += qutf8(mode)                                        # mode
    p += qutf8(msg.get("dxCall", ""))                       # DX call
    p += qutf8("")                                          # report
    p += qutf8(mode)                                        # TX mode
    p += struct.pack(">?", bool(msg.get("txEnabled")))      # TX enabled
    p += struct.pack(">?", bool(msg.get("transmitting")))   # transmitting
    p += struct.pack(">?", False)                           # decoding
    p += struct.pack(">I", int(msg.get("txFreqHz", 0)))     # RX DF
    p += struct.pack(">I", int(msg.get("txFreqHz", 0)))     # TX DF
    p += qutf8(msg.get("myCall", ""))                       # DE call
    p += qutf8(msg.get("myGrid", ""))                       # DE grid
    p += qutf8("")                                          # DX grid
    p += struct.pack(">?", False)                           # TX watchdog
    p += qutf8("")                                          # submode
    p += struct.pack(">?", False)                           # fast mode
    p += struct.pack(">B", 0)                               # special op mode
    return p


def decode_pkts(msg: dict):
    mode_code = MODE_CODES.get(msg.get("mode", "FT8"), "~")
    for d in msg.get("decodes", []):
        p = header(2)
        p += struct.pack(">?", True)                        # is new
        p += struct.pack(">I", qtime_ms(d.get("time", ""))) # time
        p += struct.pack(">i", int(d.get("snr", 0)))        # SNR
        p += struct.pack(">d", 0.0)                         # delta time (n/a)
        p += struct.pack(">I", int(d.get("freq", 0)))       # delta frequency
        p += qutf8(mode_code)                               # mode
        p += qutf8(d.get("message", ""))                    # message
        p += struct.pack(">?", False)                       # low confidence
        p += struct.pack(">?", False)                       # off air
        yield p


def qso_logged_pkt(msg: dict) -> bytes:
    p = header(5)
    p += qdatetime_now()                                    # date/time off
    p += qutf8(msg.get("call", ""))                         # DX call
    p += qutf8(msg.get("grid", ""))                         # DX grid
    p += struct.pack(">Q", int(msg.get("dialFreqHz", 0)))   # TX frequency
    p += qutf8(msg.get("mode", "FT8"))                      # mode
    p += qutf8(msg.get("rstSent", ""))                      # report sent
    p += qutf8(msg.get("rstRcvd", ""))                      # report received
    p += qutf8("")                                          # TX power
    p += qutf8("")                                          # comments
    p += qutf8("")                                          # name
    p += qdatetime_now()                                    # date/time on
    return p


async def main() -> None:
    import websockets

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ws-port", type=int, default=2442, help="WebSocket listen port (default 2442)")
    ap.add_argument("--udp-host", default="127.0.0.1", help="UDP target host (default 127.0.0.1)")
    ap.add_argument("--udp-port", type=int, default=2237, help="UDP target port (default 2237)")
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.udp_host, args.udp_port)

    def emit(pkt: bytes) -> None:
        sock.sendto(pkt, target)

    async def handler(ws) -> None:
        print(f"FT8web connected from {ws.remote_address}")
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                mtype = msg.get("type")
                if mtype == "decode":
                    for pkt in decode_pkts(msg):
                        emit(pkt)
                elif mtype == "status":
                    emit(status_pkt(msg))
                elif mtype == "qso_logged":
                    emit(qso_logged_pkt(msg))
                    print(f"QSO logged: {msg.get('call')} {msg.get('grid')}")
        finally:
            print("FT8web disconnected")

    async def heartbeats() -> None:
        while True:
            emit(heartbeat_pkt())
            await asyncio.sleep(15)

    print(f"Listening for FT8web on ws://localhost:{args.ws_port}, "
          f"emitting WSJT-X UDP to {args.udp_host}:{args.udp_port}")
    async with websockets.serve(handler, "localhost", args.ws_port):
        await heartbeats()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
