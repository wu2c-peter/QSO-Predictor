"""
Serial probe: enumerate serial ports and USB serial adapters.

Feeds the Serial/CAT Doctor (DIAGNOSTICS_SPEC.md roster item 4).
STRICTLY PASSIVE: enumeration comes from the registry (Windows), sysfs
(Linux), and `system_profiler`/`lsof` (macOS) — no port is ever opened.
Opening a CAT port can toggle DTR/RTS, and DTR/RTS is how half the
world keys PTT; a diagnostic that keys the transmitter is worse than
the disease.

Per-OS layout mirrors probe_system: `gather_serial()` dispatches, the
platform functions do I/O, and everything that interprets data
(`identify_chip`, `_win_ports_from_raw`, `_parse_system_profiler_usb`,
VID/PID extraction, problem-code mapping) is a pure function testable
with fixtures on any OS.

Windows enumeration walks HKLM SERIALCOMM (which COM ports exist right
now) and the Enum branches (USB, FTDIBUS) for identity: VID/PID from
the key path, FriendlyName, the bound service, and the driver version
from the Ports class key. Device Manager problem codes come from
cfgmgr32 via ctypes, best-effort — Code 10 on a Prolific adapter is
the counterfeit-PL2303 signature this doctor exists to catch.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from diagnostics.models import (SerialPortInfo, SerialSnapshot,
                                UsbSerialAdapter)

logger = logging.getLogger(__name__)


# =============================================================================
# Chip identification (pure, shared by every platform)
# =============================================================================

# USB vendor ids of the serial-adapter chips that dominate ham
# interfaces. Values are the family name shown in reports.
USB_SERIAL_VENDORS: Dict[int, str] = {
    0x0403: 'FTDI',
    0x10C4: 'CP210x (Silicon Labs)',
    0x1A86: 'CH340 (WCH)',
    0x067B: 'Prolific PL2303',
    0x0D8C: 'C-Media CM108/CM119',   # GPIO-PTT sound-card interfaces
}

# The FTDI-gate brick signature: counterfeit FT232 chips whose PID an
# official driver reset to 0000 — the device enumerates but is dead.
FTDI_BRICKED = (0x0403, 0x0000)

# Product/name substrings that identify a specific interface product.
KNOWN_DEVICE_LABELS = (
    ('digirig', 'Digirig'),
    ('signalink', 'SignaLink'),
    ('rigblaster', 'RigBlaster'),
)

_VIDPID_RE = re.compile(r'VID_([0-9A-Fa-f]{4})[&+]PID_([0-9A-Fa-f]{4})')


def identify_chip(vid: Optional[int], pid: Optional[int]) -> str:
    """Pure: adapter family from USB ids ('' = not USB / unknown)."""
    if vid is None:
        return ''
    if pid is not None and (vid, pid) == FTDI_BRICKED:
        return 'FTDI (bricked: PID reset to 0000)'
    return USB_SERIAL_VENDORS.get(vid, '')


def identify_device_label(*names: str) -> str:
    """Pure: recognized interface product from display strings."""
    for text in names:
        low = (text or '').casefold()
        for pattern, label in KNOWN_DEVICE_LABELS:
            if pattern in low:
                return label
    return ''


def _vidpid_from_text(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Pure: (vid, pid) from an Enum key path like
    'USB\\VID_067B&PID_2303\\...' or 'FTDIBUS\\VID_0403+PID_6001+...'."""
    m = _VIDPID_RE.search(text or '')
    if not m:
        return None, None
    return int(m.group(1), 16), int(m.group(2), 16)


# =============================================================================
# Windows: SERIALCOMM + Enum branches + class-key driver info + cfgmgr32
# =============================================================================

_SERIALCOMM_KEY = r"HARDWARE\DEVICEMAP\SERIALCOMM"
_ENUM_KEY = r"SYSTEM\CurrentControlSet\Enum"
_CLASS_KEY = r"SYSTEM\CurrentControlSet\Control\Class"
# Enumerator branches that carry USB serial adapters. FTDIBUS is FTDI's
# own bus driver; CP210x/CH340/Prolific live under USB.
_ENUM_BRANCHES = ('USB', 'FTDIBUS')

# Device Manager problem codes worth explaining by name.
WIN_PROBLEM_CODES = {
    10: 'this device cannot start (Code 10)',
    28: 'no driver is installed (Code 28)',
    43: 'Windows stopped this device after it reported problems (Code 43)',
    45: 'not currently connected (Code 45)',
}


def _win_reg():
    import winreg
    return winreg


def _win_open(root_name: str, path: str):
    winreg = _win_reg()
    access = winreg.KEY_READ | getattr(winreg, 'KEY_WOW64_64KEY', 0)
    return winreg.OpenKey(getattr(winreg, root_name), path, 0, access)


def _win_value(key, name: str):
    winreg = _win_reg()
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except OSError:
        return None


def _win_subkeys(key) -> List[str]:
    winreg = _win_reg()
    names = []
    index = 0
    while True:
        try:
            names.append(winreg.EnumKey(key, index))
        except OSError:
            break
        index += 1
    return names


def _win_active_com_ports() -> List[str]:
    """COM ports that exist RIGHT NOW (SERIALCOMM is live, unlike the
    Enum tree which remembers every device ever plugged in)."""
    winreg = _win_reg()
    ports = []
    with _win_open("HKEY_LOCAL_MACHINE", _SERIALCOMM_KEY) as key:
        index = 0
        while True:
            try:
                _, com_name, _ = winreg.EnumValue(key, index)
            except OSError:
                break
            index += 1
            if isinstance(com_name, str) and com_name:
                ports.append(com_name)
    return ports


# cfgmgr32 locate flags (cfgmgr32.h). NORMAL succeeds only for devices
# PRESENT right now — which doubles as the passive presence test that
# separates live Enum entries from the stale ones the registry keeps
# for every device ever plugged in.
CM_LOCATE_DEVNODE_NORMAL = 0


def _win_device_status(instance_id: str) -> Tuple[Optional[bool],
                                                  Optional[int]]:
    """(present, problem_code) via cfgmgr32, best-effort.

    present: True = device is connected right now; False = stale/absent
    Enum entry (CM_Locate_DevNodeW NORMAL failed); None = cfgmgr32
    unusable. problem_code: 0 healthy, nonzero = Device Manager problem
    (10 = cannot start — the counterfeit-Prolific signature); None =
    unreadable."""
    try:
        import ctypes
        from ctypes import wintypes
        cfgmgr = ctypes.windll.cfgmgr32
        devinst = wintypes.DWORD()
        if cfgmgr.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id,
                                     CM_LOCATE_DEVNODE_NORMAL) != 0:
            return False, None
        status = wintypes.ULONG()
        problem = wintypes.ULONG()
        if cfgmgr.CM_Get_DevNode_Status(ctypes.byref(status),
                                        ctypes.byref(problem),
                                        devinst, 0) != 0:
            return True, None
        # DN_HAS_PROBLEM = 0x400
        return True, (int(problem.value) if status.value & 0x400 else 0)
    except Exception as e:
        logger.debug(f"Serial probe: status for {instance_id}: {e}")
        return None, None


def _display_string(value) -> str:
    """Pure: normalize a registry display string. Vista+ stores names in
    indirect form ('@oem12.inf,%desc%;USB Serial Port') — the text after
    the last ';' is the fallback display value."""
    if not isinstance(value, str):
        return ''
    if value.startswith('@') and ';' in value:
        return value.rsplit(';', 1)[1]
    return value


def _win_driver_info(driver_ref) -> Tuple[str, str]:
    """(provider, version) from a 'Driver' value like
    '{4d36e978-...}\\0004' pointing into the class key."""
    if not isinstance(driver_ref, str) or '\\' not in driver_ref:
        return '', ''
    try:
        with _win_open("HKEY_LOCAL_MACHINE",
                       f"{_CLASS_KEY}\\{driver_ref}") as key:
            provider = _win_value(key, "ProviderName") or ''
            version = _win_value(key, "DriverVersion") or ''
            return str(provider), str(version)
    except OSError:
        return '', ''


def _win_collect_usb_serial_devices() -> List[dict]:
    """Walk the Enum branches for serial-relevant devices. Two kinds are
    kept: anything carrying a PortName (a serial port, working or not),
    and any PRESENT device whose VID is a known serial-adapter vendor
    even without a PortName — a Code 28 (driverless) or PID-0000
    (FTDI-gate-bricked) adapter never gets a PortName, and those are
    precisely the devices this doctor exists to catch. Raw dicts; pure
    interpretation happens in _win_ports_from_raw /
    _win_adapters_from_raw."""
    devices = []
    for branch in _ENUM_BRANCHES:
        try:
            branch_key = _win_open("HKEY_LOCAL_MACHINE",
                                   f"{_ENUM_KEY}\\{branch}")
        except OSError:
            continue
        with branch_key:
            hw_ids = _win_subkeys(branch_key)
        for hw_id in hw_ids:
            hw_path = f"{_ENUM_KEY}\\{branch}\\{hw_id}"
            vid, pid = _vidpid_from_text(hw_id)
            adapter_vendor = (vid in USB_SERIAL_VENDORS
                              or (vid, pid) == FTDI_BRICKED)
            try:
                with _win_open("HKEY_LOCAL_MACHINE", hw_path) as hw_key:
                    instances = _win_subkeys(hw_key)
            except OSError:
                continue
            for inst in instances:
                inst_path = f"{hw_path}\\{inst}"
                try:
                    with _win_open("HKEY_LOCAL_MACHINE",
                                   inst_path) as inst_key:
                        friendly = _display_string(
                            _win_value(inst_key, "FriendlyName")
                            or _win_value(inst_key, "DeviceDesc") or '')
                        service = _win_value(inst_key, "Service") or ''
                        driver_ref = _win_value(inst_key, "Driver")
                except OSError:
                    continue
                port_name = None
                try:
                    with _win_open("HKEY_LOCAL_MACHINE",
                                   inst_path
                                   + r"\Device Parameters") as params:
                        port_name = _win_value(params, "PortName")
                except OSError:
                    pass
                if not port_name and not adapter_vendor:
                    continue
                present, problem = _win_device_status(
                    f"{branch}\\{hw_id}\\{inst}")
                if not port_name and present is not True:
                    # Portless entries are only interesting while the
                    # hardware is actually plugged in.
                    continue
                provider, version = _win_driver_info(driver_ref)
                devices.append({
                    'enum_path': f"{branch}\\{hw_id}\\{inst}",
                    'port_name': str(port_name) if port_name else '',
                    'friendly_name': str(friendly),
                    'service': str(service),
                    'driver_provider': provider,
                    'driver_version': version,
                    'present': present,
                    'problem_code': problem,
                })
    return devices


def _port_from_device(com: str, dev: dict) -> SerialPortInfo:
    vid, pid = _vidpid_from_text(dev['enum_path'])
    return SerialPortInfo(
        device=com,
        friendly_name=dev['friendly_name'],
        vid=vid, pid=pid,
        chip=identify_chip(vid, pid),
        device_label=identify_device_label(dev['friendly_name']),
        driver_name=(dev['service'] or dev['driver_provider']),
        driver_version=dev['driver_version'],
        problem_code=dev['problem_code'],
    )


def _win_ports_from_raw(active_ports: List[str],
                        devices: List[dict]) -> List[SerialPortInfo]:
    """Pure: merge live SERIALCOMM ports with Enum identities, PLUS
    present-but-broken devices SERIALCOMM cannot list.

    SERIALCOMM is written by the serial driver's successful start path,
    so a Code 10 device (the counterfeit-Prolific trap) never appears
    there — it must be surfaced from its Enum entry directly or the
    doctor's flagship check can never fire (review 2026-07-27).

    The Enum tree remembers every device ever plugged in; stale
    claimants (present=False) never contribute identity. Among live
    claimants of one COM name: cfgmgr32-healthy (0) beats problem codes
    beats unreadable (None)."""
    def rank(dev):
        code = dev.get('problem_code')
        if code == 0:
            return 2
        if isinstance(code, int):
            return 1
        return 0

    by_port: Dict[str, dict] = {}
    for dev in devices:
        port = dev['port_name'].upper()
        if not port or dev.get('present') is False:
            continue
        existing = by_port.get(port)
        if existing is None or rank(dev) > rank(existing):
            by_port[port] = dev
    ports = []
    live = {p.upper() for p in active_ports}
    for com in sorted(active_ports, key=lambda p: (len(p), p)):
        dev = by_port.get(com.upper())
        ports.append(_port_from_device(com, dev) if dev
                     else SerialPortInfo(device=com))
    # Present devices with a PortName that ISN'T live: broken ports
    # (cannot start / driverless) — listed with their problem so the
    # driver check sees them.
    for port_name in sorted(set(by_port) - live):
        dev = by_port[port_name]
        if dev.get('present') and dev.get('problem_code') not in (0, None):
            ports.append(_port_from_device(port_name, dev))
    return ports


def _win_adapters_from_raw(devices: List[dict]) -> List[UsbSerialAdapter]:
    """Pure: USB inventory of PRESENT serial-adapter-class devices,
    ports or not — the portless ones (bricked FTDI, driverless chip)
    are what the counterfeit checks read."""
    adapters = []
    seen = set()
    for dev in devices:
        if dev.get('present') is not True:
            continue
        vid, pid = _vidpid_from_text(dev['enum_path'])
        if vid is None:
            continue
        if not (vid in USB_SERIAL_VENDORS or (vid, pid) == FTDI_BRICKED):
            continue
        key = (vid, pid, dev['enum_path'])
        if key in seen:
            continue
        seen.add(key)
        adapters.append(UsbSerialAdapter(
            vid=vid, pid=pid, product=dev['friendly_name'],
            chip=identify_chip(vid, pid)))
    return adapters


def _gather_serial_windows() -> SerialSnapshot:
    snap = SerialSnapshot(note=(
        "Which process holds a COM port is not passively detectable on "
        "Windows, so in-use information is absent — not proof the port "
        "is free"))
    try:
        active = _win_active_com_ports()
    except OSError:
        # No SERIALCOMM key = no WORKING serial port; broken adapters
        # may still exist in the Enum tree, so keep scanning.
        active = []
    devices = _win_collect_usb_serial_devices()
    snap.ports = _win_ports_from_raw(active, devices)
    snap.adapters = _win_adapters_from_raw(devices)
    return snap


# =============================================================================
# macOS: /dev/cu.* + system_profiler USB inventory + lsof holders
# =============================================================================

def _parse_system_profiler_usb(payload: str) -> List[UsbSerialAdapter]:
    """Pure: serial-adapter-class devices from
    `system_profiler SPUSBDataType -json` output."""
    adapters = []
    try:
        tree = json.loads(payload)
    except (ValueError, TypeError):
        return adapters

    def walk(items):
        for item in items or []:
            vid_raw = item.get('vendor_id', '')
            pid_raw = item.get('product_id', '')
            try:
                # "0x10c4  (Silicon Laboratories, Inc.)" or "0x10c4"
                vid = int(str(vid_raw).split()[0], 16)
                pid = int(str(pid_raw).split()[0], 16)
            except (ValueError, IndexError):
                vid = pid = None
            if vid is not None and (vid in USB_SERIAL_VENDORS
                                    or (vid, pid) == FTDI_BRICKED):
                adapters.append(UsbSerialAdapter(
                    vid=vid, pid=pid,
                    product=str(item.get('_name', '')),
                    manufacturer=str(item.get('manufacturer', '')),
                    chip=identify_chip(vid, pid)))
            walk(item.get('_items'))

    for controller in tree.get('SPUSBDataType', []):
        walk(controller.get('_items'))
    return adapters


# /dev/cu.* nodes every Mac has that are NOT usable serial hardware —
# the OS Bluetooth placeholder and the Apple Silicon debug console.
_MACOS_PSEUDO_PATTERNS = ('bluetooth-incoming-port', 'debug-console')


def is_macos_pseudo_port(device: str) -> bool:
    """Pure: an OS placeholder port, not real serial hardware."""
    low = device.casefold()
    return any(p in low for p in _MACOS_PSEUDO_PATTERNS)


def _macos_chip_from_device_name(device: str) -> str:
    """Pure: driver-assigned /dev/cu.* names reveal the driver."""
    low = device.casefold()
    if 'slab' in low:
        return 'CP210x (Silicon Labs)'
    if 'wchusbserial' in low or 'wch' in low:
        return 'CH340 (WCH)'
    if 'pl2303' in low:
        return 'Prolific PL2303'
    return ''


def _macos_holders(devices: List[str]) -> Dict[str, str]:
    """Which process has each device open, via lsof (reads the open-file
    table — it does not touch the devices). Best-effort."""
    if not devices:
        return {}
    import subprocess
    try:
        out = subprocess.run(
            ['lsof', '-Fcn', '--'] + devices,
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"Serial probe: lsof failed: {e}")
        return {}
    holders: Dict[str, str] = {}
    current_cmd = ''
    for line in (out.stdout or '').splitlines():
        if line.startswith('c'):
            current_cmd = line[1:]
        elif line.startswith('n') and current_cmd:
            holders.setdefault(line[1:], current_cmd)
    return holders


def _gather_serial_macos() -> SerialSnapshot:
    import subprocess
    snap = SerialSnapshot(note=(
        "Holder detection sees this user's processes only — an empty "
        "in-use column is not proof the port is free"))
    devices = sorted(str(p) for p in Path('/dev').glob('cu.*'))
    twins = [d.replace('/dev/cu.', '/dev/tty.') for d in devices]
    # lsof must be given the tty.* twins too — a holder that opened the
    # tty node is invisible when only cu.* paths are queried.
    holders = _macos_holders(devices + twins)
    ports = []
    for dev in devices:
        tty_twin = dev.replace('/dev/cu.', '/dev/tty.')
        ports.append(SerialPortInfo(
            device=dev,
            chip=_macos_chip_from_device_name(dev),
            device_label=identify_device_label(dev),
            in_use_by=holders.get(dev, '') or holders.get(tty_twin, ''),
            aliases=[tty_twin],
        ))
    snap.ports = ports
    try:
        out = subprocess.check_output(
            ['system_profiler', 'SPUSBDataType', '-json'],
            text=True, timeout=30)
        snap.adapters = _parse_system_profiler_usb(out)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug(f"Serial probe: system_profiler failed: {e}")
        snap.adapters = None
    # Enrich unnamed ports from the single-adapter case: with exactly
    # one PORT-CREATING adapter and one unidentified USB-ish port, the
    # pairing is safe. CM108-class audio/GPIO devices and bricked FTDIs
    # never create a port node — pairing their identity onto some
    # unrelated cu.usbmodem would misattribute it (review 2026-07-27).
    pairable = [a for a in (snap.adapters or [])
                if a.vid != 0x0D8C and (a.vid, a.pid) != FTDI_BRICKED]
    unnamed = [p for p in snap.ports
               if not p.chip and not is_macos_pseudo_port(p.device)
               and 'usb' in p.device.casefold()]
    if len(pairable) == 1 and len(unnamed) == 1:
        adapter = pairable[0]
        port = unnamed[0]
        port.vid, port.pid = adapter.vid, adapter.pid
        port.chip = adapter.chip
        port.friendly_name = adapter.product
        port.device_label = (port.device_label
                             or identify_device_label(adapter.product,
                                                      adapter.manufacturer))
    return snap


# =============================================================================
# Linux: sysfs identity + /proc holders
# =============================================================================

def _linux_port_identity(tty_name: str) -> dict:
    """Read USB identity for one tty from sysfs (plain file reads)."""
    info = {'vid': None, 'pid': None, 'product': '', 'manufacturer': '',
            'driver': ''}
    device = Path(f'/sys/class/tty/{tty_name}/device')
    try:
        driver = (device / 'driver').resolve().name
        info['driver'] = driver
    except OSError:
        pass
    # Walk up to the USB device node that carries idVendor.
    node = device
    for _ in range(6):
        try:
            node = node.resolve()
        except OSError:
            break
        if (node / 'idVendor').exists():
            def read(name):
                try:
                    return (node / name).read_text().strip()
                except OSError:
                    return ''
            try:
                info['vid'] = int(read('idVendor'), 16)
                info['pid'] = int(read('idProduct'), 16)
            except ValueError:
                pass
            info['product'] = read('product')
            info['manufacturer'] = read('manufacturer')
            break
        parent = node.parent
        if parent == node:
            break
        node = parent
    return info


def _linux_holders(devices: List[str]) -> Dict[str, str]:
    """Scan /proc/*/fd for open handles on the devices. Sees own-user
    processes without privileges — best-effort, absence proves
    nothing."""
    targets = set(devices)
    holders: Dict[str, str] = {}
    proc = Path('/proc')
    try:
        pids = [p for p in proc.iterdir() if p.name.isdigit()]
    except OSError:
        return holders
    for pid in pids:
        try:
            fds = list((pid / 'fd').iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target in targets and target not in holders:
                try:
                    holders[target] = (pid / 'comm').read_text().strip()
                except OSError:
                    holders[target] = f'pid {pid.name}'
    return holders


def _linux_usb_adapters() -> List[UsbSerialAdapter]:
    """Serial-adapter-class devices from the USB inventory — sees
    driverless and PID-0000-bricked adapters that never create a tty."""
    adapters = []
    usb_root = Path('/sys/bus/usb/devices')
    try:
        nodes = sorted(usb_root.iterdir())
    except OSError:
        return adapters
    for node in nodes:
        try:
            vid = int((node / 'idVendor').read_text().strip(), 16)
            pid = int((node / 'idProduct').read_text().strip(), 16)
        except (OSError, ValueError):
            continue
        if not (vid in USB_SERIAL_VENDORS or (vid, pid) == FTDI_BRICKED):
            continue

        def read(name):
            try:
                return (node / name).read_text().strip()
            except OSError:
                return ''
        adapters.append(UsbSerialAdapter(
            vid=vid, pid=pid, product=read('product'),
            manufacturer=read('manufacturer'),
            chip=identify_chip(vid, pid)))
    return adapters


def _gather_serial_linux() -> SerialSnapshot:
    snap = SerialSnapshot()
    devices = []
    for pattern in ('ttyUSB*', 'ttyACM*'):
        try:
            devices += sorted(Path('/dev').glob(pattern))
        except OSError:
            pass
    by_id: Dict[str, List[str]] = {}
    by_id_dir = Path('/dev/serial/by-id')
    try:
        for link in by_id_dir.iterdir():
            try:
                target = str(link.resolve())
            except OSError:
                continue
            by_id.setdefault(target, []).append(str(link))
    except OSError:
        pass
    holders = _linux_holders([str(d) for d in devices])
    ports = []
    for dev in devices:
        identity = _linux_port_identity(dev.name)
        label = ' '.join(x for x in (identity['manufacturer'],
                                     identity['product']) if x)
        ports.append(SerialPortInfo(
            device=str(dev),
            friendly_name=label,
            vid=identity['vid'], pid=identity['pid'],
            chip=identify_chip(identity['vid'], identity['pid']),
            device_label=identify_device_label(label),
            driver_name=identity['driver'],
            in_use_by=holders.get(str(dev), ''),
            aliases=by_id.get(str(dev), []),
        ))
    snap.ports = ports
    snap.adapters = _linux_usb_adapters()
    snap.note = ("Holder detection sees this user's processes only — "
                 "an empty in-use column is not proof the port is free")
    return snap


# =============================================================================
# Entry point
# =============================================================================

def gather_serial() -> SerialSnapshot:
    """Domain gatherer for 'serial'. Registry/filesystem/subprocess
    I/O — worker thread only. Never opens a port."""
    try:
        if sys.platform == 'win32':
            return _gather_serial_windows()
        if sys.platform == 'darwin':
            return _gather_serial_macos()
        return _gather_serial_linux()
    except Exception as e:
        # A snapshot with ports=None reads as "not gathered"; the
        # registry's error capture also records the cause.
        logger.warning(f"Serial probe failed: {e}")
        raise
