"""
System Doctor — is the OS environment safe for an unattended station?

The failure modes here are the slow, ambient ones (DIAGNOSTICS_SPEC.md
roster item 5): power management that suspends the rig's USB interface
mid-session, Fast Startup masquerading as a reboot, a macOS microphone
permission silently denied, a Linux user missing the serial group, and
a decode chain that nobody remembered to autostart after a reboot.

Checks are platform-scoped by `snapshot.platform` — a Linux-only check
simply isn't emitted on Windows (no UNKNOWN noise for concepts that
don't exist there). `fast-startup` keeps its un-prefixed v2.6.0
check_id: ownership moved here from the Audio Doctor with the id stable,
per the spec's "check_id slugs are forever" rule.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from typing import List, Optional

from diagnostics.models import (CheckResult, DetectedApp, SettingsPanel,
                                Severity, StationSnapshot, SystemSnapshot)


def _app_label(app: DetectedApp) -> str:
    return app.name + (f" ({app.instance_name})" if app.instance_name else "")


# ---------------------------------------------------------------------------
# Windows: Fast Startup, USB selective suspend, sleep timeout
# ---------------------------------------------------------------------------

def _check_fast_startup(system: SystemSnapshot) -> CheckResult:
    # Wording continuity: this check shipped in v2.6.0 inside the Audio
    # Doctor; the id and the core message are unchanged.
    check_id, title = "fast-startup", "Windows Fast Startup"
    power = system.power
    if power is None or power.fast_startup is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "Could not read the Fast Startup flag.")
    if power.fast_startup:
        return CheckResult(
            check_id, title, Severity.INFO,
            "Fast Startup is ON: 'Shut down' resumes a saved kernel "
            "image and does NOT reinitialize drivers (audio, serial, "
            "USB). When troubleshooting hardware, use Restart — a "
            "shutdown/power-on cycle proves nothing.",
            "Optional: Power Options → 'Change settings that are "
            "currently unavailable' → untick 'Turn on fast startup'. "
            "(The checkbox is absent if hibernation is disabled.)",
            panel=SettingsPanel.POWER_OPTIONS)
    detail = "Fast Startup is off — a shutdown is a real reboot."
    if power.hibernate_enabled is False:
        detail += " (Hibernation is disabled, which forces it off.)"
    return CheckResult(check_id, title, Severity.OK, detail)


def _check_usb_suspend(system: SystemSnapshot) -> CheckResult:
    check_id = "system/usb-selective-suspend"
    title = "USB selective suspend"
    power = system.power
    plan = f" (power plan: {power.plan_name})" if power and power.plan_name \
        else ""
    if power is None or power.usb_selective_suspend_ac is None:
        # The AC value is the one that matters on a mains-powered shack
        # PC — with it unreadable there is no honest "disabled" verdict,
        # whatever the battery value says (UNKNOWN-never-guess rule).
        battery = ""
        if power is not None and power.usb_selective_suspend_dc is not None:
            state = ('enabled' if power.usb_selective_suspend_dc
                     else 'disabled')
            battery = f" (on battery it is {state})"
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            f"Could not read the USB selective suspend setting for AC "
            f"power from the active power plan{battery}.")
    enabled_on = [label for label, value in
                  (("AC power", power.usb_selective_suspend_ac),
                   ("battery", power.usb_selective_suspend_dc))
                  if value]
    if enabled_on:
        return CheckResult(
            check_id, title, Severity.INFO,
            f"USB selective suspend is enabled on "
            f"{' and '.join(enabled_on)}{plan}. Windows may power down "
            f"'idle' USB devices — a classic cause of a rig codec or "
            f"CAT interface that works for hours and then vanishes "
            f"until replug. This is the Windows default; suspect it if "
            f"USB devices disappear mid-session.",
            "If your rig interface drops out randomly: Power Options → "
            "Change plan settings → Change advanced power settings → "
            "USB settings → USB selective suspend setting → Disabled.",
            panel=SettingsPanel.POWER_OPTIONS)
    read_sides = "AC power" if power.usb_selective_suspend_dc is None \
        else "AC power and battery"
    return CheckResult(
        check_id, title, Severity.OK,
        f"USB selective suspend is disabled on {read_sides}{plan} — "
        f"Windows will not power down the rig's USB interface to save "
        f"energy.")


def _check_sleep(system: SystemSnapshot, platform: str) -> CheckResult:
    """Platform-split wording (review 2026-07-27): the Windows
    STANDBYIDLE value is a literal wall-clock idle timeout — the machine
    WILL sleep mid-decode, since decoding is not 'user activity'. The
    macOS pmset value is only an idle timer gated by power assertions:
    active audio (coreaudiod) normally holds sleep off for a decoding
    station, so the near-universal default of 'sleep 1' must not be
    reported as 'your session ends after 1 minute'."""
    check_id, title = "system/sleep-timeout", "Automatic sleep"
    power = system.power
    if power is None or power.standby_ac_min is None:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "Could not read the automatic-sleep timeout for mains power.")
    battery = ""
    if power.standby_dc_min is not None:
        battery = (f" (on battery: "
                   f"{'never' if power.standby_dc_min == 0 else f'{power.standby_dc_min} min'})")
    if power.standby_ac_min == 0:
        return CheckResult(
            check_id, title, Severity.OK,
            f"The machine never sleeps on mains power{battery} — "
            f"unattended monitoring keeps running.")
    if platform == 'macos':
        if power.sleep_prevented_by:
            evidence = (f"Right now sleep is being prevented by: "
                        f"{power.sleep_prevented_by}.")
        else:
            evidence = ("Nothing was preventing sleep at probe time — "
                        "with no audio running, an idle Mac will "
                        "eventually sleep.")
        return CheckResult(
            check_id, title, Severity.INFO,
            f"The sleep timer is set to {power.standby_ac_min} min on "
            f"mains power{battery}, but macOS only sleeps when no app "
            f"holds a power assertion — active audio (a decoding "
            f"station) normally keeps the Mac awake indefinitely. "
            f"{evidence}",
            "If an unattended session ever ends in sleep, set System "
            "Settings → Displays → Advanced → 'Prevent automatic "
            "sleeping on power adapter when the display is off', or "
            "run `caffeinate`.")
    return CheckResult(
        check_id, title, Severity.INFO,
        f"The machine sleeps after {power.standby_ac_min} min of idle "
        f"time on mains power{battery} — and decoding does not count "
        f"as activity, so this is wall-clock for an untouched station "
        f"PC. Sleep stops decoding, spotting and logging.",
        "If you run the station unattended, set sleep to Never while "
        "on mains power (display sleep is fine).",
        panel=SettingsPanel.POWER_OPTIONS)


# ---------------------------------------------------------------------------
# macOS: TCC microphone permission
# ---------------------------------------------------------------------------

def _check_mic_permission(system: SystemSnapshot,
                          apps: Optional[List[DetectedApp]]) -> CheckResult:
    check_id, title = "system/mic-permission", "Microphone permission"
    ham_apps = ", ".join(sorted({a.name for a in (apps or [])})) or \
        "your decoding app"
    if system.mic_clients is None:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "The macOS privacy database is not readable from here "
            "(normal — it needs Full Disk Access). If decodes show no "
            "audio, verify System Settings → Privacy & Security → "
            "Microphone lists your decoding app with the toggle on.")
    denied = [c.client for c in system.mic_clients if c.allowed is False]
    allowed = [c.client for c in system.mic_clients if c.allowed]
    if denied:
        # TCC keeps decisions for long-uninstalled apps forever; a
        # denial only deserves a WARNING when it hits an app that is
        # actually part of this station (detected config). Stale
        # denials are noted, not alarmed (review 2026-07-27).
        from diagnostics.probe_system import match_known_app
        detected = {a.name for a in (apps or [])}
        relevant = [c for c in denied if match_known_app(c) in detected]
        granted = (f" Granted to: {', '.join(sorted(allowed))}."
                   if allowed else "")
        if relevant:
            return CheckResult(
                check_id, title, Severity.WARNING,
                f"Microphone access is DENIED for: "
                f"{', '.join(sorted(relevant))}. macOS silently delivers "
                f"zero audio to an app without this permission — the "
                f"waterfall stays empty while everything else looks "
                f"normal.{granted}",
                "System Settings → Privacy & Security → Microphone → "
                "enable the app, then restart it.")
        return CheckResult(
            check_id, title, Severity.INFO,
            f"A past microphone denial is recorded for: "
            f"{', '.join(sorted(denied))} — no config for it was "
            f"detected on this machine, so this only matters if you "
            f"still use it.{granted}")
    if allowed:
        return CheckResult(
            check_id, title, Severity.OK,
            f"Microphone access is granted to: {', '.join(sorted(allowed))}.")
    return CheckResult(
        check_id, title, Severity.INFO,
        f"No ham app has a recorded microphone decision yet. macOS asks "
        f"on first audio use — if {ham_apps} has never prompted and "
        f"shows no audio, check System Settings → Privacy & Security → "
        f"Microphone.")


# ---------------------------------------------------------------------------
# Linux: serial-port group membership
# ---------------------------------------------------------------------------

def _check_serial_access(system: SystemSnapshot) -> CheckResult:
    check_id, title = "system/serial-permissions", "Serial port permissions"
    if system.is_root:
        # Root bypasses file permissions — group membership is
        # irrelevant, and a usermod suggestion would be nonsense.
        return CheckResult(
            check_id, title, Severity.OK,
            "Running as root — serial CAT/PTT devices are accessible "
            "without any group membership.")
    if system.serial_member_groups is None:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "Could not enumerate this user's groups.")
    devices = system.serial_devices or []
    if system.serial_member_groups:
        return CheckResult(
            check_id, title, Severity.OK,
            f"This user is in the "
            f"{', '.join(system.serial_member_groups)} group — serial "
            f"CAT/PTT devices are accessible."
            + (f" Present now: {', '.join(devices)}." if devices else ""))
    if not system.serial_groups:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "No conventional serial-access group (dialout, uucp) exists "
            "on this system — cannot infer permissions from group "
            "membership.")
    group = system.serial_groups[0]
    if devices:
        return CheckResult(
            check_id, title, Severity.WARNING,
            f"Serial devices exist ({', '.join(devices)}) but this user "
            f"is not in the {group} group — opening them for CAT or PTT "
            f"will likely fail with 'permission denied'. (Per-session "
            f"udev ACLs, which some desktops grant, were not examined.)",
            f"Run: sudo usermod -aG {group} $USER — then log out and "
            f"back in (the new group only applies to new logins).")
    return CheckResult(
        check_id, title, Severity.INFO,
        f"This user is not in the {group} group. No serial devices are "
        f"attached right now; if you add a USB CAT interface, add "
        f"yourself to {group} first (then log out and back in).")


# ---------------------------------------------------------------------------
# All platforms: autostart inventory
# ---------------------------------------------------------------------------

def _check_autostart(system: SystemSnapshot,
                     apps: Optional[List[DetectedApp]]) -> CheckResult:
    check_id, title = "system/autostart", "Ham apps starting automatically"
    if system.autostart_entries is None:
        return CheckResult(
            check_id, title, Severity.UNKNOWN,
            "Autostart entries could not be enumerated.")
    note = f" ({system.autostart_note}.)" if system.autostart_note else ""
    other = system.autostart_other_count or 0
    others = ("" if not other else
              f" Plus {other} unrelated autostart "
              f"entr{'y' if other == 1 else 'ies'}, not listed.")
    active = [e for e in system.autostart_entries if not e.disabled]
    disabled = [e for e in system.autostart_entries if e.disabled]
    if active or disabled:
        parts = []
        if active:
            parts.append("Starting automatically: " + "; ".join(
                f"{e.app} — {e.name} ({e.source})" for e in active))
        if disabled:
            # Present but switched off (Task Manager / Hidden=true):
            # it will NOT start — saying otherwise sends helpers down
            # the wrong path.
            parts.append("Present but DISABLED (will not start): "
                         + "; ".join(f"{e.app} — {e.name} ({e.source})"
                                     for e in disabled))
        return CheckResult(
            check_id, title, Severity.INFO,
            ". ".join(parts) + f".{others}{note}")
    detected = sorted({a.name for a in (apps or [])})
    verb = "was" if len(detected) == 1 else "were"
    chain = f" ({', '.join(detected)} {verb} detected on this machine)" \
        if detected else ""
    return CheckResult(
        check_id, title, Severity.INFO,
        f"No known ham application starts automatically{chain} — after "
        f"a reboot, every link in the decode chain needs a manual "
        f"start.{others}{note}")


class SystemDoctor:
    """Doctor-protocol implementation for the OS-environment subsystem."""

    id = 'system'
    title = 'System Doctor'
    platforms = frozenset({'windows', 'macos', 'linux'})
    domains = frozenset({'system', 'apps'})

    def run(self, snap: StationSnapshot) -> List[CheckResult]:
        if snap.system is None:
            return [CheckResult(
                check_id='system/snapshot-missing',
                title='System state could not be gathered',
                severity=Severity.UNKNOWN,
                detail='The system probe did not produce a snapshot — '
                       'see the probe errors in this report.',
            )]
        results: List[CheckResult] = []
        if snap.platform == 'windows':
            results += [_check_fast_startup(snap.system),
                        _check_usb_suspend(snap.system),
                        _check_sleep(snap.system, snap.platform)]
        elif snap.platform == 'macos':
            results += [_check_sleep(snap.system, snap.platform),
                        _check_mic_permission(snap.system, snap.apps)]
        else:
            results.append(_check_serial_access(snap.system))
        results.append(_check_autostart(snap.system, snap.apps))
        return results
