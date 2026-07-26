"""
Diagnostics controller: assembles the doctor registry and runs checkups.

Owns the app-side wiring of the Doctors framework (DIAGNOSTICS_SPEC.md
step 4): registers the doctors at startup (Audio Doctor's adapter plus
the in-package Clock Doctor), runs Full Checkup / single-doctor
checkups on a worker thread (the probe pass does I/O — COM, sockets,
filesystem), and shows the results dialog.

The rig hint is snapshotted from config ON THE MAIN THREAD each time a
checkup starts (same convention as AudioHealthController), then read by
the Audio Doctor's per-run hint callable from the worker.

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from diagnostics import registry as doctor_registry
from diagnostics.doctors.clock import ClockDoctor
from utils.version import get_version

logger = logging.getLogger(__name__)


class DiagnosticsController(QObject):
    """Runs checkups and shows results. Follows the controllers pattern:
    QObject with a main_window back-reference."""

    _checkup_ready = pyqtSignal(object)     # CheckupRun or None

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._busy = False
        self._rig_hint_snapshot = ''
        self._checkup_ready.connect(self._show_results)
        self._register_doctors()

    # --- Registry assembly ---------------------------------------------

    def _register_doctors(self):
        """Assemble the doctor list, in display order. Idempotent so a
        second controller (tests, window re-creation) doesn't trip the
        registry's duplicate-id guard."""
        ids = {d.id for d in doctor_registry.registered_doctors()}
        if 'audio' not in ids:
            from audio_doctor.doctor import register as register_audio
            register_audio(rig_hint=lambda: self._rig_hint_snapshot)
        if 'clock' not in ids:
            doctor_registry.register(ClockDoctor())

    # --- Entry points (menu actions; main thread) -----------------------

    def run_full_checkup(self):
        self._start(doctor_ids=None, title="Diagnostics — Full Checkup")

    def run_clock_doctor(self):
        self._start(doctor_ids={'clock'}, title="Clock Doctor")

    # Context domains gathered on every checkup beyond what the doctors
    # declare: the report's Station identity line and Details tables
    # read these (no current doctor declares 'apps'/'udp_ports' — the
    # Config and Network Doctors will).
    CONTEXT_DOMAINS = frozenset({'apps', 'udp_ports'})

    def _start(self, doctor_ids, title):
        if self._busy:
            return
        self._busy = True
        self._dialog_title = title
        try:
            # Config reads stay on the main thread (AudioHealthController
            # convention).
            audio_health = getattr(self.main_window, 'audio_health', None)
            self._rig_hint_snapshot = (audio_health.rig_hint()
                                       if audio_health else '')
            if doctor_ids is None:
                doctors = None
            else:
                doctors = [d for d in doctor_registry.registered_doctors()
                           if d.id in doctor_ids]
            # Busy feedback: probing can take several seconds (COM on
            # Windows; NTP/DNS timeouts when offline).
            from PyQt6.QtGui import QCursor
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QApplication
            QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
            self._cursor_set = True
            if hasattr(self.main_window, 'update_status_msg'):
                self.main_window.update_status_msg(
                    "Diagnostics: running checkup…")
            threading.Thread(target=self._worker, args=(doctors,),
                             name="DiagnosticsCheckup", daemon=True).start()
        except Exception:
            logger.exception("Diagnostics: could not start checkup")
            self._restore_cursor()
            self._busy = False

    # --- Worker ---------------------------------------------------------

    def _worker(self, doctors):
        run = None
        try:
            run = doctor_registry.run_checkup(
                doctors=doctors, extra_domains=self.CONTEXT_DOMAINS)
        except Exception:
            logger.exception("Diagnostics: checkup failed")
        try:
            self._checkup_ready.emit(run)
        except RuntimeError:
            pass    # window deleted while we were working

    def _restore_cursor(self):
        if getattr(self, '_cursor_set', False):
            from PyQt6.QtWidgets import QApplication
            QApplication.restoreOverrideCursor()
            self._cursor_set = False

    # --- Results (main thread) ------------------------------------------

    def _show_results(self, run):
        self._busy = False
        self._restore_cursor()
        if run is None:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.main_window, "Diagnostics",
                "The checkup failed — see the log file for details.")
            return
        from widgets.checkup_dialog import CheckupDialog
        dialog = CheckupDialog(parent=self.main_window, checkup=run,
                               tool_name="QSO Predictor",
                               tool_version=get_version(),
                               title=self._dialog_title)
        dialog.exec()
