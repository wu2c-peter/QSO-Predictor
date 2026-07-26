# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Architectural conventions from CLAUDE.md, enforced mechanically."""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_DIRS = {'venv', '.git', '__pycache__', 'build', 'dist',
                 '.pytest_cache'}


def repo_python_files():
    for path in REPO_ROOT.rglob('*.py'):
        if not any(part in EXCLUDED_DIRS for part in path.parts):
            yield path


def test_no_module_imports_main_v2():
    """main_v2.py runs as __main__. `from main_v2 import X` anywhere else
    loads the module a SECOND time under the name 'main_v2', re-running
    setup_logging() and duplicating log handlers (see CLAUDE.md).
    Helpers that other modules need belong in utils/.
    """
    pattern = re.compile(r'^\s*(from\s+main_v2\s+import|import\s+main_v2)\b')
    offenders = []
    for path in repo_python_files():
        if path.name == 'main_v2.py':
            continue
        for lineno, line in enumerate(
                path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if pattern.match(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    assert not offenders, (
        f"Never import main_v2 from another module (it re-executes as a "
        f"duplicate): {offenders}"
    )


def test_utils_stays_free_of_qt_and_app_imports():
    """utils/ is documented as pure-stdlib with no Qt / main-app deps —
    that's what makes it safe to import from worker threads."""
    pattern = re.compile(r'^\s*(from|import)\s+(PyQt6|analyzer|controllers|'
                         r'local_intel|ionis|widgets)\b')
    offenders = []
    for path in (REPO_ROOT / 'utils').glob('*.py'):
        for lineno, line in enumerate(
                path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if pattern.match(line):
                offenders.append(f"utils/{path.name}:{lineno}")
    assert not offenders, f"utils/ must stay stdlib-only: {offenders}"


def test_release_workflow_installs_every_spec_hiddenimport():
    """v2.4.0–v2.5.8 Windows exes silently shipped WITHOUT IONIS: the
    spec listed safetensors in hiddenimports but the release workflow
    never pip-installed it, and PyInstaller drops missing hidden imports
    with a non-fatal warning. Freeze the invariant: every external
    top-level package named in qso_predictor.spec's hiddenimports must
    be installed by the build-windows job, directly or as a known
    transitive of an installed distribution."""
    spec_tree = ast.parse(
        (REPO_ROOT / 'qso_predictor.spec').read_text(encoding='utf-8'))
    hidden = set()
    for node in ast.walk(spec_tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        if not any(isinstance(t, ast.Name) and t.id == 'hiddenimports'
                   for t in targets):
            continue
        for const in ast.walk(node.value):
            if isinstance(const, ast.Constant) and isinstance(const.value, str):
                hidden.add(const.value.split('.')[0])
    assert hidden, "failed to parse hiddenimports out of qso_predictor.spec"

    workflow = (REPO_ROOT / '.github/workflows/build-release.yml').read_text(
        encoding='utf-8')
    windows_job = workflow.split('build-macos:')[0]
    installed = set()
    for line in windows_job.splitlines():
        line = line.strip()
        if line.startswith('pip install'):
            for token in line[len('pip install'):].split():
                token = token.strip('"\'')
                installed.add(re.split(r'[><=!~;]', token)[0].lower())

    # import-name -> PyPI distribution when they differ
    dist_of = {'paho': 'paho-mqtt'}
    # packages pulled in transitively by an installed distribution
    transitive_of = {
        'comtypes': 'pycaw', 'psutil': 'pycaw',
        'urllib3': 'requests', 'charset_normalizer': 'requests',
        'certifi': 'requests', 'idna': 'requests',
    }

    missing = []
    for pkg in sorted(hidden):
        if (REPO_ROOT / pkg).is_dir():
            continue    # local package, always bundled from the repo
        dist = dist_of.get(pkg, pkg).lower()
        via = transitive_of.get(pkg, '').lower()
        if dist not in installed and via not in installed:
            missing.append(pkg)
    assert not missing, (
        f"qso_predictor.spec hiddenimports name packages the release "
        f"workflow never installs — PyInstaller will silently drop them "
        f"from the exe (the v2.4.0 IONIS bug): {missing}"
    )


def test_diagnostics_stays_free_of_qt_and_app_imports():
    """diagnostics/ is the doctors-framework core (dev-docs/
    DIAGNOSTICS_SPEC.md): a future standalone/headless tester must be
    buildable from it, and doctors' check logic must stay unit-testable
    on any platform. So: no Qt and no app module AT ALL — the ban list
    is computed from the repo root (every root *.py and every local
    package except utils, which is pure stdlib by its own test) so new
    app modules are banned automatically. audio_doctor especially:
    audio_doctor.models imports diagnostics.models at module load, so a
    diagnostics -> audio_doctor import is an instant circular-import
    crash. Platform access — the platform-only libraries AND the stdlib
    escape hatches the probes actually use (subprocess for
    netstat/lsof/ss/tasklist/ps, socket for bind probes) — is confined
    to probe_* modules (same convention as audio_doctor); non-probe
    modules must work from data alone."""
    allowed_local = {'diagnostics', 'utils', 'tests'}
    banned = {'PyQt6'}
    for p in REPO_ROOT.glob('*.py'):
        banned.add(p.stem)
    for p in REPO_ROOT.iterdir():
        if (p / '__init__.py').exists() and p.name not in allowed_local:
            banned.add(p.name)
    qt_and_app = re.compile(
        r'^\s*(from|import)\s+(' + '|'.join(map(re.escape, sorted(banned)))
        + r')\b')
    platform_only = re.compile(r'^\s*(from|import)\s+(pycaw|comtypes|winreg|'
                               r'psutil|subprocess|socket)\b')
    offenders = []
    for path in (REPO_ROOT / 'diagnostics').rglob('*.py'):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        rel = path.relative_to(REPO_ROOT)
        for lineno, line in enumerate(
                path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if qt_and_app.match(line):
                offenders.append(f"{rel}:{lineno} (Qt/app)")
            elif not path.name.startswith('probe_') and platform_only.match(line):
                offenders.append(f"{rel}:{lineno} (platform-only)")
    assert not offenders, (
        f"diagnostics/ must stay free of Qt/app-module imports, with "
        f"platform access confined to probe_* modules: {offenders}"
    )


def test_diagnostics_reexports_are_the_same_objects():
    """audio_doctor.models re-exports the framework types from
    diagnostics.models. Identity (not just equality) is the contract:
    if audio_doctor ever drifts back to local definitions, cross-module
    enum comparisons and isinstance checks silently break while every
    other test stays green (same drift class as the freq_to_band
    copies)."""
    import audio_doctor.models as am
    import diagnostics.models as dm
    assert am.Severity is dm.Severity
    assert am.CheckResult is dm.CheckResult
    assert am.SettingsPanel is dm.SettingsPanel


def test_audio_doctor_core_stays_free_of_qt_and_windows_imports():
    """audio_doctor's models/parsing/checks are pure stdlib by design —
    that's what makes the diagnostic logic unit-testable off-Windows.
    Only probe_windows may touch pycaw/comtypes/winreg, and even it must
    stay free of Qt / main-app imports (it runs on worker threads)."""
    qt_and_app = re.compile(r'^\s*(from|import)\s+(PyQt6|analyzer|controllers|'
                            r'local_intel|ionis|widgets)\b')
    windows_only = re.compile(r'^\s*(from|import)\s+(pycaw|comtypes|winreg|'
                              r'psutil)\b')
    offenders = []
    for path in (REPO_ROOT / 'audio_doctor').glob('*.py'):
        for lineno, line in enumerate(
                path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
            if qt_and_app.match(line):
                offenders.append(f"audio_doctor/{path.name}:{lineno} (Qt/app)")
            elif path.name != 'probe_windows.py' and windows_only.match(line):
                offenders.append(f"audio_doctor/{path.name}:{lineno} (win-only)")
    assert not offenders, (
        f"audio_doctor core must stay pure stdlib (COM/registry access "
        f"belongs in probe_windows.py): {offenders}"
    )
