# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Config Doctor and Network Doctor (DIAGNOSTICS_SPEC.md roster items 2
and 3). Pure fixture-driven checks — no probing. The Network Doctor
fixtures include the spec-mandated daisy-chain case: an unusual but
consistent chain (4242→2238) must be healthy, never a warning."""

from pathlib import Path

from diagnostics.doctors.config import ConfigDoctor
from diagnostics.doctors.network import NetworkDoctor
from diagnostics.models import (DetectedApp, PortInfo,
                                SNAPSHOT_SCHEMA_VERSION, Severity,
                                StationSnapshot)


def _snap(**kw):
    defaults = dict(schema_version=SNAPSHOT_SCHEMA_VERSION,
                    taken_at_utc='2026-07-26T18:00:00Z',
                    platform='windows')
    defaults.update(kw)
    return StationSnapshot(**defaults)


def _app(name='WSJT-X', callsign='WU2C', udp_ip='127.0.0.1', udp_port=2237,
         **kw):
    return DetectedApp(name=name, config_path=Path(f'/cfg/{name}.ini'),
                       callsign=callsign, udp_ip=udp_ip, udp_port=udp_port,
                       **kw)


def _result(doctor, snap, check_id):
    results = doctor.run(snap)
    matches = [r for r in results if r.check_id == check_id]
    assert len(matches) == 1, f"expected exactly one {check_id!r}"
    return matches[0]


# ---------------------------------------------------------------------------
# Config Doctor
# ---------------------------------------------------------------------------

class _Ep:
    """Duck-typed endpoint: state 1=ACTIVE, 2=DISABLED, 4=NOTPRESENT,
    8=UNPLUGGED (mmdeviceapi values); flow 'render'/'capture'."""
    def __init__(self, name, state=1, flow='render'):
        self.name = name
        self.state = state
        self.flow = flow


class _Audio:
    def __init__(self, *eps):
        self.endpoints = [e if isinstance(e, _Ep) else _Ep(e) for e in eps]


def test_config_missing_domain_is_unknown():
    results = ConfigDoctor().run(_snap(apps=None))
    assert [r.check_id for r in results] == ['config/snapshot-missing']
    assert results[0].severity == Severity.UNKNOWN


def test_config_no_apps_is_informational_not_failure():
    r = _result(ConfigDoctor(), _snap(apps=[]), 'config/inventory')
    assert r.severity == Severity.INFO
    assert 'FT8web' in r.detail            # absence is legitimate


def test_config_duplicates_warn_with_mtime_evidence():
    """The edits-the-wrong-copy diagnosis: two configs for one app,
    mtimes tell which is live."""
    a = _app(config_mtime='2026-07-26T05:24:14Z')
    b = _app(config_mtime='2024-01-01T00:00:00Z')
    b.config_path = Path('/other/WSJT-X.ini')
    r = _result(ConfigDoctor(), _snap(apps=[a, b]),
                'config/duplicate-configs')
    assert r.severity == Severity.WARNING
    assert '2024-01-01' in r.detail and '2026-07-26' in r.detail
    # Multi-instance is NOT a duplicate
    c = _app(instance_name='IC-7300')
    r2 = _result(ConfigDoctor(), _snap(apps=[a, c]),
                 'config/duplicate-configs')
    assert r2.severity == Severity.OK


def test_config_missing_callsign_is_info_and_names_the_app():
    r = _result(ConfigDoctor(), _snap(apps=[_app(callsign='')]),
                'config/callsign')
    assert r.severity == Severity.INFO
    assert 'WSJT-X' in r.detail


def test_config_audio_binding_unverifiable_without_audio_domain():
    """macOS/Linux checkups don't gather audio — the check must say
    'not verified', never guess."""
    app = _app(sound_out='Speakers (USB Audio CODEC )')
    r = _result(ConfigDoctor(), _snap(apps=[app], audio=None),
                'config/audio-bindings')
    assert r.severity == Severity.UNKNOWN
    assert 'could not be gathered' in r.detail


def test_config_audio_binding_stale_after_reenumeration():
    """The v2.6.0 origin story as a config check: the stored name no
    longer matches any device because Windows renamed it '2- ...'."""
    app = _app(sound_out='Speakers (USB Audio CODEC )')
    audio = _Audio('Speakers (2- USB Audio CODEC )',
                   '1 - HF255 (AMD High Definition Audio Device)')
    r = _result(ConfigDoctor(), _snap(apps=[app], audio=audio),
                'config/audio-bindings')
    assert r.severity == Severity.WARNING
    assert 'USB Audio CODEC' in r.detail
    assert 're-select' in r.fix.lower()


def test_config_audio_binding_matches_current_device():
    app = _app(sound_in='Microphone (USB Audio CODEC )',
               sound_out='Speakers (USB Audio CODEC )')
    audio = _Audio(_Ep('Speakers (USB Audio CODEC )', flow='render'),
                   _Ep('Microphone (USB Audio CODEC )', flow='capture'))
    r = _result(ConfigDoctor(), _snap(apps=[app], audio=audio),
                'config/audio-bindings')
    assert r.severity == Severity.OK


def test_config_audio_binding_ignores_ghost_endpoints():
    """Review blocker: Windows keeps the pre-rename registry entry as
    NOTPRESENT after USB re-enumeration. A binding satisfied only by a
    ghost is stale — the check must WARN, exactly the v2.6.0 scenario."""
    app = _app(sound_out='Speakers (USB Audio CODEC )')
    audio = _Audio(
        _Ep('Speakers (USB Audio CODEC )', state=4),      # NOTPRESENT ghost
        _Ep('Speakers (2- USB Audio CODEC )', state=1))   # renamed, ACTIVE
    r = _result(ConfigDoctor(), _snap(apps=[app], audio=audio),
                'config/audio-bindings')
    assert r.severity == Severity.WARNING
    # UNPLUGGED (jack-detect, nothing plugged in) is still a real device
    audio2 = _Audio(_Ep('Speakers (USB Audio CODEC )', state=8))
    r2 = _result(ConfigDoctor(), _snap(apps=[app], audio=audio2),
                 'config/audio-bindings')
    assert r2.severity == Severity.OK


def test_config_audio_binding_short_name_cannot_vacuously_match():
    """'have in want' was dropped: a device literally named 'Speakers'
    must not satisfy a stored 'Speakers (2- USB Audio CODEC )'."""
    app = _app(sound_out='Speakers (2- USB Audio CODEC )')
    r = _result(ConfigDoctor(), _snap(apps=[app], audio=_Audio('Speakers')),
                'config/audio-bindings')
    assert r.severity == Severity.WARNING
    # Qt's 31-char truncation of the STORED name still matches
    app2 = _app(sound_out='Speakers (2- USB Audio CODE')
    r2 = _result(ConfigDoctor(),
                 _snap(apps=[app2],
                       audio=_Audio('Speakers (2- USB Audio CODEC )')),
                 'config/audio-bindings')
    assert r2.severity == Severity.OK


def test_config_audio_binding_respects_flow():
    """An output binding must match RENDER endpoints, not a capture
    device that happens to share the name fragment."""
    app = _app(sound_out='USB Audio CODEC')
    audio = _Audio(_Ep('Microphone (USB Audio CODEC )', flow='capture'))
    r = _result(ConfigDoctor(), _snap(apps=[app], audio=audio),
                'config/audio-bindings')
    assert r.severity == Severity.WARNING


def test_config_duplicates_empty_apps_is_unknown_not_ok():
    r = _result(ConfigDoctor(), _snap(apps=[]), 'config/duplicate-configs')
    assert r.severity == Severity.UNKNOWN


# ---------------------------------------------------------------------------
# Network Doctor
# ---------------------------------------------------------------------------

def test_network_missing_domains_are_unknown():
    results = NetworkDoctor().run(_snap(apps=[_app()], udp_ports=None))
    assert [r.check_id for r in results] == ['network/snapshot-missing']
    assert 'udp_ports' in results[0].detail


def test_network_daisy_chain_is_healthy_not_suspicious():
    """THE spec-mandated fixture: WU2C's real station. WSJT-X sends to
    4242 (unconventional), GridTracker listens there and forwards to
    2238 where QSOP listens. Consistent chain -> OK, zero warnings."""
    apps = [_app(udp_port=4242, is_running=True),
            _app(name='JTDX', udp_port=4242, is_running=False)]
    ports = [PortInfo(port=4242, process_name='GridTracker2.exe', pid=3812),
             PortInfo(port=2238, process_name='python.exe', pid=17192)]
    results = NetworkDoctor().run(_snap(apps=apps, udp_ports=ports))
    assert all(r.severity < Severity.WARNING for r in results)
    chain = next(r for r in results
                 if r.check_id == 'network/decode-chain')
    assert chain.severity == Severity.OK
    assert 'GridTracker2.exe' in chain.detail


def test_network_broken_link_names_port_and_consequence():
    """The forwarder died: WSJT-X is running and sending to 4242 but
    nothing listens — the report must locate the broken link."""
    apps = [_app(udp_port=4242, is_running=True)]
    ports = [PortInfo(port=2238, process_name='python.exe')]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=ports),
                'network/decode-chain')
    assert r.severity == Severity.WARNING
    assert '4242' in r.detail
    assert 'nothing is listening' in r.detail
    assert 'downstream' in r.detail


def test_network_idle_sender_with_no_listener_is_info_not_warning():
    """App not running -> the dead link is dormant, not broken."""
    apps = [_app(udp_port=4242, is_running=False)]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=[]),
                'network/decode-chain')
    assert r.severity == Severity.INFO
    assert 'not running' in r.detail


def test_network_multicast_target_is_acknowledged_not_flagged():
    apps = [_app(udp_ip='239.255.0.0', udp_port=2237, is_running=True)]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=[]),
                'network/decode-chain')
    assert r.severity == Severity.OK
    assert 'multicast' in r.detail


def test_network_listener_inventory_lists_ports():
    ports = [PortInfo(port=2238, process_name='python.exe'),
             PortInfo(port=4242, process_name='GridTracker2.exe')]
    r = _result(NetworkDoctor(), _snap(apps=[], udp_ports=ports),
                'network/listeners')
    assert r.severity == Severity.INFO
    assert '2238' in r.detail and '4242' in r.detail


def test_doctors_declare_platforms_and_domains():
    assert ConfigDoctor().domains == frozenset({'apps', 'audio'})
    assert NetworkDoctor().domains == frozenset({'apps', 'udp_ports'})
    for d in (ConfigDoctor(), NetworkDoctor()):
        assert d.platforms == frozenset({'windows', 'macos', 'linux'})


# ---------------------------------------------------------------------------
# Network Doctor — review-driven hardening
# ---------------------------------------------------------------------------

def test_network_remote_unicast_target_is_acknowledged_not_flagged():
    """Review blocker: WSJT-X sending to a logging PC on the LAN can
    never show a listener in the LOCAL port scan — acknowledged, never
    a warning."""
    apps = [_app(udp_ip='192.168.1.50', udp_port=2237, is_running=True)]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=[]),
                'network/decode-chain')
    assert r.severity == Severity.OK
    assert 'not verifiable' in r.detail


def test_network_disabled_udp_is_not_a_chain():
    """User cleared the server address to disable UDP — no fabricated
    127.0.0.1 chain, no warning."""
    apps = [_app(udp_ip='', udp_port=2237, is_running=True)]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=[]),
                'network/decode-chain')
    assert r.severity == Severity.INFO
    assert 'disabled' in r.detail


def test_network_interface_mismatch_is_flagged_not_false_ok():
    """Listener on the right port but bound to a LAN address can't
    receive loopback-targeted datagrams."""
    apps = [_app(udp_ip='127.0.0.1', udp_port=2237, is_running=True)]
    ports = [PortInfo(port=2237, ip='192.168.1.5',
                      process_name='GridTracker2.exe')]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=ports),
                'network/decode-chain')
    assert r.severity == Severity.WARNING
    assert 'bound to 192.168.1.5' in r.detail


def test_network_multi_instance_running_softens_to_info():
    """is_running is app-level: with two instance configs we can't know
    which one runs — a dead link must not claim 'is running and
    sending'."""
    apps = [_app(instance_name='IC-7300', udp_port=2237, is_running=True),
            _app(instance_name='FT-991', udp_port=2239, is_running=True)]
    ports = [PortInfo(port=2237, process_name='GridTracker2.exe')]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=ports),
                'network/decode-chain')
    assert r.severity == Severity.OK      # dead 2239 link softened, 2237 fine
    assert "which instance isn't knowable" in r.detail


def test_network_unknown_listener_name_wording():
    """Socket-probe rows prove something is bound, not what — the frozen
    wording must not read '(unknown listening)'."""
    apps = [_app(udp_port=2237, is_running=True)]
    ports = [PortInfo(port=2237, ip='0.0.0.0', process_name='unknown')]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=ports),
                'network/decode-chain')
    assert r.severity == Severity.OK
    assert 'name unknown' in r.detail
    assert 'unknown listening' not in r.detail


def test_network_warning_keeps_healthy_links_visible():
    apps = [_app(udp_port=4242, is_running=True),
            _app(name='JTDX', udp_ip='239.255.0.0', udp_port=2237,
                 is_running=True)]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=[]),
                'network/decode-chain')
    assert r.severity == Severity.WARNING
    assert 'Healthy links' in r.detail and 'multicast' in r.detail


def test_network_no_targets_is_info_not_unknown():
    """Gathered-but-empty means 'nothing found', not 'could not read' —
    UNKNOWN would land it in the report's Not-checked section."""
    r = _result(NetworkDoctor(), _snap(apps=[], udp_ports=[]),
                'network/decode-chain')
    assert r.severity == Severity.INFO


def test_network_ipv6_multicast_is_recognized():
    apps = [_app(udp_ip='ff12::1', udp_port=2237, is_running=True)]
    r = _result(NetworkDoctor(), _snap(apps=apps, udp_ports=[]),
                'network/decode-chain')
    assert r.severity == Severity.OK
    assert 'multicast' in r.detail


# ---------------------------------------------------------------------------
# Network Doctor — shared unicast port contention (2026-08-02 regression:
# JTAlert's 127.0.0.1:4242 binding silently captured the WSJT-X stream
# from GridTracker's 0.0.0.0:4242, and the checkup reported no problems)
# ---------------------------------------------------------------------------

def _contention_snap(apps, ports):
    return _snap(apps=apps, udp_ports=ports)


def test_shared_unicast_port_warns_and_names_winner_and_starved():
    """The literal 4242 scenario from the 2026-08-02 station report."""
    apps = [_app(udp_ip='127.0.0.1', udp_port=4242, is_running=True)]
    ports = [
        PortInfo(port=4242, ip='0.0.0.0',
                 process_name='GridTracker2.exe', pid=4004),
        PortInfo(port=4242, ip='0.0.0.0',
                 process_name='JTAlertV2.Manager.exe', pid=15852),
        PortInfo(port=4242, ip='127.0.0.1',
                 process_name='JTAlertV2.Manager.exe', pid=15852),
    ]
    r = _result(NetworkDoctor(), _contention_snap(apps, ports),
                'network/port-contention')
    assert r.severity == Severity.WARNING
    assert 'JTAlertV2.Manager.exe' in r.detail       # the winner
    assert 'GridTracker2.exe' in r.detail            # the starved app
    assert '127.0.0.1' in r.detail                   # why it wins
    assert 'multicast' in r.fix                      # the way out


def test_multicast_station_shared_port_is_not_flagged():
    """After a multicast migration every member binds the wildcard on the
    same port — a scan can't see group memberships, so the sender config
    (239.x target) is what marks the sharing as legitimate."""
    apps = [_app(udp_ip='239.255.0.0', udp_port=2237, is_running=True)]
    ports = [
        PortInfo(port=2237, ip='0.0.0.0',
                 process_name='GridTracker2.exe', pid=1),
        PortInfo(port=2237, ip='0.0.0.0', process_name='python.exe', pid=2),
        PortInfo(port=2237, ip='0.0.0.0',
                 process_name='JTAlertV2.Manager.exe', pid=3),
    ]
    r = _result(NetworkDoctor(), _contention_snap(apps, ports),
                'network/port-contention')
    assert r.severity == Severity.OK


def test_single_process_dual_bind_is_not_contention():
    """One process holding both 0.0.0.0 and 127.0.0.1 on its port (JTAlert
    does this) is normal, not a conflict."""
    apps = [_app(udp_ip='127.0.0.1', udp_port=2237, is_running=True)]
    ports = [
        PortInfo(port=2237, ip='0.0.0.0',
                 process_name='JTAlertV2.Manager.exe', pid=7),
        PortInfo(port=2237, ip='127.0.0.1',
                 process_name='JTAlertV2.Manager.exe', pid=7),
    ]
    r = _result(NetworkDoctor(), _contention_snap(apps, ports),
                'network/port-contention')
    assert r.severity == Severity.OK


def test_shared_port_nobody_sends_to_stays_quiet():
    """Two processes sharing a port that no detected sender targets is
    outside the decode chain this doctor can reason about — winner and
    loser aren't decidable, so no warning."""
    apps = [_app(udp_ip='127.0.0.1', udp_port=2237, is_running=True)]
    ports = [
        PortInfo(port=2237, ip='0.0.0.0', process_name='python.exe', pid=1),
        PortInfo(port=9999, ip='0.0.0.0', process_name='appA.exe', pid=2),
        PortInfo(port=9999, ip='0.0.0.0', process_name='appB.exe', pid=3),
    ]
    r = _result(NetworkDoctor(), _contention_snap(apps, ports),
                'network/port-contention')
    assert r.severity == Severity.OK
