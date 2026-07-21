"""
Data models for the Audio Doctor.

Pure stdlib — no Qt, no COM. `probe_windows.py` populates these from live
Windows state; `checks.py` reasons over them. Keeping the types platform-
neutral is what lets the diagnostic logic run under pytest on any OS.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import List, Optional


# =============================================================================
# Enums
# =============================================================================

class DataFlow(Enum):
    """Audio endpoint direction (mmdeviceapi EDataFlow)."""
    RENDER = "render"      # playback — TX audio to the rig
    CAPTURE = "capture"    # recording — RX audio from the rig


class DeviceState(IntEnum):
    """MMDevice DEVICE_STATE_* values (mmdeviceapi.h), as returned by
    EnumAudioEndpoints and persisted under MMDevices\\Audio in the registry."""
    ACTIVE = 0x1
    DISABLED = 0x2      # disabled in the Sound control panel
    NOTPRESENT = 0x4    # adapter removed / disabled in Device Manager
    UNPLUGGED = 0x8     # jack-detection says nothing is plugged in

    @property
    def label(self) -> str:
        return _STATE_LABEL[self]


_STATE_LABEL = {
    DeviceState.ACTIVE: "Active",
    DeviceState.DISABLED: "Disabled",
    DeviceState.NOTPRESENT: "Not present",
    DeviceState.UNPLUGGED: "Unplugged",
}


class SettingsPanel(Enum):
    """A Windows settings surface a finding's fix lives in. Pure data —
    the dialog renders these as "Open ..." links and probe_windows owns
    the actual launch commands."""
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


class TxVerdict(Enum):
    """Result of the live TX-path probe (and of the passive silent-TX
    monitor). Each value carries its own display text so the dialog and
    the health warning don't duplicate wording."""
    AUDIO_FLOWING = "audio_flowing"
    NO_SESSION = "no_session"
    MUTED_IN_MIXER = "muted_in_mixer"
    MIXER_VOLUME_LOW = "mixer_volume_low"
    APP_NOT_EMITTING = "app_not_emitting"
    NOT_REACHING_ENDPOINT = "not_reaching_endpoint"
    INCONCLUSIVE = "inconclusive"

    @property
    def is_problem(self) -> bool:
        return self in _PROBLEM_VERDICTS

    @property
    def headline(self) -> str:
        return _VERDICT_HEADLINE[self]

    @property
    def explanation(self) -> str:
        return _VERDICT_EXPLANATION[self]

    @property
    def fix(self) -> str:
        return _VERDICT_FIX[self]

    @property
    def panel(self) -> "Optional[SettingsPanel]":
        """Windows settings surface where this verdict's fix lives, if
        the fix is a Windows setting (vs. something inside WSJT-X)."""
        return _VERDICT_PANEL.get(self)


_PROBLEM_VERDICTS = frozenset({
    TxVerdict.NO_SESSION,
    TxVerdict.MUTED_IN_MIXER,
    TxVerdict.MIXER_VOLUME_LOW,
    TxVerdict.APP_NOT_EMITTING,
    TxVerdict.NOT_REACHING_ENDPOINT,
})

_VERDICT_HEADLINE = {
    TxVerdict.AUDIO_FLOWING: "TX audio is reaching the codec",
    TxVerdict.NO_SESSION: "No WSJT-X audio session on the codec",
    TxVerdict.MUTED_IN_MIXER: "WSJT-X is muted in the Windows mixer",
    TxVerdict.MIXER_VOLUME_LOW: "WSJT-X mixer volume is near zero",
    TxVerdict.APP_NOT_EMITTING: "WSJT-X is not producing audio",
    TxVerdict.NOT_REACHING_ENDPOINT: "Audio is not reaching the codec",
    TxVerdict.INCONCLUSIVE: "Not enough data to judge the TX path",
}

_VERDICT_EXPLANATION = {
    TxVerdict.AUDIO_FLOWING:
        "A WSJT-X audio session exists on the codec and samples are "
        "registering on the Windows peak meters. If the rig still shows "
        "no modulation, look at the rig side (USB MOD level, DATA mode).",
    TxVerdict.NO_SESSION:
        "WSJT-X has no playback session on the rig codec. Its stored "
        "output-device binding is probably stale (this happens when "
        "Windows re-enumerates the codec after a USB port change or "
        "driver event).",
    TxVerdict.MUTED_IN_MIXER:
        "Windows keeps a persistent per-app mute for WSJT-X on this "
        "device — it survives reboots and is invisible inside WSJT-X.",
    TxVerdict.MIXER_VOLUME_LOW:
        "The per-app volume for WSJT-X on this device is at or near "
        "zero in the Windows mixer. Communications ducking or a stray "
        "mixer click can leave it there; it persists across reboots.",
    TxVerdict.APP_NOT_EMITTING:
        "WSJT-X has a session on the codec but is producing silence. "
        "Check the Pwr slider in WSJT-X and that a transmission is "
        "actually in progress (Tune button).",
    TxVerdict.NOT_REACHING_ENDPOINT:
        "WSJT-X is producing audio but nothing registers on the codec "
        "endpoint meter — audio may be routed to a different device.",
    TxVerdict.INCONCLUSIVE:
        "The probe did not collect enough samples. Make sure WSJT-X is "
        "transmitting (press Tune) while the check runs.",
}

# Verdicts whose fix is inside WSJT-X (NO_SESSION, APP_NOT_EMITTING)
# deliberately carry no panel — a Windows settings link would mislead.
_VERDICT_PANEL = {
    TxVerdict.MUTED_IN_MIXER: SettingsPanel.VOLUME_MIXER,
    TxVerdict.MIXER_VOLUME_LOW: SettingsPanel.VOLUME_MIXER,
    TxVerdict.NOT_REACHING_ENDPOINT: SettingsPanel.VOLUME_MIXER,
}

_VERDICT_FIX = {
    TxVerdict.AUDIO_FLOWING: "",
    TxVerdict.NO_SESSION:
        "In WSJT-X: Settings → Audio → switch Output to another device, "
        "click OK, restart WSJT-X, then switch back and click OK.",
    TxVerdict.MUTED_IN_MIXER:
        "While WSJT-X is transmitting, open the Windows Volume Mixer "
        "with the codec selected and unmute WSJT-X — or use Settings → "
        "System → Sound → 'Reset sound devices and volumes for all "
        "apps'. If the mixer row looks greyed out or wrong, close and "
        "reopen the mixer page — its display is often stale.",
    TxVerdict.MIXER_VOLUME_LOW:
        "While WSJT-X is transmitting, open the Windows Volume Mixer "
        "with the codec selected and raise the WSJT-X slider to 100%. "
        "If the row looks greyed out or wrong, close and reopen the "
        "mixer page — its display is often stale.",
    TxVerdict.APP_NOT_EMITTING:
        "Raise the Pwr slider (bottom right in WSJT-X) and press Tune.",
    TxVerdict.NOT_REACHING_ENDPOINT:
        "Check WSJT-X Settings → Audio Output points at the codec, and "
        "check Windows per-app output routing (Volume mixer).",
    TxVerdict.INCONCLUSIVE:
        "Press Tune in WSJT-X, then run the check again.",
}


# =============================================================================
# Snapshot dataclasses (filled by probe_windows, consumed by checks)
# =============================================================================

@dataclass
class AudioFormat:
    """Decoded WAVEFORMATEX essentials."""
    channels: int
    sample_rate_hz: int
    bits_per_sample: int


@dataclass
class EndpointInfo:
    """One MMDevice audio endpoint."""
    id: str                    # full endpoint ID, e.g. "{0.0.0.00000000}.{guid}"
    name: str                  # friendly name, e.g. "Speakers (2- USB Audio CODEC)"
    flow: DataFlow
    state: DeviceState
    fmt: Optional[AudioFormat] = None   # shared-mode / default format if readable


@dataclass
class AppSessionInfo:
    """A live per-app audio session on some render endpoint."""
    endpoint_id: str
    endpoint_name: str
    process_name: str          # lowercase basename, e.g. "wsjtx.exe"
    pid: int
    volume: Optional[float] = None      # 0.0–1.0 mixer slider
    muted: Optional[bool] = None
    active: bool = False       # session state == Active (stream open now)


@dataclass
class PersistedAppAudio:
    """One entry from the per-app volume PropertyStore in the registry —
    the state that survives reboots even when the app isn't running."""
    endpoint_id: str
    exe_path: str              # NT path, e.g. \\Device\\HarddiskVolume3\\...\\wsjtx.exe
    volume: Optional[float] = None
    muted: Optional[bool] = None

    @property
    def exe_name(self) -> str:
        return self.exe_path.replace("/", "\\").rsplit("\\", 1)[-1].lower()


@dataclass
class AudioSnapshot:
    """Everything the static audit looks at, gathered in one pass.

    Fields that could not be read are left at None (or, for `persisted`,
    None as opposed to an empty list) — checks report those as UNKNOWN
    rather than guessing.
    """
    endpoints: List[EndpointInfo] = field(default_factory=list)
    default_render_id: Optional[str] = None        # eConsole role
    default_render_comm_id: Optional[str] = None   # eCommunications role
    default_capture_id: Optional[str] = None
    default_capture_comm_id: Optional[str] = None
    sessions: List[AppSessionInfo] = field(default_factory=list)
    persisted: Optional[List[PersistedAppAudio]] = None
    ducking_preference: Optional[int] = None       # see parsing.DUCKING_LABELS
    fast_startup: Optional[bool] = None
    sound_scheme: Optional[str] = None             # '.None' means silent scheme
    errors: List[str] = field(default_factory=list)  # probe-time notes for the log

    def endpoint_by_id(self, endpoint_id: Optional[str]) -> Optional[EndpointInfo]:
        for ep in self.endpoints:
            if ep.id == endpoint_id:
                return ep
        return None


@dataclass
class CheckResult:
    """Outcome of one audit check, in display order."""
    check_id: str              # stable slug, e.g. "default-communication"
    title: str
    severity: Severity
    detail: str
    fix: str = ""
    panel: Optional[SettingsPanel] = None   # where the fix lives, if a Windows setting


@dataclass
class TxProbeSample:
    """One polling sample from the live TX-path probe."""
    session_found: bool
    session_muted: Optional[bool] = None
    session_volume: Optional[float] = None
    session_peak: Optional[float] = None    # 0.0–1.0 per-session meter
    endpoint_peak: Optional[float] = None   # 0.0–1.0 endpoint mix meter
