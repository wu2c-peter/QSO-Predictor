# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]
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
import sys
from pathlib import Path


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
        'my_grid': 'FN00aa'
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

    def get_forward_ports(self):
        ports_str = self.config.get('NETWORK', 'forward_ports', fallback='')
        if not ports_str:
            return []
        try:
            return [int(p.strip()) for p in ports_str.split(',') if p.strip()]
        except ValueError:
            return []
