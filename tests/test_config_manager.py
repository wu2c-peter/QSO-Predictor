# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""ConfigManager robustness (2026-09 audit).

A config file missing NETWORK/udp_port used to reach `int(None)` inside
MainWindow.__init__ — the app died before Settings was reachable — and a
truncated ini raised MissingSectionHeaderError with no recovery path.
The placeholder-identity helpers exist because the Settings dialog
upper-cases the grid on save, so 'FN00aa' became 'FN00AA' and three
case-sensitive guards silently stopped matching.
"""

import configparser

import pytest

import config_manager
from config_manager import (ConfigManager, DEFAULT_CONFIG, is_placeholder_grid,
                            is_placeholder_callsign, station_needs_setup)


@pytest.fixture
def ini_path(tmp_path, monkeypatch):
    path = tmp_path / 'qso_predictor.ini'
    monkeypatch.setattr(config_manager, 'CONFIG_FILE', path)
    return path


def test_fresh_install_writes_every_default(ini_path):
    cm = ConfigManager()
    assert ini_path.exists()
    for section, options in DEFAULT_CONFIG.items():
        for key, value in options.items():
            assert cm.get(section, key) == value


def test_missing_keys_are_filled_from_defaults(ini_path):
    """A hand-edited / partially written ini must still resolve every
    documented key (this was the int(None) crash)."""
    ini_path.write_text("[NETWORK]\nudp_ip = 239.255.0.0\n", encoding='utf-8')
    cm = ConfigManager()
    assert cm.get('NETWORK', 'udp_ip') == '239.255.0.0'     # user value kept
    assert cm.get('NETWORK', 'udp_port') == '2237'          # default filled
    assert cm.get('ANALYSIS', 'my_callsign') == 'N0CALL'    # section added
    # ...and persisted, so the next launch doesn't repeat the repair
    reread = configparser.ConfigParser()
    reread.read(ini_path, encoding='utf-8')
    assert reread.get('NETWORK', 'udp_port') == '2237'


def test_corrupt_file_is_backed_up_and_reset(ini_path):
    ini_path.write_text("this is not an ini file\n", encoding='utf-8')
    cm = ConfigManager()
    assert cm.get('NETWORK', 'udp_port') == '2237'
    assert ini_path.with_suffix('.ini.corrupt').exists()


def test_get_int_never_raises(ini_path):
    cm = ConfigManager()
    cm.config['NETWORK']['udp_port'] = 'twenty'
    assert cm.get_int('NETWORK', 'udp_port', 2237) == 2237
    assert cm.get_int('NOSUCH', 'key', 7) == 7
    cm.config['NETWORK']['udp_port'] = ' 2238 '
    assert cm.get_int('NETWORK', 'udp_port', 2237) == 2238


def test_save_is_atomic_and_leaves_no_temp_files(ini_path):
    cm = ConfigManager()
    cm.save_setting('ANALYSIS', 'my_callsign', 'WU2C')
    leftovers = [p for p in ini_path.parent.iterdir() if p.name != ini_path.name]
    assert leftovers == []
    assert ConfigManager().get('ANALYSIS', 'my_callsign') == 'WU2C'


@pytest.mark.parametrize("grid", ['FN00aa', 'FN00AA', 'fn00aa', ' FN00aa ', '', None])
def test_placeholder_grid_is_case_insensitive(grid):
    assert is_placeholder_grid(grid)


def test_real_grid_is_not_placeholder():
    assert not is_placeholder_grid('FN42')
    assert not is_placeholder_grid('FN00ab')


def test_station_needs_setup():
    assert station_needs_setup('N0CALL', 'FN42')
    assert station_needs_setup('WU2C', 'FN00AA')
    assert not station_needs_setup('WU2C', 'FN30')
    assert is_placeholder_callsign('n0call')
