# QSO Predictor - Auto-Discovery & Setup Wizard
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.2.0: New module for automatic detection of ham radio app configurations.
# Reads WSJT-X/JTDX config files to pre-fill callsign, grid, UDP settings.
# Detects port conflicts and recommends optimal network configuration.
# Provides first-run setup wizard and on-demand "Auto-Detect" from Settings.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Auto-Discovery & Setup Wizard for QSO Predictor.

This module is the Qt layer only: the background scan worker and the
wizard dialog. The detection machinery it drives — config-file discovery,
port scanning, running-app detection, and the recommendation engine —
lives in the pure `diagnostics/` package (migration step 2 of
dev-docs/DIAGNOSTICS_SPEC.md), where it is unit-tested cross-platform.

Design principles:
  - Never write to other apps' config files (read-only)
  - Graceful fallback if detection fails
  - User always has final say (recommendations, not mandates)
  - Cross-platform: Windows, macOS, Linux
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QProgressBar, QWidget,
    QGridLayout, QLineEdit, QSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# Detection layer — re-exported here so `from setup_wizard import X` keeps
# working for all pre-step-2 import sites.
from diagnostics.models import DetectedApp, PortInfo, SetupRecommendation
from diagnostics.probe_apps import ConfigFileReader, RunningAppDetector
from diagnostics.probe_ports import PortScanner
from diagnostics.setup_analysis import SetupAnalyzer

logger = logging.getLogger(__name__)


# ============================================================================
# Background Scanner Thread
# ============================================================================

class ScanWorker(QThread):
    """Run detection in background to avoid blocking the UI."""

    scan_complete = pyqtSignal(list, list, list, object)
    # (apps, ports, running_apps, recommendation)
    progress = pyqtSignal(str)

    def run(self):
        try:
            self.progress.emit("Scanning for WSJT-X and JTDX configurations (known paths + search)...")
            reader = ConfigFileReader()
            apps = reader.discover_configs()

            self.progress.emit("Checking for port conflicts...")
            ports = PortScanner.scan_udp_ports(
                extra_ports={a.udp_port for a in apps if a.udp_port})

            self.progress.emit("Detecting running applications...")
            running = RunningAppDetector.detect()

            self.progress.emit("Analyzing configuration...")
            recommendation = SetupAnalyzer.analyze(apps, ports, running)

            self.scan_complete.emit(apps, ports, running, recommendation)

        except Exception as e:
            logger.error(f"Setup scan failed: {e}")
            self.scan_complete.emit([], [], [], SetupRecommendation())


# ============================================================================
# Setup Wizard Dialog
# ============================================================================

class SetupWizardDialog(QDialog):
    """
    The main setup wizard dialog.

    Shows detected configuration and lets user accept or customize.
    Used both for first-run setup and on-demand from Settings.
    """

    def __init__(self, parent=None, first_run=False):
        super().__init__(parent)
        self.first_run = first_run
        self.recommendation = None
        self.detected_apps = []

        self.setWindowTitle(
            "Welcome to QSO Predictor!" if first_run
            else "Auto-Detect Configuration"
        )
        self.resize(560, 500)
        self.setMinimumWidth(480)

        self._init_ui()
        self._start_scan()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        if self.first_run:
            header = QLabel(
                "<h2>Welcome to QSO Predictor!</h2>"
                "<p>Let's set things up. Scanning for your ham radio software...</p>"
            )
        else:
            header = QLabel(
                "<h2>Auto-Detect Configuration</h2>"
                "<p>Scanning for WSJT-X, JTDX, and other ham radio software...</p>"
            )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Progress
        self.progress_label = QLabel("Starting scan...")
        self.progress_label.setStyleSheet("color: #888888;")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress_bar)

        # Results area (initially hidden)
        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_widget.hide()
        layout.addWidget(self.results_widget)

        # Buttons
        self.btn_layout = QHBoxLayout()

        self.btn_manual = QPushButton("Configure Manually")
        self.btn_manual.clicked.connect(self.reject)
        self.btn_manual.setToolTip("Skip auto-detect and configure settings yourself")

        self.btn_apply = QPushButton("Apply Configuration")
        self.btn_apply.clicked.connect(self.accept)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setDefault(True)

        self.btn_layout.addWidget(self.btn_manual)
        self.btn_layout.addStretch()
        self.btn_layout.addWidget(self.btn_apply)
        layout.addLayout(self.btn_layout)

    def _start_scan(self):
        self.worker = ScanWorker()
        self.worker.progress.connect(self._on_progress)
        self.worker.scan_complete.connect(self._on_scan_complete)
        self.worker.start()

    def _on_progress(self, message: str):
        self.progress_label.setText(message)

    def done(self, result):
        # Every exit (Apply → accept, Configure Manually → reject, window
        # close → reject) funnels through done(). The scan thread must not
        # outlive the dialog ("QThread: Destroyed while thread is still
        # running"), and its completion slot must not rebuild widgets in
        # a dialog that's gone.
        worker = getattr(self, 'worker', None)
        if worker is not None and worker.isRunning():
            try:
                worker.scan_complete.disconnect(self._on_scan_complete)
                worker.progress.disconnect(self._on_progress)
            except (TypeError, RuntimeError):
                pass
            worker.wait(10000)
        super().done(result)

    def _on_scan_complete(self, apps, ports, running, recommendation):
        self.detected_apps = apps
        self.recommendation = recommendation

        # Hide progress
        self.progress_bar.hide()
        self.progress_label.hide()

        # Build results display
        self._build_results(apps, ports, running, recommendation)
        self.results_widget.show()
        self.btn_apply.setEnabled(True)

    def _build_results(self, apps, ports, running, rec):
        """Build the results display with detected info and editable fields."""
        layout = self.results_layout

        # --- Detection Summary ---
        summary_group = QGroupBox("What We Found")
        summary_layout = QVBoxLayout(summary_group)

        if apps:
            for app in apps:
                instance_suffix = f" ({app.instance_name})" if app.instance_name else ""
                text = f"✅ <b>{app.name}{instance_suffix}</b>"
                details = []
                if app.callsign:
                    details.append(f"Call: {app.callsign}")
                if app.grid:
                    details.append(f"Grid: {app.grid}")
                if app.udp_port:
                    details.append(f"UDP: {app.udp_ip}:{app.udp_port}")
                if details:
                    text += f" — {', '.join(details)}"
                label = QLabel(text)
                label.setTextFormat(Qt.TextFormat.RichText)
                summary_layout.addWidget(label)
        else:
            no_apps = QLabel(
                "⚠️ No WSJT-X or JTDX configuration files found.\n"
                "You'll need to enter your settings manually."
            )
            no_apps.setStyleSheet("color: #ffaa00;")
            no_apps.setWordWrap(True)
            summary_layout.addWidget(no_apps)

        if running:
            running_label = QLabel(
                f"📡 Running: {', '.join(running)}"
            )
            running_label.setStyleSheet("color: #888888;")
            summary_layout.addWidget(running_label)

        if ports:
            ports_text = ", ".join(
                f"{p.port} ({p.process_name})" for p in ports
            )
            port_label = QLabel(f"🔌 Ports in use: {ports_text}")
            port_label.setStyleSheet("color: #888888;")
            port_label.setWordWrap(True)
            summary_layout.addWidget(port_label)

        layout.addWidget(summary_group)

        # --- Warnings ---
        if rec.warnings:
            for warning in rec.warnings:
                warn_label = QLabel(f"⚠️ {warning}")
                warn_label.setStyleSheet(
                    "color: #ffaa00; padding: 4px; "
                    "border: 1px solid #665500; border-radius: 3px; "
                    "background-color: #332200;"
                )
                warn_label.setWordWrap(True)
                layout.addWidget(warn_label)

        # --- Editable Configuration ---
        config_group = QGroupBox("Recommended Configuration")
        config_layout = QGridLayout(config_group)
        config_layout.setColumnStretch(1, 1)

        row = 0

        # Callsign
        config_layout.addWidget(QLabel("My Callsign:"), row, 0)
        self.edit_callsign = QLineEdit(rec.callsign)
        self.edit_callsign.setPlaceholderText("e.g. W1ABC")
        self.edit_callsign.setMaximumWidth(200)
        config_layout.addWidget(self.edit_callsign, row, 1)
        if rec.callsign:
            source_label = QLabel(f"<small>({rec.source})</small>")
            source_label.setStyleSheet("color: #00cc00;")
            config_layout.addWidget(source_label, row, 2)
        row += 1

        # Grid
        config_layout.addWidget(QLabel("My Grid:"), row, 0)
        self.edit_grid = QLineEdit(rec.grid)
        self.edit_grid.setPlaceholderText("e.g. FN30pr")
        self.edit_grid.setMaximumWidth(200)
        config_layout.addWidget(self.edit_grid, row, 1)
        row += 1

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444444;")
        config_layout.addWidget(line, row, 0, 1, 3)
        row += 1

        # UDP IP
        config_layout.addWidget(QLabel("Listen IP:"), row, 0)
        self.edit_udp_ip = QLineEdit(rec.udp_ip)
        self.edit_udp_ip.setMaximumWidth(200)
        config_layout.addWidget(self.edit_udp_ip, row, 1)
        if rec.use_multicast:
            mc_label = QLabel("<small>(multicast)</small>")
            mc_label.setStyleSheet("color: #00aaff;")
            config_layout.addWidget(mc_label, row, 2)
        row += 1

        # UDP Port
        config_layout.addWidget(QLabel("Listen Port:"), row, 0)
        self.edit_udp_port = QSpinBox()
        self.edit_udp_port.setRange(1024, 65535)
        self.edit_udp_port.setValue(rec.udp_port)
        self.edit_udp_port.setMaximumWidth(200)
        config_layout.addWidget(self.edit_udp_port, row, 1)
        row += 1

        layout.addWidget(config_group)

        # --- Notes ---
        if rec.notes:
            notes_group = QGroupBox("Setup Notes")
            notes_layout = QVBoxLayout(notes_group)
            for note in rec.notes:
                note_label = QLabel(f"💡 {note}")
                note_label.setWordWrap(True)
                note_label.setStyleSheet("color: #aaaaaa; padding: 2px;")
                notes_layout.addWidget(note_label)
            layout.addWidget(notes_group)

        # Confidence indicator
        conf_colors = {'high': '#00cc00', 'medium': '#ffaa00', 'low': '#ff5555'}
        conf_text = {'high': 'High', 'medium': 'Medium', 'low': 'Low'}
        conf_label = QLabel(
            f"<small>Detection confidence: "
            f"<span style='color: {conf_colors[rec.confidence]};'>"
            f"<b>{conf_text[rec.confidence]}</b></span></small>"
        )
        conf_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(conf_label)

    def get_config(self) -> dict:
        """Return the user's chosen configuration as a dict."""
        return {
            'callsign': self.edit_callsign.text().strip().upper(),
            'grid': self.edit_grid.text().strip().upper(),
            'udp_ip': self.edit_udp_ip.text().strip(),
            'udp_port': self.edit_udp_port.value(),
        }


# ============================================================================
# Public API
# ============================================================================

def run_auto_detect() -> Optional[SetupRecommendation]:
    """
    Run auto-detection without UI. Returns recommendation or None.
    Useful for programmatic access or testing.
    """
    reader = ConfigFileReader()
    apps = reader.discover_configs()
    ports = PortScanner.scan_udp_ports(
        extra_ports={a.udp_port for a in apps if a.udp_port})
    running = RunningAppDetector.detect()
    return SetupAnalyzer.analyze(apps, ports, running)


def show_setup_wizard(parent=None, first_run=False) -> Optional[dict]:
    """
    Show the setup wizard dialog.

    Args:
        parent: Parent widget
        first_run: If True, shows welcome messaging

    Returns:
        Dict with config values if accepted, None if cancelled
    """
    dialog = SetupWizardDialog(parent=parent, first_run=first_run)
    try:
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_config()
        return None
    finally:
        # Parented dialogs survive close — release explicitly or each
        # open/close leaks a full widget tree on the parent.
        dialog.deleteLater()


def is_first_run(config) -> bool:
    """
    Check if this looks like a first run (unconfigured defaults).

    Args:
        config: ConfigManager instance
    """
    from config_manager import station_needs_setup
    callsign = config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
    grid = config.get('ANALYSIS', 'my_grid', fallback='FN00aa')
    return station_needs_setup(callsign, grid)
