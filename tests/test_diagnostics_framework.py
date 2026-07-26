# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Doctors-framework tests (DIAGNOSTICS_SPEC.md migration step 3):
StationSnapshot, the registry/checkup orchestration, report rendering,
and the Audio Doctor adapter. All pure/fixture-driven — no live probing.
"""

import json
from pathlib import Path

import pytest

from diagnostics import registry
from diagnostics.models import (CheckResult, DetectedApp, PortInfo,
                                SNAPSHOT_SCHEMA_VERSION, Severity,
                                StationSnapshot)
from diagnostics.registry import CheckupRun, DoctorRun, SkippedDoctor
from diagnostics.report import render_report, report_filename


@pytest.fixture
def clean_registry():
    """Isolate registry state; restore built-in gatherers afterwards."""
    registry._reset_for_tests()
    yield
    registry._reset_for_tests()


def _snapshot(**kw):
    defaults = dict(schema_version=SNAPSHOT_SCHEMA_VERSION,
                    taken_at_utc='2026-07-26T12:34:56Z',
                    platform=registry.current_platform(),
                    os_detail='TestOS 1.0')
    defaults.update(kw)
    return StationSnapshot(**defaults)


class FakeDoctor:
    def __init__(self, id='fake', title='Fake Doctor', platforms=None,
                 domains=frozenset(), results=None, crash=False):
        self.id = id
        self.title = title
        self.platforms = platforms if platforms is not None else frozenset(
            {registry.current_platform()})
        self.domains = domains
        self._results = results or []
        self._crash = crash

    def run(self, snap):
        if self._crash:
            raise RuntimeError('boom')
        return list(self._results)


def _result(check_id, severity, title=None, **kw):
    return CheckResult(check_id=check_id, title=title or check_id,
                       severity=severity, detail=f'detail of {check_id}',
                       **kw)


# ---------------------------------------------------------------------------
# Registry / checkup orchestration
# ---------------------------------------------------------------------------

def test_register_rejects_duplicate_ids(clean_registry):
    registry.register(FakeDoctor(id='x'))
    with pytest.raises(ValueError):
        registry.register(FakeDoctor(id='x'))


def test_checkup_runs_applicable_and_skips_foreign_platform():
    here = FakeDoctor(id='here', results=[_result('here/ok', Severity.OK)])
    elsewhere = FakeDoctor(id='away', title='Away Doctor',
                           platforms=frozenset({'nowhere'}))
    run = registry.run_checkup(doctors=[here, elsewhere],
                               snapshot=_snapshot())
    assert [e.doctor_id for e in run.entries] == ['here']
    assert [s.doctor_id for s in run.skipped] == ['away']
    assert 'not supported' in run.skipped[0].reason


def test_checkup_survives_a_crashing_doctor():
    ok = FakeDoctor(id='ok', results=[_result('ok/fine', Severity.OK)])
    bad = FakeDoctor(id='bad', title='Bad Doctor', crash=True)
    run = registry.run_checkup(doctors=[bad, ok], snapshot=_snapshot())
    assert [e.doctor_id for e in run.entries] == ['ok']
    assert any(s.doctor_id == 'bad' and 'crashed' in s.reason
               for s in run.skipped)


def test_gather_snapshot_records_failures_and_missing_gatherers(
        clean_registry):
    registry.register_gatherer('apps', lambda: [
        DetectedApp(name='WSJT-X', config_path=None, callsign='WU2C')])

    def explode():
        raise OSError('scan failed')
    registry.register_gatherer('udp_ports', explode)

    snap = registry.gather_snapshot({'apps', 'udp_ports', 'audio'})
    assert snap.apps and snap.apps[0].callsign == 'WU2C'
    assert snap.udp_ports is None
    assert snap.audio is None
    assert any('udp_ports' in e and 'scan failed' in e for e in snap.errors)
    assert any('audio' in e and 'no gatherer' in e for e in snap.errors)
    assert snap.schema_version == SNAPSHOT_SCHEMA_VERSION


def test_checkup_gathers_union_of_declared_domains(clean_registry):
    gathered = []
    registry.register_gatherer('apps', lambda: gathered.append('apps') or [])
    registry.register_gatherer('udp_ports',
                               lambda: gathered.append('udp_ports') or [])
    a = FakeDoctor(id='a', domains=frozenset({'apps'}))
    b = FakeDoctor(id='b', domains=frozenset({'apps', 'udp_ports'}))
    registry.run_checkup(doctors=[a, b])
    assert sorted(gathered) == ['apps', 'udp_ports']   # each gathered once


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def _sample_checkup(include_apps=True):
    snap = _snapshot(
        apps=[DetectedApp(name='WSJT-X',
                          config_path=Path.home() / 'cfg' / 'WSJT-X.ini',
                          callsign='WU2C', grid='FN30pr',
                          udp_ip='127.0.0.1', udp_port=2237)]
        if include_apps else None,
        udp_ports=[PortInfo(port=2237, ip='0.0.0.0',
                            process_name='GridTracker', pid=42)],
        errors=['serial: not implemented'],
    )
    entries = [DoctorRun('fake', 'Fake Doctor', [
        _result('fake/broken', Severity.FAIL, fix='Turn it off and on.'),
        _result('fake/iffy', Severity.WARNING),
        _result('fake/fine', Severity.OK),
        _result('fake/fyi', Severity.INFO),
        _result('fake/unread', Severity.UNKNOWN),
    ])]
    skipped = [SkippedDoctor('audio', 'Audio Doctor',
                             'not supported on macos')]
    return CheckupRun(snapshot=snap, entries=entries, skipped=skipped)


def test_report_section_order_and_content():
    text = render_report(_sample_checkup(), 'ShackCheck', 'v0.1')
    order = ['# ShackCheck diagnostic report', '## Station', '## Findings',
             '## Passed checks', '## Not checked', '## Details',
             '## Machine appendix']
    indices = [text.index(h) for h in order]
    assert indices == sorted(indices)
    # Worst first: FAIL line before WARNING line
    assert text.index('fake/broken') < text.index('fake/iffy')
    # Fix text carried into the finding line
    assert 'Turn it off and on.' in text
    # Passed section lists OK and INFO one-liners
    assert 'fake/fine' in text and 'fake/fyi' in text
    # Not-checked lists both the skipped doctor and the UNKNOWN result
    assert 'Audio Doctor: not supported on macos' in text
    assert 'fake/unread' in text
    # Probe errors surface in Details
    assert 'serial: not implemented' in text


def test_report_identity_toggle_and_path_scrubbing():
    with_id = render_report(_sample_checkup(), 'ShackCheck', 'v0.1')
    assert 'Station: WU2C (FN30pr)' in with_id
    # Home directory never appears; scrubbed to ~
    assert str(Path.home()) not in with_id
    assert '~' in with_id

    without = render_report(_sample_checkup(), 'ShackCheck', 'v0.1',
                            include_identity=False)
    assert 'Station: WU2C' not in without


def test_report_machine_appendix_is_valid_json_of_problems_only():
    text = render_report(_sample_checkup(), 'ShackCheck', 'v0.1')
    payload = text.split('```json', 1)[1].split('```', 1)[0]
    data = json.loads(payload)
    assert data['schema_version'] == SNAPSHOT_SCHEMA_VERSION
    ids = {f['check_id'] for f in data['findings']}
    assert ids == {'fake/broken', 'fake/iffy'}
    assert all(f['doctor'] == 'fake' for f in data['findings'])


def test_report_filename_format():
    assert (report_filename('ShackCheck', '2026-07-26T12:34:56Z')
            == 'shackcheck-report-20260726-1234Z.md')


# ---------------------------------------------------------------------------
# Audio Doctor adapter (pure paths only — no COM)
# ---------------------------------------------------------------------------

def test_audio_adapter_reports_unknown_when_domain_missing():
    from audio_doctor.doctor import AudioDoctor
    results = AudioDoctor().run(_snapshot(audio=None))
    assert len(results) == 1
    assert results[0].check_id == 'audio/snapshot-missing'
    assert results[0].severity == Severity.UNKNOWN


def test_audio_adapter_runs_real_checks_over_fixture_snapshot():
    from audio_doctor.doctor import AudioDoctor
    from audio_doctor.models import AudioSnapshot
    results = AudioDoctor(rig_hint='USB Audio CODEC').run(
        _snapshot(audio=AudioSnapshot()))
    assert len(results) >= 8                     # the full static audit
    assert all(isinstance(r, CheckResult) for r in results)
    # Empty audio snapshot means the rig codec is absent — that's a FAIL
    assert any(r.severity == Severity.FAIL for r in results)
    assert all(r.check_id and r.title for r in results)


def test_audio_adapter_declares_windows_only_and_audio_domain():
    from audio_doctor.doctor import AudioDoctor
    d = AudioDoctor()
    assert d.platforms == frozenset({'windows'})
    assert d.domains == frozenset({'audio'})
    assert d.id == 'audio' and d.title == 'Audio Doctor'


# ---------------------------------------------------------------------------
# Review-driven hardening (step-3 adversarial review findings)
# ---------------------------------------------------------------------------

def test_registry_rejects_unknown_domain_names(clean_registry):
    with pytest.raises(ValueError):
        registry.register_gatherer('audoi', lambda: [])   # typo'd domain
    bogus = FakeDoctor(id='b', domains=frozenset({'audoi'}))
    run = registry.run_checkup(doctors=[bogus])
    assert any('audoi' in e and 'not a snapshot domain' in e
               for e in run.snapshot.errors)


def test_scrub_covers_nt_paths_appendix_and_skip_reasons():
    """Usernames must not survive anywhere: NT device paths carry no
    drive letter (so exact-home replacement misses them), the JSON
    appendix serializes before the markdown-level scrub can act, and
    crash reasons can carry paths."""
    nt_path = r'\Device\HarddiskVolume3\Users\peterhirst\jtdx\bin\jtdx.exe'
    checkup = CheckupRun(
        snapshot=_snapshot(),
        entries=[DoctorRun('fake', 'Fake Doctor', [
            _result('fake/path-title', Severity.FAIL,
                    title=f'Cannot read {Path.home()}/cfg/WSJT-X.ini'),
            _result('fake/nt-path', Severity.WARNING, title=nt_path),
        ])],
        skipped=[SkippedDoctor('x', 'X Doctor',
                               f'crashed: {Path.home()}/boom.log')],
    )
    text = render_report(checkup, 'ShackCheck', 'v0.1')
    assert str(Path.home()) not in text
    assert 'peterhirst' not in text.replace(str(Path.home()), '')
    # The appendix (post-JSON-escaping) is covered too
    payload = json.loads(text.split('```json', 1)[1].split('```', 1)[0])
    titles = ' '.join(f['title'] for f in payload['findings'])
    assert 'peterhirst' not in titles and 'Users\\~' in titles


def test_identity_toggle_redacts_details_tables_too():
    text = render_report(_sample_checkup(), 'ShackCheck', 'v0.1',
                         include_identity=False)
    assert 'WU2C' not in text
    assert 'FN30pr' not in text


def test_table_schema_is_row_order_independent_and_markdown_safe():
    from dataclasses import dataclass as dc
    from typing import Optional as Opt

    @dc
    class Fmt:
        rate: int
        bits: int

    @dc
    class Row:
        name: str
        fmt: Opt[Fmt] = None

    from diagnostics.report import _table
    a = Row('Speakers | rig', Fmt(48000, 16))
    b = Row('Mic', None)
    header_ab = _table([a, b])[0]
    header_ba = _table([b, a])[0]
    assert header_ab == header_ba == '| name | fmt |'
    body = '\n'.join(_table([a, b]))
    assert 'rate=48000' in body          # compact nested rendering
    assert 'Speakers \\| rig' in body    # pipes escaped, table intact


def test_audio_adapter_rig_hint_provider_is_read_per_run():
    from audio_doctor.doctor import AudioDoctor
    from audio_doctor.models import AudioSnapshot
    hint = {'value': 'FIRST CODEC'}
    doctor = AudioDoctor(rig_hint=lambda: hint['value'])

    def rig_check_detail(results):
        return next(r for r in results if r.check_id == 'rig-endpoint').detail

    first = doctor.run(_snapshot(audio=AudioSnapshot()))
    hint['value'] = '  SECOND CODEC  '     # edited in dialog, spaces and all
    second = doctor.run(_snapshot(audio=AudioSnapshot()))
    assert 'FIRST CODEC' in rig_check_detail(first)
    assert 'SECOND CODEC' in rig_check_detail(second)   # fresh + stripped


def test_gather_audio_raises_cleanly_when_probe_unavailable():
    from audio_doctor import probe_windows
    if probe_windows.available():
        pytest.skip('real audio probe available on this machine')
    from audio_doctor.doctor import gather_audio
    with pytest.raises(RuntimeError, match='audio probe unavailable'):
        gather_audio()
