# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Incremental log scanning must never count a line twice.

2026-09 audit: `for line in f` disables TextIOWrapper.tell(), so when
stop() interrupted a scan mid-file the OSError left the byte offset
unadvanced while the already-collected decodes were still processed —
every restart re-counted them. The scanner also froze its file list at
startup, so a log created later (monthly JTDX rollover) was never read.
"""

from datetime import datetime
from pathlib import Path

import pytest

from local_intel.background_scanner import BackgroundScanner, FilePosition, ScanProgress
from local_intel.log_parser import LogParser


class _Source:
    def __init__(self, path):
        self.path = Path(path)


class _Predictor:
    def _save_history(self):
        pass


@pytest.fixture
def scanner(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    return BackgroundScanner(_Predictor())


WSJTX_LINE = "260830_181500    14.074 Rx FT8    -12  0.3 1687 CQ JA1XYZ PM95"

# Windows WSJT-X/JTDX write CRLF; macOS/Linux write LF. Files are written
# as BYTES so the on-disk newline is exactly what the test says, on every
# CI platform (Path.write_text would translate LF→CRLF on Windows and
# make byte-offset expectations platform-dependent).
NEWLINES = ["\n", "\r\n"]


def _write(path, lines, newline, partial=""):
    data = "".join(line + newline for line in lines) + partial
    path.write_bytes(data.encode('utf-8'))
    return data.encode('utf-8')


@pytest.mark.parametrize("newline", NEWLINES, ids=["lf", "crlf"])
def test_offset_advances_to_end_of_complete_lines(scanner, tmp_path, newline):
    log = tmp_path / 'ALL.TXT'
    _write(log, [WSJTX_LINE] * 3, newline)
    pos = FilePosition(path=str(log))
    decodes = scanner._scan_file_incremental(_Source(log), LogParser(), pos, ScanProgress())
    assert len(decodes) == 3
    assert pos.byte_offset == log.stat().st_size


@pytest.mark.parametrize("newline", NEWLINES, ids=["lf", "crlf"])
def test_partial_trailing_line_is_left_for_next_pass(scanner, tmp_path, newline):
    """WSJT-X writes lines incrementally; a half-written tail must not be
    parsed now AND re-read later."""
    log = tmp_path / 'ALL.TXT'
    _write(log, [WSJTX_LINE], newline, partial=WSJTX_LINE[:30])
    one_line = len((WSJTX_LINE + newline).encode())
    pos = FilePosition(path=str(log))
    decodes = scanner._scan_file_incremental(_Source(log), LogParser(), pos, ScanProgress())
    assert len(decodes) == 1
    assert pos.byte_offset == one_line
    # Complete the line; the next pass picks up exactly the one new decode
    _write(log, [WSJTX_LINE] * 2, newline)
    decodes = scanner._scan_file_incremental(_Source(log), LogParser(), pos, ScanProgress())
    assert len(decodes) == 1
    assert pos.byte_offset == log.stat().st_size


@pytest.mark.parametrize("newline", NEWLINES, ids=["lf", "crlf"])
def test_stop_mid_file_commits_a_consistent_offset(scanner, tmp_path, newline):
    log = tmp_path / 'ALL.TXT'
    _write(log, [WSJTX_LINE] * 5, newline)
    one_line = len((WSJTX_LINE + newline).encode())
    pos = FilePosition(path=str(log))

    class StopAfterTwo(LogParser):
        calls = 0
        def parse_line(self_inner, line):
            StopAfterTwo.calls += 1
            if StopAfterTwo.calls == 2:
                scanner._stop_requested = True
            return super().parse_line(line)

    decodes = scanner._scan_file_incremental(_Source(log), StopAfterTwo(), pos, ScanProgress())
    # Whatever was returned, the offset points exactly past those lines
    assert pos.byte_offset == len(decodes) * one_line


def test_positions_file_is_written_atomically(scanner, tmp_path):
    scanner._positions['x'] = FilePosition(path='x', byte_offset=42)
    scanner._save_positions()
    assert not scanner._positions_file.with_suffix('.json.tmp').exists()
    fresh = BackgroundScanner(_Predictor())
    assert fresh._positions['x'].byte_offset == 42


def test_prune_forgets_deleted_files(scanner, tmp_path):
    gone = tmp_path / 'gone.txt'
    scanner._positions[str(gone)] = FilePosition(path=str(gone))
    scanner._prune_positions(set())
    assert str(gone) not in scanner._positions
