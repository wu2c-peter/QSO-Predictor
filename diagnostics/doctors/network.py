"""
Network Doctor — does the UDP decode chain actually connect?

Stations are chains: WSJT-X/JTDX send decodes to a UDP target, something
listens there (a forwarder like GridTracker, or a consumer directly),
and downstream apps hang off forwarded ports. Every link is a separate
process someone must remember to start — "it worked yesterday" is
frequently "yesterday the forwarder was running".

This doctor diffs INTENDED topology (each config's UDP target) against
LIVE topology (who is actually bound where, from the port scan — which
covers config-referenced ports outside the conventional range; the 4242
lesson). The must-pass rule from DIAGNOSTICS_SPEC.md: an unusual but
CONSISTENT chain (e.g. WSJT-X → 4242 → forwarder → 2238) is healthy, not
suspicious — findings come from broken links, never from unconventional
port numbers.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from collections import Counter
from typing import List, Optional

from diagnostics.models import (CheckResult, DetectedApp, PortInfo,
                                Severity, StationSnapshot)

_MULTICAST_V4_PREFIXES = tuple(f'{n}.' for n in range(224, 240))
_LOOPBACK = ('localhost', '::1')
_WILDCARDS = ('', '0.0.0.0', '*', '::', '[::]')


def _label(app: DetectedApp) -> str:
    return app.name + (f" ({app.instance_name})" if app.instance_name else "")


def _is_multicast(ip: str) -> bool:
    return (ip.startswith(_MULTICAST_V4_PREFIXES)
            or (':' in ip and ip.casefold().startswith('ff')))


def _is_loopback(ip: str) -> bool:
    return ip.startswith('127.') or ip.casefold() in _LOOPBACK


def _listener_on(port: int, udp_ports: List[PortInfo]) -> Optional[PortInfo]:
    for p in udp_ports:
        if p.port == port:
            return p
    return None


def _who(listener: PortInfo) -> Optional[str]:
    """Process name, or None when the scanner couldn't identify it (the
    socket-probe fallback proves something is bound but not what)."""
    name = listener.process_name
    return name if name and name != 'unknown' else None


def _check_decode_chain(apps: List[DetectedApp],
                        udp_ports: List[PortInfo]) -> CheckResult:
    """One aggregated verdict over every sender's first hop.

    Only LOOPBACK targets are verifiable from a local port scan: remote
    unicast targets (another machine) and multicast groups are
    acknowledged, never flagged. is_running is app-level evidence — with
    multiple instance configs of one app we can't know WHICH instance
    runs, so instance-ambiguous dead links soften to INFO.
    """
    check_id, title = "network/decode-chain", "UDP decode chain"
    senders = [a for a in apps if a.udp_port and a.udp_ip]
    disabled = [a for a in apps if a.udp_port and not a.udp_ip]
    if not senders and not disabled:
        return CheckResult(
            check_id, title, Severity.INFO,
            "No configured UDP decode targets found to verify.")

    name_counts = Counter(a.name for a in senders)
    ok_lines, idle_lines, broken_lines = [], [], []
    for app in disabled:
        idle_lines.append(f"{_label(app)}: UDP output disabled (empty "
                          f"server address)")
    for app in senders:
        target = f"{app.udp_ip}:{app.udp_port}"
        if _is_multicast(app.udp_ip):
            ok_lines.append(f"{_label(app)} → {target} (multicast group — "
                            f"membership not verifiable from the port scan)")
            continue
        if not _is_loopback(app.udp_ip):
            ok_lines.append(f"{_label(app)} → {target} (remote target — "
                            f"delivery not verifiable from a local port "
                            f"scan)")
            continue
        listener = _listener_on(app.udp_port, udp_ports)
        if listener:
            who = _who(listener)
            bound_ip = listener.ip
            concrete_mismatch = (
                bound_ip not in _WILDCARDS
                and not _is_loopback(bound_ip))
            if concrete_mismatch:
                line = (f"{who or 'a process'} is on port "
                        f"{app.udp_port} but bound to {bound_ip}, so "
                        f"datagrams {_label(app)} sends to {target} may "
                        f"never reach it")
                (broken_lines if app.is_running else idle_lines).append(line)
            elif who:
                ok_lines.append(f"{_label(app)} → {target} ({who} "
                                f"listening)")
            else:
                ok_lines.append(f"{_label(app)} → {target} (a process is "
                                f"bound to the port — name unknown)")
        elif app.is_running and name_counts[app.name] == 1:
            broken_lines.append(
                f"{_label(app)} is running and sending decodes to "
                f"{target}, but nothing is listening on port "
                f"{app.udp_port} — everything downstream of that link "
                f"is receiving nothing")
        elif app.is_running:
            # Multi-instance: SOME instance of this app runs, but which
            # one isn't knowable from the process list.
            idle_lines.append(
                f"{_label(app)} targets {target}; nothing is listening "
                f"there (an {app.name} process is running, but which "
                f"instance isn't knowable)")
        else:
            idle_lines.append(
                f"{_label(app)} (not running) targets {target}; nothing "
                f"is listening there right now")

    if broken_lines:
        detail = "; ".join(broken_lines)
        if ok_lines:
            detail += ". Healthy links: " + "; ".join(ok_lines)
        return CheckResult(
            check_id, title, Severity.WARNING, detail + ".",
            "Start the app that should be listening on that port (a "
            "forwarder like GridTracker, or the consumer itself), or "
            "point the sender's UDP server setting at the port your "
            "consumer actually listens on.")
    detail_bits = ok_lines + idle_lines
    severity = Severity.OK if ok_lines else Severity.INFO
    return CheckResult(check_id, title, severity,
                       "; ".join(detail_bits) + ".")


def _check_listeners_inventory(udp_ports: List[PortInfo]) -> CheckResult:
    check_id, title = "network/listeners", "UDP listeners"
    if not udp_ports:
        return CheckResult(
            check_id, title, Severity.INFO,
            "No UDP listeners found on ham-range or config-referenced "
            "ports.")
    desc = "; ".join(
        f"port {p.port}: {_who(p) or 'name unknown'}"
        for p in sorted(udp_ports, key=lambda p: p.port))
    return CheckResult(check_id, title, Severity.INFO, desc + ".")


class NetworkDoctor:
    """Doctor-protocol implementation for the UDP-chain subsystem."""

    id = 'network'
    title = 'Network Doctor'
    platforms = frozenset({'windows', 'macos', 'linux'})
    domains = frozenset({'apps', 'udp_ports'})

    def run(self, snap: StationSnapshot) -> List[CheckResult]:
        if snap.apps is None or snap.udp_ports is None:
            missing = [d for d, v in (('apps', snap.apps),
                                      ('udp_ports', snap.udp_ports))
                       if v is None]
            return [CheckResult(
                check_id='network/snapshot-missing',
                title='Network state could not be gathered',
                severity=Severity.UNKNOWN,
                detail=f"Missing domain(s): {', '.join(missing)} — see "
                       f"the probe errors in this report.",
            )]
        return [
            _check_decode_chain(snap.apps, snap.udp_ports),
            _check_listeners_inventory(snap.udp_ports),
        ]
