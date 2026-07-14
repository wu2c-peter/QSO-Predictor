# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Shared fixtures for the QSO Predictor test suite.

Run with:  ./venv/bin/python3 -m pytest
"""

import sys
from pathlib import Path

import pytest

# Make the repo root importable regardless of how pytest is invoked
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class StubConfig:
    """Minimal stand-in for ConfigManager. Port 0 = ephemeral bind."""

    def __init__(self, overrides=None, forward_ports=None):
        self.values = {
            ('NETWORK', 'udp_port'): '0',
            ('NETWORK', 'udp_ip'): '127.0.0.1',
        }
        if overrides:
            self.values.update(overrides)
        self.forward_ports = forward_ports or []

    def get(self, section, key, fallback=None):
        return self.values.get((section, key), fallback)

    def get_forward_ports(self):
        return self.forward_ports


@pytest.fixture
def udp_handler():
    """A UDPHandler bound to an ephemeral port, with captured signals.

    Yields (handler, received) where received collects each signal's dict
    payloads under 'decode' / 'status' / 'qso_logged'. Signals are connected
    DirectConnection because there is no Qt event loop in the test process.
    """
    from PyQt6.QtCore import Qt
    from udp_handler import UDPHandler

    direct = Qt.ConnectionType.DirectConnection
    handler = UDPHandler(StubConfig())
    received = {'decode': [], 'status': [], 'qso_logged': []}
    handler.new_decode.connect(lambda d: received['decode'].append(d), direct)
    handler.status_update.connect(lambda d: received['status'].append(d), direct)
    handler.qso_logged.connect(lambda d: received['qso_logged'].append(d), direct)

    yield handler, received

    handler.sock.close()


@pytest.fixture
def outcome_recorder_home(tmp_path, monkeypatch):
    """Redirect the recorder's ~/.qso-predictor data dir into tmp_path.

    Path.home() reads HOME on POSIX and USERPROFILE on Windows.
    Returns the path the outcome JSONL will be written to.
    """
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    return tmp_path / '.qso-predictor' / 'outcome_history.jsonl'
