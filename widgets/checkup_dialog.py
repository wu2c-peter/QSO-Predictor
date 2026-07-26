"""
Checkup results dialog — shows a CheckupRun and exports the report.

The shared findings view for the Doctors framework (DIAGNOSTICS_SPEC.md
step 4): findings worst-first with the framework's severity colors and
symbols, then not-checked doctors, then a passed summary. Copy/Save
export the standard markdown report from diagnostics.report — the
artifact users paste into forums or an LLM chat. The identity checkbox
maps to render_report(include_identity=...).

QSO Predictor
Copyright (C) 2026 Peter Hirst (WU2C)
"""

import html
import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTextBrowser, QVBoxLayout
)

from diagnostics.models import Severity
from diagnostics.report import render_report, report_filename

logger = logging.getLogger(__name__)


class CheckupDialog(QDialog):
    """Results of one checkup (full or single-doctor), with report export."""

    def __init__(self, parent=None, checkup=None, tool_name="QSO Predictor",
                 tool_version="", title="Diagnostics"):
        super().__init__(parent)
        self.checkup = checkup
        self.tool_name = tool_name
        self.tool_version = tool_version
        self.setWindowTitle(title)
        self.resize(640, 520)
        self._init_ui()

    # --- UI -------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)

        view = QTextBrowser()
        view.setOpenExternalLinks(False)
        view.setHtml(self._build_html())
        layout.addWidget(view)

        self.identity_check = QCheckBox(
            "Include callsign and grid in the exported report")
        self.identity_check.setChecked(True)
        self.identity_check.setToolTip(
            "Callsign and grid help forum helpers; uncheck to export an "
            "anonymous report.")
        layout.addWidget(self.identity_check)

        hint = QLabel(
            "Copy or save the report, then paste it into a forum post or "
            "your favorite AI assistant — it starts with instructions for "
            "the reader.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888888;")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.btn_copy = QPushButton("Copy Report")
        btn_copy = self.btn_copy
        btn_copy.clicked.connect(self._copy_report)
        btn_save = QPushButton("Save Report…")
        btn_save.clicked.connect(self._save_report)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_close.setDefault(True)
        buttons.addWidget(btn_copy)
        buttons.addWidget(btn_save)
        buttons.addStretch()
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)

    def _build_html(self) -> str:
        c = self.checkup
        parts = []

        flat = [(e.title, r) for e in c.entries for r in e.results]
        problems = sorted(
            [(t, r) for t, r in flat if r.severity >= Severity.WARNING],
            key=lambda tr: tr[1].severity, reverse=True)
        unknowns = [(t, r) for t, r in flat
                    if r.severity == Severity.UNKNOWN]

        if problems:
            parts.append("<h3>Findings</h3>")
            for doctor_title, r in problems:
                fix = (f"<br><i>Fix: {html.escape(r.fix)}</i>"
                       if r.fix else "")
                parts.append(
                    f"<p><span style='color:{r.severity.color}; "
                    f"font-weight:bold'>{r.severity.symbol} "
                    f"{html.escape(r.title)}</span> "
                    f"<span style='color:#888888'>"
                    f"({html.escape(doctor_title)})</span><br>"
                    f"{html.escape(r.detail)}{fix}</p>")
        else:
            parts.append(
                "<h3><span style='color:#00C853'>✓ No problems found"
                "</span></h3><p>All checks that ran came back clean.</p>")

        if c.skipped or unknowns:
            parts.append("<h3>Not checked</h3><ul>")
            for s in c.skipped:
                parts.append(f"<li>{html.escape(s.title)}: "
                             f"{html.escape(s.reason)}</li>")
            for doctor_title, r in unknowns:
                parts.append(f"<li>? {html.escape(r.title)} — "
                             f"{html.escape(r.detail)}</li>")
            parts.append("</ul>")

        passed_bits = []
        for entry in c.entries:
            n = sum(1 for r in entry.results
                    if r.severity in (Severity.OK, Severity.INFO))
            if n:
                passed_bits.append(f"{html.escape(entry.title)}: {n}")
        if passed_bits:
            parts.append(
                f"<p style='color:#888888'>Passed checks — "
                f"{'; '.join(passed_bits)} (full list in the report).</p>")

        return "".join(parts)

    # --- Export ---------------------------------------------------------

    def _report_text(self) -> str:
        return render_report(self.checkup, self.tool_name,
                             self.tool_version,
                             include_identity=self.identity_check.isChecked())

    def _copy_report(self):
        QApplication.clipboard().setText(self._report_text())
        # Feedback, per the ClickableCopyLabel convention elsewhere in
        # the app: the user must be able to tell the copy happened.
        self.btn_copy.setText("Copied ✓")
        self.btn_copy.setEnabled(False)
        QTimer.singleShot(1500, self._reset_copy_button)

    def _reset_copy_button(self):
        self.btn_copy.setText("Copy Report")
        self.btn_copy.setEnabled(True)

    def _save_report(self):
        default = report_filename(self.tool_name,
                                  self.checkup.snapshot.taken_at_utc)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save diagnostic report", default,
            "Markdown (*.md);;All files (*)")
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self._report_text())
        except OSError as e:
            logger.error(f"Diagnostics: saving report failed: {e}")
            QMessageBox.warning(self, "Save failed",
                                f"Could not save the report:\n{e}")
