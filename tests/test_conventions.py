# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Architectural conventions from CLAUDE.md, enforced mechanically."""

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
