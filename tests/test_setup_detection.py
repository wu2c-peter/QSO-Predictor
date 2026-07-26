# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Unit tests for the detection layer lifted out of setup_wizard.py into
diagnostics/ (DIAGNOSTICS_SPEC.md migration step 2). First direct coverage
of these classes — before the move they were only exercised via the Qt
wizard on a live machine.

Import diagnostics.* only: setup_wizard imports QtWidgets, which the test
suite never does (no display available in CI).
"""

from diagnostics.models import DetectedApp, PortInfo, SetupRecommendation
from diagnostics.probe_apps import ConfigFileReader
from diagnostics.setup_analysis import SetupAnalyzer


# ---------------------------------------------------------------------------
# ConfigFileReader — INI parsing against fixture files
# ---------------------------------------------------------------------------

WSJTX_INI = """\
[Configuration]
MyCall=WU2C
MyGrid=FN30pr
UDPServerPort=2237
UDPServerAddress=127.0.0.1
AcceptUDPRequests=true
"""

# JTDX writes some keys under [General]; grid key differs (C2MyGrid seen in
# the wild). Also exercises _find_value's search across sections.
JTDX_INI = """\
[General]
mycall=WU2C
C2MyGrid=FN30pr

[Configuration]
UdpServerPort=2238
"""


def _read(tmp_path, text, name='WSJT-X.ini', app='WSJT-X'):
    ini = tmp_path / name
    ini.write_text(text, encoding='utf-8')
    return ConfigFileReader()._read_config(ini, app)


def test_read_config_wsjtx_full(tmp_path):
    app = _read(tmp_path, WSJTX_INI)
    assert app is not None
    assert app.name == 'WSJT-X'
    assert app.callsign == 'WU2C'
    assert app.grid == 'FN30pr'
    assert app.udp_ip == '127.0.0.1'
    assert app.udp_port == 2237
    assert app.accept_udp is True


def test_read_config_jtdx_key_variants_across_sections(tmp_path):
    app = _read(tmp_path, JTDX_INI, name='JTDX.ini', app='JTDX')
    assert app is not None
    assert app.callsign == 'WU2C'
    assert app.grid == 'FN30pr'       # via C2MyGrid variant
    assert app.udp_port == 2238       # via UdpServerPort variant
    assert app.udp_ip == '127.0.0.1'  # default when no address key
    assert app.accept_udp is False    # default when no accept key


def test_read_config_bad_port_falls_back_to_2237(tmp_path):
    app = _read(tmp_path, "[Configuration]\nMyCall=WU2C\nUDPServerPort=oops\n")
    assert app is not None
    assert app.udp_port == 2237


def test_read_config_empty_file_yields_defaults_not_none(tmp_path):
    """An empty/keyless INI is still a detected install — defaults apply."""
    app = _read(tmp_path, "[Configuration]\n")
    assert app is not None
    assert app.callsign == ''
    assert app.udp_port == 2237
    assert app.accept_udp is False


def test_read_config_sectionless_keys_are_not_handled(tmp_path):
    """Keys before any section header make configparser raise, and
    _read_config returns None (install reported as not found). Documented
    limitation, safe in practice: Qt QSettings always writes section
    headers. Pinned so nobody 'fixes' the docstring instead of the code
    (or vice versa) without noticing."""
    app = _read(tmp_path, "MyCall=WU2C\nMyGrid=FN30pr\n[Configuration]\n")
    assert app is None


# ---------------------------------------------------------------------------
# SetupAnalyzer — recommendation logic over synthetic detections
# ---------------------------------------------------------------------------

def _app(name, callsign='WU2C', grid='FN30pr', udp_ip='127.0.0.1',
         udp_port=2237):
    return DetectedApp(name=name, config_path=None, callsign=callsign,
                       grid=grid, udp_ip=udp_ip, udp_port=udp_port)


def test_analyze_prefers_jtdx_over_wsjtx_for_station_info():
    rec = SetupAnalyzer.analyze(
        [_app('WSJT-X', callsign='W1AAA', grid='FN31'),
         _app('JTDX', callsign='WU2C', grid='FN30PR')],
        ports_in_use=[], running_apps=[])
    assert rec.callsign == 'WU2C'
    assert rec.grid == 'FN30PR'
    assert 'JTDX' in rec.source
    assert rec.confidence == 'high'


def test_analyze_multicast_detected_joins_group():
    rec = SetupAnalyzer.analyze(
        [_app('WSJT-X', udp_ip='239.255.0.0', udp_port=2237)],
        ports_in_use=[], running_apps=[])
    assert rec.use_multicast is True
    assert rec.udp_ip == '239.255.0.0'
    assert rec.udp_port == 2237


def test_analyze_port_conflict_warns_and_names_occupier():
    """The daisy-chain-adjacent case: the app's configured port is already
    held by a forwarder, so the recommendation must move off it and say
    who has it (this is the wizard equivalent of the Network Doctor's
    chain diagnosis)."""
    rec = SetupAnalyzer.analyze(
        [_app('WSJT-X', udp_port=2237)],
        ports_in_use=[PortInfo(port=2237, process_name='GridTracker',
                               pid=4242)],
        running_apps=['GridTracker'])
    assert rec.udp_port != 2237
    assert any('GridTracker' in w for w in rec.warnings)
    assert rec.confidence == 'medium'   # callsign found, but with warnings


def test_analyze_jtalert_running_without_conflict_keeps_2237():
    rec = SetupAnalyzer.analyze(
        [_app('WSJT-X')], ports_in_use=[], running_apps=['JTAlert'])
    assert rec.udp_port == 2237
    assert rec.udp_ip == '127.0.0.1'
    assert any('JTAlert' in w for w in rec.warnings)


def test_analyze_nothing_detected_is_low_confidence_default():
    rec = SetupAnalyzer.analyze([], ports_in_use=[], running_apps=[])
    assert rec.confidence == 'low'
    assert rec.callsign == ''
    assert rec.udp_port == 2237
    assert rec.udp_ip == '127.0.0.1'


def test_recommendation_lists_are_per_instance():
    """field(default_factory=list) regression guard: two recommendations
    must not share warnings/notes lists."""
    a, b = SetupRecommendation(), SetupRecommendation()
    a.warnings.append('x')
    assert b.warnings == []
