"""Audio Doctor dialog — methodical Windows audio-path troubleshooting.

Two panels:
1. Configuration audit — read-only checklist over a full snapshot of
   Windows audio state (device roles, ducking, persisted per-app mixer
   state, endpoint formats, stale duplicates, Fast Startup).
2. Live TX-path check — the user presses Tune in WSJT-X, we watch the
   per-session and endpoint peak meters for a few seconds and return a
   verdict pointing at the exact layer that is silent.

All COM/registry work runs on daemon worker threads (main thread never
blocks); results come back via signals. Launched by
controllers/audio_health.py from the Tools menu (Windows only).

Copyright (C) 2026 Peter Hirst (WU2C)
"""

import html
import logging
import threading
import time

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from audio_doctor import probe_windows
from audio_doctor.checks import evaluate_tx_probe, run_checks, summarize_checks
from audio_doctor.models import (SettingsPanel, Severity, TxVerdict,
                                 verdict_display)

logger = logging.getLogger(__name__)

PROBE_INTERVAL_S = 0.1
PROBE_DURATION_S = 4.0
PROBE_TOTAL_SAMPLES = int(PROBE_DURATION_S / PROBE_INTERVAL_S)


class AudioDoctorDialog(QDialog):
    """Windows audio-path diagnostics for the rig's USB codec."""

    # Worker → main thread. object payloads: list[CheckResult] /
    # TxVerdict; None signals a failed run.
    _audit_ready = pyqtSignal(object)
    _probe_progress = pyqtSignal(int)
    _probe_ready = pyqtSignal(object)

    def __init__(self, parent=None, rig_hint="USB Audio CODEC",
                 ft8web_connected=None):
        """ft8web_connected: optional zero-arg callable; truthy return
        switches the TX check to browser mode (FT8web is the source, so
        the browser — not wsjtx.exe — plays TX audio). Evaluated at
        probe start so mid-dialog connects/disconnects are honored."""
        super().__init__(parent)
        self._busy = False
        self._ft8web_connected = ft8web_connected
        self._probe_browser = False
        self.setWindowTitle("Audio Doctor")
        self.setModal(True)
        self.setMinimumSize(680, 560)
        self._setup_ui(rig_hint)
        self._audit_ready.connect(self._show_audit)
        self._probe_progress.connect(self._show_probe_progress)
        self._probe_ready.connect(self._show_probe_verdict)
        self._start_audit()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self, rig_hint):
        self.setStyleSheet("""
            QDialog { background-color: #2a2a2a; color: #EEE; }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title { color: #DAA520; padding: 0 4px; }
            QLabel { color: #EEE; }
            QLineEdit {
                background-color: #1a1a1a; color: #EEE;
                border: 1px solid #444; border-radius: 3px; padding: 3px;
            }
            QPushButton {
                background-color: #333; color: #EEE;
                border: 1px solid #555; border-radius: 3px;
                padding: 5px 14px;
            }
            QPushButton:hover { background-color: #3d3d3d; }
            QPushButton:disabled { color: #777; }
            QScrollArea { border: none; }
            /* Windows: the scroll viewport + content widget paint the OS
               palette (white in light mode) unless styled explicitly —
               without these two rules the audit renders white-on-white.
               (Found in v2.6.0 Windows smoke testing.) */
            QWidget#auditViewport, QWidget#auditContainer {
                background-color: #1a1a1a;
            }
        """)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Read-only diagnosis of the Windows audio path between "
            "WSJT-X/JTDX and your rig. Nothing is changed — each finding "
            "tells you where to fix it.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Device hint row
        hint_row = QHBoxLayout()
        hint_row.addWidget(QLabel("Rig audio device name contains:"))
        self.hint_edit = QLineEdit(rig_hint)
        self.hint_edit.setToolTip(
            "Substring matched against Windows device names. The default "
            "matches SignaLink, Digirig and most rig-integrated codecs.")
        hint_row.addWidget(self.hint_edit, stretch=1)
        self.rescan_button = QPushButton("Re-scan")
        self.rescan_button.clicked.connect(self._start_audit)
        hint_row.addWidget(self.rescan_button)
        layout.addLayout(hint_row)

        # Audit panel
        audit_group = QGroupBox("Configuration audit")
        audit_layout = QVBoxLayout(audit_group)
        self.audit_label = QLabel("Scanning Windows audio state…")
        self.audit_label.setWordWrap(True)
        self.audit_label.setTextFormat(Qt.TextFormat.RichText)
        self.audit_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.audit_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.audit_label.setOpenExternalLinks(False)
        self.audit_label.linkActivated.connect(self._open_panel_link)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setObjectName("auditViewport")
        inner = QWidget()
        inner.setObjectName("auditContainer")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.addWidget(self.audit_label)
        inner_layout.addStretch()
        scroll.setWidget(inner)
        audit_layout.addWidget(scroll)
        layout.addWidget(audit_group, stretch=3)

        # Live TX probe panel
        probe_group = QGroupBox("Live TX path check")
        probe_layout = QVBoxLayout(probe_group)
        probe_intro = QLabel(
            "Press <b>Tune</b> in WSJT-X (or wait for a TX cycle), then "
            "click the button. The check watches the Windows peak meters "
            f"for {PROBE_DURATION_S:.0f} seconds and reports which layer "
            "of the TX path is silent, if any. When FT8web is connected, "
            "the check watches the browser's audio instead — start a "
            "transmission in FT8web first.<br>"
            "<span style='color:#9E9E9E'>Tip: this check reads the LIVE "
            "audio session — Windows' own Volume mixer page shows stale, "
            "greyed-out values unless WSJT-X is already transmitting "
            "when you open it. To see or change the real WSJT-X slider: "
            "press Tune FIRST, then open the mixer. Trust this verdict "
            "over what the mixer displays.</span>")
        probe_intro.setWordWrap(True)
        probe_intro.setTextFormat(Qt.TextFormat.RichText)
        probe_layout.addWidget(probe_intro)
        button_row = QHBoxLayout()
        self.probe_button = QPushButton("Check TX path")
        self.probe_button.clicked.connect(self._start_probe)
        button_row.addWidget(self.probe_button)
        self.probe_status = QLabel("")
        button_row.addWidget(self.probe_status, stretch=1)
        probe_layout.addLayout(button_row)
        self.verdict_label = QLabel("")
        self.verdict_label.setWordWrap(True)
        self.verdict_label.setTextFormat(Qt.TextFormat.RichText)
        self.verdict_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.verdict_label.setOpenExternalLinks(False)
        self.verdict_label.linkActivated.connect(self._open_panel_link)
        probe_layout.addWidget(self.verdict_label)
        layout.addWidget(probe_group, stretch=1)

        # Bottom row
        bottom = QHBoxLayout()
        bottom.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        bottom.addWidget(close_button)
        layout.addLayout(bottom)

    def current_rig_hint(self) -> str:
        """Read by the controller after exec() to persist edits."""
        return self.hint_edit.text().strip()

    @staticmethod
    def _panel_link(panel) -> str:
        """Anchor HTML for an 'Open ...' settings link, or ''."""
        if panel is None:
            return ""
        return (f" <a href='panel:{panel.value}' "
                f"style='color:#40C4FF'>{html.escape(panel.label)}</a>")

    def _open_panel_link(self, href: str):
        if href.startswith("panel:"):
            try:
                panel = SettingsPanel(href[len("panel:"):])
            except ValueError:
                return
            probe_windows.open_settings_panel(panel)

    def _set_busy(self, busy):
        self._busy = busy
        self.rescan_button.setEnabled(not busy)
        self.probe_button.setEnabled(not busy)

    # ------------------------------------------------------------------
    # Configuration audit
    # ------------------------------------------------------------------

    def _start_audit(self):
        if self._busy:
            return
        self._set_busy(True)
        self.audit_label.setText("Scanning Windows audio state…")
        hint = self.current_rig_hint() or "USB Audio CODEC"
        threading.Thread(target=self._audit_worker, args=(hint,),
                         name="AudioDoctorAudit", daemon=True).start()

    def _audit_worker(self, rig_hint):
        payload = None
        try:
            with probe_windows.com_initialized():
                snapshot = probe_windows.gather_snapshot()
            results = run_checks(snapshot, rig_hint=rig_hint)
            payload = (results, list(snapshot.errors))
        except Exception:
            logger.exception("Audio Doctor: audit failed")
        try:
            self._audit_ready.emit(payload)
        except RuntimeError:
            pass    # dialog closed and deleted while we were working

    def _show_audit(self, payload):
        self._set_busy(False)
        if payload is None:
            self.audit_label.setText(
                "<span style='color:#FF5252'>The audit failed — see the "
                "log file for details.</span>")
            return
        results, errors = payload
        # Worst first so problems are visible without scrolling.
        ordered = sorted(results, key=lambda r: r.severity, reverse=True)
        rows = []
        for r in ordered:
            # Render the settings link even when there's no fix text —
            # a panel without a fix (or vice versa) must not vanish.
            fix = (f"<br><i>Fix: {html.escape(r.fix)}</i>" if r.fix else "")
            fix += self._panel_link(r.panel)
            rows.append(
                f"<tr>"
                f"<td style='color:{r.severity.color}; font-weight:bold; "
                f"padding:4px 10px 4px 0; white-space:nowrap; "
                f"vertical-align:top'>{r.severity.symbol} "
                f"{r.severity.label}</td>"
                # Explicit color: rich-text spans don't reliably inherit the
                # QLabel stylesheet color on all platforms.
                f"<td style='padding:4px 0; color:#EEE'>"
                f"<b>{html.escape(r.title)}</b>"
                f"<br>{html.escape(r.detail)}{fix}</td></tr>")
        html_text = "<table cellspacing='0'>" + "".join(rows) + "</table>"
        if errors:
            notes = "; ".join(html.escape(e) for e in errors)
            html_text += (f"<p style='color:#9E9E9E'><i>Probe notes: "
                          f"{notes}</i></p>")
        _, summary = summarize_checks(results)
        logger.info("Audio Doctor audit: %s", summary)
        self.audit_label.setText(html_text)

    # ------------------------------------------------------------------
    # Live TX probe
    # ------------------------------------------------------------------

    def _start_probe(self):
        if self._busy:
            return
        self._set_busy(True)
        self.verdict_label.setText("")
        try:
            self._probe_browser = bool(self._ft8web_connected
                                       and self._ft8web_connected())
        except Exception:
            self._probe_browser = False
        self.probe_status.setText(
            "Sampling (FT8web browser mode)…" if self._probe_browser
            else "Sampling…")
        hint = self.current_rig_hint() or "USB Audio CODEC"
        threading.Thread(target=self._probe_worker,
                         args=(hint, self._probe_browser),
                         name="AudioDoctorProbe", daemon=True).start()

    def _probe_worker(self, rig_hint, browser_mode):
        verdict = None
        try:
            samples = []
            with probe_windows.com_initialized():
                # Browser mode: bind whatever session plays on the rig
                # device — during a browser TX that IS the app under test.
                probe = probe_windows.TxPathProbe(
                    rig_hint, app_names=None if browser_mode else
                    ("wsjtx.exe", "jtdx.exe"))
                try:
                    for i in range(PROBE_TOTAL_SAMPLES):
                        samples.append(probe.sample())
                        if i % 5 == 0:
                            try:
                                self._probe_progress.emit(i + 1)
                            except RuntimeError:
                                return    # dialog gone — stop sampling
                        time.sleep(PROBE_INTERVAL_S)
                finally:
                    probe.close()
            verdict = evaluate_tx_probe(samples)
        except Exception:
            logger.exception("Audio Doctor: TX probe failed")
        try:
            self._probe_ready.emit(verdict)
        except RuntimeError:
            pass

    def _show_probe_progress(self, count):
        self.probe_status.setText(
            f"Sampling… {count}/{PROBE_TOTAL_SAMPLES}")

    def _show_probe_verdict(self, verdict):
        self._set_busy(False)
        self.probe_status.setText("")
        if verdict is None:
            self.verdict_label.setText(
                "<span style='color:#FF5252'>The TX check failed — see "
                "the log file for details.</span>")
            return
        if verdict == TxVerdict.AUDIO_FLOWING:
            color = Severity.OK.color
        elif verdict.is_problem:
            color = Severity.FAIL.color
        else:
            color = Severity.UNKNOWN.color
        text = verdict_display(verdict, browser=self._probe_browser)
        fix = (f"<br><i>Fix: {html.escape(text.fix)}</i>"
               if text.fix else "")
        fix += self._panel_link(verdict.panel)
        self.verdict_label.setText(
            f"<b style='color:{color}'>{html.escape(text.headline)}</b>"
            f"<br>{html.escape(text.explanation)}{fix}")
        logger.info("Audio Doctor TX check: %s%s", verdict.value,
                    " (browser mode)" if self._probe_browser else "")
