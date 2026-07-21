"""Silent-TX audio monitor and Audio Doctor dialog launcher (Windows).

Two responsibilities:

1. Passive monitor: on each WSJT-X TX rising edge (from the UDP status
   stream, tapped pre-throttle in MainWindow.handle_status_update), run
   a short Core Audio meter probe on a daemon worker thread. If WSJT-X
   claims to be transmitting but no audio session/samples reach the rig
   codec, hold a problem verdict that HealthMonitor surfaces as a sticky
   "⚠" status-bar warning via check_tx_health().
2. On-demand Audio Doctor dialog (Tools menu): full configuration audit
   plus an interactive TX-path check.

The monitor stands down while FT8web is the active source — there the
browser, not wsjtx.exe, plays TX audio, so a missing WSJT-X session is
expected and not a fault.

Windows-only at runtime: everything gates on probe_windows.available().
On other platforms the controller is inert (on_status_update no-ops,
check_tx_health reports healthy).

Copyright (C) 2026 Peter Hirst (WU2C)
"""

import logging
import sys
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QDialog, QMessageBox

from audio_doctor.checks import DEFAULT_RIG_HINT, evaluate_tx_probe
from audio_doctor import probe_windows

try:
    from audio_doctor_dialog import AudioDoctorDialog
    AUDIO_DIALOG_AVAILABLE = True
except ImportError:
    AUDIO_DIALOG_AVAILABLE = False

logger = logging.getLogger(__name__)


class AudioHealthController(QObject):
    """Watch the Windows TX audio path; own the Audio Doctor dialog."""

    # Verdict (audio_doctor.models.TxVerdict) or None on probe failure.
    # Class-level signal so the daemon worker thread can hand results
    # back to the Qt main thread (UpdateChecker pattern).
    _verdict_signal = pyqtSignal(object)

    PROBE_INTERVAL_S = 0.1     # 10 Hz sampling
    PROBE_DURATION_S = 4.0     # ~40 samples, well inside a 12.6 s FT8 TX
    PROBE_COOLDOWN_S = 60.0    # at most one passive probe per minute
    WARNING_TTL_S = 600.0      # problem verdict expires if never re-probed

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self._was_transmitting = False
        self._probe_running = False
        self._last_probe_time = 0.0
        self._problem_verdict = None
        self._problem_time = 0.0
        self._verdict_signal.connect(self._on_verdict)

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return probe_windows.available()

    def monitor_enabled(self) -> bool:
        """Passive silent-TX monitoring (on by default, INI-switchable)."""
        if not self.is_available():
            return False
        config = getattr(self.main_window, 'config', None)
        if config is None:
            return True
        value = str(config.get('AUDIO', 'silent_tx_monitor',
                               fallback='true')).strip().lower()
        return value not in ('false', '0', 'no', 'off')

    def rig_hint(self) -> str:
        """Substring identifying the rig's audio interface by name."""
        config = getattr(self.main_window, 'config', None)
        if config is None:
            return DEFAULT_RIG_HINT
        hint = config.get('AUDIO', 'rig_device_hint',
                          fallback=DEFAULT_RIG_HINT)
        return (hint or DEFAULT_RIG_HINT).strip() or DEFAULT_RIG_HINT

    # ------------------------------------------------------------------
    # Passive silent-TX monitor
    # ------------------------------------------------------------------

    def on_status_update(self, transmitting: bool):
        """Tap from handle_status_update, called on EVERY status message
        (pre-throttle) — must stay cheap. A TX rising edge starts a
        one-shot probe on a worker thread, at most once per cooldown."""
        rising = transmitting and not self._was_transmitting
        self._was_transmitting = transmitting
        if not rising or self._probe_running or not self.monitor_enabled():
            return
        # FT8web active → the browser plays TX audio, not wsjtx.exe.
        ft8web = getattr(self.main_window, 'ft8web', None)
        if ft8web and ft8web.is_client_connected():
            return
        now = time.time()
        if now - self._last_probe_time < self.PROBE_COOLDOWN_S:
            return
        self._last_probe_time = now
        self._probe_running = True
        hint = self.rig_hint()   # read config on the main thread
        threading.Thread(target=self._probe_worker, args=(hint,),
                         name="AudioDoctorTxProbe", daemon=True).start()

    def _probe_worker(self, rig_hint):
        """Worker thread: sample the TX path for PROBE_DURATION_S."""
        verdict = None
        try:
            samples = []
            with probe_windows.com_initialized():
                probe = probe_windows.TxPathProbe(rig_hint)
                try:
                    deadline = time.time() + self.PROBE_DURATION_S
                    while time.time() < deadline:
                        samples.append(probe.sample())
                        time.sleep(self.PROBE_INTERVAL_S)
                finally:
                    probe.close()
            verdict = evaluate_tx_probe(samples)
        except Exception:
            logger.exception("Audio Doctor: passive TX probe failed")
        finally:
            self._verdict_signal.emit(verdict)

    def _on_verdict(self, verdict):
        """Back on the Qt main thread."""
        self._probe_running = False
        if verdict is None:
            return
        if verdict.is_problem:
            self._problem_verdict = verdict
            self._problem_time = time.time()
            logger.warning("Audio Doctor: silent TX detected — %s",
                           verdict.headline)
        else:
            if self._problem_verdict is not None:
                logger.info("Audio Doctor: TX audio path healthy again "
                            "(%s)", verdict.value)
            self._problem_verdict = None

    def check_tx_health(self) -> tuple:
        """(is_healthy, message) — same contract as the UDP/MQTT
        check_data_health() sources; consumed by HealthMonitor's
        periodic check so the warning joins the shared sticky line."""
        verdict = self._problem_verdict
        if verdict is None:
            return (True, "")
        if time.time() - self._problem_time > self.WARNING_TTL_S:
            self._problem_verdict = None
            return (True, "")
        return (False,
                f"⚠ TX audio: {verdict.headline} — see Tools → Audio Doctor")

    # ------------------------------------------------------------------
    # Dialog
    # ------------------------------------------------------------------

    def show_dialog(self):
        """Open the Audio Doctor dialog (Tools menu, Windows only)."""
        mw = self.main_window
        if not self.is_available() or not AUDIO_DIALOG_AVAILABLE:
            reason = ("Audio Doctor requires Windows."
                      if sys.platform != 'win32' else
                      "Audio Doctor needs the 'pycaw' package — reinstall "
                      "QSO Predictor or run: pip install pycaw")
            QMessageBox.information(mw, "Audio Doctor", reason)
            return

        dialog = AudioDoctorDialog(parent=mw, rig_hint=self.rig_hint())
        result = dialog.exec()

        # Persist an edited device hint for next time (and for the
        # passive monitor) — but not on Escape (= Rejected), which the
        # user rightly expects to discard experiments.
        if result == QDialog.DialogCode.Accepted:
            new_hint = dialog.current_rig_hint()
            config = getattr(mw, 'config', None)
            if config and new_hint and new_hint != self.rig_hint():
                config.save_setting('AUDIO', 'rig_device_hint', new_hint)
                logger.info("Audio Doctor: rig device hint set to %r",
                            new_hint)
        # Parented dialogs survive close — release explicitly or each
        # open/close leaks a full widget tree on MainWindow.
        dialog.deleteLater()
