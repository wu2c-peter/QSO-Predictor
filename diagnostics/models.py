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
