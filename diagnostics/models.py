"""
Shared diagnostics data models.

Two families live here:

- The findings contract every doctor uses (`Severity`, `CheckResult`,
  `SettingsPanel`) — promoted unchanged from `audio_doctor.models` (where
  they shipped in v2.6.0); `audio_doctor.models` re-exports them, so
  existing import sites and pickles keep working. See
  dev-docs/DIAGNOSTICS_SPEC.md § Contract 2.
- The detection dataclasses (`DetectedApp`, `PortInfo`,
  `SetupRecommendation`) — lifted unchanged from `setup_wizard.py`
  (v2.2.0) in migration step 2; populated by `probe_apps` / `probe_ports`
  and consumed by `setup_analysis` and the setup wizard dialog.

Pure stdlib — no Qt, no platform APIs (enforced by tests/test_conventions.py).

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import List, Optional


class SettingsPanel(Enum):
    """A settings surface a finding's fix lives in. Pure data — dialogs
    render these as "Open ..." links and the platform probe modules own
    the actual launch commands. Windows panels today; may grow
    macOS/Linux surfaces as doctors gain platform coverage."""
    PLAYBACK_DEVICES = "playback_devices"      # mmsys.cpl Playback tab
    RECORDING_DEVICES = "recording_devices"    # mmsys.cpl Recording tab
    SOUND_SCHEME = "sound_scheme"              # mmsys.cpl Sounds tab
    COMMUNICATIONS = "communications"          # mmsys.cpl Communications tab
    VOLUME_MIXER = "volume_mixer"              # per-app volume / routing
    POWER_OPTIONS = "power_options"            # Fast Startup checkbox

    @property
    def label(self) -> str:
        return _PANEL_LABEL[self]


_PANEL_LABEL = {
    SettingsPanel.PLAYBACK_DEVICES: "Open playback devices",
    SettingsPanel.RECORDING_DEVICES: "Open recording devices",
    SettingsPanel.SOUND_SCHEME: "Open sound scheme settings",
    SettingsPanel.COMMUNICATIONS: "Open the Communications tab",
    SettingsPanel.VOLUME_MIXER: "Open the volume mixer",
    SettingsPanel.POWER_OPTIONS: "Open power options",
}


class Severity(IntEnum):
    """Outcome of one audit check. IntEnum so results sort worst-first
    with plain `sorted(..., reverse=True)` on the enum value."""
    OK = 0
    INFO = 1
    UNKNOWN = 2     # state could not be read — not proof of a problem
    WARNING = 3
    FAIL = 4

    @property
    def label(self) -> str:
        return _SEVERITY_LABEL[self]

    @property
    def color(self) -> str:
        """Dark-theme hex color for dialog rendering."""
        return _SEVERITY_COLOR[self]

    @property
    def symbol(self) -> str:
        return _SEVERITY_SYMBOL[self]


_SEVERITY_LABEL = {
    Severity.OK: "OK",
    Severity.INFO: "Info",
    Severity.UNKNOWN: "Unknown",
    Severity.WARNING: "Warning",
    Severity.FAIL: "Problem",
}

_SEVERITY_COLOR = {
    Severity.OK: "#00C853",
    Severity.INFO: "#40C4FF",
    Severity.UNKNOWN: "#9E9E9E",
    Severity.WARNING: "#FFB300",
    Severity.FAIL: "#FF5252",
}

_SEVERITY_SYMBOL = {
    Severity.OK: "✓",
    Severity.INFO: "ℹ",
    Severity.UNKNOWN: "?",
    Severity.WARNING: "⚠",
    Severity.FAIL: "✗",
}


@dataclass
class CheckResult:
    """Outcome of one audit check, in display order.

    `check_id` slugs are persisted-string territory (they circulate in
    pasted reports): never rename, never reuse. New doctors namespace
    theirs as "<doctor>/<slug>"; Audio Doctor's pre-framework ids stay
    un-prefixed for continuity with v2.6.0 logs.
    """
    check_id: str              # stable slug, e.g. "default-communication"
    title: str
    severity: Severity
    detail: str
    fix: str = ""
    panel: Optional[SettingsPanel] = None   # where the fix lives, if a setting


# =============================================================================
# Detection dataclasses (filled by probe_apps / probe_ports, consumed by
# setup_analysis and the setup wizard dialog)
# =============================================================================

@dataclass
class DetectedApp:
    """A ham radio application detected on this system."""
    name: str                       # e.g. "WSJT-X", "JTDX", "JTAlert"
    config_path: Optional[Path]     # Path to config file (if found)
    config_mtime: str = ""          # config file mtime, ISO UTC ("" = unread);
                                    #   evidence for stale/duplicate-config
                                    #   diagnoses (spec Contract 3)
    instance_name: str = ""         # For multi-instance (e.g. "OmniRig Rig 1")
    callsign: str = ""
    grid: str = ""
    udp_ip: str = ""
    udp_port: int = 0
    accept_udp: bool = False
    sound_in: str = ""              # configured capture device name ("" = key absent)
    sound_out: str = ""             # configured playback device name ("" = key absent)
    is_running: bool = False
    log_directory: Optional[Path] = None
    # Rig control (v2.7.0, consumed by the Serial/CAT Doctor). "" = key
    # absent/unset. rig_name "None" means no CAT — WSJT-X leaves a
    # placeholder CATSerialPort behind, so port fields mean nothing
    # unless the matching method is actually selected.
    rig_name: str = ""
    cat_port: str = ""              # CATSerialPort
    ptt_port: str = ""              # PTTport
    ptt_method: str = ""            # decoded from the QVariant blob:
                                    #   "VOX" / "CAT" / "DTR" / "RTS"


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


# =============================================================================
# Clock domain (filled by probe_clock, consumed by the Clock Doctor)
# =============================================================================

@dataclass
class ClockSnapshot:
    """System-clock state vs NTP. offset_s None = no NTP server was
    reachable (common off-grid) — checks report UNKNOWN, not failure."""
    offset_s: Optional[float] = None    # system minus NTP; positive = fast
    round_trip_s: Optional[float] = None
    ntp_server: str = ""                # server that answered
    timezone_name: str = ""
    utc_offset_min: Optional[int] = None


# =============================================================================
# Serial domain (filled by probe_serial, consumed by the Serial/CAT Doctor)
# =============================================================================

@dataclass
class SerialPortInfo:
    """One serial port present on the system right now."""
    device: str                     # "COM3", "/dev/cu.usbserial-1420",
                                    #   "/dev/ttyUSB0"
    friendly_name: str = ""         # OS display name / USB product string
    vid: Optional[int] = None       # USB vendor id (None = not USB / unknown)
    pid: Optional[int] = None
    chip: str = ""                  # identified adapter family ("FTDI",
                                    #   "CP210x", "CH340", "Prolific", ...)
    device_label: str = ""          # recognized product (e.g. "Digirig")
    driver_name: str = ""
    driver_version: str = ""
    in_use_by: str = ""             # process holding the port ("" = free
                                    #   or not determinable — see note)
    problem_code: Optional[int] = None  # Windows Device Manager problem
                                        #   code (0 = fine, 10 = cannot
                                        #   start, 28 = no driver); None =
                                        #   not read
    aliases: List[str] = field(default_factory=list)  # other paths for the
                                                      #   same port (by-id
                                                      #   symlink, tty./cu.
                                                      #   twin)


@dataclass
class UsbSerialAdapter:
    """One USB serial-adapter-class device from the USB inventory —
    evidence even when it can't be tied to a specific port node
    (macOS)."""
    vid: int
    pid: int
    product: str = ""
    manufacturer: str = ""
    chip: str = ""


@dataclass
class SerialSnapshot:
    """Serial/CAT hardware state. Passive: enumeration only — no port is
    ever opened (opening a CAT port can toggle DTR/RTS and key the
    transmitter)."""
    ports: Optional[List[SerialPortInfo]] = None      # None = not gathered
    adapters: Optional[List[UsbSerialAdapter]] = None  # USB inventory
                                                       #   (macOS today)
    note: str = ""                  # platform caveat (e.g. holder
                                    #   detection unavailable on Windows)


# =============================================================================
# System domain (filled by probe_system, consumed by the System Doctor)
# =============================================================================

@dataclass
class PowerInfo:
    """OS power-management state. Windows fills everything it can read;
    macOS fills the sleep timeouts (pmset) and the live sleep-prevention
    evidence. None = unreadable on a platform that has the concept —
    checks on other platforms simply don't run, so a None here never
    turns into check noise."""
    fast_startup: Optional[bool] = None      # Windows: EFFECTIVE state —
                                             #   HiberbootEnabled gated by
                                             #   hibernation being enabled
    hibernate_enabled: Optional[bool] = None
    plan_name: str = ""                      # active power scheme ("" = unknown)
    usb_selective_suspend_ac: Optional[bool] = None
    usb_selective_suspend_dc: Optional[bool] = None
    standby_ac_min: Optional[int] = None     # minutes until sleep; 0 = never
    standby_dc_min: Optional[int] = None
    sleep_prevented_by: str = ""             # macOS: processes currently
                                             #   holding sleep off (pmset -g
                                             #   "sleep prevented by ...");
                                             #   "" = nothing / not macOS


@dataclass
class TccMicClient:
    """One macOS TCC microphone decision for a ham-relevant app. Only
    ham-relevant clients are stored — the full TCC table is an inventory
    of the user's software and doesn't belong in a circulated report."""
    client: str                     # bundle id or binary path
    allowed: Optional[bool] = None  # None = value scheme not understood


@dataclass
class AutostartEntry:
    """One autostart item matching a known ham app. Non-ham entries are
    counted, never listed (privacy: a startup inventory fingerprints the
    machine)."""
    name: str
    source: str                     # e.g. "HKCU Run", "Startup folder",
                                    #   "LaunchAgents", "autostart dir"
    app: str = ""                   # canonical ham app name it matched
    command: str = ""
    disabled: bool = False          # present but switched off (Task
                                    #   Manager's StartupApproved state,
                                    #   .desktop Hidden=true, plist
                                    #   Disabled) — it will NOT start


@dataclass
class SystemSnapshot:
    """OS-level station environment: power management, permissions,
    autostart. Per-platform fields stay None on platforms where the
    concept doesn't exist or the probe didn't run — the System Doctor
    only emits checks appropriate to snapshot.platform."""
    power: Optional[PowerInfo] = None                 # windows (+ macOS sleep)
    mic_clients: Optional[List[TccMicClient]] = None  # macos; None = TCC db
                                                      #   unreadable (normal
                                                      #   without Full Disk
                                                      #   Access)
    serial_member_groups: Optional[List[str]] = None  # linux: serial-granting
                                                      #   groups the user is IN.
                                                      #   Only the intersection
                                                      #   is stored — the full
                                                      #   group list would leak
                                                      #   the username (primary
                                                      #   group) and fingerprint
                                                      #   the machine
    serial_groups: Optional[List[str]] = None         # linux: serial-granting
                                                      #   groups that exist here
    serial_devices: Optional[List[str]] = None        # linux: /dev candidates
    is_root: Optional[bool] = None                    # linux: euid == 0 (root
                                                      #   needs no group)
    autostart_entries: Optional[List[AutostartEntry]] = None
    autostart_other_count: Optional[int] = None       # non-ham entries, counted
    autostart_note: str = ""                          # platform caveat (e.g.
                                                      #   macOS Login Items are
                                                      #   not visible)


# =============================================================================
# StationSnapshot — Contract 1 of dev-docs/DIAGNOSTICS_SPEC.md
# =============================================================================

SNAPSHOT_SCHEMA_VERSION = 1

# StationSnapshot fields that are checkup metadata, not gatherable
# domains. Everything else is a domain: the registry validates gatherer
# registrations against this split, and the report skips these in its
# Details section.
SNAPSHOT_META_FIELDS = frozenset({'schema_version', 'taken_at_utc',
                                  'platform', 'os_detail', 'errors'})


@dataclass
class StationSnapshot:
    """Everything one checkup's probe pass gathered, across all domains.

    Two-level availability semantics:
      - Domain level: a domain field of None means "not gathered" (no
        gatherer registered, unsupported platform, or the probe failed —
        see `errors`). Present-but-empty means "gathered, nothing found".
      - Field level inside a domain snapshot: follow that snapshot's own
        convention (None = unreadable; checks report UNKNOWN).

    Evolution is additive only: new domains and fields get defaults;
    existing field meanings never change (bump SNAPSHOT_SCHEMA_VERSION
    otherwise). Domain snapshot types owned by app-side packages appear
    as string annotations with no runtime import — the import direction
    is one-way, app -> diagnostics (see the spec's import-direction
    rule), so `AudioSnapshot` is never imported here.
    """
    schema_version: int
    taken_at_utc: str                  # ISO 8601, Z suffix
    platform: str                      # "windows" / "macos" / "linux"
    os_detail: str = ""                # e.g. "Windows-11-...", "macOS-15.5"

    audio: Optional["AudioSnapshot"] = None       # audio_doctor.models (app-side)
    apps: Optional[List[DetectedApp]] = None      # probe_apps
    udp_ports: Optional[List[PortInfo]] = None    # probe_ports
    clock: Optional[ClockSnapshot] = None         # probe_clock
    system: Optional[SystemSnapshot] = None       # probe_system
    serial: Optional[SerialSnapshot] = None       # probe_serial

    errors: List[str] = field(default_factory=list)  # probe-time notes
