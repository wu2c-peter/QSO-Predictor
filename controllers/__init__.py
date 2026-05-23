"""Controllers extracted from MainWindow.

Each controller owns a focused subsystem (update checking, data health,
hunt mode, etc.) and keeps a back-reference to the main window for the
small number of UI hooks it needs (status bar, dialogs, tray icon).
This lets MainWindow shrink toward a UI shell + signal router.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

from .update_checker import UpdateChecker
from .health_monitor import HealthMonitor
from .hunt_coordinator import HuntCoordinator
from .ionis_integration import IonisIntegration
from .fox_hound import FoxHoundController

__all__ = [
    "UpdateChecker",
    "HealthMonitor",
    "HuntCoordinator",
    "IonisIntegration",
    "FoxHoundController",
]
