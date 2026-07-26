"""
Config Doctor — are the app configs consistent with each other and with
reality?

The classic failure modes (DIAGNOSTICS_SPEC.md roster item 2): two copies
of the same config where the user edits the one the app doesn't read
(mtime evidence tells the story), and stored audio-device bindings gone
stale after Windows renamed a USB device on re-enumeration — the "config
names a device that doesn't exist" diagnosis.

Declares 'apps' AND 'audio' per Contract 4 (a doctor declares every
domain it reads). Off-Windows the audio gatherer returns None (domain
"not gathered", no error noise — see audio_doctor.doctor.gather_audio),
and the binding check reports UNKNOWN rather than guessing.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from collections import Counter
from typing import List, Optional

from diagnostics.models import (CheckResult, DetectedApp, Severity,
                                StationSnapshot)


def _label(app: DetectedApp) -> str:
    return app.name + (f" ({app.instance_name})" if app.instance_name else "")


def _check_inventory(apps: List[DetectedApp]) -> CheckResult:
    check_id, title = "config/inventory", "Detected app configurations"
    if not apps:
        return CheckResult(
            check_id, title, Severity.INFO,
            "No WSJT-X or JTDX configuration files were found on this "
            "machine. Fine for FT8web-only stations; otherwise the "
            "logging app may not be installed or has never been run.")
    parts = []
    for app in apps:
        bits = [_label(app)]
        if app.is_running:
            bits.append("running")
        if app.config_mtime:
            bits.append(f"config modified {app.config_mtime}")
        parts.append(f"{bits[0]} ({', '.join(bits[1:])})" if bits[1:]
                     else bits[0])
    return CheckResult(check_id, title, Severity.OK, "; ".join(parts) + ".")


def _check_duplicates(apps: List[DetectedApp]) -> CheckResult:
    check_id = "config/duplicate-configs"
    title = "Duplicate configuration files"
    if not apps:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "No configs found to check.")
    counts = Counter((a.name, a.instance_name) for a in apps)
    dupes = {key for key, n in counts.items() if n > 1}
    if not dupes:
        return CheckResult(
            check_id, title, Severity.OK,
            "One configuration file per app/instance.")
    lines = []
    for name, instance in sorted(dupes):
        copies = [a for a in apps
                  if (a.name, a.instance_name) == (name, instance)]
        desc = "; ".join(
            f"{a.config_path} (modified {a.config_mtime or 'unknown'})"
            for a in copies)
        lines.append(f"{name}{f' ({instance})' if instance else ''}: {desc}")
    return CheckResult(
        check_id, title, Severity.WARNING,
        f"Multiple config files exist for the same app — settings edited "
        f"in the copy the app doesn't read silently do nothing. The "
        f"modification times say which copy is live: {' | '.join(lines)}",
        "Open the app's own Settings dialog to see its live values, "
        "work out which file it actually reads, and remove or ignore "
        "the stale copy.")


def _check_callsign(apps: List[DetectedApp]) -> CheckResult:
    check_id, title = "config/callsign", "Callsign configured"
    if not apps:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "No configs found to check.")
    missing = [_label(a) for a in apps if not a.callsign]
    if missing:
        return CheckResult(
            check_id, title, Severity.INFO,
            f"No callsign stored in: {', '.join(missing)}. The app "
            f"hasn't been configured (or never saved its settings) — "
            f"and this report's Station line relies on it.")
    return CheckResult(check_id, title, Severity.OK,
                       "Every detected config has a callsign.")


# mmdeviceapi DEVICE_STATE values, duplicated here as plain ints because
# the one-way import rule forbids importing audio_doctor's DeviceState.
# ACTIVE (0x1) is a usable device; UNPLUGGED (0x8) merely has nothing in
# the jack — still a real, selectable device, so a binding to it isn't
# stale. NOTPRESENT/DISABLED ghosts must NOT satisfy a binding: Windows
# keeps the pre-rename registry entry around after USB re-enumeration,
# which is exactly the stale-binding scenario this check hunts.
_USABLE_STATES = (0x1, 0x8)


def _endpoint_names(audio, flow: Optional[str] = None) -> List[str]:
    names = []
    for ep in getattr(audio, 'endpoints', []):
        state = getattr(ep, 'state', None)
        if state is not None and int(state) not in _USABLE_STATES:
            continue
        ep_flow = getattr(getattr(ep, 'flow', None), 'value',
                          getattr(ep, 'flow', None))
        if flow is not None and ep_flow is not None and ep_flow != flow:
            continue
        names.append(ep.name)
    return names


def _binding_matches(configured: str, endpoint_names: List[str]) -> bool:
    # One-directional containment only: Qt truncates STORED names (the
    # 31-char MME limit), so the stored name may be a prefix of the live
    # one — but a live name is never a substring of the stored one in
    # any real same-device case, and allowing that direction lets a
    # short device name ('Speakers') vacuously satisfy a stale binding.
    want = configured.casefold().strip()
    for name in endpoint_names:
        have = name.casefold().strip()
        if want == have or want in have:
            return True
    return False


def _check_audio_bindings(apps: List[DetectedApp], audio) -> CheckResult:
    check_id = "config/audio-bindings"
    title = "Configured audio devices exist"
    with_bindings = [a for a in apps if a.sound_in or a.sound_out]
    if not with_bindings:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "No stored audio device names were found in the detected "
            "configs, so nothing to verify.")
    if audio is None:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "Audio state could not be gathered (the audio probe is "
            "Windows-only today), so the configured device names were "
            "not verified against live devices.")
    stale = []
    for app in with_bindings:
        for configured, names in (
                (app.sound_out, _endpoint_names(audio, flow='render')),
                (app.sound_in, _endpoint_names(audio, flow='capture'))):
            direction = 'output' if configured is app.sound_out else 'input'
            if configured and not _binding_matches(configured, names):
                stale.append(f"{_label(app)} {direction} '{configured}'")
    if stale:
        return CheckResult(
            check_id, title, Severity.WARNING,
            f"Configured audio devices that match no current device: "
            f"{'; '.join(stale)}. The stored binding is probably stale — "
            f"Windows renames USB audio devices on re-enumeration "
            f"('2- ...'), and the app may be playing to a dead entry.",
            "In the app: Settings → Audio → re-select the input and "
            "output devices, click OK, and restart the app.")
    return CheckResult(
        check_id, title, Severity.OK,
        "Every stored audio device name matches a current device.")


class ConfigDoctor:
    """Doctor-protocol implementation for the app-config subsystem."""

    id = 'config'
    title = 'Config Doctor'
    platforms = frozenset({'windows', 'macos', 'linux'})
    domains = frozenset({'apps', 'audio'})

    def run(self, snap: StationSnapshot) -> List[CheckResult]:
        if snap.apps is None:
            return [CheckResult(
                check_id='config/snapshot-missing',
                title='App configurations could not be gathered',
                severity=Severity.UNKNOWN,
                detail='The config probe did not produce results — see '
                       'the probe errors in this report.',
            )]
        return [
            _check_inventory(snap.apps),
            _check_duplicates(snap.apps),
            _check_callsign(snap.apps),
            _check_audio_bindings(snap.apps, snap.audio),
        ]
