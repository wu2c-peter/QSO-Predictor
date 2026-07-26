"""
Shared diagnostics data models — the findings contract every doctor uses.

Promoted unchanged from `audio_doctor.models` (where they shipped in
v2.6.0); `audio_doctor.models` re-exports them, so existing import sites
and pickles of these types keep working. See dev-docs/DIAGNOSTICS_SPEC.md
§ Contract 2.

Pure stdlib — no Qt, no platform APIs (enforced by tests/test_conventions.py).

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Optional


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
