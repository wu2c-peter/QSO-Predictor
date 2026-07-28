"""
Serial/CAT Doctor — will rig control actually work?

CAT failures are the "it worked yesterday" of the hardware side
(DIAGNOSTICS_SPEC.md roster item 4): Windows renumbered COM ports after
a replug and the config still says COM5; a counterfeit Prolific chip
hit the driver that refuses it (Code 10); two apps fight over one port;
an FTDI clone got its PID zeroed years ago and the cable is silently
dead. All checks are pure functions over the snapshot — the probe never
opens a port (opening can toggle DTR/RTS and key the transmitter).

Config semantics matter here: WSJT-X keeps CATSerialPort populated even
with Rig=None (a placeholder like Bluetooth-Incoming-Port), and PTTport
means nothing when PTTMethod is VOX or CAT — a port is only "expected"
when the matching feature is actually selected.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import re
from typing import List, Optional, Tuple

from diagnostics.models import (CheckResult, DetectedApp, SerialPortInfo,
                                SerialSnapshot, Severity, StationSnapshot)
from diagnostics.probe_serial import (FTDI_BRICKED, WIN_PROBLEM_CODES,
                                      is_macos_pseudo_port)
from diagnostics.probe_system import match_known_app

# Rig choices whose rig control does NOT go through this app's
# CATSerialPort (network CAT, or an external program that owns the
# port from its own config).
_EXTERNAL_RIG_MARKERS = ('none', 'hamlib net', 'flrig', 'dx lab',
                        'commander', 'omnirig', 'ham radio deluxe',
                        'tci')

_PROLIFIC_FIX = (
    "If CAT fails with this adapter: counterfeit PL2303 chips are "
    "extremely common in cheap CAT/programming cables, and current "
    "Prolific drivers deliberately refuse them ('this device cannot "
    "start', Code 10). Either install the last driver that accepted "
    "them (3.3.11.152) or — better — replace the cable with an "
    "FTDI/CP210x one."
)


def _label(app: DetectedApp) -> str:
    return app.name + (f" ({app.instance_name})" if app.instance_name else "")


# Win32 device-namespace prefix ('\\.\COM15'), possibly with doubled
# backslashes: QSettings escapes '\' on write and the ini reader does
# not unescape, so any depth of leading backslashes must normalize.
_WIN_NAMESPACE_RE = re.compile(r'^[\\]+\.[\\]+')


def _normalize_port_name(value: str) -> str:
    """Pure: canonical comparison form for a port name — the '\\.\\'
    namespace prefix stripped (in any escaping depth), casefolded."""
    return _WIN_NAMESPACE_RE.sub('', value.strip()).casefold()


def _port_names(port: SerialPortInfo) -> List[str]:
    return ([_normalize_port_name(port.device)]
            + [_normalize_port_name(a) for a in port.aliases])


def _find_port(configured: str,
               ports: List[SerialPortInfo]) -> Optional[SerialPortInfo]:
    want = _normalize_port_name(configured)
    for port in ports:
        if want in _port_names(port):
            return port
    return None


def _device_like(value: str) -> bool:
    """Pure: does a config value name a local serial device (as opposed
    to empty, 'None', 'USB', or a network endpoint)?"""
    v = _normalize_port_name(value)
    if not v or v in ('none', 'usb', 'emu'):
        return False
    if v.startswith('com'):
        return v[3:].isdigit()
    return v.startswith('/dev/')


def _expected_ports(app: DetectedApp) -> List[Tuple[str, str]]:
    """Pure: [(purpose, configured port)] this app will actually open.
    CAT only counts when a real serial-CAT rig is selected; a PTT port
    only counts for DTR/RTS keying. The same-port dedupe applies only
    when CAT was actually expected — with Rig=None, cat_port is a stale
    placeholder and must not swallow a real DTR/RTS keying port that
    happens to equal it (review 2026-07-27)."""
    expected = []
    rig = app.rig_name.strip().casefold()
    cat_is_serial = (rig and not any(m in rig
                                     for m in _EXTERNAL_RIG_MARKERS))
    cat_expected = cat_is_serial and _device_like(app.cat_port)
    if cat_expected:
        expected.append(('CAT', app.cat_port.strip()))
    if (app.ptt_method.upper() in ('DTR', 'RTS')
            and _device_like(app.ptt_port)
            and not (cat_expected
                     and _normalize_port_name(app.ptt_port)
                     == _normalize_port_name(app.cat_port))):
        expected.append(('PTT', app.ptt_port.strip()))
    return expected


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _describe(port: SerialPortInfo) -> str:
    bits = []
    if port.device_label:
        bits.append(port.device_label)
    if port.chip:
        bits.append(port.chip)
    elif port.friendly_name:
        bits.append(port.friendly_name)
    if port.driver_name:
        drv = port.driver_name
        if port.driver_version:
            drv += f" {port.driver_version}"
        bits.append(f"driver {drv}")
    if port.in_use_by:
        bits.append(f"held by {port.in_use_by}")
    return f"{port.device}" + (f" ({', '.join(bits)})" if bits else "")


def _check_inventory(serial: SerialSnapshot) -> CheckResult:
    check_id, title = "serial/inventory", "Serial ports present"
    ports = serial.ports or []
    note = f" ({serial.note}.)" if serial.note else ""
    real = [p for p in ports if not is_macos_pseudo_port(p.device)]
    if not real:
        placeholders = ""
        if ports:
            # Every Mac has cu.Bluetooth-Incoming-Port — listing OS
            # placeholders as healthy serial hardware would hide "your
            # adapter is gone" behind a green row.
            placeholders = (" Only OS placeholder ports are present: "
                            + ", ".join(p.device for p in ports) + ".")
        return CheckResult(
            check_id, title, Severity.INFO,
            f"No usable serial ports were found.{placeholders} Fine for "
            f"stations using VOX keying and no CAT; serial rig control "
            f"or DTR/RTS keying needs one.")
    return CheckResult(
        check_id, title, Severity.OK,
        "; ".join(_describe(p) for p in real) + f".{note}")


def _check_configured_ports(apps: Optional[List[DetectedApp]],
                            serial: SerialSnapshot) -> CheckResult:
    check_id = "serial/configured-port-exists"
    title = "Configured CAT/PTT ports exist"
    if apps is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "App configurations were not gathered, so no "
                           "configured ports to verify.")
    expectations = [(app, purpose, port_name)
                    for app in apps
                    for purpose, port_name in _expected_ports(app)]
    if not expectations:
        return CheckResult(
            check_id, title, Severity.INFO,
            "No detected app is configured to open a serial port "
            "(network CAT, VOX keying, or no rig control).")
    ports = serial.ports or []
    ok_lines, missing_lines = [], []
    for app, purpose, port_name in expectations:
        port = _find_port(port_name, ports)
        if port is not None:
            ok_lines.append(f"{_label(app)} {purpose} → {port_name}"
                            + (f" ({port.chip})" if port.chip else ""))
        else:
            missing_lines.append(
                f"{_label(app)} expects {purpose} on {port_name}, but "
                f"no such port exists right now")
    if missing_lines:
        present = ""
        if ports:
            present = (" Ports that DO exist: "
                       + ", ".join(p.device for p in ports) + ".")
        return CheckResult(
            check_id, title, Severity.WARNING,
            "; ".join(missing_lines) + f".{present} Rig control will "
            f"fail the moment the app opens the rig. The usual cause: "
            f"the adapter was replugged and the OS issued a new port "
            f"name, or the interface is unplugged/off.",
            "Plug in / power the interface, or point the app's "
            "CAT/PTT port setting at one of the ports that exists.")
    return CheckResult(
        check_id, title, Severity.OK,
        "Every configured CAT/PTT port exists: "
        + "; ".join(ok_lines) + ".")


def _check_driver_problems(serial: SerialSnapshot) -> CheckResult:
    """Windows only: Device Manager problem codes on serial devices."""
    check_id, title = "serial/driver-problem", "Serial driver status"
    ports = serial.ports or []
    if not ports:
        # The scan ran and found nothing — that is a successful read of
        # an empty subject, not an UNKNOWN (which would land this in
        # "Not checked" on every serial-less machine forever).
        return CheckResult(check_id, title, Severity.OK,
                           "No serial devices present — nothing to "
                           "examine.")
    broken = [(p, p.problem_code) for p in ports
              if p.problem_code not in (0, None)]
    unread = [p for p in ports if p.problem_code is None and p.vid]
    if broken:
        lines = []
        for port, code in broken:
            desc = WIN_PROBLEM_CODES.get(code, f"problem code {code}")
            line = f"{port.device} ({port.chip or port.friendly_name}): {desc}"
            if code == 10 and 'prolific' in port.chip.casefold():
                line += (" — on a Prolific adapter this is almost always "
                         "the counterfeit-PL2303 trap")
            lines.append(line)
        return CheckResult(
            check_id, title, Severity.FAIL,
            "; ".join(lines) + ". The port may appear in lists but "
            "cannot be opened.",
            "Open Device Manager → Ports: a yellow-marked device "
            "confirms it. " + _PROLIFIC_FIX)
    if unread:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            f"Device Manager status could not be read for: "
            f"{', '.join(p.device for p in unread)}. Check Device "
            f"Manager → Ports for yellow markers manually.")
    return CheckResult(
        check_id, title, Severity.OK,
        "No Device Manager problems on any serial device.")


def _check_counterfeit_traps(serial: SerialSnapshot) -> CheckResult:
    check_id, title = "serial/counterfeit-traps", "Counterfeit adapter traps"
    ports = serial.ports or []
    adapters = serial.adapters or []
    ids = ([(p.vid, p.pid) for p in ports if p.vid is not None]
           + [(a.vid, a.pid) for a in adapters])
    if serial.adapters is None and not ids:
        # No USB inventory AND no port carries an identity — there is
        # zero chip evidence, and "no traps" would be a guess (macOS
        # with system_profiler failed/timed out).
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "The USB inventory could not be read and no port carries a "
            "chip identity, so adapters were not checked against known "
            "counterfeit traps.")
    chips = ([p.chip for p in ports] + [a.chip for a in adapters])
    if FTDI_BRICKED in ids:
        return CheckResult(
            check_id, title, Severity.FAIL,
            "An FTDI adapter reports PID 0000 — the signature of a "
            "counterfeit FT232 whose PID was zeroed (the 2014 "
            "'FTDI-gate' driver did this). The device enumerates but "
            "is dead.",
            "The chip can be restored with the FT_Prog utility "
            "(rewrite PID 6001), but the cable remains a counterfeit — "
            "replacing it is the durable fix.")
    if any('prolific' in c.casefold() for c in chips if c):
        return CheckResult(
            check_id, title, Severity.INFO,
            "A Prolific PL2303 adapter is present. Genuine ones are "
            "fine, but counterfeits dominate the cheap-cable market "
            "and current Prolific drivers refuse them.",
            _PROLIFIC_FIX)
    return CheckResult(
        check_id, title, Severity.OK,
        "No adapters matching known counterfeit-chip traps.")


def _check_port_sharing(apps: Optional[List[DetectedApp]],
                        serial: SerialSnapshot) -> CheckResult:
    check_id, title = "serial/port-sharing", "Serial port contention"
    if apps is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "App configurations were not gathered, so "
                           "port usage cannot be cross-checked.")
    claims = {}
    for app in apps:
        for purpose, port_name in _expected_ports(app):
            claims.setdefault(_normalize_port_name(port_name), []).append(
                (app, purpose, port_name))
    lines = []
    severity = Severity.OK
    for key, claimants in claims.items():
        if len(claimants) > 1:
            who = ", ".join(f"{_label(a)} ({purpose})"
                            for a, purpose, _ in claimants)
            lines.append(
                f"{claimants[0][2]} is configured in more than one "
                f"place: {who} — serial ports are exclusive, so "
                f"whichever app opens it second loses (rig-sharing "
                f"software like OmniRig, rigctld or FLRig exists for "
                f"exactly this)")
            severity = Severity.INFO
    holder_data_seen = False
    for key, claimants in claims.items():
        app, purpose, port_name = claimants[0]
        port = _find_port(port_name, serial.ports or [])
        if port is None or not port.in_use_by:
            continue
        holder_data_seen = True
        holder_app = match_known_app(port.in_use_by)
        if holder_app and holder_app == app.name:
            continue    # its own app holds it — the healthy case
        if app.is_running:
            lines.append(
                f"{port_name} is currently held by '{port.in_use_by}', "
                f"not by {_label(app)} which is configured to use it — "
                f"if {app.name} reports a rig-control error, this is "
                f"who has the port")
            severity = Severity.WARNING
    if lines:
        return CheckResult(
            check_id, title, severity, "; ".join(lines) + ".",
            "Close the other program (or move one of them to a "
            "different port / a rig-sharing server) and retry."
            if severity == Severity.WARNING else "")
    # The holder half of the claim needs holder evidence: on Windows
    # holders are not passively detectable at all, and elsewhere lsof /
    # /proc only see this user's processes — an unqualified "nothing
    # holds your ports" would overclaim (review 2026-07-27).
    detail = "No two apps are configured for the same serial port."
    if holder_data_seen:
        detail += (" Every configured port that reports a holder is "
                   "held by its own app.")
    elif serial.note:
        detail += f" ({serial.note}.)"
    return CheckResult(check_id, title, Severity.OK, detail)


class SerialDoctor:
    """Doctor-protocol implementation for the serial/CAT subsystem."""

    id = 'serial'
    title = 'Serial/CAT Doctor'
    platforms = frozenset({'windows', 'macos', 'linux'})
    domains = frozenset({'serial', 'apps'})

    def run(self, snap: StationSnapshot) -> List[CheckResult]:
        if snap.serial is None or snap.serial.ports is None:
            return [CheckResult(
                check_id='serial/snapshot-missing',
                title='Serial state could not be gathered',
                severity=Severity.UNKNOWN,
                detail='The serial probe did not produce a snapshot — '
                       'see the probe errors in this report.',
            )]
        results = [
            _check_inventory(snap.serial),
            _check_configured_ports(snap.apps, snap.serial),
            _check_counterfeit_traps(snap.serial),
            _check_port_sharing(snap.apps, snap.serial),
        ]
        if snap.platform == 'windows':
            results.insert(2, _check_driver_problems(snap.serial))
        return results
