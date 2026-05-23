"""GitHub release-check controller.

Spawns a daemon thread to query the GitHub releases API; reports the
result back to the GUI thread via a Qt signal so the dialog/header
update happens on the main thread. Self-contained: no other subsystem
depends on its internal state, only on `update_available` which
MainWindow reads to render the "update available" indicator.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
import threading
import webbrowser
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

from utils.version import compare_versions, get_version

logger = logging.getLogger(__name__)

GITHUB_RELEASES_API = (
    "https://api.github.com/repos/wu2c-peter/qso-predictor/releases/latest"
)
GITHUB_RELEASES_PAGE = "https://github.com/wu2c-peter/qso-predictor/releases"


class UpdateChecker(QObject):
    """Background GitHub release check + result dialog handling."""

    # Worker → GUI thread: (version_or_status_token, was_manual)
    # Tokens: "UP_TO_DATE", "ERROR", "NO_REQUESTS", or a version string.
    _result_signal = pyqtSignal(str, bool)

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.update_available: Optional[str] = None  # version string if update available
        self._result_signal.connect(self._on_result)

    def start_check(self, manual: bool = False):
        """Kick off a background check. `manual=True` triggers user-visible result dialogs."""
        t = threading.Thread(target=self._worker, args=(manual,), daemon=True)
        t.start()

    def _worker(self, manual: bool):
        """Worker thread for update check."""
        try:
            import requests  # Lazy import - app works without it
        except ImportError:
            if manual:
                self._result_signal.emit("NO_REQUESTS", manual)
            return

        try:
            r = requests.get(GITHUB_RELEASES_API, timeout=10)
            if r.status_code == 200:
                latest = r.json().get('tag_name', '').lstrip('v')
                current = get_version()
                if latest and compare_versions(current, latest):
                    self._result_signal.emit(latest, manual)
                elif manual:
                    self._result_signal.emit("UP_TO_DATE", manual)
            elif manual:
                self._result_signal.emit("ERROR", manual)
        except Exception:
            if manual:
                self._result_signal.emit("ERROR", manual)
            # Fail silently for automatic checks

    def _on_result(self, result: str, was_manual: bool):
        """Handle update check result on the GUI thread."""
        if result == "UP_TO_DATE":
            QMessageBox.information(
                self.main_window,
                "Up to Date",
                f"You're running the latest version (v{get_version()})."
            )
        elif result == "ERROR":
            QMessageBox.warning(
                self.main_window,
                "Update Check Failed",
                "Couldn't reach GitHub to check for updates.\nPlease check your internet connection."
            )
        elif result == "NO_REQUESTS":
            QMessageBox.warning(
                self.main_window,
                "Update Check Unavailable",
                "The 'requests' module is not installed.\n\n"
                "To enable update checking, run:\n"
                "  pip install requests"
            )
        else:
            # It's a version number - update available
            self.update_available = result
            self.main_window.update_header()

            if was_manual:
                reply = QMessageBox.information(
                    self.main_window,
                    "Update Available",
                    f"A new version is available: v{result}\n\n"
                    f"You're currently running v{get_version()}.\n\n"
                    f"Would you like to open the download page?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    webbrowser.open(GITHUB_RELEASES_PAGE)
