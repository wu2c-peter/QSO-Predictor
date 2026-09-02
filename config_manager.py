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
import functools
import logging
import os
import socket
import sys
import tempfile
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

# Placeholder identity written by create_default_config(). Compared
# case-insensitively everywhere: the Settings dialog upper-cases the grid
# on save, so a premature Save turns 'FN00aa' into 'FN00AA' and every
# case-sensitive guard used to stop matching (IONIS then predicted from
# western Pennsylvania for everyone).
PLACEHOLDER_CALLSIGN = 'N0CALL'
PLACEHOLDER_GRID = 'FN00aa'


def is_placeholder_callsign(call):
    return not call or str(call).strip().upper() == PLACEHOLDER_CALLSIGN


def is_placeholder_grid(grid):
    return not grid or str(grid).strip().upper() == PLACEHOLDER_GRID.upper()


def station_needs_setup(call, grid):
    """True until the operator has replaced BOTH placeholder values."""
    return is_placeholder_callsign(call) or is_placeholder_grid(grid)


class ConfigManager:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.load_config()

    def load_config(self):
        """Read the ini, tolerating a corrupt or partial file.

        A truncated / hand-edited file used to raise at startup (before
        any window existed) or come back missing keys that callers then
        int()'d into a TypeError. Now: parse errors back the file up and
        start from defaults; missing sections/keys are filled from
        DEFAULT_CONFIG so every documented key always resolves.
        """
        self.config = configparser.ConfigParser()
        if CONFIG_FILE.exists():
            try:
                try:
                    self.config.read(CONFIG_FILE, encoding='utf-8')
                except UnicodeDecodeError:
                    # Older releases wrote with the platform codec
                    # (cp1252 on Windows) — re-read that way once.
                    self.config = configparser.ConfigParser()
                    self.config.read(CONFIG_FILE)
            except configparser.Error as e:
                logger.error(f"Config: {CONFIG_FILE} is unreadable ({e}); "
                             f"backing it up and starting from defaults")
                try:
                    os.replace(CONFIG_FILE, CONFIG_FILE.with_suffix('.ini.corrupt'))
                except OSError as e2:
                    logger.warning(f"Config: could not back up corrupt file: {e2}")
                self.config = configparser.ConfigParser()
        if self._apply_defaults() or not CONFIG_FILE.exists():
            self._write()

    def _apply_defaults(self):
        """Fill in any missing section/key from DEFAULT_CONFIG.
        Returns True if anything was added."""
        changed = False
        for section, options in DEFAULT_CONFIG.items():
            if section not in self.config:
                self.config.add_section(section)
                changed = True
            for key, value in options.items():
                if key not in self.config[section]:
                    self.config[section][key] = value
                    changed = True
        return changed

    def create_default_config(self):
        for section, options in DEFAULT_CONFIG.items():
            self.config[section] = dict(options)
        self._write()

    def _write(self):
        """Atomic write: temp file in the same directory, then os.replace,
        so a crash mid-write can never leave a truncated ini behind."""
        fd, tmp = tempfile.mkstemp(prefix='.qso_predictor_', suffix='.ini',
                                   dir=str(CONFIG_FILE.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                self.config.write(f)
            os.replace(tmp, CONFIG_FILE)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def save_setting(self, section, key, value):
        if section not in self.config:
            self.config.add_section(section)
        self.config[section][str(key)] = str(value)
        self._write()

    def get(self, section, key, fallback=None):
        return self.config.get(section, key, fallback=fallback)

    def get_int(self, section, key, default):
        """Integer read that never raises: a missing or non-numeric value
        returns `default` (and logs it) instead of int(None) blowing up
        during MainWindow construction."""
        raw = self.config.get(section, key, fallback=None)
        try:
            return int(str(raw).strip())
        except (TypeError, ValueError):
            if raw is not None:
                logger.warning(f"Config: {section}/{key}={raw!r} is not an "
                               f"integer; using {default}")
            return default

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


@functools.lru_cache(maxsize=1)
def local_host_identities():
    """Names and IPv4 addresses that mean *this machine*, lower-cased.

    Beyond loopback: the hostname, its short form, the mDNS
    `<hostname>.local` form, and every IPv4 address the hostname
    resolves to locally. Cached — the getaddrinfo is a local lookup
    (same call multicast_join_addrs makes at startup) but there is no
    reason to repeat it per settings-dialog keystroke.
    """
    names = {'localhost', '0.0.0.0'}
    try:
        hostname = socket.gethostname()
    except OSError:
        return frozenset(names)
    if hostname:
        h = hostname.casefold()
        short = h.split('.')[0]
        names.update({h, short, f"{short}.local"})
        try:
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET,
                                           socket.SOCK_DGRAM):
                names.add(info[4][0])
        except OSError:
            pass
    return frozenset(names)


def is_local_host(host):
    """True for destinations on this machine (the self-forward filters
    only ever strip LOCAL loops — a remote target reusing our listen
    port number is legitimate).

    Recognises loopback, `localhost`, and this machine's own hostname /
    `.local` name / LAN addresses: `my-mac.local:2237` with the listener
    on 2237 is exactly as much of a loop as `127.0.0.1:2237`, and used
    to sail past this check.
    """
    h = (host or '').strip().casefold()
    if not h:
        return False
    if h.startswith('127.') or h == 'localhost':
        return True
    return h in local_host_identities()
