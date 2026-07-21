# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""audio_doctor pure core — parsers, audit checks, TX-probe verdicts.

The registry blob layouts encoded here were verified against real
Windows exports during the July 2026 "WSJT-X silent TX after browser
audio" investigation; the check semantics freeze the failure modes that
incident surfaced (persisted per-app mixer mute, communications
ducking, default-role hijacking, stale re-enumerated endpoints).

Everything under test is stdlib-only — the Windows COM/registry access
lives in audio_doctor/probe_windows.py, which is deliberately NOT
imported here (it can't be, off-Windows).
"""

import struct

import pytest

from audio_doctor.checks import (
    DEFAULT_RIG_HINT, evaluate_tx_probe, is_rig_endpoint, run_checks,
    summarize_checks,
)
from audio_doctor.models import (
    AppSessionInfo, AudioFormat, AudioSnapshot, DataFlow, DeviceState,
    EndpointInfo, PersistedAppAudio, Severity, TxProbeSample, TxVerdict,
)
from audio_doctor.parsing import (
    APP_PROPERTY_STORE_PATHS, decode_propvariant, ducking_label,
    endpoint_guid, has_enum_prefix, parse_property_store_entry,
    parse_waveformat, strip_enum_prefix,
)


# ---------------------------------------------------------------------------
# Registry-format constants (external contracts)
# ---------------------------------------------------------------------------

def test_property_store_scans_both_registry_locations():
    """Win11 24H2 moved the per-app store out of the legacy IE key; a
    probe that only scans one path misses half the installed base."""
    assert len(APP_PROPERTY_STORE_PATHS) == 2
    assert any("Internet Explorer" in p for p in APP_PROPERTY_STORE_PATHS)
    assert any("Multimedia" in p for p in APP_PROPERTY_STORE_PATHS)


# ---------------------------------------------------------------------------
# Per-app PropertyStore entry names
# ---------------------------------------------------------------------------

WSJTX_ENTRY = (
    "{0.0.0.00000000}.{9152c723-4321-4321-4321-cba987654321}"
    "|\\Device\\HarddiskVolume3\\WSJT\\wsjtx\\bin\\wsjtx.exe"
    "%b{00000000-0000-0000-0000-000000000000}")


def test_parse_property_store_entry_splits_three_parts():
    endpoint_id, exe_path, guid = parse_property_store_entry(WSJTX_ENTRY)
    assert endpoint_id.startswith("{0.0.0.00000000}.")
    assert exe_path.endswith("wsjtx.exe")
    assert guid == "{00000000-0000-0000-0000-000000000000}"


@pytest.mark.parametrize("raw", [
    "",                                # empty
    "no separators at all",            # not an app entry
    "{id}|no-session-guid-marker",     # missing %b
    "|\\path\\x.exe%b{guid}",          # empty endpoint id
])
def test_parse_property_store_entry_rejects_non_app_values(raw):
    assert parse_property_store_entry(raw) is None


def test_persisted_exe_name_normalizes_nt_path():
    p = PersistedAppAudio(endpoint_id="{e}",
                          exe_path="\\Device\\HarddiskVolume3\\WSJT\\WSJTX.EXE")
    assert p.exe_name == "wsjtx.exe"


# ---------------------------------------------------------------------------
# Serialized PROPVARIANT blobs
# ---------------------------------------------------------------------------

def propvariant(vt, payload):
    """Build a serialized-PROPVARIANT registry blob: variant-type DWORD
    at offset 0, payload at offset 8 (as observed in real exports)."""
    return struct.pack("<I", vt) + b"\x00\x00\x00\x00" + payload


@pytest.mark.parametrize("blob, expected", [
    # VT_R4 volume scalars — 1.0 is the exact blob from a real export
    (propvariant(4, struct.pack("<f", 1.0)), 1.0),
    (propvariant(4, struct.pack("<f", 0.0)), 0.0),
    (propvariant(4, struct.pack("<f", 0.25)), 0.25),
    # VT_BOOL mute — VARIANT_TRUE is 0xFFFF (-1 as int16)
    (propvariant(11, b"\xff\xff"), True),
    (propvariant(11, b"\x00\x00"), False),
    # VT_I4 / VT_UI4
    (propvariant(3, struct.pack("<i", -2)), -2),
    (propvariant(19, struct.pack("<I", 7)), 7),
], ids=["r4-1.0", "r4-0.0", "r4-0.25", "bool-true", "bool-false",
        "i4", "ui4"])
def test_decode_propvariant_scalars(blob, expected):
    value = decode_propvariant(blob)
    assert value == expected
    assert type(value) is type(expected)


@pytest.mark.parametrize("blob", [
    b"",                                   # empty
    b"\x04\x00\x00\x00",                   # truncated before payload
    propvariant(0x2004, b"\x00" * 8),      # vector/array — not scalar
    propvariant(0x1F, b"\x00" * 8),        # VT_LPWSTR — unsupported here
], ids=["empty", "truncated", "vector", "lpwstr"])
def test_decode_propvariant_rejects_unusable_blobs(blob):
    assert decode_propvariant(blob) is None


# ---------------------------------------------------------------------------
# WAVEFORMATEX blobs
# ---------------------------------------------------------------------------

def waveformatex(tag=1, channels=2, rate=48000, bits=16):
    block_align = channels * bits // 8
    return struct.pack("<HHIIHH", tag, channels, rate,
                       rate * block_align, block_align, bits)


def test_parse_waveformat_at_offset_zero():
    fmt = parse_waveformat(waveformatex())
    assert fmt == AudioFormat(channels=2, sample_rate_hz=48000,
                              bits_per_sample=16)


def test_parse_waveformat_skips_serialized_property_header():
    """The registry blob prefixes the struct with a variable-size
    serialized-property header — the parser must find the struct by
    invariant-scanning, not by a hardcoded offset."""
    blob = b"\x41\x00\x00\x00\x28\x00\x00\x00" + waveformatex(
        tag=0xFFFE, channels=2, rate=44100, bits=16)
    fmt = parse_waveformat(blob)
    assert fmt is not None
    assert fmt.sample_rate_hz == 44100


@pytest.mark.parametrize("blob", [
    b"",
    b"\x00" * 64,                                      # all zeros
    waveformatex(rate=999),                            # implausible rate
    waveformatex()[:10],                               # truncated
    struct.pack("<HHIIHH", 1, 2, 48000, 12345, 4, 16), # inconsistent avg rate
], ids=["empty", "zeros", "bad-rate", "truncated", "inconsistent"])
def test_parse_waveformat_rejects_garbage(blob):
    assert parse_waveformat(blob) is None


# ---------------------------------------------------------------------------
# Name / ID helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, stripped, renamed", [
    ("USB Audio CODEC", "USB Audio CODEC", False),
    ("2- USB Audio CODEC", "USB Audio CODEC", True),
    ("12 - USB Audio CODEC", "USB Audio CODEC", True),
    # Friendly names put the prefix inside the parenthesized part
    ("Speakers (2- USB Audio CODEC)", "Speakers (USB Audio CODEC)", True),
    ("Speakers (USB Audio CODEC)", "Speakers (USB Audio CODEC)", False),
    # Digits followed by '-' elsewhere must not trip the detector
    ("Realtek HD Audio 2nd output", "Realtek HD Audio 2nd output", False),
    ("", "", False),
    # Review 2026-07: digit+dash WITHOUT trailing space is a legitimate
    # name, not a Windows re-enumeration prefix — must pass unmangled
    ("2-Channel USB Codec", "2-Channel USB Codec", False),
    ("Line Out (4-port Hub Audio)", "Line Out (4-port Hub Audio)", False),
])
def test_enum_prefix_detection(name, stripped, renamed):
    assert strip_enum_prefix(name) == stripped
    assert has_enum_prefix(name) is renamed


def test_endpoint_guid_extraction():
    full = "{0.0.0.00000000}.{9152C723-1111-2222-3333-CBA987654321}"
    assert endpoint_guid(full) == "{9152c723-1111-2222-3333-cba987654321}"
    assert endpoint_guid("not an endpoint id") is None


def test_ducking_labels_cover_all_documented_values():
    for v in range(4):
        assert "unknown" not in ducking_label(v)
    assert ducking_label(None) == "unreadable"
    assert "unknown value 9" == ducking_label(9)


# ---------------------------------------------------------------------------
# Static audit checks
# ---------------------------------------------------------------------------

CODEC_RENDER = EndpointInfo(
    id="{0.0.0.00000000}.{aaaa0000-0000-0000-0000-000000000001}",
    name="Speakers (USB Audio CODEC)", flow=DataFlow.RENDER,
    state=DeviceState.ACTIVE,
    fmt=AudioFormat(channels=2, sample_rate_hz=48000, bits_per_sample=16))

CODEC_CAPTURE = EndpointInfo(
    id="{0.0.1.00000000}.{aaaa0000-0000-0000-0000-000000000002}",
    name="Microphone (USB Audio CODEC)", flow=DataFlow.CAPTURE,
    state=DeviceState.ACTIVE,
    fmt=AudioFormat(channels=1, sample_rate_hz=48000, bits_per_sample=16))

SPEAKERS = EndpointInfo(
    id="{0.0.0.00000000}.{bbbb0000-0000-0000-0000-000000000003}",
    name="Speakers (Realtek HD Audio)", flow=DataFlow.RENDER,
    state=DeviceState.ACTIVE)

MONITOR = EndpointInfo(
    id="{0.0.0.00000000}.{cccc0000-0000-0000-0000-000000000004}",
    name="DELL U2720Q (NVIDIA High Definition Audio)", flow=DataFlow.RENDER,
    state=DeviceState.ACTIVE)


def healthy_snapshot(**overrides):
    """The recommended configuration: codec active, PC speakers holding
    both default roles, ducking off, no persisted silencing."""
    snap = AudioSnapshot(
        endpoints=[CODEC_RENDER, CODEC_CAPTURE, SPEAKERS, MONITOR],
        default_render_id=SPEAKERS.id,
        default_render_comm_id=SPEAKERS.id,
        default_capture_id="{0.0.1.00000000}.{dddd0000-0000-0000-0000-000000000005}",
        default_capture_comm_id="{0.0.1.00000000}.{dddd0000-0000-0000-0000-000000000005}",
        sessions=[],
        persisted=[],
        ducking_preference=3,
        fast_startup=False,
        sound_scheme=".None",
    )
    for key, value in overrides.items():
        setattr(snap, key, value)
    return snap


def result_by_id(results, check_id):
    matches = [r for r in results if r.check_id == check_id]
    assert len(matches) == 1, f"expected exactly one {check_id!r} result"
    return matches[0]


def test_is_rig_endpoint_matches_renamed_duplicate():
    renamed = EndpointInfo(id="{x}", name="Speakers (2- USB Audio CODEC)",
                           flow=DataFlow.RENDER, state=DeviceState.ACTIVE)
    assert is_rig_endpoint(renamed, DEFAULT_RIG_HINT)
    assert not is_rig_endpoint(SPEAKERS, DEFAULT_RIG_HINT)


def test_healthy_snapshot_has_no_warnings_or_failures():
    results = run_checks(healthy_snapshot())
    assert len(results) == 11
    worst = max(r.severity for r in results)
    assert worst <= Severity.INFO, [
        (r.check_id, r.severity, r.detail) for r in results
        if r.severity > Severity.INFO]
    severity, text = summarize_checks(results)
    assert text == "All audio checks passed"


def test_missing_codec_fails_rig_endpoint_check():
    snap = healthy_snapshot(endpoints=[SPEAKERS, MONITOR])
    r = result_by_id(run_checks(snap), "rig-endpoint")
    assert r.severity == Severity.FAIL


def test_unplugged_codec_fails_rig_endpoint_check():
    dead = EndpointInfo(id=CODEC_RENDER.id, name=CODEC_RENDER.name,
                        flow=DataFlow.RENDER, state=DeviceState.UNPLUGGED)
    snap = healthy_snapshot(endpoints=[dead, SPEAKERS])
    r = result_by_id(run_checks(snap), "rig-endpoint")
    assert r.severity == Severity.FAIL


def test_stale_duplicate_codec_endpoints_warn():
    """The port-move signature: an active '2- USB Audio CODEC' plus the
    original endpoint lingering as Not present."""
    ghost = EndpointInfo(
        id="{0.0.0.00000000}.{eeee0000-0000-0000-0000-000000000006}",
        name="Speakers (USB Audio CODEC)", flow=DataFlow.RENDER,
        state=DeviceState.NOTPRESENT)
    live = EndpointInfo(
        id="{0.0.0.00000000}.{ffff0000-0000-0000-0000-000000000007}",
        name="Speakers (2- USB Audio CODEC)", flow=DataFlow.RENDER,
        state=DeviceState.ACTIVE,
        fmt=AudioFormat(channels=2, sample_rate_hz=48000, bits_per_sample=16))
    snap = healthy_snapshot(endpoints=[ghost, live, SPEAKERS])
    r = result_by_id(run_checks(snap), "stale-duplicates")
    assert r.severity == Severity.WARNING
    assert "Not present" in r.detail


def test_single_offline_codec_is_not_a_stale_duplicate():
    """Review 2026-07: rig switched off = one UNPLUGGED endpoint. That's
    the rig-endpoint check's FAIL, not a port-move duplicate diagnosis."""
    dead = EndpointInfo(id=CODEC_RENDER.id, name=CODEC_RENDER.name,
                        flow=DataFlow.RENDER, state=DeviceState.UNPLUGGED)
    snap = healthy_snapshot(endpoints=[dead, SPEAKERS])
    r = result_by_id(run_checks(snap), "stale-duplicates")
    assert r.severity != Severity.WARNING


def test_codec_as_default_device_warns():
    snap = healthy_snapshot(default_render_id=CODEC_RENDER.id)
    r = result_by_id(run_checks(snap), "default-device")
    assert r.severity == Severity.WARNING


def test_codec_as_communication_device_warns():
    """The July 2026 incident config: comm role on the codec arms
    ducking against WSJT-X whenever a browser opens the codec mic."""
    snap = healthy_snapshot(default_render_comm_id=CODEC_RENDER.id)
    r = result_by_id(run_checks(snap), "default-communication")
    assert r.severity == Severity.WARNING
    assert "ducking" in r.detail


@pytest.mark.parametrize("pref, severity", [
    (3, Severity.OK),          # Do nothing
    (1, Severity.WARNING),     # Windows default: reduce 80%
    (0, Severity.WARNING),     # Mute all
    (None, Severity.UNKNOWN),  # unreadable
])
def test_ducking_check(pref, severity):
    snap = healthy_snapshot(ducking_preference=pref)
    assert result_by_id(run_checks(snap), "ducking").severity == severity


def test_wrong_sample_rate_warns():
    cd = EndpointInfo(id=CODEC_RENDER.id, name=CODEC_RENDER.name,
                      flow=DataFlow.RENDER, state=DeviceState.ACTIVE,
                      fmt=AudioFormat(channels=2, sample_rate_hz=44100,
                                      bits_per_sample=16))
    snap = healthy_snapshot(endpoints=[cd, CODEC_CAPTURE, SPEAKERS])
    r = result_by_id(run_checks(snap), "tx-format")
    assert r.severity == Severity.WARNING
    assert "44100" in r.detail


def test_persisted_mute_for_wsjtx_on_codec_is_a_failure():
    """THE incident: registry-persisted per-app mute, invisible in
    WSJT-X, survives reboots, silences TX only."""
    snap = healthy_snapshot(persisted=[
        PersistedAppAudio(endpoint_id=CODEC_RENDER.id,
                          exe_path="\\Device\\HarddiskVolume3\\wsjtx.exe",
                          volume=1.0, muted=True)])
    r = result_by_id(run_checks(snap), "app-mixer-persisted")
    assert r.severity == Severity.FAIL
    assert "wsjtx.exe" in r.detail


def test_persisted_near_zero_volume_is_a_failure():
    snap = healthy_snapshot(persisted=[
        PersistedAppAudio(endpoint_id=CODEC_RENDER.id,
                          exe_path="\\Device\\HarddiskVolume3\\wsjtx.exe",
                          volume=0.0, muted=False)])
    r = result_by_id(run_checks(snap), "app-mixer-persisted")
    assert r.severity == Severity.FAIL


def test_persisted_entries_on_other_devices_are_ignored():
    snap = healthy_snapshot(persisted=[
        PersistedAppAudio(endpoint_id=SPEAKERS.id,
                          exe_path="\\Device\\HarddiskVolume3\\wsjtx.exe",
                          volume=0.0, muted=True),
        PersistedAppAudio(endpoint_id=CODEC_RENDER.id,
                          exe_path="\\Device\\HarddiskVolume3\\chrome.exe",
                          volume=0.0, muted=True)])
    r = result_by_id(run_checks(snap), "app-mixer-persisted")
    assert r.severity == Severity.OK


def test_unreadable_persisted_store_reports_unknown():
    snap = healthy_snapshot(persisted=None)
    r = result_by_id(run_checks(snap), "app-mixer-persisted")
    assert r.severity == Severity.UNKNOWN


def test_live_session_muted_on_codec_is_a_failure():
    snap = healthy_snapshot(sessions=[
        AppSessionInfo(endpoint_id=CODEC_RENDER.id,
                       endpoint_name=CODEC_RENDER.name,
                       process_name="wsjtx.exe", pid=4242,
                       volume=1.0, muted=True, active=True)])
    r = result_by_id(run_checks(snap), "app-live-session")
    assert r.severity == Severity.FAIL


def test_live_session_on_wrong_device_warns():
    snap = healthy_snapshot(sessions=[
        AppSessionInfo(endpoint_id=MONITOR.id, endpoint_name=MONITOR.name,
                       process_name="wsjtx.exe", pid=4242,
                       volume=1.0, muted=False, active=True)])
    r = result_by_id(run_checks(snap), "app-live-session")
    assert r.severity == Severity.WARNING
    assert "DELL" in r.detail


def test_expired_session_on_wrong_device_does_not_warn():
    """Review 2026-07: WASAPI's enumerator retains expired sessions from
    long-closed streams (e.g. before the user fixed their routing) —
    only ACTIVE sessions elsewhere indicate a routing problem."""
    snap = healthy_snapshot(sessions=[
        AppSessionInfo(endpoint_id=MONITOR.id, endpoint_name=MONITOR.name,
                       process_name="wsjtx.exe", pid=4242,
                       volume=1.0, muted=False, active=False)])
    r = result_by_id(run_checks(snap), "app-live-session")
    assert r.severity == Severity.INFO


def test_summarize_unknown_only_does_not_claim_zero_issues():
    """Review 2026-07: one unreadable registry key on an otherwise
    healthy box must not produce 'UNKNOWN: 0 issues found'."""
    results = run_checks(healthy_snapshot(fast_startup=None))
    severity, text = summarize_checks(results)
    assert severity == Severity.UNKNOWN
    assert "could not run" in text


def test_system_sounds_with_codec_default_warns():
    snap = healthy_snapshot(sound_scheme=".Default",
                            default_render_id=CODEC_RENDER.id)
    r = result_by_id(run_checks(snap), "sound-scheme")
    assert r.severity == Severity.WARNING


def test_fast_startup_is_informational():
    snap = healthy_snapshot(fast_startup=True)
    r = result_by_id(run_checks(snap), "fast-startup")
    assert r.severity == Severity.INFO
    assert "Restart" in r.detail


# ---------------------------------------------------------------------------
# TX-probe verdicts
# ---------------------------------------------------------------------------

def samples(n=12, **kwargs):
    return [TxProbeSample(**kwargs) for _ in range(n)]


def test_probe_too_few_samples_is_inconclusive():
    got = evaluate_tx_probe(samples(3, session_found=True, session_peak=0.5,
                                    endpoint_peak=0.5))
    assert got == TxVerdict.INCONCLUSIVE


def test_probe_no_session_anywhere():
    assert evaluate_tx_probe(samples(session_found=False)) == TxVerdict.NO_SESSION


def test_probe_muted_session_beats_peak_evidence():
    got = evaluate_tx_probe(samples(session_found=True, session_muted=True,
                                    session_volume=1.0, session_peak=0.5,
                                    endpoint_peak=0.5))
    assert got == TxVerdict.MUTED_IN_MIXER


def test_probe_near_zero_mixer_volume():
    got = evaluate_tx_probe(samples(session_found=True, session_muted=False,
                                    session_volume=0.02, session_peak=0.5))
    assert got == TxVerdict.MIXER_VOLUME_LOW


def test_probe_app_producing_silence():
    got = evaluate_tx_probe(samples(session_found=True, session_muted=False,
                                    session_volume=1.0, session_peak=0.0,
                                    endpoint_peak=0.0))
    assert got == TxVerdict.APP_NOT_EMITTING


def test_probe_samples_not_reaching_endpoint():
    got = evaluate_tx_probe(samples(session_found=True, session_muted=False,
                                    session_volume=1.0, session_peak=0.4,
                                    endpoint_peak=0.0))
    assert got == TxVerdict.NOT_REACHING_ENDPOINT


def test_probe_audio_flowing():
    got = evaluate_tx_probe(samples(session_found=True, session_muted=False,
                                    session_volume=1.0, session_peak=0.4,
                                    endpoint_peak=0.4))
    assert got == TxVerdict.AUDIO_FLOWING
    assert not got.is_problem


def test_probe_endpoint_meter_alone_suffices():
    """Session meter unavailable (None) — endpoint meter still judges."""
    got = evaluate_tx_probe(samples(session_found=True, session_muted=False,
                                    session_volume=1.0, session_peak=None,
                                    endpoint_peak=0.4))
    assert got == TxVerdict.AUDIO_FLOWING


def test_probe_no_meters_at_all_is_inconclusive():
    got = evaluate_tx_probe(samples(session_found=True, session_muted=False,
                                    session_volume=1.0))
    assert got == TxVerdict.INCONCLUSIVE


def test_every_problem_verdict_carries_display_text():
    for verdict in TxVerdict:
        assert verdict.headline
        assert verdict.explanation
        if verdict.is_problem:
            assert verdict.fix
