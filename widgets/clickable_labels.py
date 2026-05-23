"""Clickable QLabel variants used by the target dashboard and header.

ClickableLabel: emits `clicked` and optionally opens a URL when pressed.
ClickableCopyLabel: copies a configured value to the clipboard on click.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import webbrowser

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QApplication, QLabel


class ClickableLabel(QLabel):
    """QLabel that emits `clicked` on mouse press and can open a URL."""

    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_url = None

    def mousePressEvent(self, event):
        if self.update_url:
            webbrowser.open(self.update_url)
        self.clicked.emit()


# --- v2.1.0: CLICKABLE LABEL THAT COPIES VALUE TO CLIPBOARD ---
class ClickableCopyLabel(QLabel):
    """Label that copies a value to clipboard when clicked."""

    copied = pyqtSignal(str)  # Emits the copied value for status bar feedback

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._copy_value = ""
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def set_copy_value(self, value):
        """Set the value that will be copied to clipboard on click."""
        self._copy_value = str(value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._copy_value:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._copy_value)
            self.copied.emit(f"Copied to clipboard: {self._copy_value} Hz")
