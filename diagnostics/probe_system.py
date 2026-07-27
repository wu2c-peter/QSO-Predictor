"""
System probe: OS power management, permissions, and autostart state.

Feeds the System Doctor (DIAGNOSTICS_SPEC.md roster item 5). Everything
platform-specific lives here; the doctor's checks are pure functions
over the SystemSnapshot. Reads are best-effort and passive: registry
values, one pmset invocation, one read-only sqlite open, directory
listings — nothing is modified, no device is opened.

Windows power settings are read from the registry, not parsed out of
`powercfg` output: powercfg localizes every label, and the registry
layout (scheme overrides falling back to per-scheme defaults) is exactly
what powercfg itself resolves.

The interpreting helpers (`_effective_fast_startup`, `_tcc_allowed`,
`_parse_pmset_sleep`, `match_known_app`, ...) are pure and unit-tested
cross-platform; only `gather_system()` and the per-OS `_gather_*`
functions touch the machine.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from diagnostics.models import (AutostartEntry, PowerInfo, SystemSnapshot,
                                TccMicClient)

logger = logging.getLogger(__name__)


# =============================================================================
# Known ham apps (autostart + TCC matching)
# =============================================================================

# Lowercase substring -> canonical name. Superset of
# probe_apps.RunningAppDetector.KNOWN_APPS: autostart entries and TCC
# clients cover apps the config scan doesn't (rig control, digi suites,
# QSO Predictor itself).
KNOWN_HAM_PATTERNS: Dict[str, str] = {
    'wsjt': 'WSJT-X',
    'jtdx': 'JTDX',
    'jtalert': 'JTAlert',
    'gridtracker': 'GridTracker',
    'n3fjp': 'N3FJP ACLog',
    # 'maclogger' MUST precede 'aclog': "macloggerdx" contains "aclog",
    # and dict order is match order.
    'maclogger': 'MacLoggerDX',
    'aclog': 'N3FJP ACLog',
    'hamradiodeluxe': 'Ham Radio Deluxe',
    'ham radio deluxe': 'Ham Radio Deluxe',   # shortcut display names
    'log4om': 'Log4OM',
    'js8': 'JS8Call',
    'fldigi': 'fldigi',
    'flrig': 'flrig',
    'flmsg': 'flmsg',
    'omnirig': 'OmniRig',
    'sparksdr': 'SparkSDR',
    'qso predictor': 'QSO Predictor',
    'qso-predictor': 'QSO Predictor',
    'qsopredictor': 'QSO Predictor',
    # 'hrd' deliberately excluded: three letters substring-match too much
    # ("hrdlog" would be nice to catch, but "hrd" hides in random paths).
    'hrdlog': 'Ham Radio Deluxe',
}


def match_known_app(*texts: str) -> str:
    """Canonical ham app name if any text mentions one, else ''."""
    for text in texts:
        low = (text or '').casefold()
        if not low:
            continue
        for pattern, name in KNOWN_HAM_PATTERNS.items():
            if pattern in low:
                return name
    return ''


# =============================================================================
# Windows: power settings + fast startup (registry) and Run/Startup autostart
# =============================================================================

# Session Manager fast-startup flag (same key the Audio Doctor read
# before ownership moved here — dev-docs/DIAGNOSTICS_SPEC.md, "Fast
# Startup ownership").
_FAST_STARTUP_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Power"
_FAST_STARTUP_VALUE = "HiberbootEnabled"
# Fast Startup is hibernation technology: with hibernation off the
# HiberbootEnabled flag is inert.
_POWER_KEY = r"SYSTEM\CurrentControlSet\Control\Power"
_HIBERNATE_VALUE = "HibernateEnabled"

_SCHEMES_KEY = _POWER_KEY + r"\User\PowerSchemes"
_SETTINGS_KEY = _POWER_KEY + r"\PowerSettings"

# Power-setting GUIDs (stable across Windows versions; the same ids
# `powercfg /q SCHEME_CURRENT SUB_USB USBSELECTSUSPEND` resolves).
_SUB_USB = "2a737441-1930-4402-8d77-b2bebba308a3"
_USB_SELECTIVE_SUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
_SUB_SLEEP = "238c9fa8-0aad-41ed-83f4-97be242c8f20"
_STANDBY_IDLE = "29f6c1db-86da-48c5-9fdb-f2b67b1f44da"

_PLAN_NAMES = {
    "381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced",
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "High performance",
    "a1841308-3541-4fab-bc81-f71556f20b4a": "Power saver",
    "e9a42b02-d5df-448d-aa00-03f14749eb61": "Ultimate Performance",
}

# (source label, root, Run key, matching StartupApproved subkey).
# StartupApproved is where Task Manager's Startup tab records disable
# decisions while leaving the Run value / .lnk itself in place — an
# entry present in Run but flagged there is NOT going to start.
_APPROVED_BASE = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                  r"\StartupApproved")
_RUN_KEYS = (
    ("HKCU Run", "HKEY_CURRENT_USER",
     r"Software\Microsoft\Windows\CurrentVersion\Run",
     _APPROVED_BASE + r"\Run"),
    ("HKLM Run", "HKEY_LOCAL_MACHINE",
     r"Software\Microsoft\Windows\CurrentVersion\Run",
     _APPROVED_BASE + r"\Run"),
    ("HKLM Run (32-bit)", "HKEY_LOCAL_MACHINE",
     r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
     _APPROVED_BASE + r"\Run32"),
)


def _startup_disabled(approved_value) -> bool:
    """Pure: interpret one StartupApproved binary value. First byte even
    (0x02, 0x06) = enabled; odd (0x03, 0x07) = disabled; absent or
    malformed = enabled (the flag only exists once the user has touched
    the Startup tab)."""
    if not isinstance(approved_value, bytes) or not approved_value:
        return False
    return bool(approved_value[0] & 1)


def _effective_fast_startup(hiberboot: Optional[bool],
                            hibernate: Optional[bool]) -> Optional[bool]:
    """Pure: the state that actually governs boot behavior. Hibernation
    disabled forces fast startup off regardless of the checkbox flag
    (`powercfg /h off` is a common tweak that leaves HiberbootEnabled=1
    behind)."""
    if hiberboot is None:
        return None
    if hiberboot and hibernate is False:
        return False
    return hiberboot


def _plan_display_name(guid: str, friendly_name: Optional[str]) -> str:
    """Pure: prefer the well-known name (FriendlyName is usually an
    untranslatable '@powrprof.dll,-13' indirect string)."""
    known = _PLAN_NAMES.get(guid.strip('{}').lower())
    if known:
        return known
    if friendly_name and not friendly_name.startswith('@'):
        return friendly_name
    return guid


def _win_read_value(root_name: str, key_path: str, value_name: str):
    """One registry value or None. 64-bit view (system hives are not
    redirected, but be explicit like audio_doctor's probe)."""
    import winreg
    root = getattr(winreg, root_name)
    access = winreg.KEY_READ | getattr(winreg, 'KEY_WOW64_64KEY', 0)
    try:
        with winreg.OpenKey(root, key_path, 0, access) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return value
    except OSError:
        return None


def _as_int(value) -> Optional[int]:
    """Registry data defensively coerced: OEM tools have been seen
    writing setting indices as REG_BINARY or decimal REG_SZ. Anything
    that won't coerce reads as unreadable, never as a crash."""
    if value is None:
        return None
    try:
        if isinstance(value, bytes):
            return int.from_bytes(value[:4], 'little')
        return int(value)
    except (ValueError, TypeError):
        return None


def _win_power_setting_index(scheme: str, subgroup: str,
                             setting: str, ac: bool) -> Optional[int]:
    """Resolve one power setting the way powercfg does: the scheme's
    override value, else the setting's per-scheme default."""
    value_name = "ACSettingIndex" if ac else "DCSettingIndex"
    override = _as_int(_win_read_value(
        "HKEY_LOCAL_MACHINE",
        f"{_SCHEMES_KEY}\\{scheme}\\{subgroup}\\{setting}", value_name))
    if override is not None:
        return override
    return _as_int(_win_read_value(
        "HKEY_LOCAL_MACHINE",
        f"{_SETTINGS_KEY}\\{subgroup}\\{setting}"
        f"\\DefaultPowerSchemeValues\\{scheme}", value_name))


def _gather_power_windows() -> PowerInfo:
    power = PowerInfo()

    hiberboot = _win_read_value("HKEY_LOCAL_MACHINE", _FAST_STARTUP_KEY,
                                _FAST_STARTUP_VALUE)
    hibernate = _win_read_value("HKEY_LOCAL_MACHINE", _POWER_KEY,
                                _HIBERNATE_VALUE)
    power.hibernate_enabled = None if hibernate is None else bool(hibernate)
    power.fast_startup = _effective_fast_startup(
        None if hiberboot is None else bool(hiberboot),
        power.hibernate_enabled)

    scheme = _win_read_value("HKEY_LOCAL_MACHINE", _SCHEMES_KEY,
                             "ActivePowerScheme")
    if scheme:
        scheme = str(scheme)
        friendly = _win_read_value("HKEY_LOCAL_MACHINE",
                                   f"{_SCHEMES_KEY}\\{scheme}", "FriendlyName")
        power.plan_name = _plan_display_name(
            scheme, str(friendly) if friendly else None)
        for attr, subgroup, setting, to_bool in (
                ('usb_selective_suspend_ac', _SUB_USB,
                 _USB_SELECTIVE_SUSPEND, True),
                ('usb_selective_suspend_dc', _SUB_USB,
                 _USB_SELECTIVE_SUSPEND, True),
                ('standby_ac_min', _SUB_SLEEP, _STANDBY_IDLE, False),
                ('standby_dc_min', _SUB_SLEEP, _STANDBY_IDLE, False)):
            ac = attr.endswith('_ac') or attr.endswith('_ac_min')
            index = _win_power_setting_index(scheme, subgroup, setting, ac)
            if index is None:
                continue
            if to_bool:
                setattr(power, attr, bool(index))
            else:
                # STANDBYIDLE is stored in seconds; 0 = never. Ceiling:
                # a 30-second timeout must not floor to 0 ("never").
                setattr(power, attr, (index + 59) // 60)
    return power


def _gather_autostart_windows() -> Tuple[List[AutostartEntry], int]:
    import winreg
    entries, other = [], 0

    for source, root_name, key_path, approved_path in _RUN_KEYS:
        root = getattr(winreg, root_name)
        access = winreg.KEY_READ | getattr(winreg, 'KEY_WOW64_64KEY', 0)
        try:
            key = winreg.OpenKey(root, key_path, 0, access)
        except OSError:
            continue
        with key:
            index = 0
            while True:
                try:
                    name, command, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                app = match_known_app(name, str(command))
                if app:
                    disabled = _startup_disabled(_win_read_value(
                        root_name, approved_path, name))
                    entries.append(AutostartEntry(
                        name=name, source=source, app=app,
                        command=str(command), disabled=disabled))
                else:
                    other += 1

    folders = []
    appdata = os.environ.get('APPDATA')
    programdata = os.environ.get('PROGRAMDATA')
    startup_tail = r"Microsoft\Windows\Start Menu\Programs\Startup"
    if appdata:
        folders.append(("HKEY_CURRENT_USER", Path(appdata) / startup_tail))
    if programdata:
        folders.append(("HKEY_LOCAL_MACHINE",
                        Path(programdata) / startup_tail))
    for root_name, folder in folders:
        try:
            children = sorted(folder.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.casefold() == 'desktop.ini':
                continue
            app = match_known_app(child.stem)
            if app:
                # StartupFolder approvals key on the file name incl.
                # extension.
                disabled = _startup_disabled(_win_read_value(
                    root_name, _APPROVED_BASE + r"\StartupFolder",
                    child.name))
                entries.append(AutostartEntry(
                    name=child.stem, source="Startup folder", app=app,
                    command=str(child), disabled=disabled))
            else:
                other += 1
    return entries, other


# =============================================================================
# macOS: sleep timeouts (pmset), TCC microphone decisions, LaunchAgents
# =============================================================================

_PMSET_SECTION_RE = re.compile(r'^(AC Power|Battery Power):\s*$')
_PMSET_SLEEP_RE = re.compile(r'^\s*sleep\s+(\d+)')
_PMSET_PREVENTED_RE = re.compile(
    r'^\s*sleep\s+\d+\s+\(sleep prevented by ([^)]*)\)', re.MULTILINE)


def _parse_pmset_sleep(output: str) -> Tuple[Optional[int], Optional[int]]:
    """Pure: (ac_minutes, battery_minutes) from `pmset -g custom`.
    Desktops have no Battery section; 0 means never sleeps."""
    ac = dc = None
    section = None
    for line in output.splitlines():
        m = _PMSET_SECTION_RE.match(line.strip())
        if m:
            section = m.group(1)
            continue
        m = _PMSET_SLEEP_RE.match(line)
        if m:
            minutes = int(m.group(1))
            if section == 'Battery Power':
                dc = minutes
            else:
                ac = minutes
    return ac, dc


def _parse_pmset_prevention(output: str) -> str:
    """Pure: the "(sleep prevented by proc, proc, ...)" annotation from
    `pmset -g` (live settings), de-duplicated. This is the evidence that
    the macOS sleep timer is NOT wall-clock: assertions (active audio,
    open serial with ttyskeepawake) hold sleep off indefinitely."""
    m = _PMSET_PREVENTED_RE.search(output)
    if not m:
        return ''
    seen = []
    for proc in (p.strip() for p in m.group(1).split(',')):
        if proc and proc not in seen:
            seen.append(proc)
    return ', '.join(seen)


def _gather_power_macos() -> Optional[PowerInfo]:
    import subprocess
    try:
        output = subprocess.check_output(['pmset', '-g', 'custom'],
                                         text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"System probe: pmset failed: {e}")
        return None
    power = PowerInfo()
    power.standby_ac_min, power.standby_dc_min = _parse_pmset_sleep(output)
    try:
        live = subprocess.check_output(['pmset', '-g'], text=True, timeout=5)
        power.sleep_prevented_by = _parse_pmset_prevention(live)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"System probe: pmset -g failed: {e}")
    return power


def _tcc_allowed(value: Optional[int], column: str) -> Optional[bool]:
    """Pure: interpret one TCC decision value. Modern schema
    (`auth_value`): 0 denied, 1 unknown, 2 allowed, 3 limited. Legacy
    schema (`allowed`): plain 0/1."""
    if value is None:
        return None
    if column == 'auth_value':
        if value in (2, 3):
            return True
        if value == 0:
            return False
        return None
    return bool(value)


def _gather_mic_clients_macos() -> Optional[List[TccMicClient]]:
    """Ham-relevant microphone decisions from the user TCC database.
    Usually unreadable (macOS protects TCC.db unless the process has
    Full Disk Access) — that is a normal UNKNOWN, not an error."""
    import sqlite3
    db = Path.home() / "Library/Application Support/com.apple.TCC/TCC.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        for column in ('auth_value', 'allowed'):
            try:
                rows = con.execute(
                    f"SELECT client, {column} FROM access "
                    f"WHERE service = 'kTCCServiceMicrophone'").fetchall()
            except sqlite3.Error:
                continue
            clients = []
            for client, value in rows:
                client = str(client)
                if not match_known_app(client):
                    continue
                try:
                    value = int(value) if value is not None else None
                except (ValueError, TypeError):
                    value = None    # odd row -> undetermined, not a crash
                clients.append(TccMicClient(
                    client=client, allowed=_tcc_allowed(value, column)))
            return clients
        return None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def _plist_disabled(path: Path) -> bool:
    """Best-effort read of a LaunchAgent's Disabled key (plistlib
    handles both XML and binary plists). Unreadable = assume enabled."""
    import plistlib
    try:
        with open(path, 'rb') as fh:
            return bool(plistlib.load(fh).get('Disabled', False))
    except Exception:
        return False


def _gather_autostart_macos() -> Tuple[List[AutostartEntry], int]:
    entries, other = [], 0
    for folder, source in ((Path.home() / "Library/LaunchAgents",
                            "user LaunchAgents"),
                           (Path("/Library/LaunchAgents"),
                            "system LaunchAgents")):
        try:
            children = sorted(folder.glob("*.plist"))
        except OSError:
            continue
        for child in children:
            app = match_known_app(child.stem)
            if app:
                entries.append(AutostartEntry(
                    name=child.stem, source=source, app=app,
                    command=str(child),
                    disabled=_plist_disabled(child)))
            else:
                other += 1
    return entries, other


# =============================================================================
# Linux: serial-port group membership, autostart .desktop entries
# =============================================================================

# Groups that grant access to /dev/tty* serial devices, by distro
# convention (Debian/Ubuntu: dialout; Arch: uucp; some others).
SERIAL_GROUP_CANDIDATES = ('dialout', 'uucp', 'dialer', 'modem')

_SERIAL_DEVICE_GLOBS = ('ttyUSB*', 'ttyACM*')


def _gather_groups_linux() -> Tuple[Optional[List[str]],
                                    Optional[List[str]]]:
    """(serial-granting groups the user is IN, serial-granting groups
    that exist on this system). Only the serial-relevant intersection is
    stored — the full group list would leak the username via the primary
    group and fingerprint the machine (review 2026-07-27). Uses the
    current process's supplementary groups — also the practically
    relevant view: a `usermod -aG dialout` without a re-login hasn't
    taken effect yet, and that is exactly the trap."""
    try:
        import grp
        gids = set(os.getgroups())
        gids.add(os.getgid())
        all_groups = grp.getgrall()
        names = {g.gr_name for g in all_groups}
        present = [name for name in SERIAL_GROUP_CANDIDATES
                   if name in names]
        member = [name for name in present
                  if any(g.gr_name == name and g.gr_gid in gids
                         for g in all_groups)]
        return member, present
    except OSError as e:
        logger.debug(f"System probe: group enumeration failed: {e}")
        return None, None


def _gather_serial_devices_linux() -> List[str]:
    devices = []
    dev = Path('/dev')
    for pattern in _SERIAL_DEVICE_GLOBS:
        try:
            devices += [str(p) for p in dev.glob(pattern)]
        except OSError:
            pass
    by_id = Path('/dev/serial/by-id')
    try:
        devices += [str(p) for p in by_id.iterdir()]
    except OSError:
        pass
    return sorted(set(devices))


def _parse_desktop_entry(text: str) -> Tuple[str, str, bool]:
    """Pure: (Name, Exec, disabled) from a .desktop file's
    [Desktop Entry]. Hidden=true and X-GNOME-Autostart-enabled=false
    both mean the entry will not autostart."""
    name = command = ''
    disabled = False
    in_section = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            in_section = line == '[Desktop Entry]'
            continue
        if not in_section:
            continue
        if line.startswith('Name=') and not name:
            name = line[len('Name='):].strip()
        elif line.startswith('Exec=') and not command:
            command = line[len('Exec='):].strip()
        elif line.startswith('Hidden='):
            disabled |= line[len('Hidden='):].strip().casefold() == 'true'
        elif line.startswith('X-GNOME-Autostart-enabled='):
            disabled |= (line.split('=', 1)[1].strip().casefold()
                         == 'false')
    return name, command, disabled


def _gather_autostart_linux() -> Tuple[List[AutostartEntry], int]:
    entries, other = [], 0
    config_home = Path(os.environ.get('XDG_CONFIG_HOME',
                                      Path.home() / '.config'))
    for folder, source in ((config_home / 'autostart', "user autostart"),
                           (Path('/etc/xdg/autostart'), "system autostart")):
        try:
            children = sorted(folder.glob('*.desktop'))
        except OSError:
            continue
        for child in children:
            try:
                name, command, disabled = _parse_desktop_entry(
                    child.read_text(encoding='utf-8', errors='replace'))
            except OSError:
                name, command, disabled = '', '', False
            app = match_known_app(child.stem, name, command)
            if app:
                entries.append(AutostartEntry(
                    name=name or child.stem, source=source, app=app,
                    command=command, disabled=disabled))
            else:
                other += 1
    return entries, other


# =============================================================================
# Entry point
# =============================================================================

def _fenced(label: str, fn, default=None):
    """One sub-gatherer, isolated: a malformed registry value or odd
    database row loses that field, never the whole system domain (an
    uncaught raise would make registry.gather_snapshot null the domain
    and discard every healthy sibling reading)."""
    try:
        return fn()
    except Exception as e:
        logger.warning(f"System probe: {label} failed: {e}")
        return default


def gather_system() -> SystemSnapshot:
    """Domain gatherer for 'system'. Filesystem/registry/subprocess
    I/O — worker thread only."""
    snap = SystemSnapshot()

    if sys.platform == 'win32':
        snap.power = _fenced('power', _gather_power_windows)
        entries, other = _fenced('autostart', _gather_autostart_windows,
                                 (None, None))
        snap.autostart_entries, snap.autostart_other_count = entries, other
        snap.autostart_note = ("Task Scheduler tasks are not visible to "
                               "this probe — only Run keys and Startup "
                               "folders were examined")
    elif sys.platform == 'darwin':
        snap.power = _fenced('power', _gather_power_macos)
        snap.mic_clients = _fenced('tcc', _gather_mic_clients_macos)
        entries, other = _fenced('autostart', _gather_autostart_macos,
                                 (None, None))
        snap.autostart_entries, snap.autostart_other_count = entries, other
        snap.autostart_note = ("macOS Login Items are not visible to this "
                               "probe — only LaunchAgents were examined")
    else:
        member, present = _fenced('groups', _gather_groups_linux,
                                  (None, None))
        snap.serial_member_groups, snap.serial_groups = member, present
        try:
            snap.is_root = os.geteuid() == 0
        except AttributeError:
            snap.is_root = None
        snap.serial_devices = _fenced('serial-devices',
                                      _gather_serial_devices_linux)
        entries, other = _fenced('autostart', _gather_autostart_linux,
                                 (None, None))
        snap.autostart_entries, snap.autostart_other_count = entries, other

    return snap
