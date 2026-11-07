"""WS - Digital Mode Suite (successor to WSJT-X Improved) compatibility.

WS 3.2 changed its UDP traffic relative to stock WSJT-X in ways read from
its 3.2.1 source (ws-3.2.1_261010.tgz, Network/ and widgets/mainwindow.cpp):

- The instance id is "WS" (or "WS - <rig>") instead of "WSJT-X". Its
  "WSJT-X compatibility mode" checkbox only rewrites that id back to
  "WSJT-X"; nothing else on the wire changes.
- Status (type 1) gains a trailing utf8 "Tx Symbols" field after Tx message.
- QSO Logged (type 5) gains three trailing utf8 fields (satellite, sat
  mode, freq rx).
- A new outbound message type 17 (InhibitStatus) exists.
- Schema number is unchanged (3 after negotiation).

QSOP echoes whatever id it last heard, parses only the fields it knows and
ignores unknown message types, so none of this should need the
compatibility mode. These tests pin that down with WS-shaped packets.
"""

import struct

import pytest

from tests import wsjtx_packets as pkt
from utils import wsjtx_protocol


WS_ID = "WS"
WS_RIG_ID = "WS - IC-705"


def ws_header(msg_type, client_id=WS_ID, schema=3):
    """WS header: same magic, negotiated schema 3, id 'WS'."""
    return struct.pack('>III', pkt.MAGIC, schema, msg_type) + pkt.utf8(client_id)


def ws_status(client_id=WS_ID, tx_symbols="0123456701234567", **kw):
    """Stock Status fields, WS header, plus WS's trailing Tx Symbols."""
    stock = pkt.status(**kw)
    body = stock[len(pkt.header(1)):]
    # Stock builder stops at field 18 (special op mode); real WSJT-X 2.6+
    # continues with frequency tolerance, T/R period, configuration name,
    # Tx message — then WS appends Tx Symbols. Emit that full tail so the
    # trailer lands where WS puts it.
    tail = struct.pack('>I', 0xFFFFFFFF)          # frequency tolerance
    tail += struct.pack('>I', 0xFFFFFFFF)         # T/R period
    tail += pkt.utf8("Default")                   # configuration name
    tail += pkt.utf8("CQ WU2C FN30")              # Tx message
    tail += pkt.utf8(tx_symbols)                  # WS: Tx Symbols
    return ws_header(1, client_id) + body + tail


def ws_qso_logged(**kw):
    """Stock QSO Logged plus WS's three trailing fields."""
    stock = pkt.qso_logged(**kw)
    body = stock[len(pkt.header(5)):]
    # Real packets also carry operator call, my call, my grid, exchange
    # sent/rcvd, ADIF propmode before WS's additions; include them too.
    tail = pkt.utf8("WU2C") + pkt.utf8("WU2C") + pkt.utf8("FN30")
    tail += pkt.utf8("") + pkt.utf8("") + pkt.utf8("")
    tail += pkt.utf8("QO-100") + pkt.utf8("SSB") + pkt.utf8("10489.650")  # WS
    return ws_header(5) + body + tail


def ws_inhibit_status(client_id=WS_ID):
    """Type 17 InhibitStatus: id, port, inhibited, source, 4 counters."""
    p = ws_header(17, client_id)
    p += struct.pack('>H', 22372) + struct.pack('>?', True) + pkt.utf8("KEY")
    p += struct.pack('>IIII', 1, 0, 0, 0)
    return p


def test_ws_status_parses_with_trailing_tx_symbols(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(ws_status(
        dial_freq=14074000, dx_call='JA1XYZ', tx_df=1512,
        tx_enabled=True, de_call='WU2C', de_grid='FN30', dx_grid='PM95'))
    assert len(received['status']) == 1
    st = received['status'][0]
    assert st['dial_freq'] == 14074000
    assert st['dx_call'] == 'JA1XYZ'
    assert st['dx_grid'] == 'PM95'
    assert st['tx_df'] == 1512
    assert st['tx_enabled'] is True
    assert st['de_call'] == 'WU2C'
    assert st['de_grid'] == 'FN30'


@pytest.mark.parametrize("client_id", [WS_ID, WS_RIG_ID])
def test_ws_id_is_captured_and_echoed_in_requests(udp_handler, client_id):
    """WS drops requests whose id differs from its own, exactly like
    WSJT-X, so click-to-call must echo 'WS' / 'WS - rig' verbatim."""
    handler, _ = udp_handler
    handler._parse_packet(ws_status(client_id=client_id))
    assert handler._last_client_id == client_id
    p = wsjtx_protocol.build_configure(handler._last_client_id, "JA1XYZ", "PM95")
    echoed_len = struct.unpack('>I', p[12:16])[0]
    assert p[16:16 + echoed_len].decode() == client_id


def test_ws_decode_still_extracts_callsign(udp_handler):
    handler, received = udp_handler
    body = pkt.decode("CQ JA1XYZ PM95")[len(pkt.header(2)):]
    handler._parse_packet(ws_header(2) + body)
    assert len(received['decode']) == 1
    assert received['decode'][0]['call'] == 'JA1XYZ'
    assert received['decode'][0]['grid'] == 'PM95'


def test_ws_qso_logged_with_trailing_fields(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(ws_qso_logged(dx_call='K1ABC', dx_grid='FN42'))
    assert received['qso_logged'] == [{'dx_call': 'K1ABC', 'dx_grid': 'FN42'}]


def test_ws_inhibit_status_type_17_is_ignored(udp_handler):
    handler, received = udp_handler
    handler._parse_packet(ws_inhibit_status())
    assert received == {'decode': [], 'status': [], 'qso_logged': []}
    # ...but it is still a genuine WS datagram, so it may set the id
    # (harmless either way); it must not raise or corrupt routing.
    handler._parse_packet(ws_status())
    assert handler._last_client_id == WS_ID
