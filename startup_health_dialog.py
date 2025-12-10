# QSO Predictor
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.1.0 New file: Startup health check dialog
# Shows helpful guidance when no data is detected after startup.
# Feature added based on user feedback from Doug McDonald.

"""
Startup Health Check Dialog for QSO Predictor

Shows a helpful popup if no data is detected after startup,
guiding users through common configuration issues.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCheckBox, QFrame, QGroupBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class StartupHealthDialog(QDialog):
    """
    Dialog shown when no data is detected after startup.
    Provides diagnostic info and setup guidance.
    """
    
    def __init__(self, parent=None, udp_ok=False, mqtt_ok=False):
        super().__init__(parent)
        self.udp_ok = udp_ok
        self.mqtt_ok = mqtt_ok
        self.dont_show_again = False
        
        self.setWindowTitle("No Data Detected")
        self.setMinimumWidth(520)
        self.setModal(True)
        
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Header
        header = QLabel("⚠️ No Data Detected")
        header_font = QFont()
        header_font.setPointSize(14)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)
        
        # Intro text
        intro = QLabel(
            "QSO Predictor isn't receiving data from WSJT-X or JTDX.\n"
            "Here's what to check:"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        
        # Checklist group
        checklist_group = QGroupBox("Setup Checklist")
        checklist_layout = QVBoxLayout(checklist_group)
        checklist_layout.setSpacing(12)
        
        # Item 1: UDP Settings
        udp_section = QLabel(
            "<b>1. WSJT-X/JTDX UDP Settings</b><br>"
            "&nbsp;&nbsp;&nbsp;→ Settings → Reporting → UDP Server<br>"
            "&nbsp;&nbsp;&nbsp;→ Address: <code>127.0.0.1</code>&nbsp;&nbsp;Port: <code>2237</code><br>"
            "&nbsp;&nbsp;&nbsp;→ ☑ Accept UDP Requests"
        )
        udp_section.setTextFormat(Qt.TextFormat.RichText)
        checklist_layout.addWidget(udp_section)
        
        # Item 2: Running and decoding
        running_section = QLabel(
            "<b>2. WSJT-X/JTDX is running and decoding</b><br>"
            "&nbsp;&nbsp;&nbsp;→ Make sure the waterfall shows activity<br>"
            "&nbsp;&nbsp;&nbsp;→ Wait for at least one decode cycle (15 seconds)"
        )
        running_section.setTextFormat(Qt.TextFormat.RichText)
        checklist_layout.addWidget(running_section)
        
        # Item 3: Multicast (if applicable)
        multicast_section = QLabel(
            "<b>3. Using JTAlert, GridTracker, or N3FJP?</b><br>"
            "&nbsp;&nbsp;&nbsp;→ You may need multicast UDP configuration<br>"
            "&nbsp;&nbsp;&nbsp;→ See wiki: Help → Documentation for details"
        )
        multicast_section.setTextFormat(Qt.TextFormat.RichText)
        checklist_layout.addWidget(multicast_section)
        
        layout.addWidget(checklist_group)
        
        # Status box
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        status_frame.setStyleSheet("QFrame { background-color: #f0f0f0; }")
        status_layout = QVBoxLayout(status_frame)
        status_layout.setContentsMargins(10, 10, 10, 10)
        
        status_label = QLabel("<b>Current Status:</b>")
        status_label.setTextFormat(Qt.TextFormat.RichText)
        status_layout.addWidget(status_label)
        
        # UDP status
        udp_icon = "✓" if self.udp_ok else "✗"
        udp_color = "green" if self.udp_ok else "red"
        udp_text = "Receiving messages" if self.udp_ok else "No messages received"
        udp_status = QLabel(f"&nbsp;&nbsp;UDP: <span style='color:{udp_color};font-weight:bold;'>{udp_icon} {udp_text}</span>")
        udp_status.setTextFormat(Qt.TextFormat.RichText)
        status_layout.addWidget(udp_status)
        
        # MQTT status
        mqtt_icon = "✓" if self.mqtt_ok else "○"
        mqtt_color = "green" if self.mqtt_ok else "#888"
        mqtt_text = "Connected to PSK Reporter" if self.mqtt_ok else "Not connected (optional for basic use)"
        mqtt_status = QLabel(f"&nbsp;&nbsp;MQTT: <span style='color:{mqtt_color};'>{mqtt_icon} {mqtt_text}</span>")
        mqtt_status.setTextFormat(Qt.TextFormat.RichText)
        status_layout.addWidget(mqtt_status)
        
        layout.addWidget(status_frame)
        
        # Don't show again checkbox
        self.dont_show_checkbox = QCheckBox("Don't show this again on startup")
        layout.addWidget(self.dont_show_checkbox)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        settings_btn = QPushButton("Open Settings")
        settings_btn.clicked.connect(self.open_settings)
        button_layout.addWidget(settings_btn)
        
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        ok_btn.setMinimumWidth(80)
        button_layout.addWidget(ok_btn)
        
        layout.addLayout(button_layout)
    
    def open_settings(self):
        """Open the settings dialog."""
        self.done(2)  # Custom return code for "open settings"
    
    def accept(self):
        """Handle OK button."""
        self.dont_show_again = self.dont_show_checkbox.isChecked()
        super().accept()


# Standalone test
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    # Test with different states
    print("Testing dialog with UDP=False, MQTT=True...")
    dialog = StartupHealthDialog(udp_ok=False, mqtt_ok=True)
    result = dialog.exec()
    
    print(f"Result: {result}")
    print(f"Don't show again: {dialog.dont_show_again}")
    
    sys.exit(0)
