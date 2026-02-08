# QSO Predictor - Auto-Discovery & Setup Wizard
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.2.0: New module for automatic detection of ham radio app configurations.
# Reads WSJT-X/JTDX config files to pre-fill callsign, grid, UDP settings.
# Detects port conflicts and recommends optimal network configuration.
# Provides first-run setup wizard and on-demand "Auto-Detect" from Settings.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Auto-Discovery & Setup Wizard for QSO Predictor.

Three-phase approach:
  Phase 1: Read WSJT-X/JTDX config files (callsign, grid, UDP port)
  Phase 2: Detect port conflicts with other running apps
  Phase 3: Full setup wizard with recommendations

Design principles:
  - Never write to other apps' config files (read-only)
  - Graceful fallback if detection fails
  - User always has final say (recommendations, not mandates)
  - Cross-platform: Windows, macOS, Linux
"""

import configparser
import logging
import os
import platform
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QRadioButton, QButtonGroup, QFrame,
    QMessageBox, QProgressBar, QScrollArea, QWidget,
    QGridLayout, QLineEdit, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class DetectedApp:
    """A ham radio application detected on this system."""
    name: str                       # e.g. "WSJT-X", "JTDX", "JTAlert"
    config_path: Optional[Path]     # Path to config file (if found)
    instance_name: str = ""         # For multi-instance (e.g. "OmniRig Rig 1")
    callsign: str = ""
    grid: str = ""
    udp_ip: str = ""
    udp_port: int = 0
    accept_udp: bool = False
    is_running: bool = False
    log_directory: Optional[Path] = None


@dataclass
class PortInfo:
    """Information about a UDP port in use."""
    port: int
    ip: str = ""
    process_name: str = ""
    pid: int = 0


@dataclass
class SetupRecommendation:
    """A recommended configuration for QSO Predictor."""
    callsign: str = ""
    grid: str = ""
    udp_ip: str = "127.0.0.1"
    udp_port: int = 2237
    forward_ports: str = ""
    use_multicast: bool = False
    confidence: str = "low"         # low / medium / high
    source: str = ""                # Where the recommendation came from
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# ============================================================================
# Phase 1: Config File Discovery
# ============================================================================

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
            # Also check directly in Preferences (flat file)
            paths.append({
                'app': 'WSJT-X',
                'dir': prefs,
                'ini': 'WSJT-X.ini',
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
                                
                                app = self._read_config(ini_path, app_name)
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
        
        Qt QSettings INI format uses [General] section by default,
        but settings may be at top level (no section) or under 
        [Configuration] depending on Qt version.
        """
        try:
            # Qt INI files sometimes have keys outside any section header.
            # configparser requires sections, so we'll parse more carefully.
            config = configparser.ConfigParser()
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
            
            # Search across all sections for our keys
            app.callsign = self._find_value(config, self.KEYS_CALLSIGN)
            app.grid = self._find_value(config, self.KEYS_GRID)
            
            port_str = self._find_value(config, self.KEYS_UDP_PORT)
            if port_str:
                try:
                    app.udp_port = int(port_str)
                except ValueError:
                    app.udp_port = 2237  # Default
            else:
                app.udp_port = 2237
            
            app.udp_ip = self._find_value(config, self.KEYS_UDP_ADDR) or '127.0.0.1'
            
            accept_str = self._find_value(config, self.KEYS_ACCEPT_UDP)
            app.accept_udp = accept_str in ('true', '1', 'True', 'yes')
            
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


# ============================================================================
# Phase 2: Port Conflict Detection
# ============================================================================

class PortScanner:
    """
    Detect UDP port usage to identify conflicts.
    
    Uses platform-native tools (netstat/ss) rather than psutil
    to avoid adding a dependency. Falls back gracefully.
    """
    
    # Common ham radio UDP ports
    HAM_PORT_RANGE = range(2230, 2260)
    
    @staticmethod
    def scan_udp_ports() -> List[PortInfo]:
        """
        Find processes listening on UDP ports in the ham radio range.
        Returns list of PortInfo for occupied ports.
        """
        occupied = []
        
        try:
            if sys.platform == 'win32':
                occupied = PortScanner._scan_windows()
            elif sys.platform == 'darwin':
                occupied = PortScanner._scan_macos()
            else:
                occupied = PortScanner._scan_linux()
        except Exception as e:
            logger.debug(f"Setup: Port scan failed: {e}")
        
        # Also do a quick socket probe for common ports
        for port in [2237, 2238, 2239, 2240]:
            if not any(p.port == port for p in occupied):
                if PortScanner._is_port_in_use(port):
                    occupied.append(PortInfo(port=port, ip='0.0.0.0',
                                            process_name='unknown'))
        
        if occupied:
            logger.info(f"Setup: Ports in use: "
                       f"{', '.join(f'{p.port} ({p.process_name})' for p in occupied)}")
        
        return occupied
    
    @staticmethod
    def _scan_windows() -> List[PortInfo]:
        """Parse netstat -ano on Windows for UDP listeners."""
        result = []
        try:
            output = subprocess.check_output(
                ['netstat', '-ano', '-p', 'UDP'],
                text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            for line in output.splitlines():
                # UDP    0.0.0.0:2237    *:*    12345
                parts = line.split()
                if len(parts) >= 4 and parts[0] == 'UDP':
                    addr = parts[1]
                    if ':' in addr:
                        ip, port_str = addr.rsplit(':', 1)
                        try:
                            port = int(port_str)
                            if port in PortScanner.HAM_PORT_RANGE:
                                pid = int(parts[-1]) if parts[-1].isdigit() else 0
                                proc_name = PortScanner._get_process_name_win(pid)
                                result.append(PortInfo(
                                    port=port, ip=ip,
                                    process_name=proc_name, pid=pid
                                ))
                        except ValueError:
                            pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return result
    
    @staticmethod
    def _get_process_name_win(pid: int) -> str:
        """Get process name from PID on Windows."""
        if pid == 0:
            return 'unknown'
        try:
            output = subprocess.check_output(
                ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                text=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            for line in output.strip().splitlines():
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    return parts[0]
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return f'PID {pid}'
    
    @staticmethod
    def _scan_macos() -> List[PortInfo]:
        """Parse lsof on macOS for UDP listeners."""
        result = []
        try:
            output = subprocess.check_output(
                ['lsof', '-iUDP', '-nP'],
                text=True, timeout=5
            )
            for line in output.splitlines()[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 9:
                    name_field = parts[8] if len(parts) > 8 else parts[-1]
                    if ':' in name_field:
                        port_str = name_field.rsplit(':', 1)[-1]
                        try:
                            port = int(port_str)
                            if port in PortScanner.HAM_PORT_RANGE:
                                result.append(PortInfo(
                                    port=port, ip='0.0.0.0',
                                    process_name=parts[0],
                                    pid=int(parts[1]) if parts[1].isdigit() else 0
                                ))
                        except ValueError:
                            pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return result
    
    @staticmethod
    def _scan_linux() -> List[PortInfo]:
        """Parse ss on Linux for UDP listeners."""
        result = []
        try:
            output = subprocess.check_output(
                ['ss', '-ulnp'],
                text=True, timeout=5
            )
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    addr = parts[4]
                    if ':' in addr:
                        port_str = addr.rsplit(':', 1)[-1]
                        try:
                            port = int(port_str)
                            if port in PortScanner.HAM_PORT_RANGE:
                                # Extract process name from users: field
                                proc = 'unknown'
                                for p in parts:
                                    if 'users:' in p:
                                        match = re.search(r'"([^"]+)"', p)
                                        if match:
                                            proc = match.group(1)
                                result.append(PortInfo(
                                    port=port, ip=addr.rsplit(':', 1)[0],
                                    process_name=proc
                                ))
                        except ValueError:
                            pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return result
    
    @staticmethod
    def _is_port_in_use(port: int) -> bool:
        """Quick check if a UDP port is in use by trying to bind it."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            return False  # We bound it, so it was free
        except OSError:
            return True   # Already in use
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
    
    @staticmethod
    def find_free_port(start: int = 2237, count: int = 20) -> int:
        """Find the first available UDP port starting from 'start'."""
        for port in range(start, start + count):
            if not PortScanner._is_port_in_use(port):
                return port
        return start  # Fallback


# ============================================================================
# Phase 3: Running App Detection
# ============================================================================

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


# ============================================================================
# Recommendation Engine
# ============================================================================

class SetupAnalyzer:
    """
    Combines all detection results into a recommended configuration.
    """
    
    @staticmethod
    def analyze(apps: List[DetectedApp],
                ports_in_use: List[PortInfo],
                running_apps: List[str]) -> SetupRecommendation:
        """
        Analyze detected environment and produce a recommendation.
        
        Priority for callsign/grid:
          1. JTDX config (preferred for QSO Predictor)
          2. WSJT-X config
          
        Priority for UDP config:
          1. If multicast detected, join multicast
          2. If port free, use standard 2237
          3. If port occupied, find secondary or suggest secondary UDP
        """
        rec = SetupRecommendation()
        
        # --- Station info (callsign/grid) ---
        # Prefer JTDX, then WSJT-X, then first with data
        jtdx_apps = [a for a in apps if a.name == 'JTDX' and a.callsign]
        wsjtx_apps = [a for a in apps if a.name == 'WSJT-X' and a.callsign]
        any_with_call = [a for a in apps if a.callsign]
        
        source_app = None
        if jtdx_apps:
            source_app = jtdx_apps[0]
        elif wsjtx_apps:
            source_app = wsjtx_apps[0]
        elif any_with_call:
            source_app = any_with_call[0]
        
        if source_app:
            rec.callsign = source_app.callsign.upper()
            rec.grid = source_app.grid.upper() if source_app.grid else ''
            rec.source = f"from {source_app.name}" + (
                f" ({source_app.instance_name})" if source_app.instance_name else ""
            )
            rec.confidence = "high"
            rec.notes.append(
                f"Callsign and grid detected {rec.source}"
            )
        
        # --- UDP configuration ---
        # Check if any detected app uses multicast
        multicast_apps = [a for a in apps
                         if a.udp_ip and a.udp_ip.startswith(('224.', '225.', '226.',
                                '227.', '228.', '229.', '230.', '231.', '232.',
                                '233.', '234.', '235.', '236.', '237.', '238.', '239.'))]
        
        # Check if JTAlert is running (strong indicator of multicast need)
        jtalert_running = 'JTAlert' in running_apps
        
        if multicast_apps:
            # Use same multicast group as the detected app
            mcast_app = multicast_apps[0]
            rec.udp_ip = mcast_app.udp_ip
            rec.udp_port = mcast_app.udp_port
            rec.use_multicast = True
            rec.notes.append(
                f"Multicast detected: {mcast_app.name} uses {mcast_app.udp_ip}:{mcast_app.udp_port}"
            )
            
        elif jtalert_running:
            # JTAlert is running - likely needs multicast or secondary port
            rec.warnings.append(
                "JTAlert is running — you may need multicast or a secondary UDP port"
            )
            # Check if port 2237 is occupied
            port_2237_used = any(p.port == 2237 for p in ports_in_use)
            if port_2237_used:
                free_port = PortScanner.find_free_port(2238)
                rec.udp_port = free_port
                rec.udp_ip = '127.0.0.1'
                rec.notes.append(
                    f"Port 2237 in use — recommending port {free_port}"
                )
                rec.notes.append(
                    "Configure WSJT-X/JTDX secondary UDP to match this port"
                )
            else:
                rec.udp_port = 2237
                rec.udp_ip = '127.0.0.1'
                
        else:
            # Standard setup - use detected port or default
            if source_app and source_app.udp_port:
                target_port = source_app.udp_port
            else:
                target_port = 2237
            
            port_used = any(p.port == target_port for p in ports_in_use)
            if port_used:
                # Port is taken - find a free one
                free_port = PortScanner.find_free_port(target_port + 1)
                rec.udp_port = free_port
                rec.udp_ip = '127.0.0.1'
                
                # Find who's using the port
                occupier = next((p for p in ports_in_use if p.port == target_port), None)
                occupier_name = occupier.process_name if occupier else 'another app'
                
                rec.warnings.append(
                    f"Port {target_port} is in use by {occupier_name}"
                )
                rec.notes.append(
                    f"Recommending port {free_port} — configure WSJT-X/JTDX "
                    f"secondary UDP to send to 127.0.0.1:{free_port}"
                )
            else:
                rec.udp_port = target_port
                rec.udp_ip = source_app.udp_ip if source_app else '127.0.0.1'
        
        # --- Detect potential forward port needs ---
        other_listeners = [a for a in running_apps
                         if a not in ('WSJT-X', 'JTDX')]
        if other_listeners and not rec.use_multicast:
            rec.notes.append(
                f"Other apps detected ({', '.join(other_listeners)}) — "
                f"consider UDP forwarding if they need decode data"
            )
        
        # --- Confidence level ---
        if rec.callsign and rec.callsign != 'N0CALL':
            if not rec.warnings:
                rec.confidence = "high"
            else:
                rec.confidence = "medium"
        elif apps:
            rec.confidence = "medium"  # Found apps but no callsign
        else:
            rec.confidence = "low"
        
        return rec


# ============================================================================
# Background Scanner Thread
# ============================================================================

class ScanWorker(QThread):
    """Run detection in background to avoid blocking the UI."""
    
    scan_complete = pyqtSignal(list, list, list, object)
    # (apps, ports, running_apps, recommendation)
    progress = pyqtSignal(str)
    
    def run(self):
        try:
            self.progress.emit("Scanning for WSJT-X and JTDX configurations (known paths + search)...")
            reader = ConfigFileReader()
            apps = reader.discover_configs()
            
            self.progress.emit("Checking for port conflicts...")
            ports = PortScanner.scan_udp_ports()
            
            self.progress.emit("Detecting running applications...")
            running = RunningAppDetector.detect()
            
            self.progress.emit("Analyzing configuration...")
            recommendation = SetupAnalyzer.analyze(apps, ports, running)
            
            self.scan_complete.emit(apps, ports, running, recommendation)
            
        except Exception as e:
            logger.error(f"Setup scan failed: {e}")
            self.scan_complete.emit([], [], [], SetupRecommendation())


# ============================================================================
# Setup Wizard Dialog
# ============================================================================

class SetupWizardDialog(QDialog):
    """
    The main setup wizard dialog.
    
    Shows detected configuration and lets user accept or customize.
    Used both for first-run setup and on-demand from Settings.
    """
    
    def __init__(self, parent=None, first_run=False):
        super().__init__(parent)
        self.first_run = first_run
        self.recommendation = None
        self.detected_apps = []
        
        self.setWindowTitle(
            "Welcome to QSO Predictor!" if first_run 
            else "Auto-Detect Configuration"
        )
        self.resize(560, 500)
        self.setMinimumWidth(480)
        
        self._init_ui()
        self._start_scan()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # Header
        if self.first_run:
            header = QLabel(
                "<h2>Welcome to QSO Predictor!</h2>"
                "<p>Let's set things up. Scanning for your ham radio software...</p>"
            )
        else:
            header = QLabel(
                "<h2>Auto-Detect Configuration</h2>"
                "<p>Scanning for WSJT-X, JTDX, and other ham radio software...</p>"
            )
        header.setWordWrap(True)
        layout.addWidget(header)
        
        # Progress
        self.progress_label = QLabel("Starting scan...")
        self.progress_label.setStyleSheet("color: #888888;")
        layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)
        
        # Results area (initially hidden)
        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_widget.hide()
        layout.addWidget(self.results_widget)
        
        # Buttons
        self.btn_layout = QHBoxLayout()
        
        self.btn_manual = QPushButton("Configure Manually")
        self.btn_manual.clicked.connect(self.reject)
        self.btn_manual.setToolTip("Skip auto-detect and configure settings yourself")
        
        self.btn_apply = QPushButton("Apply Configuration")
        self.btn_apply.clicked.connect(self.accept)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setDefault(True)
        
        self.btn_layout.addWidget(self.btn_manual)
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_apply)
        layout.addLayout(self.btn_layout)
    
    def _start_scan(self):
        self.worker = ScanWorker()
        self.worker.progress.connect(self._on_progress)
        self.worker.scan_complete.connect(self._on_scan_complete)
        self.worker.start()
    
    def _on_progress(self, message: str):
        self.progress_label.setText(message)
    
    def _on_scan_complete(self, apps, ports, running, recommendation):
        self.detected_apps = apps
        self.recommendation = recommendation
        
        # Hide progress
        self.progress_bar.hide()
        self.progress_label.hide()
        
        # Build results display
        self._build_results(apps, ports, running, recommendation)
        self.results_widget.show()
        self.btn_apply.setEnabled(True)
    
    def _build_results(self, apps, ports, running, rec):
        """Build the results display with detected info and editable fields."""
        layout = self.results_layout
        
        # --- Detection Summary ---
        summary_group = QGroupBox("What We Found")
        summary_layout = QVBoxLayout(summary_group)
        
        if apps:
            for app in apps:
                instance_suffix = f" ({app.instance_name})" if app.instance_name else ""
                text = f"✅ <b>{app.name}{instance_suffix}</b>"
                details = []
                if app.callsign:
                    details.append(f"Call: {app.callsign}")
                if app.grid:
                    details.append(f"Grid: {app.grid}")
                if app.udp_port:
                    details.append(f"UDP: {app.udp_ip}:{app.udp_port}")
                if details:
                    text += f" — {', '.join(details)}"
                label = QLabel(text)
                label.setTextFormat(Qt.TextFormat.RichText)
                summary_layout.addWidget(label)
        else:
            no_apps = QLabel(
                "⚠️ No WSJT-X or JTDX configuration files found.\n"
                "You'll need to enter your settings manually."
            )
            no_apps.setStyleSheet("color: #ffaa00;")
            no_apps.setWordWrap(True)
            summary_layout.addWidget(no_apps)
        
        if running:
            running_label = QLabel(
                f"📡 Running: {', '.join(running)}"
            )
            running_label.setStyleSheet("color: #888888;")
            summary_layout.addWidget(running_label)
        
        if ports:
            ports_text = ", ".join(
                f"{p.port} ({p.process_name})" for p in ports
            )
            port_label = QLabel(f"🔌 Ports in use: {ports_text}")
            port_label.setStyleSheet("color: #888888;")
            port_label.setWordWrap(True)
            summary_layout.addWidget(port_label)
        
        layout.addWidget(summary_group)
        
        # --- Warnings ---
        if rec.warnings:
            for warning in rec.warnings:
                warn_label = QLabel(f"⚠️ {warning}")
                warn_label.setStyleSheet(
                    "color: #ffaa00; padding: 4px; "
                    "border: 1px solid #665500; border-radius: 3px; "
                    "background-color: #332200;"
                )
                warn_label.setWordWrap(True)
                layout.addWidget(warn_label)
        
        # --- Editable Configuration ---
        config_group = QGroupBox("Recommended Configuration")
        config_layout = QGridLayout(config_group)
        config_layout.setColumnStretch(1, 1)
        
        row = 0
        
        # Callsign
        config_layout.addWidget(QLabel("My Callsign:"), row, 0)
        self.edit_callsign = QLineEdit(rec.callsign)
        self.edit_callsign.setPlaceholderText("e.g. W1ABC")
        self.edit_callsign.setMaximumWidth(200)
        config_layout.addWidget(self.edit_callsign, row, 1)
        if rec.callsign:
            source_label = QLabel(f"<small>({rec.source})</small>")
            source_label.setStyleSheet("color: #00cc00;")
            config_layout.addWidget(source_label, row, 2)
        row += 1
        
        # Grid
        config_layout.addWidget(QLabel("My Grid:"), row, 0)
        self.edit_grid = QLineEdit(rec.grid)
        self.edit_grid.setPlaceholderText("e.g. FN30pr")
        self.edit_grid.setMaximumWidth(200)
        config_layout.addWidget(self.edit_grid, row, 1)
        row += 1
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444444;")
        config_layout.addWidget(line, row, 0, 1, 3)
        row += 1
        
        # UDP IP
        config_layout.addWidget(QLabel("Listen IP:"), row, 0)
        self.edit_udp_ip = QLineEdit(rec.udp_ip)
        self.edit_udp_ip.setMaximumWidth(200)
        config_layout.addWidget(self.edit_udp_ip, row, 1)
        if rec.use_multicast:
            mc_label = QLabel("<small>(multicast)</small>")
            mc_label.setStyleSheet("color: #00aaff;")
            config_layout.addWidget(mc_label, row, 2)
        row += 1
        
        # UDP Port
        config_layout.addWidget(QLabel("Listen Port:"), row, 0)
        self.edit_udp_port = QSpinBox()
        self.edit_udp_port.setRange(1024, 65535)
        self.edit_udp_port.setValue(rec.udp_port)
        self.edit_udp_port.setMaximumWidth(200)
        config_layout.addWidget(self.edit_udp_port, row, 1)
        row += 1
        
        layout.addWidget(config_group)
        
        # --- Notes ---
        if rec.notes:
            notes_group = QGroupBox("Setup Notes")
            notes_layout = QVBoxLayout(notes_group)
            for note in rec.notes:
                note_label = QLabel(f"💡 {note}")
                note_label.setWordWrap(True)
                note_label.setStyleSheet("color: #aaaaaa; padding: 2px;")
                notes_layout.addWidget(note_label)
            layout.addWidget(notes_group)
        
        # Confidence indicator
        conf_colors = {'high': '#00cc00', 'medium': '#ffaa00', 'low': '#ff5555'}
        conf_text = {'high': 'High', 'medium': 'Medium', 'low': 'Low'}
        conf_label = QLabel(
            f"<small>Detection confidence: "
            f"<span style='color: {conf_colors[rec.confidence]};'>"
            f"<b>{conf_text[rec.confidence]}</b></span></small>"
        )
        conf_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(conf_label)
    
    def get_config(self) -> dict:
        """Return the user's chosen configuration as a dict."""
        return {
            'callsign': self.edit_callsign.text().strip().upper(),
            'grid': self.edit_grid.text().strip().upper(),
            'udp_ip': self.edit_udp_ip.text().strip(),
            'udp_port': self.edit_udp_port.value(),
        }


# ============================================================================
# Public API
# ============================================================================

def run_auto_detect() -> Optional[SetupRecommendation]:
    """
    Run auto-detection without UI. Returns recommendation or None.
    Useful for programmatic access or testing.
    """
    reader = ConfigFileReader()
    apps = reader.discover_configs()
    ports = PortScanner.scan_udp_ports()
    running = RunningAppDetector.detect()
    return SetupAnalyzer.analyze(apps, ports, running)


def show_setup_wizard(parent=None, first_run=False) -> Optional[dict]:
    """
    Show the setup wizard dialog.
    
    Args:
        parent: Parent widget
        first_run: If True, shows welcome messaging
        
    Returns:
        Dict with config values if accepted, None if cancelled
    """
    dialog = SetupWizardDialog(parent=parent, first_run=first_run)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.get_config()
    return None


def is_first_run(config) -> bool:
    """
    Check if this looks like a first run (unconfigured defaults).
    
    Args:
        config: ConfigManager instance
    """
    callsign = config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
    grid = config.get('ANALYSIS', 'my_grid', fallback='FN00aa')
    return callsign == 'N0CALL' or grid == 'FN00aa'
