# QSO Predictor - Hunt List Dialog
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.1.0: Initial implementation

import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QGroupBox, QCompleter
)
from PyQt6.QtCore import Qt, QStringListModel
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)


class HuntListDialog(QDialog):
    """Dialog for managing the Hunt List.
    
    Allows users to:
    - View current hunt list
    - Add new callsigns/prefixes/grids
    - Remove items from list
    - Clear entire list
    """
    
    def __init__(self, hunt_manager, parent=None):
        super().__init__(parent)
        self.hunt_manager = hunt_manager
        self.setWindowTitle("Hunt List")
        self.setMinimumSize(350, 400)
        self.setup_ui()
        self.load_list()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Header / explanation
        header = QLabel(
            "<b>Hunt Mode</b><br>"
            "Add callsigns, prefixes, grids, or countries to watch for.<br>"
            "You'll be alerted when they become active."
        )
        header.setWordWrap(True)
        header.setStyleSheet("color: #AAA; padding: 5px;")
        layout.addWidget(header)
        
        # Add new item section
        add_group = QGroupBox("Add to Hunt List")
        add_layout = QHBoxLayout(add_group)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("K5D, VU4, FN31, or Japan...")
        self.input_field.returnPressed.connect(self.add_item)
        
        # Add autocomplete for country names
        countries = self.hunt_manager.get_available_countries()
        completer = QCompleter(countries)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.input_field.setCompleter(completer)
        
        add_layout.addWidget(self.input_field)
        
        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(self.add_item)
        self.btn_add.setFixedWidth(60)
        add_layout.addWidget(self.btn_add)
        
        layout.addWidget(add_group)
        
        # Hunt list display
        list_group = QGroupBox("Currently Hunting")
        list_layout = QVBoxLayout(list_group)
        
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                color: #EEE;
                border: 1px solid #333;
                font-size: 12pt;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #DAA520;
                color: #000;
            }
            QListWidget::item:alternate {
                background-color: #222;
            }
        """)
        list_layout.addWidget(self.list_widget)
        
        # List action buttons
        btn_layout = QHBoxLayout()
        
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self.remove_selected)
        btn_layout.addWidget(self.btn_remove)
        
        self.btn_clear = QPushButton("Clear All")
        self.btn_clear.clicked.connect(self.clear_all)
        btn_layout.addWidget(self.btn_clear)
        
        list_layout.addLayout(btn_layout)
        layout.addWidget(list_group)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Close button
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)
        
        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #2a2a2a;
                color: #EEE;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                color: #DAA520;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #444;
                color: #DDD;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #333;
            }
            QLineEdit {
                background-color: #333;
                color: #EEE;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px;
            }
        """)
    
    def load_list(self):
        """Load current hunt list into the widget."""
        self.list_widget.clear()
        items = self.hunt_manager.get_list()
        for item in items:
            # Show indicator for countries
            if self.hunt_manager.is_country_name(item):
                display_text = f"🌍 {item}"
            else:
                display_text = item
            self.list_widget.addItem(display_text)
        self.update_status()
    
    def update_status(self):
        """Update the status label."""
        count = self.list_widget.count()
        if count == 0:
            self.status_label.setText("No items in hunt list. Type a country name for suggestions.")
        else:
            self.status_label.setText(f"Hunting {count} item{'s' if count != 1 else ''}")
    
    def add_item(self):
        """Add item from input field to hunt list."""
        text = self.input_field.text().strip().upper()
        if not text:
            return
        
        # Basic validation
        if len(text) < 2:
            QMessageBox.warning(self, "Invalid Entry", 
                "Entry must be at least 2 characters.")
            return
        
        # Allow longer entries for country names
        is_country = self.hunt_manager.is_country_name(text)
        if len(text) > 30 and not is_country:
            QMessageBox.warning(self, "Invalid Entry", 
                "Entry must be 30 characters or less.")
            return
        
        # Warn about overly broad targets that would cause notification spam
        broad_targets = [
            "UNITED STATES", "USA", "GERMANY", "JAPAN", "RUSSIA", "CHINA",
            "ENGLAND", "ITALY", "SPAIN", "FRANCE", "POLAND", "BRAZIL",
            "K", "W", "N", "DL", "JA", "UA", "G", "I", "EA", "F"
        ]
        if text in broad_targets:
            reply = QMessageBox.warning(
                self, "High Traffic Warning",
                f"'{text}' matches a very large number of stations.\n\n"
                "This will generate many notifications and may be distracting.\n\n"
                "Consider hunting specific callsigns, rare prefixes, or smaller countries instead.\n\n"
                "Add anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        if self.hunt_manager.add(text):
            # Show with indicator if it's a country
            display_text = f"🌍 {text}" if is_country else text
            self.list_widget.addItem(display_text)
            self.input_field.clear()
            self.update_status()
        else:
            QMessageBox.information(self, "Duplicate", 
                f"'{text}' is already in the hunt list.")
    
    def remove_selected(self):
        """Remove selected item from hunt list."""
        current = self.list_widget.currentItem()
        if not current:
            return
        
        item_text = current.text()
        # Strip the country indicator emoji if present
        if item_text.startswith("🌍 "):
            item_text = item_text[2:].strip()
        
        if self.hunt_manager.remove(item_text):
            self.list_widget.takeItem(self.list_widget.row(current))
            self.update_status()
    
    def clear_all(self):
        """Clear entire hunt list with confirmation."""
        if self.list_widget.count() == 0:
            return
        
        reply = QMessageBox.question(
            self, "Clear Hunt List",
            "Are you sure you want to clear the entire hunt list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.hunt_manager.clear()
            self.list_widget.clear()
            self.update_status()
