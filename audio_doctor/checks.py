"""
Audit checks and TX-probe evaluation for the Audio Doctor.

Pure stdlib. `run_checks()` turns an AudioSnapshot into an ordered
checklist; `evaluate_tx_probe()` turns a series of live meter samples
into a TxVerdict. Neither touches Windows — probe_windows gathers, this
module judges.

The checks encode the failure modes researched from the July 2026
"WSJT-X silent TX after browser audio" incident: persisted per-app
mixer mutes, communications ducking, default-role hijacking by monitor
audio, stale re-enumerated codec endpoints, and wrong endpoint formats.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

from typing import Iterable, List, Optional, Sequence, Tuple

from audio_doctor.models import (
    AppSessionInfo, AudioSnapshot, CheckResult, DataFlow, DeviceState,
    EndpointInfo, Severity, TxProbeSample, TxVerdict,
)
from audio_doctor.parsing import (
    DUCKING_DO_NOTHING, ducking_label, has_enum_prefix, strip_enum_prefix,
)

# The generic USB Audio Class name of TI PCM290x-family codecs (SignaLink,
# Digirig, IC-7300 and most rig-integrated interfaces). Overridable via
# config for users with differently-named interfaces.
DEFAULT_RIG_HINT = "USB Audio CODEC"

# Digital-mode apps whose playback path we care about.
DEFAULT_APP_NAMES = ("wsjtx.exe", "jtdx.exe")

# A mixer slider at or below this is "effectively zero" — ducking leaves
# sliders at exactly 0.2/0.5 of original, but the incident case is 0/near-0.
LOW_VOLUME = 0.05

# Peak-meter floor: WSJT-X's Tune tone registers orders of magnitude above
# this on both the session and endpoint meters.
SILENCE_PEAK = 0.005

# Below this many probe samples we refuse to judge (at 10 Hz this is ~1 s
# of TX actually observed).
MIN_PROBE_SAMPLES = 8


def is_rig_endpoint(ep: EndpointInfo, rig_hint: str) -> bool:
    """Match an endpoint to the rig interface by name, ignoring the
    "N- " prefix Windows adds to re-enumerated duplicates."""
    return rig_hint.casefold() in strip_enum_prefix(ep.name).casefold()


def _rig_endpoints(snap: AudioSnapshot, rig_hint: str,
                   flow: DataFlow) -> List[EndpointInfo]:
    return [ep for ep in snap.endpoints
            if ep.flow == flow and is_rig_endpoint(ep, rig_hint)]


def _app_sessions(snap: AudioSnapshot,
                  app_names: Sequence[str]) -> List[AppSessionInfo]:
    wanted = {n.casefold() for n in app_names}
    return [s for s in snap.sessions if s.process_name.casefold() in wanted]


# =============================================================================
# Static audit
# =============================================================================

def run_checks(snap: AudioSnapshot,
               rig_hint: str = DEFAULT_RIG_HINT,
               app_names: Sequence[str] = DEFAULT_APP_NAMES) -> List[CheckResult]:
    """Run every audit check against the snapshot. Always returns the
    full checklist (one CheckResult per check, OK included) so the
    dialog reads as a methodical walkthrough, not just a list of
    complaints."""
    rig_render = _rig_endpoints(snap, rig_hint, DataFlow.RENDER)
    rig_capture = _rig_endpoints(snap, rig_hint, DataFlow.CAPTURE)
    results = [
        _check_rig_present(rig_render, rig_hint),
        _check_stale_duplicates(rig_render + rig_capture),
        _check_default_device(snap, rig_render),
        _check_default_communication(snap, rig_render, rig_capture),
        _check_ducking(snap),
        _check_format(rig_render, "tx-format", "TX (playback) format"),
        _check_format(rig_capture, "rx-format", "RX (recording) format"),
        _check_persisted_app_volume(snap, rig_render, app_names),
        _check_live_sessions(snap, rig_render, app_names),
        _check_sound_scheme(snap, rig_render),
        _check_fast_startup(snap),
    ]
    return results


def _active(endpoints: Iterable[EndpointInfo]) -> List[EndpointInfo]:
    return [ep for ep in endpoints if ep.state == DeviceState.ACTIVE]


def _check_rig_present(rig_render: List[EndpointInfo],
                       rig_hint: str) -> CheckResult:
    check_id, title = "rig-endpoint", "Rig codec playback device"
    if not rig_render:
        return CheckResult(
            check_id, title, Severity.FAIL,
            f"No playback device matching '{rig_hint}' found in any state.",
            "Check the USB cable and that the rig is on. If your "
            "interface has a different name, set it in the device box "
            "above.")
    active = _active(rig_render)
    if not active:
        states = ", ".join(f"{ep.name} ({ep.state.label})" for ep in rig_render)
        return CheckResult(
            check_id, title, Severity.FAIL,
            f"Codec playback endpoint(s) exist but none is active: {states}.",
            "Re-plug the USB cable (same port as usual). If disabled, "
            "enable it in the Sound control panel (show disabled devices).")
    return CheckResult(
        check_id, title, Severity.OK,
        f"Active: {', '.join(ep.name for ep in active)}.")


def _check_stale_duplicates(rig_all: List[EndpointInfo]) -> CheckResult:
    check_id, title = "stale-duplicates", "Duplicate / stale codec entries"
    # Only the port-move signature counts: a non-active leftover ALONGSIDE
    # a live endpoint. A codec that is simply offline (single endpoint,
    # unplugged/not-present) is the rig-endpoint check's finding, not a
    # duplicate problem.
    has_active = any(ep.state == DeviceState.ACTIVE for ep in rig_all)
    stale = ([ep for ep in rig_all if ep.state != DeviceState.ACTIVE]
             if has_active else [])
    renamed = [ep for ep in rig_all if has_enum_prefix(ep.name)]
    if stale:
        listing = ", ".join(f"{ep.name} ({ep.state.label}, {ep.flow.value})"
                            for ep in stale)
        return CheckResult(
            check_id, title, Severity.WARNING,
            f"Stale codec endpoint(s) lingering: {listing}. These appear "
            "when the codec is moved to a different USB port (it has no "
            "serial number, so Windows treats it as a new device) and "
            "they confuse device selection in apps.",
            "Keep the codec on one fixed USB port. Stale entries can be "
            "removed via Device Manager (show hidden devices).")
    if renamed:
        names = ", ".join(ep.name for ep in renamed)
        return CheckResult(
            check_id, title, Severity.INFO,
            f"Codec has been re-enumerated at least once (renamed: "
            f"{names}). Apps that stored the old name may need their "
            "audio device re-selected.")
    if not rig_all:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "No codec endpoints identified.")
    return CheckResult(check_id, title, Severity.OK,
                       "Single clean codec entry per direction.")


def _check_default_device(snap: AudioSnapshot,
                          rig_render: List[EndpointInfo]) -> CheckResult:
    check_id, title = "default-device", "Windows default playback device"
    if snap.default_render_id is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "Could not read the default device.")
    default_ep = snap.endpoint_by_id(snap.default_render_id)
    if any(ep.id == snap.default_render_id for ep in rig_render):
        return CheckResult(
            check_id, title, Severity.WARNING,
            f"The rig codec ({default_ep.name if default_ep else 'codec'}) "
            "is the Windows default playback device — system sounds and "
            "app audio will be transmitted over the air.",
            "Set your PC speakers as the default device (Settings → "
            "System → Sound), never the codec.")
    name = default_ep.name if default_ep else snap.default_render_id
    return CheckResult(check_id, title, Severity.OK,
                       f"Default is '{name}' (not the codec).")


def _check_default_communication(snap: AudioSnapshot,
                                 rig_render: List[EndpointInfo],
                                 rig_capture: List[EndpointInfo]) -> CheckResult:
    check_id, title = ("default-communication",
                       "Windows default communication device")
    if snap.default_render_comm_id is None and snap.default_capture_comm_id is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "Could not read the communication-device roles.")
    offenders = []
    if any(ep.id == snap.default_render_comm_id for ep in rig_render):
        offenders.append("playback")
    if any(ep.id == snap.default_capture_comm_id for ep in rig_capture):
        offenders.append("recording")
    if offenders:
        return CheckResult(
            check_id, title, Severity.WARNING,
            f"The rig codec is the default communication device for "
            f"{' and '.join(offenders)}. Browser/VoIP audio counts as a "
            "'call' on this device: calls could go out over the air, and "
            "a browser opening the codec mic will trigger Windows "
            "communications ducking of WSJT-X TX audio.",
            "Point both communication-device roles at your PC "
            "speakers/mic (Sound control panel → right-click device → "
            "Set as Default Communication Device).")
    return CheckResult(check_id, title, Severity.OK,
                       "Codec holds neither communication-device role.")


def _check_ducking(snap: AudioSnapshot) -> CheckResult:
    check_id, title = "ducking", "Communications ducking"
    pref = snap.ducking_preference
    if pref is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "Could not read the ducking preference.")
    if pref == DUCKING_DO_NOTHING:
        return CheckResult(check_id, title, Severity.OK,
                           "Set to 'Do nothing' — Windows will not "
                           "attenuate TX audio during calls.")
    return CheckResult(
        check_id, title, Severity.WARNING,
        f"Set to '{ducking_label(pref)}'. When any app opens a "
        "communications stream, Windows lowers other apps' mixer "
        "sliders — this can leave WSJT-X's TX audio attenuated or "
        "muted, and the lowered slider persists across reboots.",
        "Sound control panel → Communications tab → 'Do nothing'.")


def _check_format(rig_eps: List[EndpointInfo], check_id: str,
                  title: str) -> CheckResult:
    active = _active(rig_eps)
    if not active:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "No active codec endpoint to inspect.")
    ep = active[0]
    if ep.fmt is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           f"Could not read the format of '{ep.name}'.")
    desc = (f"{ep.fmt.bits_per_sample}-bit, {ep.fmt.sample_rate_hz} Hz, "
            f"{ep.fmt.channels} ch on '{ep.name}'")
    if ep.fmt.sample_rate_hz != 48000:
        return CheckResult(
            check_id, title, Severity.WARNING,
            f"{desc}. WSJT-X expects 48000 Hz — other rates force lossy "
            "resampling that degrades decoding and TX audio.",
            "Sound control panel → codec Properties → Advanced → "
            "'16 bit, 48000 Hz (DVD Quality)'.")
    return CheckResult(check_id, title, Severity.OK, f"{desc}.")


def _check_persisted_app_volume(snap: AudioSnapshot,
                                rig_render: List[EndpointInfo],
                                app_names: Sequence[str]) -> CheckResult:
    check_id, title = ("app-mixer-persisted",
                       "Persisted Windows mixer state for WSJT-X/JTDX")
    if snap.persisted is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "Could not read the per-app volume store.")
    wanted = {n.casefold() for n in app_names}
    rig_ids = {ep.id for ep in rig_render}
    hits = [p for p in snap.persisted
            if p.exe_name in wanted and p.endpoint_id in rig_ids]
    problems = [p for p in hits
                if p.muted or (p.volume is not None and p.volume <= LOW_VOLUME)]
    if problems:
        parts = []
        for p in problems:
            state = "MUTED" if p.muted else f"volume {p.volume:.0%}"
            parts.append(f"{p.exe_name}: {state}")
        return CheckResult(
            check_id, title, Severity.FAIL,
            f"Windows has persisted a silenced mixer state on the codec "
            f"for: {'; '.join(parts)}. This survives reboots, is "
            "invisible inside WSJT-X, and silences TX audio only — the "
            "classic 'RX works, TX dead' failure.",
            "While the app is transmitting, unmute / raise its slider in "
            "the Volume Mixer — or Settings → System → Sound → 'Reset "
            "sound devices and volumes for all apps'.")
    if hits:
        levels = "; ".join(
            f"{p.exe_name}: "
            + ("muted" if p.muted else
               f"{p.volume:.0%}" if p.volume is not None else "level unknown")
            for p in hits)
        return CheckResult(check_id, title, Severity.OK,
                           f"Healthy persisted mixer state ({levels}).")
    return CheckResult(
        check_id, title, Severity.OK,
        "No persisted entry for WSJT-X/JTDX on the codec (normal if the "
        "app hasn't played audio to it yet).")


def _check_live_sessions(snap: AudioSnapshot,
                         rig_render: List[EndpointInfo],
                         app_names: Sequence[str]) -> CheckResult:
    check_id, title = "app-live-session", "Live WSJT-X/JTDX audio session"
    sessions = _app_sessions(snap, app_names)
    rig_ids = {ep.id for ep in rig_render}
    on_rig = [s for s in sessions if s.endpoint_id in rig_ids]
    if not on_rig:
        # Only ACTIVE sessions elsewhere indicate a routing problem — the
        # WASAPI enumerator retains expired sessions from streams that
        # closed long ago (e.g. before the user fixed their routing).
        elsewhere_active = [s for s in sessions if s.active]
        if elsewhere_active:
            elsewhere = ", ".join(f"{s.process_name} → {s.endpoint_name}"
                                  for s in elsewhere_active)
            return CheckResult(
                check_id, title, Severity.WARNING,
                f"Audio is playing, but not to the codec: {elsewhere}.",
                "Check WSJT-X Settings → Audio Output, and Windows "
                "per-app output routing in the Volume mixer.")
        return CheckResult(
            check_id, title, Severity.INFO,
            "No live audio session on the codec. Start WSJT-X (and "
            "ideally press Tune) then use 'Check TX path' below for a "
            "live verdict.")
    bad = [s for s in on_rig
           if s.muted or (s.volume is not None and s.volume <= LOW_VOLUME)]
    if bad:
        parts = [f"{s.process_name}: "
                 + ("MUTED" if s.muted else f"volume {s.volume:.0%}")
                 for s in bad]
        return CheckResult(
            check_id, title, Severity.FAIL,
            f"Session on the codec is silenced in the mixer — "
            f"{'; '.join(parts)}.",
            "Unmute / raise the app slider in the Volume Mixer with the "
            "codec selected.")
    desc = "; ".join(
        f"{s.process_name} on {s.endpoint_name}"
        + (f" (volume {s.volume:.0%})" if s.volume is not None else "")
        for s in on_rig)
    return CheckResult(check_id, title, Severity.OK, f"{desc}.")


def _check_sound_scheme(snap: AudioSnapshot,
                        rig_render: List[EndpointInfo]) -> CheckResult:
    check_id, title = "sound-scheme", "System sounds"
    if snap.sound_scheme is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "Could not read the sound scheme.")
    if snap.sound_scheme == ".None":
        return CheckResult(check_id, title, Severity.OK,
                           "Sound scheme is 'No Sounds'.")
    codec_is_default = any(ep.id == snap.default_render_id
                           for ep in rig_render)
    if codec_is_default:
        return CheckResult(
            check_id, title, Severity.WARNING,
            "System sounds are enabled AND the codec is the default "
            "playback device — Windows dings will be transmitted.",
            "Either set PC speakers as default, or set the sound scheme "
            "to 'No Sounds'.")
    return CheckResult(
        check_id, title, Severity.INFO,
        "System sounds are enabled. Harmless while the codec is not the "
        "default device, but 'No Sounds' is cheap insurance.")


def _check_fast_startup(snap: AudioSnapshot) -> CheckResult:
    check_id, title = "fast-startup", "Windows Fast Startup"
    if snap.fast_startup is None:
        return CheckResult(check_id, title, Severity.UNKNOWN,
                           "Could not read the Fast Startup flag.")
    if snap.fast_startup:
        return CheckResult(
            check_id, title, Severity.INFO,
            "Fast Startup is ON: 'Shut down' resumes a saved kernel "
            "image and does NOT reinitialize audio drivers. When "
            "troubleshooting audio, use Restart — a shutdown/power-on "
            "cycle proves nothing.")
    return CheckResult(check_id, title, Severity.OK,
                       "Fast Startup is off — a shutdown is a real reboot.")


# =============================================================================
# Live TX-path probe evaluation
# =============================================================================

def evaluate_tx_probe(samples: Sequence[TxProbeSample]) -> TxVerdict:
    """Judge a series of live meter samples taken while the app should
    be transmitting (Tune pressed, or WSJT-X reporting transmitting=True).

    Precedence mirrors diagnostic value: a definitive mixer mute beats
    peak readings; session-level evidence beats endpoint-level.
    """
    if len(samples) < MIN_PROBE_SAMPLES:
        return TxVerdict.INCONCLUSIVE

    with_session = [s for s in samples if s.session_found]
    if not with_session:
        return TxVerdict.NO_SESSION

    if any(s.session_muted for s in with_session):
        return TxVerdict.MUTED_IN_MIXER

    volumes = [s.session_volume for s in with_session
               if s.session_volume is not None]
    if volumes and max(volumes) <= LOW_VOLUME:
        return TxVerdict.MIXER_VOLUME_LOW

    session_peaks = [s.session_peak for s in with_session
                     if s.session_peak is not None]
    endpoint_peaks = [s.endpoint_peak for s in samples
                      if s.endpoint_peak is not None]

    if session_peaks and max(session_peaks) < SILENCE_PEAK:
        return TxVerdict.APP_NOT_EMITTING
    if session_peaks and max(session_peaks) >= SILENCE_PEAK:
        if endpoint_peaks and max(endpoint_peaks) < SILENCE_PEAK:
            return TxVerdict.NOT_REACHING_ENDPOINT
        return TxVerdict.AUDIO_FLOWING
    # No session meter available; fall back to the endpoint meter alone.
    if endpoint_peaks:
        return (TxVerdict.AUDIO_FLOWING
                if max(endpoint_peaks) >= SILENCE_PEAK
                else TxVerdict.NOT_REACHING_ENDPOINT)
    return TxVerdict.INCONCLUSIVE


def summarize_checks(results: Sequence[CheckResult]) -> Tuple[Severity, str]:
    """One-line rollup for logs / status display: worst severity plus a
    count of non-OK findings."""
    if not results:
        return Severity.UNKNOWN, "No checks ran"
    worst = max(r.severity for r in results)
    flagged = sum(1 for r in results
                  if r.severity in (Severity.WARNING, Severity.FAIL))
    if worst <= Severity.INFO:
        return worst, "All audio checks passed"
    if flagged:
        return worst, f"{flagged} audio configuration issue(s) found"
    # Worst is UNKNOWN with nothing actually flagged — say that, not "0 issues".
    unknown = sum(1 for r in results if r.severity == Severity.UNKNOWN)
    return worst, f"{unknown} audio check(s) could not run"
