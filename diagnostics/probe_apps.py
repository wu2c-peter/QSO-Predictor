"""
App detection probes: config-file discovery and running-process listing.

Lifted unchanged from `setup_wizard.py` (v2.2.0) in migration step 2 of
dev-docs/DIAGNOSTICS_SPEC.md. Cross-platform by design — per-OS branches
run at call time, so the module imports safely everywhere. Uses platform-
native tools (tasklist/ps) via subprocess rather than psutil to avoid a
dependency.

Read-only: never writes to other apps' config files.

QSO Predictor
Copyright (C) 2025 Peter Hirst (WU2C)
"""

import configparser
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from diagnostics.models import DetectedApp

logger = logging.getLogger(__name__)


def _instance_from_stem(stem: str, app_name: str) -> str:
    """Rig-name instance from a multi-instance ini filename ("WSJT-X -
    IC-7300.ini" -> "IC-7300"). Fallback-search hits must keep their
    instance identity or two legitimate rig configs read as duplicate
    copies of one config (Config Doctor false WARNING)."""
    prefix = f"{app_name} - "
    return stem[len(prefix):] if stem.startswith(prefix) else ""


class ConfigFileReader:
    """
    Reads configuration from WSJT-X and JTDX installations.

    WSJT-X and JTDX both use Qt QSettings in INI format.

    Known locations:
      Windows: %LOCALAPPDATA%/WSJT-X/WSJT-X.ini
               %LOCALAPPDATA%/JTDX/JTDX.ini
      macOS:   ~/Library/Preferences/WSJT-X.ini (or plist)
      Linux:   ~/.config/WSJT-X.ini

    Multi-instance WSJT-X uses:
      %LOCALAPPDATA%/WSJT-X - <RIGNAME>/WSJT-X - <RIGNAME>.ini

    Key QSettings entries (from WSJT-X Configuration.cpp):
      MyCall, MyGrid, UDPServerPort, UDPServerAddress,
      AcceptUDPRequests, N1MMServer, N1MMServerPort
    """

    # QSettings key names from WSJT-X/JTDX source code
    KEYS_CALLSIGN = ['MyCall', 'mycall', 'myCall']
    KEYS_GRID = ['MyGrid', 'mygrid', 'myGrid', 'C2MyGrid']
    KEYS_UDP_PORT = ['UDPServerPort', 'udpServerPort', 'UdpServerPort']
    KEYS_UDP_ADDR = ['UDPServerAddress', 'udpServerAddress', 'UDPServer']
    KEYS_ACCEPT_UDP = ['AcceptUDPRequests', 'acceptUDPRequests']
    KEYS_SOUND_IN = ['SoundInName', 'soundInName']
    KEYS_SOUND_OUT = ['SoundOutName', 'soundOutName']
    # Rig control (v2.7.0 — Serial/CAT Doctor). PTTMethod is stored as a
    # QVariant blob ("@Variant(...PTT_method_VOX\0)"); _read_config
    # regex-extracts the method name.
    KEYS_RIG = ['Rig']
    KEYS_CAT_PORT = ['CATSerialPort']
    KEYS_PTT_PORT = ['PTTport', 'PTTPort']
    KEYS_PTT_METHOD = ['PTTMethod']

    def __init__(self):
        self._search_paths = self._build_search_paths()

    def _build_search_paths(self) -> List[Dict]:
        """Build list of potential config file locations by platform."""
        paths = []

        if sys.platform == 'win32':
            local_appdata = Path(os.environ.get('LOCALAPPDATA', ''))
            if local_appdata.exists():
                # Standard WSJT-X
                paths.append({
                    'app': 'WSJT-X',
                    'dir': local_appdata / 'WSJT-X',
                    'ini': 'WSJT-X.ini',
                })
                # Standard JTDX
                paths.append({
                    'app': 'JTDX',
                    'dir': local_appdata / 'JTDX',
                    'ini': 'JTDX.ini',
                })
                # Multi-instance WSJT-X: scan for "WSJT-X - *" directories
                try:
                    for d in local_appdata.iterdir():
                        if d.is_dir() and d.name.startswith('WSJT-X - '):
                            instance = d.name.replace('WSJT-X - ', '')
                            paths.append({
                                'app': 'WSJT-X',
                                'dir': d,
                                'ini': f'{d.name}.ini',
                                'instance': instance,
                            })
                except PermissionError:
                    pass

                # Multi-instance JTDX: scan for "JTDX - *" directories
                try:
                    for d in local_appdata.iterdir():
                        if d.is_dir() and d.name.startswith('JTDX - '):
                            instance = d.name.replace('JTDX - ', '')
                            paths.append({
                                'app': 'JTDX',
                                'dir': d,
                                'ini': f'{d.name}.ini',
                                'instance': instance,
                            })
                except PermissionError:
                    pass

        elif sys.platform == 'darwin':
            # macOS: Qt stores INI files in ~/Library/Preferences/
            prefs = Path.home() / 'Library' / 'Preferences'
            app_support = Path.home() / 'Library' / 'Application Support'

            # WSJT-X on macOS can use either location
            for base in [prefs, app_support]:
                paths.append({
                    'app': 'WSJT-X',
                    'dir': base / 'WSJT-X',
                    'ini': 'WSJT-X.ini',
                })
                paths.append({
                    'app': 'JTDX',
                    'dir': base / 'JTDX',
                    'ini': 'JTDX.ini',
                })
            # Also check directly in Preferences (flat files — the
            # location Qt's ConfigLocation actually uses on macOS)
            paths.append({
                'app': 'WSJT-X',
                'dir': prefs,
                'ini': 'WSJT-X.ini',
            })
            paths.append({
                'app': 'JTDX',
                'dir': prefs,
                'ini': 'JTDX.ini',
            })

        else:
            # Linux: ~/.config/
            config_dir = Path.home() / '.config'
            paths.append({
                'app': 'WSJT-X',
                'dir': config_dir / 'WSJT-X',
                'ini': 'WSJT-X.ini',
            })
            paths.append({
                'app': 'JTDX',
                'dir': config_dir / 'JTDX',
                'ini': 'JTDX.ini',
            })
            # Also check flat in .config
            paths.append({
                'app': 'WSJT-X',
                'dir': config_dir,
                'ini': 'WSJT-X.ini',
            })
            paths.append({
                'app': 'JTDX',
                'dir': config_dir,
                'ini': 'JTDX.ini',
            })

        return paths

    def _fallback_search(self, seen_paths: set) -> List[DetectedApp]:
        """
        Fallback: search common config parent directories for any .ini file
        with 'WSJT' or 'JTDX' in the filename.

        These are unusual, distinctive names — no collision risk — so a
        broader search is safe and fast when standard paths miss.

        Only searches config-plausible locations (not entire disk):
          Windows: %LOCALAPPDATA%, %APPDATA%, %USERPROFILE%
          macOS:   ~/Library/Preferences, ~/Library/Application Support,
                   ~/Library/Containers, ~/.config
          Linux:   ~/.config, ~/.local/share, ~/

        Searches up to 3 levels deep. Skips huge directories.
        """
        found = []

        # Build list of parent directories to search
        search_roots = []

        if sys.platform == 'win32':
            for env_var in ['LOCALAPPDATA', 'APPDATA']:
                p = Path(os.environ.get(env_var, ''))
                if p.exists():
                    search_roots.append(p)
        elif sys.platform == 'darwin':
            home = Path.home()
            for subdir in ['Library/Preferences', 'Library/Application Support',
                           'Library/Containers', '.config']:
                p = home / subdir
                if p.exists():
                    search_roots.append(p)
        else:
            home = Path.home()
            for subdir in ['.config', '.local/share', '.local']:
                p = home / subdir
                if p.exists():
                    search_roots.append(p)

        # Search patterns — case-insensitive matching
        patterns = ['wsjt', 'jtdx']

        for root in search_roots:
            try:
                # glob up to 3 levels: root/*/*.ini, root/*/*/*.ini, etc.
                for depth_pattern in ['*/*.ini', '*/*/*.ini', '*/*/*/*.ini']:
                    for ini_path in root.glob(depth_pattern):
                        if ini_path in seen_paths:
                            continue

                        name_lower = ini_path.name.lower()
                        dir_lower = ini_path.parent.name.lower()

                        for pattern in patterns:
                            if pattern in name_lower or pattern in dir_lower:
                                seen_paths.add(ini_path)

                                # Determine app name from what we matched
                                app_name = 'WSJT-X' if 'wsjt' in name_lower or 'wsjt' in dir_lower else 'JTDX'

                                logger.info(f"Setup: Fallback search found {app_name} config at {ini_path}")

                                app = self._read_config(
                                    ini_path, app_name,
                                    _instance_from_stem(ini_path.stem,
                                                        app_name))
                                if app:
                                    app.log_directory = ini_path.parent
                                    found.append(app)
                                break  # Don't match both patterns for same file

            except (PermissionError, OSError) as e:
                logger.debug(f"Setup: Fallback search skipped {root}: {e}")
                continue

        return found

    def discover_configs(self) -> List[DetectedApp]:
        """
        Scan for WSJT-X and JTDX configuration files.

        Strategy:
          1. Check known/standard paths first (instant)
          2. If nothing found, do a broader search in config directories
             for files with 'WSJT' or 'JTDX' in the name (still fast,
             these are very distinctive names)

        Returns list of DetectedApp with extracted settings.
        """
        found = []
        seen_paths = set()

        # Phase 1: Check known paths
        for entry in self._search_paths:
            ini_path = entry['dir'] / entry['ini']

            if ini_path.exists() and ini_path not in seen_paths:
                seen_paths.add(ini_path)
                logger.debug(f"Setup: Found config at {ini_path}")

                app = self._read_config(
                    ini_path,
                    entry['app'],
                    entry.get('instance', '')
                )
                if app:
                    # Also record the log directory (for bootstrap)
                    app.log_directory = entry['dir']
                    found.append(app)

        # Phase 2: If nothing found, do a broader fallback search
        if not found:
            logger.info("Setup: Standard paths found nothing, trying broader search...")
            found.extend(self._fallback_search(seen_paths))

        if found:
            logger.info(f"Setup: Discovered {len(found)} app config(s): "
                       f"{', '.join(a.name + (' (' + a.instance_name + ')' if a.instance_name else '') for a in found)}")
        else:
            logger.info("Setup: No WSJT-X or JTDX configurations found")

        return found

    def _read_config(self, ini_path: Path, app_name: str,
                     instance: str = "") -> Optional[DetectedApp]:
        """
        Read settings from a WSJT-X/JTDX .ini file.

        Qt QSettings INI format uses [General] section by default, but the
        keys we want may live under [Configuration] or any other section
        depending on Qt version — _find_value searches them all. Keys
        BEFORE any section header are NOT handled (configparser raises and
        we return None); QSettings always writes section headers, so real
        WSJT-X/JTDX files have them. Pinned by test.
        """
        try:
            # interpolation=None: Qt QSettings does no %-interpolation,
            # and a bare '%' in any value (a device name, a free-text
            # field) would otherwise raise at get() and silently drop
            # the whole DetectedApp (review 2026-07-27).
            config = configparser.ConfigParser(interpolation=None)
            # Preserve case of keys (Qt QSettings is case-sensitive)
            config.optionxform = str

            try:
                config.read(ini_path, encoding='utf-8')
            except (configparser.Error, UnicodeDecodeError):
                try:
                    config.read(ini_path, encoding='latin-1')
                except configparser.Error as e:
                    logger.debug(f"Setup: Could not parse {ini_path}: {e}")
                    return None

            app = DetectedApp(
                name=app_name,
                config_path=ini_path,
                instance_name=instance,
            )
            try:
                app.config_mtime = datetime.fromtimestamp(
                    ini_path.stat().st_mtime, timezone.utc
                ).strftime('%Y-%m-%dT%H:%M:%SZ')
            except OSError:
                pass    # "" = unread, per the field's convention

            # Search across all sections for our keys
            app.callsign = self._find_value(config, self.KEYS_CALLSIGN)
            app.grid = self._find_value(config, self.KEYS_GRID)

            port_str = self._find_value(config, self.KEYS_UDP_PORT)
            if port_str:
                try:
                    port = int(port_str)
                    # Range-clamp: hand-edited/corrupt configs happen,
                    # and out-of-range ports crash downstream binds.
                    app.udp_port = port if 0 < port < 65536 else 2237
                except ValueError:
                    app.udp_port = 2237  # Default
            else:
                app.udp_port = 2237

            # Absent key -> the app's own baked-in default (127.0.0.1)
            # applies. Key PRESENT but empty -> the user cleared it to
            # disable UDP; preserve that as '' so downstream doctors
            # don't invent a chain the operator turned off.
            raw_addr = self._find_raw(config, self.KEYS_UDP_ADDR)
            if raw_addr is None:
                app.udp_ip = '127.0.0.1'
            else:
                app.udp_ip = raw_addr.strip()

            accept_str = self._find_value(config, self.KEYS_ACCEPT_UDP)
            app.accept_udp = accept_str in ('true', '1', 'True', 'yes')

            # Stored audio device bindings — the Config Doctor verifies
            # these against live audio state (stale after USB
            # re-enumeration renames a device).
            app.sound_in = self._find_value(config, self.KEYS_SOUND_IN)
            app.sound_out = self._find_value(config, self.KEYS_SOUND_OUT)

            # Rig control — the Serial/CAT Doctor verifies configured
            # ports against enumerated serial hardware. PTTMethod is a
            # QVariant blob; the method name is embedded as
            # "PTT_method_VOX" etc.
            app.rig_name = self._find_value(config, self.KEYS_RIG)
            app.cat_port = self._find_value(config, self.KEYS_CAT_PORT)
            app.ptt_port = self._find_value(config, self.KEYS_PTT_PORT)
            raw_method = self._find_value(config, self.KEYS_PTT_METHOD)
            m = re.search(r'PTT_method_(\w+)', raw_method)
            app.ptt_method = m.group(1) if m else raw_method

            logger.debug(f"Setup: {app_name}{' (' + instance + ')' if instance else ''}: "
                        f"call={app.callsign}, grid={app.grid}, "
                        f"udp={app.udp_ip}:{app.udp_port}, accept={app.accept_udp}")

            return app

        except Exception as e:
            logger.warning(f"Setup: Error reading {ini_path}: {e}")
            return None

    def _find_value(self, config: configparser.ConfigParser,
                    key_variants: List[str]) -> str:
        """
        Search all sections of a config file for any of the given key names.
        Returns first match found, or empty string.
        """
        for section in config.sections():
            for key in key_variants:
                try:
                    val = config.get(section, key, fallback=None)
                    if val is not None and val.strip():
                        return val.strip()
                except (configparser.NoSectionError, configparser.NoOptionError):
                    pass
        return ""

    def _find_raw(self, config: configparser.ConfigParser,
                  key_variants: List[str]) -> Optional[str]:
        """Like _find_value but distinguishes key-absent (None) from
        key-present-but-empty ("") — the difference between "app default
        applies" and "user cleared the setting"."""
        for section in config.sections():
            for key in key_variants:
                try:
                    val = config.get(section, key, fallback=None)
                    if val is not None:
                        return val
                except (configparser.NoSectionError, configparser.NoOptionError):
                    pass
        return None


class RunningAppDetector:
    """
    Detect which ham radio applications are currently running.
    Uses platform-native process listing.
    """

    # Process names to look for (lowercase for matching)
    KNOWN_APPS = {
        'wsjtx': 'WSJT-X',
        'wsjt-x': 'WSJT-X',
        'jtdx': 'JTDX',
        'jtalert': 'JTAlert',
        'gridtracker': 'GridTracker',
        'n3fjp': 'N3FJP ACLog',
        'aclog': 'N3FJP ACLog',
        'hrd': 'Ham Radio Deluxe',
        'hamradiodeluxe': 'Ham Radio Deluxe',
        'log4om': 'Log4OM',
    }

    @staticmethod
    def detect() -> List[str]:
        """Return list of detected running ham radio app names."""
        running = []

        try:
            if sys.platform == 'win32':
                output = subprocess.check_output(
                    ['tasklist', '/FO', 'CSV', '/NH'],
                    text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                for line in output.splitlines():
                    parts = line.strip('"').split('","')
                    if parts:
                        proc_lower = parts[0].lower().replace('.exe', '')
                        for pattern, name in RunningAppDetector.KNOWN_APPS.items():
                            if pattern in proc_lower and name not in running:
                                running.append(name)

            elif sys.platform == 'darwin':
                output = subprocess.check_output(
                    ['ps', '-eo', 'comm'],
                    text=True, timeout=5
                )
                for line in output.splitlines():
                    proc_lower = line.strip().lower()
                    for pattern, name in RunningAppDetector.KNOWN_APPS.items():
                        if pattern in proc_lower and name not in running:
                            running.append(name)

            else:  # Linux
                output = subprocess.check_output(
                    ['ps', '-eo', 'comm'],
                    text=True, timeout=5
                )
                for line in output.splitlines():
                    proc_lower = line.strip().lower()
                    for pattern, name in RunningAppDetector.KNOWN_APPS.items():
                        if pattern in proc_lower and name not in running:
                            running.append(name)

        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.debug(f"Setup: Process detection failed: {e}")

        if running:
            logger.info(f"Setup: Running apps: {', '.join(running)}")

        return running
