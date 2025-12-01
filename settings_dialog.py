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
                             QFormLayout, QMessageBox, QComboBox)

class SettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Configuration")
        self.resize(450, 350)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        
        # Tab 1
        tab_station = QWidget()
        form_station = QFormLayout()
        self.inp_call = QLineEdit(self.config.get('ANALYSIS', 'my_callsign'))
        self.inp_grid = QLineEdit(self.config.get('ANALYSIS', 'my_grid'))
        form_station.addRow("My Callsign:", self.inp_call)
        form_station.addRow("My Grid Square:", self.inp_grid)
        tab_station.setLayout(form_station)
        tabs.addTab(tab_station, "Station")

        # Tab 2
        tab_net = QWidget()
        form_net = QFormLayout()
        self.inp_ip = QLineEdit(self.config.get('NETWORK', 'udp_ip'))
        self.inp_port = QLineEdit(self.config.get('NETWORK', 'udp_port'))
        self.inp_fwd = QLineEdit(self.config.get('NETWORK', 'forward_ports'))
        form_net.addRow("Listen IP:", self.inp_ip)
        form_net.addRow("Listen Port:", self.inp_port)
        form_net.addRow("Forward To:", self.inp_fwd)
        tab_net.setLayout(form_net)
        tabs.addTab(tab_net, "Network")

        # Tab 3
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
        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save"); btn_save.clicked.connect(self.save_settings)
        btn_cancel = QPushButton("Cancel"); btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch(); btn_box.addWidget(btn_cancel); btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def save_settings(self):
        self.config.save_setting('ANALYSIS', 'my_callsign', self.inp_call.text().upper())
        self.config.save_setting('ANALYSIS', 'my_grid', self.inp_grid.text().upper())
        self.config.save_setting('NETWORK', 'udp_ip', self.inp_ip.text())
        self.config.save_setting('NETWORK', 'udp_port', self.inp_port.text())
        self.config.save_setting('NETWORK', 'forward_ports', self.inp_fwd.text())
        self.config.save_setting('APPEARANCE', 'font_family', self.inp_font.currentText())
        self.config.save_setting('APPEARANCE', 'font_size', self.inp_size.text())
        self.config.save_setting('APPEARANCE', 'high_prob_color', self.inp_hi.text())
        self.config.save_setting('APPEARANCE', 'low_prob_color', self.inp_lo.text())
        self.accept()


