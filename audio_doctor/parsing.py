"""
Binary and registry-format parsers for the Audio Doctor.

Pure stdlib. Everything here decodes bytes/strings that probe_windows
reads from the registry — kept separate so the decoding (the part most
likely to harbor bugs) is unit-testable off-Windows with byte fixtures.

Format references (verified July 2026):
- Per-app volume store: HKCU subkeys named "<hash>_<n>" whose default
  value is "<endpoint-id>|<NT exe path>%b<session guid>", with volume /
  mute in a nested {219ED5A0-...} key as serialized-PROPVARIANT blobs
  (variant type DWORD at offset 0, payload at offset 8).
- Endpoint Default Format: PKEY_AudioEngine_DeviceFormat property blob
  wrapping a WAVEFORMATEX(TENSIBLE) struct.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import re
import struct
from typing import Optional, Tuple

from audio_doctor.models import AudioFormat


# =============================================================================
# Registry locations (constants live here so tests can pin them)
# =============================================================================

# Per-app persisted volume/mute/device store. Windows 11 24H2 moved it out
# of the legacy Internet Explorer key — a probe must scan both.
APP_PROPERTY_STORE_PATHS = (
    r"Software\Microsoft\Internet Explorer\LowRegistry\Audio"
    r"\PolicyConfig\PropertyStore",                              # Vista–Win11 23H2
    r"Software\Microsoft\Multimedia\Audio\PolicyConfig\PropertyStore",  # Win11 24H2+
)

# Nested subkey (under each per-app entry) holding the volume/mute blobs.
APP_VOLUME_SUBKEY = "{219ED5A0-9CBF-4F3A-B927-37C9E5C5F14F}"
APP_VOLUME_VALUE = "3"   # VT_R4 master volume scalar
APP_MUTE_VALUE = "5"     # VT_BOOL

# Communications-tab ducking preference ("When Windows detects
# communications activity"). Value absent = Windows default (reduce 80%).
DUCKING_KEY_PATH = r"Software\Microsoft\Multimedia\Audio"
DUCKING_VALUE_NAME = "UserDuckingPreference"
DUCKING_DEFAULT = 1
DUCKING_DO_NOTHING = 3

# NOTE: this mapping matches the mmsys.cpl option order and the majority of
# published sources, but one Microsoft Q&A thread orders it differently —
# verify empirically on a real Windows box before trusting 0/1/2 apart.
DUCKING_LABELS = {
    0: "Mute all other sounds",
    1: "Reduce other sounds by 80% (Windows default)",
    2: "Reduce other sounds by 50%",
    3: "Do nothing",
}

# Endpoint inventory (HKLM). DeviceState DWORD + Properties per endpoint.
MMDEVICES_RENDER_PATH = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render")
MMDEVICES_CAPTURE_PATH = (
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture")

# PKEY_AudioEngine_DeviceFormat — the user-selected shared-mode format
# (Advanced tab "Default Format"); OEMFormat is the driver default.
PKEY_DEVICE_FORMAT = "{f19f064d-082c-4e27-bc73-6882a1bb8e4c},0"

# Fast Startup ("hiberboot"). 1 = shutdown does NOT reinit drivers.
FAST_STARTUP_KEY_PATH = r"SYSTEM\CurrentControlSet\Control\Session Manager\Power"
FAST_STARTUP_VALUE_NAME = "HiberbootEnabled"

# Active system sound scheme; '.None' is the "No Sounds" scheme.
SOUND_SCHEME_KEY_PATH = r"AppEvents\Schemes"


# =============================================================================
# Per-app PropertyStore entry names
# =============================================================================

def parse_property_store_entry(raw: str) -> Optional[Tuple[str, str, str]]:
    """Split a per-app PropertyStore entry value into its three parts.

    Format: "<endpoint-id>|<NT path to exe>%b<session guid>", e.g.
    "{0.0.0.00000000}.{9152...}|\\Device\\HarddiskVolume3\\WSJT\\wsjtx.exe%b{0000...}"

    Returns (endpoint_id, exe_path, session_guid) or None if the value
    doesn't look like an app entry (some entries hold other role data).
    """
    if not raw or "|" not in raw:
        return None
    endpoint_id, rest = raw.split("|", 1)
    if "%b" not in rest:
        return None
    exe_path, session_guid = rest.split("%b", 1)
    if not endpoint_id or not exe_path:
        return None
    return endpoint_id, exe_path, session_guid


# =============================================================================
# Serialized PROPVARIANT blobs (per-app volume / mute values)
# =============================================================================

_VT_I4 = 3
_VT_R4 = 4
_VT_BOOL = 11
_VT_UI4 = 19

def decode_propvariant(data: bytes):
    """Decode a scalar serialized-PROPVARIANT registry blob.

    Layout: variant type in the DWORD at offset 0, payload at offset 8.
    Returns float (VT_R4), bool (VT_BOOL), int (VT_I4/VT_UI4), or None
    for anything else (vectors, truncated blobs).
    """
    if not data or len(data) < 10:   # 8-byte header + smallest payload
        return None
    vt = struct.unpack_from("<I", data, 0)[0] & 0xFFFF
    if vt == _VT_BOOL:
        # VARIANT_BOOL: 0 = FALSE, anything else (canonically -1) = TRUE
        return struct.unpack_from("<h", data, 8)[0] != 0
    if len(data) < 12:
        return None
    if vt == _VT_R4:
        return struct.unpack_from("<f", data, 8)[0]
    if vt == _VT_I4:
        return struct.unpack_from("<i", data, 8)[0]
    if vt == _VT_UI4:
        return struct.unpack_from("<I", data, 8)[0]
    return None


# =============================================================================
# WAVEFORMATEX blobs (endpoint Default Format)
# =============================================================================

_VALID_FORMAT_TAGS = {0x0001, 0x0003, 0xFFFE}   # PCM, IEEE float, EXTENSIBLE
_VALID_BITS = {8, 16, 24, 32, 64}

def parse_waveformat(data: bytes) -> Optional[AudioFormat]:
    """Find and decode a WAVEFORMATEX inside a registry property blob.

    The PKEY_AudioEngine_DeviceFormat value wraps the struct in a
    serialized-property header whose exact size varies by Windows
    version, so rather than hardcoding an offset we scan for a position
    where all the WAVEFORMATEX invariants hold simultaneously
    (nBlockAlign == nChannels * wBitsPerSample / 8 and
    nAvgBytesPerSec == nSamplesPerSec * nBlockAlign) — 14 bytes of
    mutually-consistent fields make false positives implausible.
    """
    if not data or len(data) < 16:
        return None
    for offset in range(0, len(data) - 15, 2):
        tag, channels = struct.unpack_from("<HH", data, offset)
        if tag not in _VALID_FORMAT_TAGS or not 1 <= channels <= 8:
            continue
        rate, avg_bytes = struct.unpack_from("<II", data, offset + 4)
        if not 8000 <= rate <= 384000:
            continue
        block_align, bits = struct.unpack_from("<HH", data, offset + 12)
        if bits not in _VALID_BITS:
            continue
        if block_align != channels * bits // 8:
            continue
        if avg_bytes != rate * block_align:
            continue
        return AudioFormat(channels=channels, sample_rate_hz=rate,
                           bits_per_sample=bits)
    return None


# =============================================================================
# Endpoint name / ID helpers
# =============================================================================

# Windows prefixes re-enumerated duplicates with "N- ". In endpoint
# friendly names the prefix lands on the interface part, which may sit
# inside parentheses: "Speakers (2- USB Audio CODEC)". The trailing
# whitespace is REQUIRED (\s+): the real Windows prefix is always
# "N- " / "N - ", and requiring it keeps legitimate names like
# "2-Channel USB Codec" or "(4-port Hub Audio)" from being mangled.
_ENUM_PREFIX = re.compile(r"(^|\()\s*\d+\s*-\s+")

def strip_enum_prefix(name: str) -> str:
    """Remove the "N- " duplicate-device prefix Windows adds on
    re-enumeration, so "2- USB Audio CODEC" (or
    "Speakers (2- USB Audio CODEC)") compares equal to the original."""
    return _ENUM_PREFIX.sub(r"\1", name or "")


def has_enum_prefix(name: str) -> bool:
    """True if the name carries a re-enumeration prefix — evidence the
    device has been treated as 'new' by Windows at least once."""
    return bool(_ENUM_PREFIX.search(name or ""))


_ENDPOINT_GUID = re.compile(r"\{[0-9a-fA-F-]{36}\}$")

def endpoint_guid(endpoint_id: str) -> Optional[str]:
    """Extract the trailing endpoint GUID from a full MMDevice ID.
    "{0.0.0.00000000}.{9152...-...}" → "{9152...-...}" (lowercased).
    The registry keys under MMDevices\\Audio use just this GUID."""
    m = _ENDPOINT_GUID.search(endpoint_id or "")
    return m.group(0).lower() if m else None


def ducking_label(value: Optional[int]) -> str:
    if value is None:
        return "unreadable"
    return DUCKING_LABELS.get(value, f"unknown value {value}")
