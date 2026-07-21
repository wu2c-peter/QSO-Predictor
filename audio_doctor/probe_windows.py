"""
Windows probe layer for the Audio Doctor — the only module in the
package that touches COM (pycaw/comtypes) and the registry.

Import rules:
- This module IS imported on every platform (controllers/audio_health
  and the dialog import it at module top), so it must stay import-safe
  everywhere: winreg/comtypes/pycaw may only be referenced inside the
  guarded try-block below or inside function bodies. Gate at runtime
  with available(), never at import time.
- The pycaw/comtypes imports are soft (PYCAW_AVAILABLE flag, same
  pattern as psutil in analyzer/core.py) so a source install without
  the optional deps degrades to "diagnostics unavailable" not a crash.

Threading contract: every public function/class here performs COM calls
and MUST run inside `with com_initialized():` when called from any
thread other than the Qt main thread (comtypes requires per-thread
CoInitialize). All callers in QSO Predictor run probes on daemon worker
threads, per the main-thread-never-blocks rule.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import logging
import sys
from contextlib import contextmanager
from typing import List, Optional, Sequence

from audio_doctor import parsing
from audio_doctor.models import (
    AppSessionInfo, AudioSnapshot, DataFlow, DeviceState, EndpointInfo,
    PersistedAppAudio, SettingsPanel, TxProbeSample,
)

logger = logging.getLogger(__name__)

try:
    import winreg

    import comtypes
    import psutil
    from pycaw.api.audiopolicy import IAudioSessionControl2
    from pycaw.api.audioclient import ISimpleAudioVolume
    from pycaw.api.endpointvolume import IAudioMeterInformation
    from pycaw.constants import EDataFlow, ERole
    from pycaw.utils import AudioUtilities
    PYCAW_AVAILABLE = True
except (ImportError, OSError):
    PYCAW_AVAILABLE = False


def available() -> bool:
    """True when the probe can actually run on this system."""
    return sys.platform == "win32" and PYCAW_AVAILABLE


@contextmanager
def com_initialized():
    """Per-thread COM bracket for worker threads. Safe to nest —
    CoInitialize just returns S_FALSE when already initialized."""
    comtypes.CoInitialize()
    try:
        yield
    finally:
        comtypes.CoUninitialize()


# =============================================================================
# Settings-panel launcher (dialog "Open ..." links)
# =============================================================================

# Classic Sound applet tabs open via control.exe with a tab index:
# mmsys.cpl,,0=Playback  ,,1=Recording  ,,2=Sounds  ,,3=Communications.
# The volume mixer / per-app routing page is a modern ms-settings URI.
_PANEL_COMMANDS = {
    SettingsPanel.PLAYBACK_DEVICES: ["control.exe", "mmsys.cpl,,0"],
    SettingsPanel.RECORDING_DEVICES: ["control.exe", "mmsys.cpl,,1"],
    SettingsPanel.SOUND_SCHEME: ["control.exe", "mmsys.cpl,,2"],
    SettingsPanel.COMMUNICATIONS: ["control.exe", "mmsys.cpl,,3"],
    SettingsPanel.VOLUME_MIXER: "ms-settings:apps-volume",
    SettingsPanel.POWER_OPTIONS: [
        "control.exe", "/name", "Microsoft.PowerOptions",
        "/page", "pageGlobalSettings"],
}


def open_settings_panel(panel: SettingsPanel) -> bool:
    """Launch the Windows settings surface for a finding's fix. Fire and
    forget; returns False (and logs) if the launch failed."""
    command = _PANEL_COMMANDS.get(panel)
    if command is None or sys.platform != "win32":
        return False
    try:
        if isinstance(command, str):
            # ms-settings: URIs launch through the shell handler.
            import os
            os.startfile(command)
        else:
            import subprocess
            subprocess.Popen(command)
        logger.info("Audio Doctor: opened settings panel %s", panel.value)
        return True
    except OSError as exc:
        logger.warning("Audio Doctor: could not open %s: %s",
                       panel.value, exc)
        return False


# =============================================================================
# Registry readers (each returns None on failure and logs once at DEBUG)
# =============================================================================

_KEY_READ_64 = None  # set lazily; winreg only exists on Windows


def _open_key(root, path):
    global _KEY_READ_64
    if _KEY_READ_64 is None:
        _KEY_READ_64 = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    return winreg.OpenKey(root, path, 0, _KEY_READ_64)


def read_ducking_preference() -> Optional[int]:
    """Communications-tab setting. An absent value means the user never
    changed it, i.e. the Windows default (reduce by 80%)."""
    try:
        with _open_key(winreg.HKEY_CURRENT_USER, parsing.DUCKING_KEY_PATH) as key:
            try:
                value, _ = winreg.QueryValueEx(key, parsing.DUCKING_VALUE_NAME)
                return int(value)
            except FileNotFoundError:
                return parsing.DUCKING_DEFAULT
    except FileNotFoundError:
        return parsing.DUCKING_DEFAULT
    except OSError as exc:
        logger.debug("Audio Doctor: ducking preference unreadable: %s", exc)
        return None


def read_fast_startup() -> Optional[bool]:
    try:
        with _open_key(winreg.HKEY_LOCAL_MACHINE,
                       parsing.FAST_STARTUP_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, parsing.FAST_STARTUP_VALUE_NAME)
            return bool(value)
    except OSError as exc:
        logger.debug("Audio Doctor: Fast Startup flag unreadable: %s", exc)
        return None


def read_sound_scheme() -> Optional[str]:
    try:
        with _open_key(winreg.HKEY_CURRENT_USER,
                       parsing.SOUND_SCHEME_KEY_PATH) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return str(value)
    except OSError as exc:
        logger.debug("Audio Doctor: sound scheme unreadable: %s", exc)
        return None


def read_persisted_app_audio() -> Optional[List[PersistedAppAudio]]:
    """Scan the per-app volume PropertyStore (both registry locations —
    Win11 24H2 moved it). Returns None only if NO location was readable."""
    entries: List[PersistedAppAudio] = []
    any_readable = False
    for path in parsing.APP_PROPERTY_STORE_PATHS:
        try:
            with _open_key(winreg.HKEY_CURRENT_USER, path) as store:
                any_readable = True
                index = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(store, index)
                    except OSError:
                        break
                    index += 1
                    entry = _read_store_entry(store, subkey_name)
                    if entry is not None:
                        entries.append(entry)
        except FileNotFoundError:
            continue    # this location doesn't exist on this Windows build
        except OSError as exc:
            logger.debug("Audio Doctor: PropertyStore %s unreadable: %s",
                         path, exc)
    return entries if any_readable else None


def _read_store_entry(store, subkey_name) -> Optional[PersistedAppAudio]:
    try:
        with winreg.OpenKey(store, subkey_name) as entry_key:
            raw, _ = winreg.QueryValueEx(entry_key, "")
            parsed = parsing.parse_property_store_entry(str(raw))
            if parsed is None:
                return None
            endpoint_id, exe_path, _guid = parsed
            volume = muted = None
            try:
                with winreg.OpenKey(entry_key,
                                    parsing.APP_VOLUME_SUBKEY) as vol_key:
                    volume = _read_propvariant_value(
                        vol_key, parsing.APP_VOLUME_VALUE, float)
                    muted = _read_propvariant_value(
                        vol_key, parsing.APP_MUTE_VALUE, bool)
            except FileNotFoundError:
                pass    # entry has no volume payload — device pin only
            return PersistedAppAudio(endpoint_id=endpoint_id,
                                     exe_path=exe_path,
                                     volume=volume, muted=muted)
    except OSError:
        return None


def _read_propvariant_value(key, value_name, expected_type):
    try:
        blob, _ = winreg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        return None
    if not isinstance(blob, bytes):
        logger.debug("Audio Doctor: PropertyStore value %r is not binary "
                     "(%r)", value_name, type(blob).__name__)
        return None
    decoded = parsing.decode_propvariant(blob)
    if decoded is None:
        # A blob we couldn't decode is a diagnosis gap — leave the hex
        # in the debug log so the format can be added.
        logger.debug("Audio Doctor: undecodable PropertyStore value %r: %s",
                     value_name, blob.hex())
        return None
    try:
        return expected_type(decoded)
    except (TypeError, ValueError):
        return None


def _read_endpoint_formats() -> dict:
    """Map endpoint GUID (lowercase '{...}') → AudioFormat, from the
    MMDevices registry tree. Works for inactive endpoints too."""
    formats = {}
    for tree in (parsing.MMDEVICES_RENDER_PATH, parsing.MMDEVICES_CAPTURE_PATH):
        try:
            with _open_key(winreg.HKEY_LOCAL_MACHINE, tree) as root:
                index = 0
                while True:
                    try:
                        guid = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    index += 1
                    try:
                        with winreg.OpenKey(root, guid + r"\Properties") as props:
                            blob, _ = winreg.QueryValueEx(
                                props, parsing.PKEY_DEVICE_FORMAT)
                    except OSError:
                        continue
                    if isinstance(blob, bytes):
                        fmt = parsing.parse_waveformat(blob)
                        if fmt is not None:
                            formats[guid.lower()] = fmt
        except OSError as exc:
            logger.debug("Audio Doctor: MMDevices tree %s unreadable: %s",
                         tree, exc)
    return formats


# =============================================================================
# COM gatherers
# =============================================================================

def _flow_from_endpoint_id(endpoint_id: str) -> Optional[DataFlow]:
    """MMDevice IDs encode the flow: '{0.0.0.00000000}.' = render,
    '{0.0.1.00000000}.' = capture."""
    if endpoint_id.startswith("{0.0.0."):
        return DataFlow.RENDER
    if endpoint_id.startswith("{0.0.1."):
        return DataFlow.CAPTURE
    return None


def _default_endpoint_id(enumerator, flow, role) -> Optional[str]:
    try:
        return enumerator.GetDefaultAudioEndpoint(flow.value, role.value).GetId()
    except Exception:   # no default configured, or COMError
        return None


def _gather_endpoints(snapshot: AudioSnapshot):
    formats = _read_endpoint_formats()
    for dev in AudioUtilities.GetAllDevices():
        if dev is None or dev.id is None:
            continue
        flow = _flow_from_endpoint_id(dev.id)
        if flow is None:
            continue
        try:
            state = DeviceState(dev.state.value)
        except ValueError:
            continue
        guid = parsing.endpoint_guid(dev.id)
        snapshot.endpoints.append(EndpointInfo(
            id=dev.id,
            name=str(dev.FriendlyName or ""),
            flow=flow,
            state=state,
            fmt=formats.get(guid) if guid else None,
        ))


def _gather_defaults(snapshot: AudioSnapshot):
    enumerator = AudioUtilities.GetDeviceEnumerator()
    snapshot.default_render_id = _default_endpoint_id(
        enumerator, EDataFlow.eRender, ERole.eConsole)
    snapshot.default_render_comm_id = _default_endpoint_id(
        enumerator, EDataFlow.eRender, ERole.eCommunications)
    snapshot.default_capture_id = _default_endpoint_id(
        enumerator, EDataFlow.eCapture, ERole.eConsole)
    snapshot.default_capture_comm_id = _default_endpoint_id(
        enumerator, EDataFlow.eCapture, ERole.eCommunications)


def _iter_render_sessions(dev):
    """Yield IAudioSessionControl2 for every session on one ACTIVE
    render device. Swallows per-session COM errors."""
    try:
        session_enum = dev.AudioSessionManager.GetSessionEnumerator()
        count = session_enum.GetCount()
    except Exception as exc:
        logger.debug("Audio Doctor: session enum failed on %s: %s",
                     dev.FriendlyName, exc)
        return
    for i in range(count):
        try:
            ctl = session_enum.GetSession(i)
            if ctl is not None:
                yield ctl.QueryInterface(IAudioSessionControl2)
        except Exception:
            continue


def _process_name(pid: int) -> Optional[str]:
    if not pid:
        return None
    try:
        return psutil.Process(pid).name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def _gather_sessions(snapshot: AudioSnapshot):
    for dev in AudioUtilities.GetAllDevices(
            EDataFlow.eRender.value, 0x1):     # ACTIVE render only
        if dev is None:
            continue
        for ctl in _iter_render_sessions(dev):
            try:
                pid = ctl.GetProcessId()
            except Exception:
                continue
            name = _process_name(pid)
            if name is None:
                continue
            volume = muted = None
            try:
                simple = ctl.QueryInterface(ISimpleAudioVolume)
                volume = float(simple.GetMasterVolume())
                muted = bool(simple.GetMute())
            except Exception:
                pass
            try:
                active = ctl.GetState() == 1    # AudioSessionStateActive
            except Exception:
                active = False
            snapshot.sessions.append(AppSessionInfo(
                endpoint_id=dev.id,
                endpoint_name=str(dev.FriendlyName or ""),
                process_name=name, pid=pid,
                volume=volume, muted=muted, active=active,
            ))


def gather_snapshot() -> AudioSnapshot:
    """Take a full read-only snapshot of Windows audio state. Never
    raises — sections that fail are left unset and noted in .errors.

    Runs COM + registry I/O; call from a worker thread inside
    `with com_initialized():`.
    """
    snapshot = AudioSnapshot()
    for label, step in (
        ("endpoints", _gather_endpoints),
        ("defaults", _gather_defaults),
        ("sessions", _gather_sessions),
    ):
        try:
            step(snapshot)
        except Exception as exc:
            msg = f"{label} probe failed: {exc}"
            snapshot.errors.append(msg)
            logger.warning("Audio Doctor: %s", msg)
    snapshot.persisted = read_persisted_app_audio()
    snapshot.ducking_preference = read_ducking_preference()
    snapshot.fast_startup = read_fast_startup()
    snapshot.sound_scheme = read_sound_scheme()
    _log_snapshot_summary(snapshot)
    return snapshot


def _log_snapshot_summary(snapshot: AudioSnapshot,
                          interesting=("wsjtx", "jtdx")):
    """One DEBUG block per audit so a user report with debug logging
    enabled shows exactly what the probe saw (smart-logging: audits are
    manual/rare, so this stays quiet in normal operation)."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    persisted = snapshot.persisted or []
    logger.debug(
        "Audio Doctor snapshot: %d endpoints, %d sessions, %d persisted "
        "entries, ducking=%s, fast_startup=%s",
        len(snapshot.endpoints), len(snapshot.sessions), len(persisted),
        snapshot.ducking_preference, snapshot.fast_startup)
    for s in snapshot.sessions:
        if any(k in s.process_name for k in interesting):
            logger.debug("  session: %s pid=%s on %r vol=%s muted=%s "
                         "active=%s", s.process_name, s.pid,
                         s.endpoint_name, s.volume, s.muted, s.active)
    for p in persisted:
        if any(k in p.exe_name for k in interesting):
            logger.debug("  persisted: %s vol=%s muted=%s endpoint=%s",
                         p.exe_name, p.volume, p.muted, p.endpoint_id)


# =============================================================================
# Live TX-path probe
# =============================================================================

class TxPathProbe:
    """Holds the COM meter/volume interfaces needed to sample the TX
    path repeatedly at low cost.

    Create, sample() in a loop, close() — all on the SAME worker thread,
    inside one `with com_initialized():` block. The probe re-scans for
    the app session every RESCAN_EVERY samples until it finds one (the
    session may only appear once the app starts transmitting).
    """

    RESCAN_EVERY = 5

    def __init__(self, rig_hint: str,
                 app_names: Sequence[str] = ("wsjtx.exe", "jtdx.exe")):
        self._rig_hint = rig_hint
        self._app_names = {n.lower() for n in app_names}
        self._session_volume = None      # ISimpleAudioVolume
        self._session_meter = None       # IAudioMeterInformation (session)
        self._endpoint_meter = None      # IAudioMeterInformation (endpoint mix)
        self._sample_count = 0
        self._bind_endpoint_meter()
        self._bind_session()

    def _rig_devices(self):
        """ACTIVE render devices, rig-matching first."""
        devices = [d for d in AudioUtilities.GetAllDevices(
            EDataFlow.eRender.value, 0x1) if d is not None]
        hint = self._rig_hint.casefold()
        devices.sort(key=lambda d: hint not in
                     parsing.strip_enum_prefix(str(d.FriendlyName or "")).casefold())
        return devices

    def _bind_endpoint_meter(self):
        for dev in self._rig_devices():
            name = parsing.strip_enum_prefix(str(dev.FriendlyName or ""))
            if self._rig_hint.casefold() not in name.casefold():
                break   # sorted rig-first; no rig device present at all
            try:
                iface = dev._dev.Activate(
                    IAudioMeterInformation._iid_, comtypes.CLSCTX_ALL, None)
                self._endpoint_meter = iface.QueryInterface(
                    IAudioMeterInformation)
                return
            except Exception as exc:
                logger.debug("Audio Doctor: endpoint meter bind failed: %s", exc)

    def _bind_session(self):
        for dev in self._rig_devices():
            for ctl in _iter_render_sessions(dev):
                try:
                    name = _process_name(ctl.GetProcessId())
                except Exception:
                    continue
                if name not in self._app_names:
                    continue
                try:
                    self._session_volume = ctl.QueryInterface(ISimpleAudioVolume)
                except Exception:
                    self._session_volume = None
                try:
                    self._session_meter = ctl.QueryInterface(
                        IAudioMeterInformation)
                except Exception:
                    self._session_meter = None
                return

    def sample(self) -> TxProbeSample:
        self._sample_count += 1
        if (self._session_volume is None and self._session_meter is None
                and self._sample_count % self.RESCAN_EVERY == 0):
            self._bind_session()

        session_found = (self._session_volume is not None
                         or self._session_meter is not None)
        muted = volume = session_peak = endpoint_peak = None
        if self._session_volume is not None:
            try:
                volume = float(self._session_volume.GetMasterVolume())
                muted = bool(self._session_volume.GetMute())
            except Exception:
                # Session died (app closed its stream) — force a re-bind.
                self._session_volume = self._session_meter = None
                session_found = False
        if self._session_meter is not None:
            try:
                session_peak = float(self._session_meter.GetPeakValue())
            except Exception:
                self._session_meter = None
        if self._endpoint_meter is not None:
            try:
                endpoint_peak = float(self._endpoint_meter.GetPeakValue())
            except Exception:
                self._endpoint_meter = None
        return TxProbeSample(session_found=session_found,
                             session_muted=muted, session_volume=volume,
                             session_peak=session_peak,
                             endpoint_peak=endpoint_peak)

    def close(self):
        """Drop COM references (they are released by comtypes GC, but
        dropping promptly keeps the endpoint free)."""
        self._session_volume = None
        self._session_meter = None
        self._endpoint_meter = None
