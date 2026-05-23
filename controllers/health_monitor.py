"""Periodic data-health monitor and startup connection diagnostics.

Two responsibilities, sharing a small amount of state:

1. Periodic check (every 10s) of UDP and MQTT data flow. When either goes
   silent, surfaces a warning in the status bar; when it resumes, restores
   the previous "normal" status text.
2. On-demand connection-help dialog (wired to a Help-menu action). Looks
   at message counters to decide whether to show the troubleshooting
   dialog or just confirm everything is working.

The controller reads `_decode_count`, `_decode_start_time`, `_normal_status`,
and `str_status` off MainWindow because those are touched by code paths
(UDP handler, status bar) that haven't been moved yet.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QMessageBox

try:
    from startup_health_dialog import StartupHealthDialog
    STARTUP_HEALTH_AVAILABLE = True
except ImportError:
    STARTUP_HEALTH_AVAILABLE = False

logger = logging.getLogger(__name__)


class HealthMonitor(QObject):
    """Monitor UDP/MQTT data flow and surface warnings + troubleshooting dialogs."""

    PERIODIC_INTERVAL_MS = 10_000

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self._last_health_warning = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_data_health)

    def start_periodic_check(self):
        """Begin periodic data-health checks."""
        self._timer.start(self.PERIODIC_INTERVAL_MS)

    # --- v2.1.1: Periodic Data Health Check ---
    def _check_data_health(self):
        """Check if UDP and MQTT data sources are flowing.

        Called every 10 seconds. Shows/clears status bar warnings when data
        sources go silent, without blocking the main thread.
        """
        mw = self.main_window
        warnings = []

        # Check UDP health
        udp = getattr(mw, 'udp', None)
        if udp:
            udp_ok, udp_msg = udp.check_data_health()
            if not udp_ok and udp_msg:
                warnings.append(udp_msg)

        # Check MQTT health
        mqtt = getattr(mw, 'mqtt', None)
        if mqtt:
            mqtt_ok, mqtt_msg = mqtt.check_data_health()
            if not mqtt_ok and mqtt_msg:
                warnings.append(mqtt_msg)

        # MainWindow.update_status_msg is sticky for warnings — a single
        # call holds until clear_health_warning() runs, so we only need to
        # act on transitions: warning_text changed text, or warning lifted.
        warning_text = "   |   ".join(warnings) if warnings else ""
        if warning_text and warning_text != self._last_health_warning:
            mw.update_status_msg(warning_text)
        elif not warning_text and self._last_health_warning:
            mw.clear_health_warning()
        self._last_health_warning = warning_text

    def show_connection_help(self):
        """Manually show the connection help dialog (from Help menu)."""
        has_udp, has_mqtt = self._data_status()
        self._show_dialog(has_udp, has_mqtt)

    def _data_status(self):
        """Return (has_udp, has_mqtt) flags based on current counters."""
        mw = self.main_window
        has_udp = False
        udp = getattr(mw, 'udp', None)
        if udp:
            has_udp = getattr(udp, 'messages_received', 0) > 0
        if not has_udp:
            has_udp = getattr(mw, '_decode_count', 0) > 0

        has_mqtt = False
        str_status = getattr(mw, 'str_status', '')
        if str_status:
            lc = str_status.lower()
            has_mqtt = 'tracking' in lc or 'stations' in lc

        return has_udp, has_mqtt

    def _show_dialog(self, udp_ok, mqtt_ok):
        """Display the startup health check dialog."""
        mw = self.main_window
        if not STARTUP_HEALTH_AVAILABLE:
            configured_port = mw.config.get('NETWORK', 'udp_port', fallback='2237')
            QMessageBox.warning(
                mw,
                "No Data Detected",
                f"QSO Predictor isn't receiving data from WSJT-X or JTDX.\n\n"
                f"Please check:\n"
                f"• WSJT-X/JTDX Settings → Reporting → UDP Server\n"
                f"• Port in WSJT-X/JTDX matches QSO Predictor ({configured_port})\n"
                f"• 'Accept UDP Requests' is checked\n\n"
                f"See Help → Documentation for more details."
            )
            return

        configured_port = int(mw.config.get('NETWORK', 'udp_port', fallback='2237'))

        dialog = StartupHealthDialog(
            parent=mw,
            udp_ok=udp_ok,
            mqtt_ok=mqtt_ok,
            configured_port=configured_port
        )

        result = dialog.exec()

        if dialog.dont_show_again:
            mw.config.save_setting('UI', 'skip_startup_health_check', 'true')

        # "Open Settings" button returns custom code 2
        if result == 2:
            mw.open_settings()

    def get_udp_status(self) -> dict:
        """Get current UDP connection status (called by Settings dialog)."""
        mw = self.main_window
        decode_count = getattr(mw, '_decode_count', 0)
        decode_start: Optional[datetime] = getattr(mw, '_decode_start_time', None)

        if decode_start is None or decode_count == 0:
            return {'receiving': False, 'rate': 0}

        elapsed = (datetime.now() - decode_start).total_seconds()
        if elapsed < 1:
            elapsed = 1  # Avoid division by zero

        rate = (decode_count / elapsed) * 60  # decodes per minute

        return {
            'receiving': decode_count > 0,
            'rate': rate
        }
