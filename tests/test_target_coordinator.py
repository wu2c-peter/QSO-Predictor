# QSO Predictor test suite
# Copyright (C) 2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Path state must not leak from one target to the next.

2026-11-25, live on 80m: the operator went from K4JJL (US) to LY5A
(KO15) via a JTDX sync. LY5A had no row in the decode table, so nothing
recomputed the path — and the Insights panel went on showing K4JJL's
"Your signal reported nearby / Spotted at -9 dB by NK5B" under the
LY5A header, while the status bar correctly said "0 near target".
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from PyQt6.QtCore import QObject

from local_intel.models import PathStatus

# Load the module by path: `from controllers.target_coordinator import …`
# runs controllers/__init__.py, which imports every controller — some
# pull in QtWidgets, and the Linux CI runners have no display libraries
# (libEGL). target_coordinator.py itself needs only QtCore.
_spec = importlib.util.spec_from_file_location(
    "_target_coordinator_under_test",
    Path(__file__).resolve().parent.parent / "controllers" / "target_coordinator.py")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
TargetCoordinator = _module.TargetCoordinator


def _coordinator(rows):
    mw = MagicMock()
    mw.model._data = rows
    mw.analyzer.call_grid_map = {'LY5A': 'KO15'}
    mw.current_target_call = 'K4JJL'
    tc = TargetCoordinator.__new__(TargetCoordinator)
    QObject.__init__(tc)
    tc.main_window = mw
    return tc, mw


def test_target_without_a_decode_row_resets_path_state():
    tc, mw = _coordinator(rows=[])
    tc.set_target('LY5A')
    mw.local_intel.set_path_status.assert_called_once_with(PathStatus.UNKNOWN)
    mw._update_local_intel_path_status.assert_not_called()


def test_target_with_a_decode_row_takes_path_from_that_row():
    row = {'call': 'LY5A', 'grid': 'KO15', 'freq': 1500,
           'path': 'Not Reported in Region', 'competition': 'Clear'}
    tc, mw = _coordinator(rows=[row])
    tc.set_target('LY5A')
    mw._update_local_intel_path_status.assert_called_once_with(row)
    mw.local_intel.set_path_status.assert_not_called()


def test_clearing_the_target_resets_path_state():
    tc, mw = _coordinator(rows=[])
    tc.set_target('')
    mw.local_intel.set_path_status.assert_called_once_with(PathStatus.UNKNOWN)
