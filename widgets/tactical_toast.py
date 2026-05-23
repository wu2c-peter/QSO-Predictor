"""Thin notification bar for tactical observations.

Shows event-driven alerts (hidden pileups, path changes, competition
shifts) and auto-dismisses after 8 seconds. Rate-limited to one toast
per 15 seconds to avoid spam; queued toasts are deduped to the most
recent.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel

from local_intel.models import PathStatus


# --- v2.2.0: TACTICAL OBSERVATION TOASTS ---
class TacticalToast(QFrame):
    """Thin notification bar for tactical observations.

    Shows event-driven alerts like hidden pileups, path changes,
    and competition shifts. Auto-dismisses after 8 seconds.
    Rate-limited to 1 toast per 15 seconds to avoid spam.
    """

    # Style presets by priority
    STYLES = {
        'warning': "background-color: #3A2800; color: #FFA500; border: 1px solid #664400; border-radius: 3px; padding: 4px 12px; font-weight: bold;",
        'success': "background-color: #002A00; color: #00FF00; border: 1px solid #004400; border-radius: 3px; padding: 4px 12px; font-weight: bold;",
        'info':    "background-color: #001A2A; color: #00CCFF; border: 1px solid #003344; border-radius: 3px; padding: 4px 12px; font-weight: bold;",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(4)

        self._label = QLabel()
        self._label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self._label, 1)

        self._dismiss_btn = QLabel("✕")
        self._dismiss_btn.setStyleSheet("color: #888; font-size: 14px; font-weight: bold;")
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.mousePressEvent = lambda e: self._dismiss()
        layout.addWidget(self._dismiss_btn)

        # Auto-dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)

        # Rate limiting
        self._last_show_time = 0
        self._min_interval = 15  # seconds between toasts
        self._queue = []  # [(message, style_key)]

        # State tracking for change detection
        self._prev_competition_count = 0
        self._prev_path_status = ""
        self._prev_reporting_near_target = 0

    def show_toast(self, message, style='info', duration=8000):
        """Show a toast notification, or queue it if rate-limited."""
        now = time.time()
        elapsed = now - self._last_show_time

        if elapsed < self._min_interval and self.isVisible():
            # Rate-limited — queue it (keep only the latest)
            self._queue = [(message, style)]
            return

        self._display(message, style, duration)

    def _display(self, message, style, duration):
        """Actually show the toast."""
        self._label.setText(message)
        self.setStyleSheet(self.STYLES.get(style, self.STYLES['info']))
        self._last_show_time = time.time()
        self._timer.start(duration)
        self.show()

    def _dismiss(self):
        """Hide toast and show queued toast if any."""
        self._timer.stop()
        self.hide()

        # Show queued toast after a brief pause
        if self._queue:
            msg, style = self._queue.pop(0)
            QTimer.singleShot(500, lambda: self._display(msg, style, 8000))

    def check_competition_change(self, competition_str, local_callers):
        """Detect and toast competition changes.

        Args:
            competition_str: e.g. "High (4)", "PILEUP (8)", "Low (1)", "High (6) local"
            local_callers: int count from local pileup tracking
        """
        # Extract count from competition string
        count = 0
        if competition_str and '(' in competition_str:
            try:
                count = int(competition_str.split('(')[1].split(')')[0])
            except (ValueError, IndexError):
                pass

        # v2.2.1: Local decode data is never "hidden" — you can see it
        is_local_source = 'local' in str(competition_str).lower()

        prev = self._prev_competition_count
        self._prev_competition_count = count

        # Skip if no previous data (first update)
        if prev == 0 and count == 0:
            return

        # Hidden pileup detection — only for PSK Reporter data, not local decodes
        if count >= 3 and local_callers <= 1 and prev < 3 and not is_local_source:
            self.show_toast(
                f"⚠️ Hidden pileup: {local_callers} caller{'s' if local_callers != 1 else ''} locally, "
                f"{count} at target's end — you can't hear your competition",
                'warning'
            )
        # Significant pileup growth
        elif count >= prev + 3 and prev > 0:
            self.show_toast(
                f"📈 Competition increasing at target: was {prev}, now {count}",
                'warning'
            )
        # Pileup thinning
        elif count <= prev - 3 and count > 0 and prev > 3:
            self.show_toast(
                f"📉 Competition dropping at target: was {prev}, now {count}",
                'success'
            )

    def check_path_change(self, new_path_status, target_call):
        """Detect and toast path status changes."""
        prev = self._prev_path_status
        self._prev_path_status = new_path_status

        if not prev or not target_call:
            return

        good = (PathStatus.HEARD_BY_TARGET, PathStatus.REPORTED_IN_REGION)
        bad = (PathStatus.NOT_REPORTED_IN_REGION,)  # other no-evidence states stay quiet
        new_status = PathStatus.from_display(new_path_status)
        prev_status = PathStatus.from_display(prev)

        # Path opened (wasn't connected/open, now is)
        if new_status in good and prev_status not in good:
            if new_status == PathStatus.HEARD_BY_TARGET:
                self.show_toast(
                    f"🎯 {target_call} has decoded YOU — call now!",
                    'success'
                )
            else:
                self.show_toast(
                    f"🟢 Path to {target_call}'s region confirmed!",
                    'success'
                )
        # Path lost
        elif new_status in bad and prev_status in good:
            self.show_toast(
                f"🔴 Path to {target_call}'s region no longer confirmed",
                'warning'
            )

    def check_near_target_spotted(self, near_target_count, target_call):
        """Toast when first spotted near target."""
        prev = self._prev_reporting_near_target
        self._prev_reporting_near_target = near_target_count

        if prev == 0 and near_target_count > 0 and target_call:
            self.show_toast(
                f"📡 You've been spotted near {target_call}! Keep calling",
                'success'
            )

    def reset_state(self):
        """Reset state tracking (called on target clear/change)."""
        self._prev_competition_count = 0
        self._prev_path_status = ""
        self._prev_reporting_near_target = 0
        self._queue.clear()
        self._dismiss()
