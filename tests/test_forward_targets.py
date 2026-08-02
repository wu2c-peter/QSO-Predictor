# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""UDP forward-target parsing and the local self-forward filter.

The NETWORK/forward_ports value is persisted-format territory: bare
ports are the historic syntax (meaning 127.0.0.1) and must keep working
forever; host:port entries (2026-08) add cross-machine chains, because
multicast doesn't traverse Wi-Fi/routers reliably.
"""

import pytest

from config_manager import parse_forward_targets, is_local_host
from udp_handler import strip_local_self_forwards


@pytest.mark.parametrize("spec, expected", [
    # Historic bare-port syntax: implicit 127.0.0.1
    ("2238", [('127.0.0.1', 2238)]),
    ("2238,2239", [('127.0.0.1', 2238), ('127.0.0.1', 2239)]),
    # host:port entries
    ("192.168.1.50:2237", [('192.168.1.50', 2237)]),
    ("shackpc.local:2237", [('shackpc.local', 2237)]),
    # Mixed list with whitespace
    (" 2238 , 192.168.160.60:2237 ",
     [('127.0.0.1', 2238), ('192.168.160.60', 2237)]),
    # Empty / blank entries
    ("", []),
    (None, []),
    (",,  ,", []),
], ids=["bare", "bare-pair", "ip-port", "hostname-port", "mixed-ws",
        "empty", "none", "commas-only"])
def test_parse_forward_targets(spec, expected):
    assert parse_forward_targets(spec) == expected


@pytest.mark.parametrize("spec, expected", [
    # Invalid entries are skipped, never fatal — and never poison the
    # valid entries beside them (the old parser returned [] wholesale)
    ("2238,notaport", [('127.0.0.1', 2238)]),
    ("host:xyz,2239", [('127.0.0.1', 2239)]),
    ("0,70000,2238", [('127.0.0.1', 2238)]),
    ("192.168.1.50:", [] ),
], ids=["trailing-garbage", "bad-port-in-hostpair", "out-of-range",
        "missing-port"])
def test_parse_forward_targets_skips_invalid(spec, expected):
    assert parse_forward_targets(spec) == expected


def test_is_local_host():
    assert is_local_host('127.0.0.1')
    assert is_local_host('127.9.9.9')
    assert is_local_host('LocalHost')
    assert not is_local_host('192.168.1.50')
    assert not is_local_host('shackpc.local')


def test_self_forward_filter_strips_local_loop_keeps_remote():
    """The loop filter must only strip LOCAL targets on the listen port:
    forwarding to the SAME port number on another machine is the whole
    point of host:port support."""
    targets = [('127.0.0.1', 2237),        # local loop — dropped
               ('localhost', 2237),        # local loop — dropped
               ('127.0.0.1', 2238),        # different port — kept
               ('192.168.160.60', 2237)]   # remote, same port — kept
    assert strip_local_self_forwards(targets, 2237) == [
        ('127.0.0.1', 2238), ('192.168.160.60', 2237)]
