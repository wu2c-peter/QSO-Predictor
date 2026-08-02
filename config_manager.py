# QSO Predictor
# Copyright (C) 2025 Peter Hirst (WU2C)
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

import configparser
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_config_dir():
    """Get platform-appropriate config directory."""
    if sys.platform == "win32":
        # Windows: AppData/Roaming
        base = Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        # macOS: ~/Library/Application Support
        base = Path.home() / "Library" / "Application Support"
    else:
        # Linux: ~/.config
        base = Path.home() / ".config"
    
    config_dir = base / "QSO Predictor"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


CONFIG_FILE = get_config_dir() / 'qso_predictor.ini'

DEFAULT_CONFIG = {
    'NETWORK': {
        'udp_ip': '127.0.0.1',
        'udp_port': '2237',
        'forward_ports': '2238' 
    },
    'APPEARANCE': {
        'font_family': 'Segoe UI',
        'font_size': '10',
        'theme_mode': 'Dark',
        'high_prob_color': '#00FF00',
        'low_prob_color': '#FF5555'
    },
    'ANALYSIS': {
        'my_callsign': 'N0CALL',
        'my_grid': 'FN00aa',
        'outcome_recording': 'true'
    },
    'IONIS': {
        'enabled': 'true'
    },
    'FT8WEB': {
        'enabled': 'false',
        'ws_port': '2442'
    }
}

class ConfigManager:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.load_config()

    def load_config(self):
        if not CONFIG_FILE.exists():
            self.create_default_config()
        self.config.read(CONFIG_FILE)

    def create_default_config(self):
        for section, options in DEFAULT_CONFIG.items():
            self.config[section] = options
        with open(CONFIG_FILE, 'w') as f:
            self.config.write(f)

    def save_setting(self, section, key, value):
        if section not in self.config:
            self.config.add_section(section)
        self.config[section][str(key)] = str(value)
        with open(CONFIG_FILE, 'w') as f:
            self.config.write(f)

    def get(self, section, key, fallback=None):
        return self.config.get(section, key, fallback=fallback)

    def get_forward_targets(self):
        return parse_forward_targets(
            self.config.get('NETWORK', 'forward_ports', fallback=''))


def parse_forward_targets(spec):
    """Parse the NETWORK/forward_ports value into (host, port) tuples.

    Persisted-format contract: bare ports ("2238") are the historic
    syntax and mean 127.0.0.1:2238 — existing configs keep working
    unchanged. "host:port" entries ("192.168.1.50:2237",
    "shackpc.local:2237") forward across machines; multicast doesn't
    traverse Wi-Fi/routers reliably, so multi-machine stations chain
    with unicast forwards instead. Invalid entries are skipped with a
    warning, never fatal.
    """
    targets = []
    for entry in (spec or '').split(','):
        entry = entry.strip()
        if not entry:
            continue
        host, sep, port_str = entry.rpartition(':')
        if not sep:
            host, port_str = '127.0.0.1', entry
        host = host.strip() or '127.0.0.1'
        try:
            port = int(port_str.strip())
        except ValueError:
            logger.warning(f"Config: ignoring invalid forward target {entry!r}")
            continue
        if not 1 <= port <= 65535:
            logger.warning(f"Config: ignoring out-of-range forward target {entry!r}")
            continue
        targets.append((host, port))
    return targets


def is_local_host(host):
    """True for destinations on this machine (the self-forward filters
    only ever strip LOCAL loops — a remote target reusing our listen
    port number is legitimate)."""
    return host.startswith('127.') or host.casefold() == 'localhost'
