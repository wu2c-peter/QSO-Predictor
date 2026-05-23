"""Reusable Qt widgets for QSO Predictor.

These classes were previously inlined in main_v2.py. They are kept here
so the main module can focus on application lifecycle and high-level
wiring; the widgets themselves have no dependency on MainWindow.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

from .clickable_labels import ClickableLabel, ClickableCopyLabel
from .tactical_toast import TacticalToast
from .target_dashboard import TargetDashboard
from .decode_table import DecodeTableModel, HuntHighlightDelegate

__all__ = [
    "ClickableLabel",
    "ClickableCopyLabel",
    "TacticalToast",
    "TargetDashboard",
    "DecodeTableModel",
    "HuntHighlightDelegate",
]
