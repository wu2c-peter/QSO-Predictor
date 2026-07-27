# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""System Doctor (DIAGNOSTICS_SPEC.md roster item 5). Pure
fixture-driven checks plus the probe's pure parsing helpers — no
platform probing. Includes the Fast Startup ownership migration
contract: the check moved here from the Audio Doctor with its v2.6.0
check_id ("fast-startup", un-prefixed) intact."""

from diagnostics.doctors.system import SystemDoctor
from diagnostics.models import (AutostartEntry, DetectedApp, PowerInfo,
                                SNAPSHOT_SCHEMA_VERSION, Severity,
                                StationSnapshot, SystemSnapshot,
                                TccMicClient)
from diagnostics.probe_system import (_as_int, _effective_fast_startup,
                                      _parse_desktop_entry,
                                      _parse_pmset_prevention,
                                      _parse_pmset_sleep,
                                      _plan_display_name,
                                      _startup_disabled, _tcc_allowed,
                                      match_known_app)

DOCTOR = SystemDoctor()


def _snap(platform='windows', system=None, apps=None):
    return StationSnapshot(schema_version=SNAPSHOT_SCHEMA_VERSION,
                           taken_at_utc='2026-07-27T18:00:00Z',
                           platform=platform, system=system, apps=apps)


def _result(snap, check_id):
    results = DOCTOR.run(snap)
    matches = [r for r in results if r.check_id == check_id]
    assert len(matches) == 1, (
        f"expected exactly one {check_id!r}, got "
        f"{[r.check_id for r in results]}")
    return matches[0]


def _ids(snap):
    return {r.check_id for r in DOCTOR.run(snap)}


def _system(**kw):
    defaults = dict(autostart_entries=[], autostart_other_count=0)
    defaults.update(kw)
    return SystemSnapshot(**defaults)


# ---------------------------------------------------------------------------
# Doctor protocol / platform scoping
# ---------------------------------------------------------------------------

def test_doctor_declares_all_platforms_and_domains():
    assert DOCTOR.id == 'system'
    assert DOCTOR.platforms == frozenset({'windows', 'macos', 'linux'})
    assert DOCTOR.domains == frozenset({'system', 'apps'})


def test_missing_snapshot_reports_unknown():
    r = DOCTOR.run(_snap(system=None))
    assert len(r) == 1
    assert r[0].check_id == 'system/snapshot-missing'
    assert r[0].severity == Severity.UNKNOWN


def test_platform_scoping_no_foreign_concept_noise():
    """A Linux report must not carry Windows UNKNOWNs and vice versa —
    absent concepts are absent, not 'could not read'."""
    win = _ids(_snap('windows', _system()))
    mac = _ids(_snap('macos', _system()))
    lin = _ids(_snap('linux', _system()))
    assert 'fast-startup' in win and 'system/usb-selective-suspend' in win
    assert 'fast-startup' not in mac and 'fast-startup' not in lin
    assert 'system/mic-permission' in mac
    assert 'system/mic-permission' not in win
    assert 'system/serial-permissions' in lin
    assert 'system/serial-permissions' not in win
    # Autostart is universal.
    for ids in (win, mac, lin):
        assert 'system/autostart' in ids
    # Sleep applies where pmset/powercfg exist.
    assert 'system/sleep-timeout' in win and 'system/sleep-timeout' in mac
    assert 'system/sleep-timeout' not in lin


def test_every_check_always_returns_a_result_windows():
    """Contract 2: every applicable check emits, including OK."""
    snap = _snap('windows', _system(power=PowerInfo(
        fast_startup=False, usb_selective_suspend_ac=False,
        standby_ac_min=0)))
    assert _ids(snap) == {'fast-startup', 'system/usb-selective-suspend',
                          'system/sleep-timeout', 'system/autostart'}


# ---------------------------------------------------------------------------
# fast-startup (migrated from Audio Doctor — id and semantics stable)
# ---------------------------------------------------------------------------

def test_fast_startup_on_is_informational_with_restart_advice():
    snap = _snap('windows', _system(power=PowerInfo(fast_startup=True)))
    r = _result(snap, 'fast-startup')
    assert r.severity == Severity.INFO
    assert 'Restart' in r.detail


def test_fast_startup_off_is_ok():
    snap = _snap('windows', _system(power=PowerInfo(fast_startup=False)))
    assert _result(snap, 'fast-startup').severity == Severity.OK


def test_fast_startup_unreadable_is_unknown():
    snap = _snap('windows', _system(power=PowerInfo()))
    assert _result(snap, 'fast-startup').severity == Severity.UNKNOWN


def test_fast_startup_off_because_hibernation_disabled_says_so():
    snap = _snap('windows', _system(power=PowerInfo(
        fast_startup=False, hibernate_enabled=False)))
    r = _result(snap, 'fast-startup')
    assert r.severity == Severity.OK
    assert 'Hibernation is disabled' in r.detail


def test_effective_fast_startup_gated_by_hibernation():
    """powercfg /h off leaves HiberbootEnabled=1 behind; the effective
    state is off."""
    assert _effective_fast_startup(True, False) is False
    assert _effective_fast_startup(True, True) is True
    assert _effective_fast_startup(True, None) is True   # assume default
    assert _effective_fast_startup(False, True) is False
    assert _effective_fast_startup(None, True) is None


# ---------------------------------------------------------------------------
# system/usb-selective-suspend
# ---------------------------------------------------------------------------

def test_usb_suspend_enabled_is_info_with_dropout_wording():
    snap = _snap('windows', _system(power=PowerInfo(
        usb_selective_suspend_ac=True, usb_selective_suspend_dc=True,
        plan_name='Balanced')))
    r = _result(snap, 'system/usb-selective-suspend')
    assert r.severity == Severity.INFO
    assert 'AC power' in r.detail and 'battery' in r.detail
    assert 'Balanced' in r.detail
    assert r.fix     # actionable


def test_usb_suspend_disabled_is_ok():
    snap = _snap('windows', _system(power=PowerInfo(
        usb_selective_suspend_ac=False, usb_selective_suspend_dc=False)))
    assert (_result(snap, 'system/usb-selective-suspend').severity
            == Severity.OK)


def test_usb_suspend_unreadable_is_unknown():
    for power in (None, PowerInfo()):
        snap = _snap('windows', _system(power=power))
        assert (_result(snap, 'system/usb-selective-suspend').severity
                == Severity.UNKNOWN)


def test_usb_suspend_desktop_without_battery_value():
    """Desktops have no DC index — an AC-only reading still judges."""
    snap = _snap('windows', _system(power=PowerInfo(
        usb_selective_suspend_ac=True)))
    r = _result(snap, 'system/usb-selective-suspend')
    assert r.severity == Severity.INFO
    assert 'battery' not in r.detail.split('.')[0]  # not claimed enabled there


def test_usb_suspend_unreadable_ac_never_claims_disabled():
    """Review 2026-07-27: ac=None + dc=False must not produce an OK
    'disabled' verdict — the AC side (the one that matters on a shack
    PC) was never read."""
    snap = _snap('windows', _system(power=PowerInfo(
        usb_selective_suspend_dc=False)))
    r = _result(snap, 'system/usb-selective-suspend')
    assert r.severity == Severity.UNKNOWN
    assert 'disabled' in r.detail    # the battery reading is still shown


def test_usb_suspend_ok_names_only_the_sides_read():
    snap = _snap('windows', _system(power=PowerInfo(
        usb_selective_suspend_ac=False)))
    r = _result(snap, 'system/usb-selective-suspend')
    assert r.severity == Severity.OK
    assert 'AC power' in r.detail and 'battery' not in r.detail


# ---------------------------------------------------------------------------
# system/sleep-timeout
# ---------------------------------------------------------------------------

def test_sleep_never_is_ok():
    snap = _snap('windows', _system(power=PowerInfo(standby_ac_min=0)))
    assert _result(snap, 'system/sleep-timeout').severity == Severity.OK


def test_sleep_timeout_windows_is_literal_wall_clock_wording():
    snap = _snap('windows', _system(power=PowerInfo(standby_ac_min=30,
                                                    standby_dc_min=10)))
    r = _result(snap, 'system/sleep-timeout')
    assert r.severity == Severity.INFO
    assert '30 min' in r.detail and '10 min' in r.detail
    assert 'sleeps after' in r.detail


def test_sleep_timeout_macos_is_assertion_qualified():
    """Review 2026-07-27: 'sleep 1' is the modern macOS default and the
    timer is gated by power assertions — the check must NOT claim the
    session ends after 1 minute."""
    snap = _snap('macos', _system(power=PowerInfo(
        standby_ac_min=1, standby_dc_min=1,
        sleep_prevented_by='powerd, coreaudiod')))
    r = _result(snap, 'system/sleep-timeout')
    assert r.severity == Severity.INFO
    assert 'sleeps after' not in r.detail          # no literal claim
    assert 'assertion' in r.detail
    assert 'coreaudiod' in r.detail                # live evidence shown


def test_sleep_timeout_macos_without_prevention_evidence():
    snap = _snap('macos', _system(power=PowerInfo(standby_ac_min=20)))
    r = _result(snap, 'system/sleep-timeout')
    assert r.severity == Severity.INFO
    assert 'Nothing was preventing sleep' in r.detail


def test_sleep_unreadable_is_unknown():
    snap = _snap('macos', _system(power=None))
    assert _result(snap, 'system/sleep-timeout').severity == Severity.UNKNOWN


# ---------------------------------------------------------------------------
# system/mic-permission (macOS)
# ---------------------------------------------------------------------------

def test_mic_denied_for_detected_app_warns_and_names_it():
    snap = _snap('macos',
                 _system(mic_clients=[
                     TccMicClient('org.k1jt.wsjtx', allowed=False)]),
                 apps=[DetectedApp(name='WSJT-X', config_path=None)])
    r = _result(snap, 'system/mic-permission')
    assert r.severity == Severity.WARNING
    assert 'org.k1jt.wsjtx' in r.detail
    assert r.fix


def test_mic_denied_for_undetected_app_is_stale_info():
    """Review 2026-07-27: TCC keeps decisions for uninstalled apps
    forever — a denial for an app with no detected config must not
    alarm on every checkup."""
    snap = _snap('macos', _system(mic_clients=[
        TccMicClient('org.k1jt.wsjtx', allowed=False)]), apps=[])
    r = _result(snap, 'system/mic-permission')
    assert r.severity == Severity.INFO
    assert 'past' in r.detail.casefold()


def test_mic_allowed_is_ok():
    snap = _snap('macos', _system(mic_clients=[
        TccMicClient('org.k1jt.wsjtx', allowed=True)]))
    r = _result(snap, 'system/mic-permission')
    assert r.severity == Severity.OK
    assert 'org.k1jt.wsjtx' in r.detail


def test_mic_denied_warning_also_names_allowed_clients():
    snap = _snap('macos',
                 _system(mic_clients=[
                     TccMicClient('org.k1jt.wsjtx', allowed=True),
                     TccMicClient('com.jtdx.jtdx', allowed=False)]),
                 apps=[DetectedApp(name='JTDX', config_path=None)])
    r = _result(snap, 'system/mic-permission')
    assert r.severity == Severity.WARNING
    assert 'com.jtdx.jtdx' in r.detail
    assert 'org.k1jt.wsjtx' in r.detail    # the granted one is context


def test_mic_db_unreadable_is_unknown_with_manual_path():
    snap = _snap('macos', _system(mic_clients=None))
    r = _result(snap, 'system/mic-permission')
    assert r.severity == Severity.UNKNOWN
    assert 'Privacy & Security' in r.detail


def test_mic_no_recorded_decision_is_info():
    snap = _snap('macos', _system(mic_clients=[]),
                 apps=[DetectedApp(name='WSJT-X', config_path=None)])
    r = _result(snap, 'system/mic-permission')
    assert r.severity == Severity.INFO
    assert 'WSJT-X' in r.detail


# ---------------------------------------------------------------------------
# system/serial-permissions (Linux)
# ---------------------------------------------------------------------------

def test_serial_member_is_ok():
    snap = _snap('linux', _system(serial_member_groups=['dialout'],
                                  serial_groups=['dialout'],
                                  serial_devices=['/dev/ttyUSB0'],
                                  is_root=False))
    r = _result(snap, 'system/serial-permissions')
    assert r.severity == Severity.OK
    assert 'dialout' in r.detail


def test_serial_root_is_ok_without_group():
    """Review 2026-07-27: root bypasses file permissions — a Pi
    appliance running as root must not get a usermod WARNING."""
    snap = _snap('linux', _system(serial_member_groups=[],
                                  serial_groups=['dialout'],
                                  serial_devices=['/dev/ttyUSB0'],
                                  is_root=True))
    r = _result(snap, 'system/serial-permissions')
    assert r.severity == Severity.OK
    assert 'root' in r.detail


def test_serial_devices_present_but_not_member_warns_with_relogin():
    snap = _snap('linux', _system(serial_member_groups=[],
                                  serial_groups=['dialout'],
                                  serial_devices=['/dev/ttyUSB0'],
                                  is_root=False))
    r = _result(snap, 'system/serial-permissions')
    assert r.severity == Severity.WARNING
    assert '/dev/ttyUSB0' in r.detail
    assert 'likely' in r.detail            # udev ACLs not examined
    assert 'usermod' in r.fix and 'log out' in r.fix


def test_serial_no_devices_not_member_is_info():
    snap = _snap('linux', _system(serial_member_groups=[],
                                  serial_groups=['dialout'],
                                  serial_devices=[], is_root=False))
    assert (_result(snap, 'system/serial-permissions').severity
            == Severity.INFO)


def test_serial_groups_unreadable_is_unknown():
    snap = _snap('linux', _system(serial_member_groups=None,
                                  is_root=False))
    assert (_result(snap, 'system/serial-permissions').severity
            == Severity.UNKNOWN)


def test_serial_no_conventional_group_is_unknown():
    snap = _snap('linux', _system(serial_member_groups=[],
                                  serial_groups=[],
                                  serial_devices=['/dev/ttyUSB0'],
                                  is_root=False))
    assert (_result(snap, 'system/serial-permissions').severity
            == Severity.UNKNOWN)


def test_serial_uucp_system_uses_uucp_in_fix():
    """Arch-style systems say uucp, not dialout."""
    snap = _snap('linux', _system(serial_member_groups=[],
                                  serial_groups=['uucp'],
                                  serial_devices=['/dev/ttyACM0'],
                                  is_root=False))
    r = _result(snap, 'system/serial-permissions')
    assert 'uucp' in r.detail and 'uucp' in r.fix


# ---------------------------------------------------------------------------
# system/autostart
# ---------------------------------------------------------------------------

def test_autostart_ham_entries_listed_with_source():
    snap = _snap('windows', _system(
        autostart_entries=[AutostartEntry(name='GridTracker',
                                          source='HKCU Run',
                                          app='GridTracker',
                                          command='C:/gt/GridTracker.exe')],
        autostart_other_count=7))
    r = _result(snap, 'system/autostart')
    assert r.severity == Severity.INFO
    assert 'GridTracker' in r.detail and 'HKCU Run' in r.detail
    assert '7' in r.detail          # others counted, not listed


def test_autostart_disabled_entry_reported_as_not_starting():
    """Review 2026-07-27: a Task-Manager-disabled Run entry must not be
    described as 'starting automatically'."""
    snap = _snap('windows', _system(
        autostart_entries=[AutostartEntry(name='GridTracker',
                                          source='HKCU Run',
                                          app='GridTracker',
                                          command='C:/gt/GridTracker.exe',
                                          disabled=True)],
        autostart_other_count=0))
    r = _result(snap, 'system/autostart')
    assert 'DISABLED' in r.detail and 'will not start' in r.detail
    assert 'Starting automatically' not in r.detail


def test_autostart_singular_plural_grammar():
    one = _snap('windows', _system(autostart_entries=[],
                                   autostart_other_count=1))
    r = _result(one, 'system/autostart')
    assert '1 unrelated autostart entry' in r.detail
    assert 'entries' not in r.detail
    zero = _snap('linux', _system(autostart_entries=[],
                                  autostart_other_count=0))
    r0 = _result(zero, 'system/autostart')
    assert 'Plus 0' not in r0.detail and 'unrelated' not in r0.detail


def test_autostart_none_mentions_manual_starts_and_detected_apps():
    snap = _snap('windows',
                 _system(autostart_entries=[], autostart_other_count=3),
                 apps=[DetectedApp(name='WSJT-X', config_path=None)])
    r = _result(snap, 'system/autostart')
    assert r.severity == Severity.INFO
    assert 'manual' in r.detail
    assert 'WSJT-X was detected' in r.detail


def test_autostart_unreadable_is_unknown():
    snap = _snap('windows', _system(autostart_entries=None))
    assert _result(snap, 'system/autostart').severity == Severity.UNKNOWN


def test_autostart_macos_note_carried_into_detail():
    snap = _snap('macos', _system(
        autostart_entries=[], autostart_other_count=0,
        autostart_note='macOS Login Items are not visible to this probe'))
    r = _result(snap, 'system/autostart')
    assert 'Login Items' in r.detail


# ---------------------------------------------------------------------------
# Probe pure helpers
# ---------------------------------------------------------------------------

def test_match_known_app_matches_names_and_commands():
    assert match_known_app('GridTracker') == 'GridTracker'
    assert match_known_app('', 'C:/WSJT/bin/wsjtx.exe') == 'WSJT-X'
    assert match_known_app('org.k1jt.wsjtx') == 'WSJT-X'
    assert match_known_app('JS8Call') == 'JS8Call'
    assert match_known_app('Dropbox') == ''
    assert match_known_app('') == ''


def test_match_known_app_maclogger_not_mislabeled_as_aclog():
    """Review 2026-07-27: 'macloggerdx' contains 'aclog' — order in the
    pattern dict must give MacLoggerDX its own name."""
    assert match_known_app('com.dogparksoftware.MacLoggerDX') \
        == 'MacLoggerDX'


def test_match_known_app_spaced_shortcut_names():
    """Startup-folder .lnk files carry display names with spaces."""
    assert match_known_app('Ham Radio Deluxe') == 'Ham Radio Deluxe'


def test_match_known_app_hrd_needs_more_than_three_letters():
    """'hrd' alone substring-matches too much; only hrdlog-ish and full
    names count."""
    assert match_known_app('C:/Users/x/hrdlog_uploader.exe') \
        == 'Ham Radio Deluxe'
    assert match_known_app('shrdlu.exe') == ''


def test_tcc_allowed_both_schemas():
    # Modern auth_value: 0 denied, 1 unknown, 2 allowed, 3 limited.
    assert _tcc_allowed(0, 'auth_value') is False
    assert _tcc_allowed(1, 'auth_value') is None
    assert _tcc_allowed(2, 'auth_value') is True
    assert _tcc_allowed(3, 'auth_value') is True
    # Legacy allowed column: plain boolean.
    assert _tcc_allowed(0, 'allowed') is False
    assert _tcc_allowed(1, 'allowed') is True
    assert _tcc_allowed(None, 'auth_value') is None


def test_parse_pmset_sleep_sections():
    output = (
        "Battery Power:\n"
        " lidwake              1\n"
        " sleep                10\n"
        "AC Power:\n"
        " sleep                0\n"
        " displaysleep         20\n")
    assert _parse_pmset_sleep(output) == (0, 10)


def test_parse_pmset_sleep_desktop_single_section():
    output = ("Currently in use:\n"
              " sleep                45\n")
    ac, dc = _parse_pmset_sleep(output)
    assert ac == 45 and dc is None


def test_parse_pmset_ignores_displaysleep():
    ac, dc = _parse_pmset_sleep("AC Power:\n displaysleep 5\n")
    assert ac is None and dc is None


def test_plan_display_name_prefers_known_guid_over_indirect_string():
    assert _plan_display_name(
        '381b4222-f694-41f0-9685-ff5bb260df2e',
        '@%SystemRoot%\\system32\\powrprof.dll,-13') == 'Balanced'
    assert _plan_display_name('12345678-aaaa-bbbb-cccc-000000000000',
                              'My Custom Plan') == 'My Custom Plan'
    assert _plan_display_name('12345678-aaaa-bbbb-cccc-000000000000',
                              '@dll,-1') \
        == '12345678-aaaa-bbbb-cccc-000000000000'


def test_parse_desktop_entry_reads_main_section_only():
    text = ("[Desktop Entry]\n"
            "Name=GridTracker\n"
            "Exec=/usr/bin/gridtracker --hidden\n"
            "[Desktop Action other]\n"
            "Name=Other Name\n"
            "Exec=/bin/other\n")
    assert _parse_desktop_entry(text) == (
        'GridTracker', '/usr/bin/gridtracker --hidden', False)
    assert _parse_desktop_entry('') == ('', '', False)


def test_parse_desktop_entry_disabled_forms():
    assert _parse_desktop_entry(
        "[Desktop Entry]\nName=X\nHidden=true\n")[2] is True
    assert _parse_desktop_entry(
        "[Desktop Entry]\nName=X\nX-GNOME-Autostart-enabled=false\n")[2] \
        is True
    assert _parse_desktop_entry(
        "[Desktop Entry]\nName=X\nHidden=false\n")[2] is False


def test_parse_pmset_prevention():
    live = (" System-wide power settings:\n"
            "Currently in use:\n"
            " standby              1\n"
            " sleep                1 (sleep prevented by powerd, "
            "coreaudiod, coreaudiod)\n"
            " displaysleep         10\n")
    assert _parse_pmset_prevention(live) == 'powerd, coreaudiod'
    assert _parse_pmset_prevention("sleep 5\n") == ''


def test_startup_disabled_first_byte_parity():
    assert _startup_disabled(b'\x03' + b'\x00' * 11) is True
    assert _startup_disabled(b'\x02' + b'\x00' * 11) is False
    assert _startup_disabled(b'\x06' + b'\x00' * 11) is False
    assert _startup_disabled(None) is False       # absent = enabled
    assert _startup_disabled(b'') is False
    assert _startup_disabled('surprise') is False  # wrong type


def test_as_int_defensive_coercion():
    """Review 2026-07-27: OEM tools write setting indices in odd
    registry types — none may crash the probe."""
    assert _as_int(1) == 1
    assert _as_int('30') == 30
    assert _as_int(b'\x2c\x01\x00\x00') == 300
    assert _as_int('balanced') is None
    assert _as_int(None) is None
