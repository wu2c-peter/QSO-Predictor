"""Hunt Mode v2.1.0 coordinator.

Owns the HuntManager instance and the UI hooks for managing the hunt list
(context menu, dialog, tray-icon alerts). The actual matching/notification
logic stays in HuntManager; this controller just routes Qt-side events.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
import time
from typing import Optional

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

try:
    from hunt_manager import HuntManager
    from hunt_dialog import HuntListDialog
    HUNT_MODE_AVAILABLE = True
except ImportError:
    HUNT_MODE_AVAILABLE = False

logger = logging.getLogger(__name__)


class HuntCoordinator(QObject):
    """Holds the HuntManager and bridges Qt UI actions to it."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.hunt_manager: Optional["HuntManager"] = None
        if HUNT_MODE_AVAILABLE:
            self._init_hunt_manager()

    def _init_hunt_manager(self):
        """Initialize HuntManager and wire its alert signal."""
        try:
            self.hunt_manager = HuntManager(config_manager=self.main_window.config)

            # Set user's grid for "working nearby" detection
            my_grid = self.main_window.config.get('ANALYSIS', 'my_grid', fallback='')
            self.hunt_manager.set_my_grid(my_grid)

            # Connect hunt alerts to notification handler
            self.hunt_manager.hunt_alert.connect(self._on_alert)

            logger.info(f"Hunt Mode initialized with {len(self.hunt_manager.get_list())} items")
        except Exception as e:
            logger.error(f"Failed to initialize Hunt Mode: {e}")
            self.hunt_manager = None

    def show_list_dialog(self):
        """Show the Hunt List management dialog."""
        if not self.hunt_manager:
            return
        dialog = HuntListDialog(self.hunt_manager, self.main_window)
        dialog.exec()
        # Refresh table to update highlighting
        self.main_window.model.layoutChanged.emit()

    def show_table_context_menu(self, pos):
        """Show context menu for decode table with Hunt Mode options."""
        mw = self.main_window
        index = mw.table_view.indexAt(pos)
        if not index.isValid():
            return

        # Get the callsign from the clicked row
        row_data = mw.model._data[index.row()]
        callsign = row_data.get('call', '')

        if not callsign:
            return

        menu = QMenu(mw)

        # Hunt Mode actions
        if self.hunt_manager:
            if self.hunt_manager.is_hunted(callsign):
                remove_action = menu.addAction(f"Remove {callsign} from Hunt List")
                remove_action.triggered.connect(lambda: self.remove(callsign))
            else:
                add_action = menu.addAction(f"Add {callsign} to Hunt List")
                add_action.triggered.connect(lambda: self.add(callsign))

            menu.addSeparator()

        # Set as Target action
        target_action = menu.addAction(f"Set {callsign} as Target")
        target_action.triggered.connect(lambda: mw.on_row_click(index))

        menu.exec(mw.table_view.viewport().mapToGlobal(pos))

    def add(self, callsign):
        """Add callsign to hunt list from context menu."""
        if self.hunt_manager and self.hunt_manager.add(callsign):
            self.main_window.model.layoutChanged.emit()  # Refresh highlighting
            self.main_window.tray_icon.showMessage(
                "Hunt Mode",
                f"Added {callsign} to hunt list",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )

    def remove(self, callsign):
        """Remove callsign from hunt list from context menu."""
        if self.hunt_manager and self.hunt_manager.remove(callsign):
            self.main_window.model.layoutChanged.emit()  # Refresh highlighting

    def check_spot(self, spot):
        """Check incoming MQTT spot against hunt list."""
        if not self.hunt_manager or self.hunt_manager.is_empty():
            return
        self.hunt_manager.check_spot(spot, time.time())

    def _on_alert(self, call, band, alert_type, details):
        """Handle hunt alert - show notification to user."""
        mw = self.main_window

        # Don't show notifications if we're closing
        if getattr(mw, '_closing', False):
            return

        if alert_type == 'working_nearby':
            # High priority - propagation path to your region confirmed!
            title = f"🎯 {call} Heard Nearby!"
            message = f"{call} on {band}: {details}"
            icon = QSystemTrayIcon.MessageIcon.Warning
            duration = 5000
        else:
            # Normal - they're just active
            title = f"📡 {call} Active"
            message = f"{call} spotted on {band}"
            icon = QSystemTrayIcon.MessageIcon.Information
            duration = 3000

        # System tray notification
        mw.tray_icon.showMessage(title, message, icon, duration)

        # Also update status bar briefly
        mw.update_status_msg(f"Hunt: {call} {alert_type} on {band}")
