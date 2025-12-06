# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.


from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QTabWidget, QWidget, 
                             QFormLayout, QMessageBox, QComboBox, QGroupBox,
                             QSpinBox)
from PyQt6.QtCore import Qt


# Common UDP configurations
UDP_PRESETS = {
    "Standard (localhost)": ("127.0.0.1", 2237),
    "Multicast (JTAlert/N3FJP)": ("239.0.0.2", 2237),
    "Custom": (None, None),  # User-defined
}


class SettingsDialog(QDialog):
    def __init__(self, config, parent=None, udp_status=None):
        """
        Initialize settings dialog.
        
        Args:
            config: ConfigManager instance
            parent: Parent widget
            udp_status: Optional dict with 'receiving' (bool) and 'rate' (decodes/min)
        """
        super().__init__(parent)
        self.config = config
        self.udp_status = udp_status
        self.setWindowTitle("Configuration")
        self.resize(500, 420)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        
        # Tab 1: Station
        tab_station = QWidget()
        form_station = QFormLayout()
        self.inp_call = QLineEdit(self.config.get('ANALYSIS', 'my_callsign'))
        self.inp_grid = QLineEdit(self.config.get('ANALYSIS', 'my_grid'))
        form_station.addRow("My Callsign:", self.inp_call)
        form_station.addRow("My Grid Square:", self.inp_grid)
        tab_station.setLayout(form_station)
        tabs.addTab(tab_station, "Station")

        # Tab 2: Network (enhanced)
        tab_net = QWidget()
        net_layout = QVBoxLayout(tab_net)
        
        # UDP Status indicator
        status_group = QGroupBox("Connection Status")
        status_layout = QHBoxLayout(status_group)
        self.status_indicator = QLabel()
        self._update_status_display()
        status_layout.addWidget(self.status_indicator)
        status_layout.addStretch()
        net_layout.addWidget(status_group)
        
        # UDP Configuration group
        udp_group = QGroupBox("UDP Configuration")
        udp_layout = QVBoxLayout(udp_group)
        
        # Preset selector
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Setup:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(UDP_PRESETS.keys())
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self.preset_combo, 1)
        udp_layout.addLayout(preset_layout)
        
        # IP and Port fields
        fields_layout = QFormLayout()
        self.inp_ip = QLineEdit(self.config.get('NETWORK', 'udp_ip'))
        self.inp_ip.textChanged.connect(self._on_manual_change)
        fields_layout.addRow("Listen IP:", self.inp_ip)
        
        port_layout = QHBoxLayout()
        self.inp_port = QSpinBox()
        self.inp_port.setRange(1024, 65535)
        self.inp_port.setValue(int(self.config.get('NETWORK', 'udp_port', fallback='2237')))
        self.inp_port.valueChanged.connect(self._on_manual_change)
        port_layout.addWidget(self.inp_port)
        port_layout.addStretch()
        fields_layout.addRow("Listen Port:", port_layout)
        
        udp_layout.addLayout(fields_layout)
        
        # Help text
        help_label = QLabel(
            "<small><b>Port tips:</b> Default is 2237. If another app (GridTracker, JTAlert) "
            "already uses this port, try 2238 or 2239.<br>"
            "<b>Multicast:</b> Use if JTDX sends to a multicast group (e.g., 239.0.0.2) "
            "so multiple apps can receive.<br>"
            "<b>Important:</b> WSJT-X/JTDX UDP settings must match.</small>"
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #888888; padding: 8px;")
        udp_layout.addWidget(help_label)
        
        net_layout.addWidget(udp_group)
        
        # Forward ports
        fwd_group = QGroupBox("UDP Forwarding (Optional)")
        fwd_layout = QFormLayout(fwd_group)
        self.inp_fwd = QLineEdit(self.config.get('NETWORK', 'forward_ports'))
        fwd_layout.addRow("Forward to ports:", self.inp_fwd)
        fwd_help = QLabel(
            "<small>Comma-separated ports to forward received packets to (e.g., 2238,2239).<br>"
            "Useful for daisy-chaining to other apps.</small>"
        )
        fwd_help.setWordWrap(True)
        fwd_help.setStyleSheet("color: #888888;")
        fwd_layout.addRow(fwd_help)
        net_layout.addWidget(fwd_group)
        
        net_layout.addStretch()
        tabs.addTab(tab_net, "Network")

        # Tab 3: Appearance
        tab_app = QWidget()
        form_app = QFormLayout()
        self.inp_font = QComboBox()
        self.inp_font.addItems(["Segoe UI", "Arial", "Consolas", "Verdana"])
        self.inp_font.setCurrentText(self.config.get('APPEARANCE', 'font_family'))
        self.inp_size = QLineEdit(self.config.get('APPEARANCE', 'font_size'))
        self.inp_hi = QLineEdit(self.config.get('APPEARANCE', 'high_prob_color'))
        self.inp_lo = QLineEdit(self.config.get('APPEARANCE', 'low_prob_color'))
        form_app.addRow("Font:", self.inp_font)
        form_app.addRow("Size:", self.inp_size)
        form_app.addRow("High Prob Color:", self.inp_hi)
        form_app.addRow("Low Prob Color:", self.inp_lo)
        tab_app.setLayout(form_app)
        tabs.addTab(tab_app, "Appearance")

        layout.addWidget(tabs)
        
        # Buttons
        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save_settings)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)
        
        # Set initial preset based on current config
        self._set_initial_preset()
    
    def _update_status_display(self):
        """Update the UDP status indicator."""
        if self.udp_status:
            if self.udp_status.get('receiving', False):
                rate = self.udp_status.get('rate', 0)
                self.status_indicator.setText(
                    f"<span style='color: #00ff00;'>● Connected</span> "
                    f"<span style='color: #888888;'>({rate:.0f} decodes/min)</span>"
                )
            else:
                self.status_indicator.setText(
                    "<span style='color: #ff5555;'>○ No data received</span> "
                    "<span style='color: #888888;'>(check WSJT-X/JTDX settings)</span>"
                )
        else:
            self.status_indicator.setText(
                "<span style='color: #888888;'>○ Status unknown</span>"
            )
    
    def _set_initial_preset(self):
        """Determine which preset matches current config."""
        current_ip = self.inp_ip.text()
        current_port = self.inp_port.value()
        
        # Check if it matches a known preset
        for preset_name, (ip, port) in UDP_PRESETS.items():
            if ip is None:  # Skip "Custom"
                continue
            if current_ip == ip and current_port == port:
                self.preset_combo.setCurrentText(preset_name)
                return
        
        # No match - set to Custom
        self.preset_combo.setCurrentText("Custom")
    
    def _on_preset_changed(self, preset_name):
        """Handle preset selection change."""
        if preset_name not in UDP_PRESETS:
            return
        
        ip, port = UDP_PRESETS[preset_name]
        
        if ip is not None and port is not None:
            # Block signals to avoid triggering _on_manual_change
            self.inp_ip.blockSignals(True)
            self.inp_port.blockSignals(True)
            
            self.inp_ip.setText(ip)
            self.inp_port.setValue(port)
            
            self.inp_ip.blockSignals(False)
            self.inp_port.blockSignals(False)
    
    def _on_manual_change(self):
        """Handle manual IP/port changes - switch to Custom preset."""
        current_ip = self.inp_ip.text()
        current_port = self.inp_port.value()
        
        # Check if it still matches current preset
        current_preset = self.preset_combo.currentText()
        if current_preset in UDP_PRESETS:
            preset_ip, preset_port = UDP_PRESETS[current_preset]
            if preset_ip is not None:
                if current_ip != preset_ip or current_port != preset_port:
                    self.preset_combo.blockSignals(True)
                    self.preset_combo.setCurrentText("Custom")
                    self.preset_combo.blockSignals(False)

    def save_settings(self):
        self.config.save_setting('ANALYSIS', 'my_callsign', self.inp_call.text().upper())
        self.config.save_setting('ANALYSIS', 'my_grid', self.inp_grid.text().upper())
        self.config.save_setting('NETWORK', 'udp_ip', self.inp_ip.text())
        self.config.save_setting('NETWORK', 'udp_port', str(self.inp_port.value()))
        self.config.save_setting('NETWORK', 'forward_ports', self.inp_fwd.text())
        self.config.save_setting('APPEARANCE', 'font_family', self.inp_font.currentText())
        self.config.save_setting('APPEARANCE', 'font_size', self.inp_size.text())
        self.config.save_setting('APPEARANCE', 'high_prob_color', self.inp_hi.text())
        self.config.save_setting('APPEARANCE', 'low_prob_color', self.inp_lo.text())
        self.accept()
