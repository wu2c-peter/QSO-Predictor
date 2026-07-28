# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Serial/CAT Doctor (DIAGNOSTICS_SPEC.md roster item 4). Pure
fixture-driven checks plus the probe's pure helpers — no port is ever
opened anywhere in this subsystem. The must-not-flag case throughout:
WSJT-X keeps a placeholder CATSerialPort (Bluetooth-Incoming-Port) even
with Rig=None, and PTTport means nothing under VOX keying."""

from pathlib import Path

from diagnostics.doctors.serial import (SerialDoctor, _device_like,
                                        _expected_ports, _find_port,
                                        _normalize_port_name)
from diagnostics.models import (DetectedApp, SNAPSHOT_SCHEMA_VERSION,
                                SerialPortInfo, SerialSnapshot, Severity,
                                StationSnapshot, UsbSerialAdapter)
from diagnostics.probe_serial import (_display_string,
                                      _macos_chip_from_device_name,
                                      _parse_system_profiler_usb,
                                      _vidpid_from_text,
                                      _win_adapters_from_raw,
                                      _win_ports_from_raw, identify_chip,
                                      identify_device_label,
                                      is_macos_pseudo_port)

DOCTOR = SerialDoctor()


def _snap(platform='windows', serial=None, apps=None):
    return StationSnapshot(schema_version=SNAPSHOT_SCHEMA_VERSION,
                           taken_at_utc='2026-07-27T20:00:00Z',
                           platform=platform, serial=serial, apps=apps)


def _app(name='WSJT-X', rig_name='Kenwood TS-590S', cat_port='COM5',
         ptt_method='CAT', ptt_port='', is_running=False, **kw):
    return DetectedApp(name=name, config_path=Path(f'/cfg/{name}.ini'),
                       rig_name=rig_name, cat_port=cat_port,
                       ptt_method=ptt_method, ptt_port=ptt_port,
                       is_running=is_running, **kw)


def _result(snap, check_id):
    results = DOCTOR.run(snap)
    matches = [r for r in results if r.check_id == check_id]
    assert len(matches) == 1, (
        f"expected exactly one {check_id!r}, got "
        f"{[r.check_id for r in results]}")
    return matches[0]


# ---------------------------------------------------------------------------
# Doctor protocol
# ---------------------------------------------------------------------------

def test_doctor_declares_platforms_and_domains():
    assert DOCTOR.id == 'serial'
    assert DOCTOR.platforms == frozenset({'windows', 'macos', 'linux'})
    assert DOCTOR.domains == frozenset({'serial', 'apps'})


def test_missing_snapshot_reports_unknown():
    results = DOCTOR.run(_snap(serial=None))
    assert len(results) == 1
    assert results[0].check_id == 'serial/snapshot-missing'
    assert results[0].severity == Severity.UNKNOWN


def test_driver_problem_check_is_windows_only():
    serial = SerialSnapshot(ports=[SerialPortInfo(device='/dev/ttyUSB0')])
    ids_linux = {r.check_id for r in DOCTOR.run(_snap('linux', serial))}
    ids_win = {r.check_id for r in DOCTOR.run(_snap('windows', serial))}
    assert 'serial/driver-problem' not in ids_linux
    assert 'serial/driver-problem' in ids_win


# ---------------------------------------------------------------------------
# serial/inventory
# ---------------------------------------------------------------------------

def test_inventory_empty_is_info_not_warning():
    snap = _snap(serial=SerialSnapshot(ports=[]))
    r = _result(snap, 'serial/inventory')
    assert r.severity == Severity.INFO
    assert 'VOX' in r.detail


def test_inventory_describes_chip_driver_and_holder():
    snap = _snap('linux', SerialSnapshot(ports=[SerialPortInfo(
        device='/dev/ttyUSB0', vid=0x10C4, pid=0xEA60,
        chip='CP210x (Silicon Labs)', device_label='Digirig',
        driver_name='cp210x', in_use_by='wsjtx')]))
    r = _result(snap, 'serial/inventory')
    assert r.severity == Severity.OK
    for text in ('/dev/ttyUSB0', 'Digirig', 'CP210x', 'cp210x',
                 'held by wsjtx'):
        assert text in r.detail


def test_inventory_carries_platform_note():
    snap = _snap(serial=SerialSnapshot(
        ports=[SerialPortInfo(device='COM3')],
        note='holder detection unavailable'))
    assert 'holder detection unavailable' in \
        _result(snap, 'serial/inventory').detail


# ---------------------------------------------------------------------------
# serial/configured-port-exists
# ---------------------------------------------------------------------------

def test_rig_none_placeholder_port_is_not_expected():
    """The real config on the dev Mac: Rig=None with
    CATSerialPort=/dev/cu.Bluetooth-Incoming-Port and PTTMethod=VOX.
    Nothing must be flagged."""
    apps = [_app(rig_name='None',
                 cat_port='/dev/cu.Bluetooth-Incoming-Port',
                 ptt_method='VOX',
                 ptt_port='/dev/cu.Bluetooth-Incoming-Port')]
    snap = _snap('macos', SerialSnapshot(ports=[]), apps)
    r = _result(snap, 'serial/configured-port-exists')
    assert r.severity == Severity.INFO
    assert 'No detected app' in r.detail


def test_network_cat_rigs_do_not_expect_serial_ports():
    for rig in ('Hamlib NET rigctl', 'FLRig FLRig', 'OmniRig Rig 1',
                'DX Lab Suite Commander'):
        app = _app(rig_name=rig, cat_port='COM9')
        assert _expected_ports(app) == [], rig


def test_missing_cat_port_warns_and_lists_existing_ports():
    apps = [_app(cat_port='COM5', is_running=True)]
    snap = _snap('windows', SerialSnapshot(ports=[
        SerialPortInfo(device='COM6', chip='FTDI')]), apps)
    r = _result(snap, 'serial/configured-port-exists')
    assert r.severity == Severity.WARNING
    assert 'COM5' in r.detail and 'COM6' in r.detail
    assert 'replugged' in r.detail
    assert r.fix


def test_present_cat_port_matches_case_insensitively():
    apps = [_app(cat_port='com5')]
    snap = _snap('windows', SerialSnapshot(ports=[
        SerialPortInfo(device='COM5', chip='FTDI')]), apps)
    r = _result(snap, 'serial/configured-port-exists')
    assert r.severity == Severity.OK


def test_by_id_alias_satisfies_the_config():
    """Linux best practice: configs point at the stable by-id symlink."""
    alias = ('/dev/serial/by-id/'
             'usb-Silicon_Labs_CP2102N_USB_to_UART-if00-port0')
    apps = [_app(cat_port=alias)]
    snap = _snap('linux', SerialSnapshot(ports=[SerialPortInfo(
        device='/dev/ttyUSB0', aliases=[alias])]), apps)
    assert (_result(snap, 'serial/configured-port-exists').severity
            == Severity.OK)


def test_tty_cu_twin_satisfies_the_config_on_macos():
    apps = [_app(rig_name='Icom IC-7300',
                 cat_port='/dev/tty.SLAB_USBtoUART')]
    snap = _snap('macos', SerialSnapshot(ports=[SerialPortInfo(
        device='/dev/cu.SLAB_USBtoUART',
        aliases=['/dev/tty.SLAB_USBtoUART'])]), apps)
    assert (_result(snap, 'serial/configured-port-exists').severity
            == Severity.OK)


def test_dtr_ptt_port_is_expected_and_missing_warns():
    apps = [_app(rig_name='None', cat_port='', ptt_method='DTR',
                 ptt_port='COM7')]
    snap = _snap('windows', SerialSnapshot(ports=[]), apps)
    r = _result(snap, 'serial/configured-port-exists')
    assert r.severity == Severity.WARNING
    assert 'PTT' in r.detail and 'COM7' in r.detail


def test_ptt_on_cat_port_not_double_counted():
    app = _app(cat_port='COM5', ptt_method='DTR', ptt_port='COM5')
    assert _expected_ports(app) == [('CAT', 'COM5')]


def test_rig_none_does_not_swallow_real_dtr_port_equal_to_placeholder():
    """Review 2026-07-27: with Rig=None the CAT port is a stale
    placeholder — a genuine DTR keying port that happens to equal it
    must still be expected."""
    app = _app(rig_name='None', cat_port='COM5', ptt_method='DTR',
               ptt_port='COM5')
    assert _expected_ports(app) == [('PTT', 'COM5')]


def test_apps_missing_is_unknown():
    snap = _snap(serial=SerialSnapshot(ports=[]), apps=None)
    assert (_result(snap, 'serial/configured-port-exists').severity
            == Severity.UNKNOWN)


def test_device_like_rejects_special_values():
    for value in ('', 'None', 'USB', 'EMU', 'localhost:4532',
                  '127.0.0.1:12345', 'COMPUTER'):
        assert not _device_like(value), value
    for value in ('COM5', 'com12', '/dev/ttyUSB0',
                  '/dev/cu.SLAB_USBtoUART', '\\\\.\\COM15',
                  '\\\\\\\\.\\\\COM15'):    # QSettings-doubled form
        assert _device_like(value), value


def test_win_namespace_form_matches_enumerated_port():
    """Review 2026-07-27: '\\\\.\\COM15' passed _device_like but could
    never match 'COM15' — a guaranteed false 'port missing' WARNING."""
    ports = [SerialPortInfo(device='COM15')]
    assert _find_port('\\\\.\\COM15', ports) is not None
    assert _find_port('\\\\\\\\.\\\\COM15', ports) is not None
    assert _normalize_port_name('\\\\.\\COM15') == 'com15'
    apps = [_app(cat_port='\\\\.\\COM15')]
    snap = _snap('windows', SerialSnapshot(ports=ports), apps)
    assert (_result(snap, 'serial/configured-port-exists').severity
            == Severity.OK)


# ---------------------------------------------------------------------------
# serial/driver-problem (Windows)
# ---------------------------------------------------------------------------

def test_problem_code_10_on_prolific_fails_with_counterfeit_wording():
    snap = _snap('windows', SerialSnapshot(ports=[SerialPortInfo(
        device='COM4', vid=0x067B, pid=0x2303,
        chip='Prolific PL2303', problem_code=10)]))
    r = _result(snap, 'serial/driver-problem')
    assert r.severity == Severity.FAIL
    assert 'cannot start' in r.detail
    assert 'counterfeit' in r.detail
    assert '3.3.11.152' in r.fix


def test_problem_code_28_reported_as_no_driver():
    snap = _snap('windows', SerialSnapshot(ports=[SerialPortInfo(
        device='COM4', vid=0x1A86, pid=0x7523, chip='CH340 (WCH)',
        problem_code=28)]))
    r = _result(snap, 'serial/driver-problem')
    assert r.severity == Severity.FAIL
    assert 'no driver' in r.detail


def test_unreadable_problem_codes_are_unknown_for_usb_ports():
    snap = _snap('windows', SerialSnapshot(ports=[SerialPortInfo(
        device='COM4', vid=0x0403, pid=0x6001, chip='FTDI',
        problem_code=None)]))
    r = _result(snap, 'serial/driver-problem')
    assert r.severity == Severity.UNKNOWN
    assert 'Device Manager' in r.detail


def test_healthy_codes_are_ok():
    snap = _snap('windows', SerialSnapshot(ports=[
        SerialPortInfo(device='COM4', vid=0x0403, pid=0x6001,
                       chip='FTDI', problem_code=0),
        SerialPortInfo(device='COM1', problem_code=None)]))  # non-USB
    assert (_result(snap, 'serial/driver-problem').severity
            == Severity.OK)


# ---------------------------------------------------------------------------
# serial/counterfeit-traps
# ---------------------------------------------------------------------------

def test_bricked_ftdi_fails():
    snap = _snap(serial=SerialSnapshot(ports=[SerialPortInfo(
        device='COM4', vid=0x0403, pid=0x0000,
        chip='FTDI (bricked: PID reset to 0000)')]))
    r = _result(snap, 'serial/counterfeit-traps')
    assert r.severity == Severity.FAIL
    assert 'PID 0000' in r.detail


def test_prolific_present_is_advisory_info_with_fix():
    snap = _snap(serial=SerialSnapshot(ports=[SerialPortInfo(
        device='COM4', vid=0x067B, pid=0x2303,
        chip='Prolific PL2303')]))
    r = _result(snap, 'serial/counterfeit-traps')
    assert r.severity == Severity.INFO
    assert r.fix                          # renders in Advisories
    assert 'counterfeit' in r.detail.casefold() \
        or 'counterfeit' in r.fix.casefold()


def test_prolific_in_usb_inventory_only_still_advises():
    """macOS: the adapter may be visible in the USB tree without a
    mapped port node."""
    snap = _snap('macos', SerialSnapshot(ports=[], adapters=[
        UsbSerialAdapter(vid=0x067B, pid=0x2303, product='USB-Serial',
                         chip='Prolific PL2303')]))
    assert (_result(snap, 'serial/counterfeit-traps').severity
            == Severity.INFO)


def test_no_traps_is_ok():
    snap = _snap(serial=SerialSnapshot(ports=[SerialPortInfo(
        device='COM4', vid=0x0403, pid=0x6001, chip='FTDI')]))
    assert (_result(snap, 'serial/counterfeit-traps').severity
            == Severity.OK)


# ---------------------------------------------------------------------------
# serial/port-sharing
# ---------------------------------------------------------------------------

def test_two_apps_on_one_port_is_info_with_rig_sharing_hint():
    apps = [_app(name='WSJT-X', cat_port='COM5'),
            _app(name='JTDX', cat_port='COM5')]
    snap = _snap('windows', SerialSnapshot(ports=[
        SerialPortInfo(device='COM5')]), apps)
    r = _result(snap, 'serial/port-sharing')
    assert r.severity == Severity.INFO
    assert 'OmniRig' in r.detail or 'rigctld' in r.detail


def test_port_held_by_foreign_process_warns_when_app_running():
    apps = [_app(cat_port='/dev/ttyUSB0', is_running=True)]
    snap = _snap('linux', SerialSnapshot(ports=[SerialPortInfo(
        device='/dev/ttyUSB0', in_use_by='minicom')]), apps)
    r = _result(snap, 'serial/port-sharing')
    assert r.severity == Severity.WARNING
    assert 'minicom' in r.detail
    assert r.fix


def test_port_held_by_its_own_app_is_ok():
    apps = [_app(cat_port='/dev/ttyUSB0', is_running=True)]
    snap = _snap('linux', SerialSnapshot(ports=[SerialPortInfo(
        device='/dev/ttyUSB0', in_use_by='wsjtx')]), apps)
    assert _result(snap, 'serial/port-sharing').severity == Severity.OK


def test_no_contention_is_ok():
    apps = [_app(cat_port='COM5')]
    snap = _snap('windows', SerialSnapshot(ports=[
        SerialPortInfo(device='COM5')]), apps)
    assert _result(snap, 'serial/port-sharing').severity == Severity.OK


# ---------------------------------------------------------------------------
# Probe pure helpers
# ---------------------------------------------------------------------------

def test_identify_chip_families_and_brick():
    assert identify_chip(0x0403, 0x6001) == 'FTDI'
    assert 'bricked' in identify_chip(0x0403, 0x0000)
    assert 'CP210x' in identify_chip(0x10C4, 0xEA60)
    assert 'CH340' in identify_chip(0x1A86, 0x7523)
    assert 'Prolific' in identify_chip(0x067B, 0x2303)
    assert 'CM108' in identify_chip(0x0D8C, 0x013A)
    assert identify_chip(0x1234, 0x5678) == ''
    assert identify_chip(None, None) == ''


def test_identify_device_label():
    assert identify_device_label('Digirig Mobile') == 'Digirig'
    assert identify_device_label('', 'SignaLink USB') == 'SignaLink'
    assert identify_device_label('USB Serial Port') == ''


def test_vidpid_from_enum_paths():
    assert _vidpid_from_text(r'USB\VID_067B&PID_2303\5&123') \
        == (0x067B, 0x2303)
    assert _vidpid_from_text(r'FTDIBUS\VID_0403+PID_6001+A5028BIA\0000') \
        == (0x0403, 0x6001)
    assert _vidpid_from_text('no ids here') == (None, None)


def test_win_broken_device_surfaces_without_serialcomm_entry():
    """Review 2026-07-27 BLOCKER: SERIALCOMM only lists successfully
    started drivers, so the Code 10 counterfeit-Prolific device is
    absent from it — it must be surfaced from its Enum entry or the
    doctor's flagship check can never fire."""
    devices = [{'enum_path': r'USB\VID_067B&PID_2303\a',
                'port_name': 'COM5', 'friendly_name': 'Prolific',
                'service': 'ser2pl', 'driver_provider': 'Prolific',
                'driver_version': '5.0', 'present': True,
                'problem_code': 10}]
    ports = _win_ports_from_raw([], devices)     # SERIALCOMM empty
    assert [p.device for p in ports] == ['COM5']
    assert ports[0].problem_code == 10
    # And the check fires on it.
    snap = _snap('windows', SerialSnapshot(ports=ports))
    assert (_result(snap, 'serial/driver-problem').severity
            == Severity.FAIL)


def test_win_stale_enum_entry_never_contributes_identity():
    """A not-present (stale) Enum instance claiming a live COM number
    must not shadow the live device, whatever the enumeration order."""
    stale = {'enum_path': r'USB\VID_067B&PID_2303\old',
             'port_name': 'COM5', 'friendly_name': 'Prolific (stale)',
             'service': 'ser2pl', 'driver_provider': 'Prolific',
             'driver_version': '3.3', 'present': False,
             'problem_code': None}
    live = {'enum_path': r'USB\VID_0403&PID_6001\new',
            'port_name': 'COM5', 'friendly_name': 'FTDI adapter',
            'service': 'FTSER2K', 'driver_provider': 'FTDI',
            'driver_version': '2.12', 'present': True, 'problem_code': 0}
    for order in ([stale, live], [live, stale]):
        ports = _win_ports_from_raw(['COM5'], order)
        assert ports[0].chip == 'FTDI', order[0]['friendly_name']


def test_win_adapters_inventory_sees_portless_bricked_ftdi():
    """Review 2026-07-27: a PID-0000 FTDI never gets a PortName, so it
    must reach the adapters inventory for the counterfeit FAIL to be
    reachable on Windows."""
    devices = [{'enum_path': r'USB\VID_0403&PID_0000\x',
                'port_name': '', 'friendly_name': 'USB Serial Converter',
                'service': '', 'driver_provider': '',
                'driver_version': '', 'present': True,
                'problem_code': 28},
               {'enum_path': r'USB\VID_0403&PID_6001\gone',
                'port_name': '', 'friendly_name': 'unplugged',
                'service': '', 'driver_provider': '',
                'driver_version': '', 'present': False,
                'problem_code': None}]
    adapters = _win_adapters_from_raw(devices)
    assert len(adapters) == 1                # not-present one excluded
    assert (adapters[0].vid, adapters[0].pid) == (0x0403, 0x0000)
    snap = _snap('windows', SerialSnapshot(ports=[], adapters=adapters))
    assert (_result(snap, 'serial/counterfeit-traps').severity
            == Severity.FAIL)


def test_display_string_unwraps_indirect_registry_form():
    assert _display_string('@oem12.inf,%desc%;USB Serial Port') \
        == 'USB Serial Port'
    assert _display_string('USB Serial Port (COM3)') \
        == 'USB Serial Port (COM3)'
    assert _display_string(None) == ''


def test_win_ports_from_raw_merges_and_prefers_healthy_instance():
    """Replug cycles leave multiple Enum instances claiming one COM
    port; the healthy one wins. Live ports without USB identity
    (motherboard COM1) are still listed."""
    active = ['COM1', 'COM5']
    devices = [
        {'enum_path': r'USB\VID_067B&PID_2303\a', 'port_name': 'COM5',
         'friendly_name': 'Prolific (old)', 'service': 'ser2pl',
         'driver_provider': 'Prolific', 'driver_version': '3.3.11.152',
         'problem_code': 10},
        {'enum_path': r'USB\VID_0403&PID_6001\b', 'port_name': 'COM5',
         'friendly_name': 'FTDI adapter', 'service': 'FTSER2K',
         'driver_provider': 'FTDI', 'driver_version': '2.12.36.4',
         'problem_code': 0},
        {'enum_path': r'USB\VID_1A86&PID_7523\c', 'port_name': 'COM9',
         'friendly_name': 'CH340 (unplugged)', 'service': 'CH341SER',
         'driver_provider': 'wch.cn', 'driver_version': '3.5',
         'problem_code': 45},
    ]
    ports = _win_ports_from_raw(active, devices)
    assert [p.device for p in ports] == ['COM1', 'COM5']
    com1, com5 = ports
    assert com1.vid is None and com1.chip == ''
    assert com5.chip == 'FTDI'              # healthy instance won
    assert com5.problem_code == 0
    assert com5.driver_version == '2.12.36.4'


def test_parse_system_profiler_usb_fixture():
    payload = '''
    {"SPUSBDataType": [{"_items": [
        {"_name": "USB3 Hub", "_items": [
            {"_name": "CP2102N USB to UART Bridge Controller",
             "vendor_id": "0x10c4  (Silicon Laboratories, Inc.)",
             "product_id": "0xea60",
             "manufacturer": "Silicon Labs"},
            {"_name": "Backup Disk", "vendor_id": "0x0bc2",
             "product_id": "0x2344"}
        ]},
        {"_name": "Digirig", "vendor_id": "0x0d8c",
         "product_id": "0x013a", "manufacturer": "C-Media"}
    ]}]}
    '''
    adapters = _parse_system_profiler_usb(payload)
    assert len(adapters) == 2               # disk excluded
    cp210x = next(a for a in adapters if a.vid == 0x10C4)
    assert cp210x.pid == 0xEA60 and 'CP210x' in cp210x.chip
    cmedia = next(a for a in adapters if a.vid == 0x0D8C)
    assert 'CM108' in cmedia.chip
    assert _parse_system_profiler_usb('not json') == []


def test_macos_chip_from_device_name():
    assert 'CP210x' in _macos_chip_from_device_name(
        '/dev/cu.SLAB_USBtoUART')
    assert 'CH340' in _macos_chip_from_device_name(
        '/dev/cu.wchusbserial1420')
    assert _macos_chip_from_device_name(
        '/dev/cu.Bluetooth-Incoming-Port') == ''


def test_macos_pseudo_ports_recognized():
    assert is_macos_pseudo_port('/dev/cu.Bluetooth-Incoming-Port')
    assert is_macos_pseudo_port('/dev/cu.debug-console')
    assert not is_macos_pseudo_port('/dev/cu.usbserial-1420')


def test_inventory_with_only_pseudo_ports_is_info():
    """Review 2026-07-27: every Mac has cu.Bluetooth-Incoming-Port —
    an all-green 'Serial ports present' over OS placeholders would hide
    a vanished adapter."""
    snap = _snap('macos', SerialSnapshot(ports=[
        SerialPortInfo(device='/dev/cu.Bluetooth-Incoming-Port'),
        SerialPortInfo(device='/dev/cu.debug-console')]))
    r = _result(snap, 'serial/inventory')
    assert r.severity == Severity.INFO
    assert 'placeholder' in r.detail


def test_counterfeit_traps_unknown_when_no_chip_evidence():
    """Review 2026-07-27: adapters=None (system_profiler failed) with
    identity-less ports = zero evidence; 'no traps' would be a guess."""
    snap = _snap('macos', SerialSnapshot(ports=[
        SerialPortInfo(device='/dev/cu.usbserial-1')], adapters=None))
    r = _result(snap, 'serial/counterfeit-traps')
    assert r.severity == Severity.UNKNOWN


def test_driver_problems_no_devices_is_ok_not_unknown():
    """Review 2026-07-27: a serial-less machine WAS successfully read;
    UNKNOWN would park it in 'Not checked' forever."""
    snap = _snap('windows', SerialSnapshot(ports=[]))
    r = _result(snap, 'serial/driver-problem')
    assert r.severity == Severity.OK


def test_port_sharing_ok_does_not_overclaim_without_holder_data():
    """Review 2026-07-27: Windows can't see holders — the OK wording
    must not assert 'no port is held by an unexpected process'."""
    apps = [_app(cat_port='COM5')]
    note = 'holder detection unavailable on Windows'
    snap = _snap('windows', SerialSnapshot(
        ports=[SerialPortInfo(device='COM5')], note=note), apps)
    r = _result(snap, 'serial/port-sharing')
    assert r.severity == Severity.OK
    assert 'unexpected process' not in r.detail
    assert note in r.detail


def test_config_value_with_percent_does_not_drop_the_app(tmp_path):
    """Review 2026-07-27: configparser interpolation made a bare '%'
    in any value raise and silently drop the whole DetectedApp."""
    from diagnostics.probe_apps import ConfigFileReader
    ini = tmp_path / 'WSJT-X.ini'
    ini.write_text('[Configuration]\n'
                   'MyCall=WU2C\n'
                   'Rig=Kenwood TS-590S\n'
                   'AzElDir=C:/100% ham stuff\n', encoding='utf-8')
    app = ConfigFileReader()._read_config(ini, 'WSJT-X')
    assert app is not None
    assert app.callsign == 'WU2C'


# ---------------------------------------------------------------------------
# Config parsing (probe_apps rig-control fields)
# ---------------------------------------------------------------------------

def test_config_reader_extracts_rig_control_fields(tmp_path):
    from diagnostics.probe_apps import ConfigFileReader
    ini = tmp_path / 'WSJT-X.ini'
    ini.write_text(
        '[Configuration]\n'
        'MyCall=WU2C\n'
        'Rig=Kenwood TS-590S\n'
        'CATSerialPort=/dev/cu.SLAB_USBtoUART\n'
        'PTTport=COM7\n'
        'PTTMethod=@Variant(\\0\\0\\0\\x7f\\0\\0\\0\\x1e'
        'TransceiverFactory::PTTMethod\\0\\0\\0\\0\\xfPTT_method_VOX\\0)\n',
        encoding='utf-8')
    app = ConfigFileReader()._read_config(ini, 'WSJT-X')
    assert app.rig_name == 'Kenwood TS-590S'
    assert app.cat_port == '/dev/cu.SLAB_USBtoUART'
    assert app.ptt_port == 'COM7'
    assert app.ptt_method == 'VOX'      # extracted from the QVariant blob
