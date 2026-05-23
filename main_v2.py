# QSO Predictor v2.1.4
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.1.4 Changes:
# - Fixed: JTDX detection in auto-paste scripts (title bar contains "WSJT-X")
# - Fixed: Band map frequency scale too dim on Windows (brightened labels and ticks)
# - Added: Auto-paste scripts click Enable TX after pasting callsign
# - Added: Separate JTDX/WSJT-X coordinates in auto-paste scripts
#
# v2.1.3 Changes:
# - Added: Click-to-copy target callsign (click target in either panel)
# - Added: Local decode evidence for path detection (works without PSK Reporter)
# - Changed: Path status labels clarified (Heard by Target, Reported in Region, etc.)
# - Changed: "Sync to JTDX" renamed to "Fetch Target" (clearer direction)
# - Changed: Combined AutoHotkey/Hammerspoon scripts support frequency + callsign
# - Fixed: AP decode codes (a1-a7) stripped from Call column
#
# v2.1.1 Changes:
# - Added: Band map hover tooltips showing callsign, SNR, tier, grid (Brian's request)
# - Added: Frequency scale with Hz labels on band map (Brian's request)
# - Added: Resilient data source monitoring - status bar warns if UDP/MQTT data stops
# - Added: Diagnostic logging in analyzer for debugging empty Target Perspective
# - Fixed: Silent exception handler in analyzer.handle_live_spot now logs errors
#
# v2.1.0 Changes:
# - Added: Target View as undockable panel (Dashboard + Band Map)
# - Added: Insights as undockable panel (right side, full height)
# - Added: View menu with panel toggles and Reset Layout option
# - Added: Hunt Mode - track stations/prefixes/countries, alert when active (suggested by Warren KC0GU)
#   - Hunt List dialog (Tools → Hunt List, Ctrl+H)
#   - Right-click context menu to add/remove from hunt list
#   - Gold highlighting for hunted stations in decode table
#   - System tray alerts when hunted station active
#   - "Heard nearby" alerts when hunted station's signal reaches your region
#   - Country/DXCC support with autocomplete (type "Japan" to hunt all JA stations)
# - Added: Click-to-clipboard - click band map or Rec frequency to copy to clipboard
# - Added: Auto-clear on QSY - clear target when changing bands (Brian's request)
# - Fixed: Right dock (Local Intel) no longer pushes down band map (setCorner fix)
# - Changed: Decode table uses less vertical space by default
#
# v2.0.8 Changes:
# - Added: Background scanner for incremental log file processing
# - Added: Behavior distribution display (L/M/R bar) in Insights panel
# - Added: get_behavior_distribution() method for historical data
# - Added: Bayesian update_observations() for incremental count updates
# - Fixed: Bootstrap timeout with large log files (background processing)
# - Fixed: JTDX dated file trailing markers (^ * . d)
#
# v2.0.7 Changes:
# - Fixed: UI freeze when clicking stations with large ALL.TXT files
#   (removed blocking log scan, now cache-only lookup)
# - Fixed: Rapid table refresh from UDP status flooding (throttled to 2Hz)
# - Fixed: Yellow TX line flickering on band map
# - Fixed: Table re-sorting jitter during decode updates
#   (reported by Doug McDonald)
#
# v2.0.9 Changes:
# - Added: Startup health check dialog when no UDP data detected
#   (based on user feedback from Doug McDonald)
#
# v2.0.6 Changes:
# - Fixed: Severe CPU usage on macOS (band map optimization)
# - Fixed: Splitter position persistence (suggested by KC0GU)
# - Fixed: VERSION file not bundled in macOS build
# - Added: Sync to WSJT-X/JTDX button and Ctrl+Y shortcut (suggested by KC0GU)
#          (renamed to "Fetch Target" in v2.1.3 for clarity)
# - Added: Dock widget (Insights panel) position persistence
#
# v2.0.4 Changes:
# - Fixed: Cache cleanup thread death (analyzer.py)
# - Fixed: MQTT auto-reconnect (mqtt_client.py)
# - Fixed: Status bar shows unique stations instead of total spots
# - Added: Solar data refresh timer (every 15 minutes)
#
# v2.0.3 Changes:
# - Added: Column width persistence (suggested by KC0GU)
# - Added: Clear Target button and Ctrl+R shortcut (suggested by KC0GU)
# - Added: QSO Logged message handling for auto-clear (suggested by KC0GU)
# - Added: Auto-clear on QSO logged setting
# - Fixed: Ctrl+R shortcut (was documented but not implemented)

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Initialize logging FIRST before other imports
from logging_config import setup_logging, set_debug_mode, get_log_file_path, open_log_folder
setup_logging(console=True, file=True)

logger = logging.getLogger(__name__)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableView, QLabel, QHeaderView, QDockWidget,
                             QMessageBox, QProgressBar, QAbstractItemView, QFrame, QSizePolicy, 
                             QSystemTrayIcon, QMenu, QToolBar, QPushButton, QCheckBox,
                             QStyledItemDelegate, QComboBox, QLineEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QAbstractTableModel, QModelIndex, QByteArray
from PyQt6.QtGui import QColor, QAction, QKeySequence, QFont, QIcon, QCursor, QBrush, QShortcut

# v2.1.0: Hunt Mode imports
try:
    from hunt_manager import HuntManager
    from hunt_dialog import HuntListDialog
    HUNT_MODE_AVAILABLE = True
except ImportError as e:
    HUNT_MODE_AVAILABLE = False
    logger.warning(f"Hunt Mode not available: {e}")

# OutcomeRecorder — silent data collector for performance analysis
try:
    from outcome_recorder import OutcomeRecorder
    OUTCOME_RECORDER_AVAILABLE = True
except ImportError as e:
    OUTCOME_RECORDER_AVAILABLE = False
    logger.warning(f"OutcomeRecorder not available: {e}")


from utils.version import compare_versions, get_version, is_packaged_install


try:
    from config_manager import ConfigManager
    from udp_handler import UDPHandler
    from analyzer import QSOAnalyzer
    from band_map_widget import BandMapWidget
    from settings_dialog import SettingsDialog
except ImportError as e:
    app = QApplication(sys.argv)
    QMessageBox.critical(None, "Missing Files", f"Error: {e}")
    sys.exit(1)

# v2.0.9: Import startup health dialog
try:
    from startup_health_dialog import StartupHealthDialog
    STARTUP_HEALTH_AVAILABLE = True
except ImportError:
    STARTUP_HEALTH_AVAILABLE = False

try:
    from solar_client import SolarClient
    SOLAR_AVAILABLE = True
except ImportError:
    SOLAR_AVAILABLE = False

# PathStatus is the canonical domain type for path classification and is used
# unconditionally for UI dispatch (dashboard, decode table). It lives in the
# pure-stdlib models module so it stays importable even when the heavier
# local-intel stack (numpy/pandas/sklearn) isn't available.
from local_intel.models import PathStatus

# --- LOCAL INTELLIGENCE v2.0 ---
try:
    from local_intel_integration import LocalIntelligence
    LOCAL_INTEL_AVAILABLE = True
except ImportError as e:
    LOCAL_INTEL_AVAILABLE = False
    logger.warning(f"Local Intelligence not available: {e}")

# --- IONIS PROPAGATION v2.4.0 ---
try:
    from ionis import IonisEngine, freq_to_band as ionis_freq_to_band
    IONIS_AVAILABLE = True
except ImportError as e:
    IONIS_AVAILABLE = False
    logger.info(f"IONIS propagation engine not available: {e}")


# --- WIDGETS ---
# Reusable Qt widgets live in the `widgets/` package. See widgets/__init__.py.
from widgets import (
    ClickableCopyLabel,
    ClickableLabel,
    DecodeTableModel,
    HuntHighlightDelegate,
    TacticalToast,
    TargetDashboard,
)

# --- CONTROLLERS ---
# Focused subsystems extracted from MainWindow. See controllers/__init__.py.
from controllers import (
    HealthMonitor,
    HuntCoordinator,
    UpdateChecker,
)


# --- v2.3.0: TARGET ACTIVITY STATE PARSER ---
def parse_target_activity(message, target_call, my_call):
    """Parse an FT8/FT4 message to determine target's activity state.
    
    Analyzes decoded messages to infer what the target station is doing:
    - CQing (open for calls)
    - Working you (responding to your callsign)  
    - Working another station (competition confirmed)
    - Being called by someone
    
    Args:
        message: Raw FT8 message string (e.g., "WU2C J51A -04")
        target_call: Current target callsign (uppercase)
        my_call: Our callsign (uppercase)
    
    Returns:
        (state, other_call) tuple, or (None, None) if message doesn't involve target.
        state values: 'cqing', 'working_you', 'completing_with_you',
                      'working_other', 'completing_with_other', 'being_called'
    """
    if not message or not target_call:
        return None, None
    
    parts = message.split()
    if len(parts) < 2:
        return None, None
    
    target_upper = target_call.upper()
    my_upper = my_call.upper() if my_call else ""
    
    # Target is CQing: "CQ J51A GF25" or "CQ DX J51A GF25"
    if parts[0] == 'CQ':
        if target_upper in parts:
            return 'cqing', None
        return None, None
    
    # Target in Position 2 — they are transmitting TO the station in Position 1
    # Pattern: "OTHERCALL TARGET payload"
    if len(parts) >= 3 and parts[1] == target_upper:
        other_call = parts[0]
        payload = ' '.join(parts[2:])
        
        if my_upper and other_call == my_upper:
            # Target is working US
            if 'RR73' in payload or payload.strip() == '73':
                return 'completing_with_you', my_upper
            return 'working_you', my_upper
        else:
            # Target is working someone else
            if 'RR73' in payload or payload.strip() == '73':
                return 'completing_with_other', other_call
            return 'working_other', other_call
    
    # Target in Position 1 — someone is calling/responding TO target
    # Pattern: "TARGET CALLER payload"
    if len(parts) >= 2 and parts[0] == target_upper:
        caller = parts[1] if len(parts) >= 2 else None
        # Don't count if caller looks like a grid or report
        if caller and len(caller) >= 3 and any(c.isdigit() for c in caller) and any(c.isalpha() for c in caller):
            return 'being_called', caller
    
    return None, None


# --- MAIN APPLICATION WINDOW ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.setWindowTitle(f"QSO Predictor v{get_version()} by WU2C")
        self.resize(1100, 800)
        
        # --- v2.0.3: Restore window geometry ---
        geo = self.config.get('WINDOW', 'geometry')
        if geo:
            self.restoreGeometry(QByteArray.fromHex(geo.encode()))
            
            # v2.1.0: Ensure window fits on screen (fix for Windows off-screen issue)
            screen = QApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry()
                frame = self.frameGeometry()
                
                # If window extends beyond screen, resize to fit
                if frame.bottom() > available.bottom():
                    new_height = available.height() - 50  # Leave some margin
                    if new_height < 600:
                        new_height = 600  # Minimum usable height
                    self.resize(self.width(), new_height)
                    self.move(frame.x(), available.y() + 10)
                
                if frame.right() > available.right():
                    self.move(available.x() + 10, self.y())

        self.analyzer = QSOAnalyzer(self.config)
        self.udp = UDPHandler(self.config)
        
        # --- TARGET TRACKING STATE ---
        self.current_target_call = ""
        self.current_target_grid = ""
        self.jtdx_last_dx_call = ""  # Track what JTDX last sent (separate from our selection)
        self._is_manual_target = False  # v2.4.4: True when target entered manually (not decoded)
        
        # v2.3.0: Target Activity State tracking
        self._target_activity_state = 'unknown'
        self._target_activity_other = None  # Who target is working
        self._target_activity_time = 0  # Last activity timestamp
        self._inferred_competitors = {}  # {callsign: timestamp} — competitors inferred from target responses
        self._activity_idle_timeout = 120  # Seconds before state goes to 'idle'
        
        # v2.3.0: Fox/Hound mode state
        self._fh_active = False           # Master F/H state (from any trigger)
        self._fh_source = None            # What triggered F/H: 'manual', 'udp', 'inferred'
        self._fh_type = None              # 'fh' (old-style) or 'superfh' — controls clamping behavior
        self._fh_fox_qso = False          # Fox is controlling our TX frequency
        self._fh_dialog_shown = False     # Prevent repeated dialogs in same session
        
        # --- UPDATE CHECK ---
        self.update_checker = UpdateChecker(self)
        self._normal_status = ""     # v2.1.1: Last non-warning status message

        # --- HEALTH MONITOR ---
        self.health_monitor = HealthMonitor(self)
        
        # --- UDP STATUS TRACKING ---
        self._decode_count = 0
        self._decode_start_time = None
        
        # --- v2.1.0: Shutdown flag for clean notification handling ---
        self._closing = False
        
        if SOLAR_AVAILABLE:
            self.solar = SolarClient()
            self.solar_update_signal.connect(self.update_solar_ui)
        
        # --- LOCAL INTELLIGENCE v2.0 ---
        self.local_intel = None
        if LOCAL_INTEL_AVAILABLE:
            self._init_local_intelligence()
        
        # --- v2.1.0: HUNT MODE ---
        self.hunt_coordinator = HuntCoordinator(self)
        # Convenience alias — many MainWindow paths still reference hunt_manager directly.
        self.hunt_manager = self.hunt_coordinator.hunt_manager
        
        # --- v2.4.0: IONIS PROPAGATION ---
        self._ionis_engine = None
        self._ionis_shown = False  # Track whether prediction is displayed
        if IONIS_AVAILABLE:
            self._init_ionis()
        
        # --- OUTCOME RECORDER: Silent data collector for performance analysis ---
        self.outcome_recorder = None
        if OUTCOME_RECORDER_AVAILABLE:
            try:
                my_call = self.config.get('ANALYSIS', 'my_callsign', fallback='')
                my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='')
                enabled = self.config.get('ANALYSIS', 'outcome_recording',
                                          fallback='true').lower() == 'true'
                self.outcome_recorder = OutcomeRecorder(my_call, my_grid, enabled)
            except Exception as e:
                logger.warning(f"OutcomeRecorder init failed: {e}")
            
        self.init_ui()
        self.setup_connections()
        
        self.buffer = []
        self.buffer_timer = QTimer()
        self.buffer_timer.timeout.connect(self.process_buffer)
        self.buffer_timer.start(500) 
        
        # --- PERSPECTIVE REFRESH TIMER ---
        self.perspective_timer = QTimer()
        self.perspective_timer.timeout.connect(self.refresh_target_perspective)
        self.perspective_timer.start(3000)  # Refresh every 3 seconds
        
        self.udp.start()
        
        # --- v2.0.6: Solar data fetch with periodic refresh ---
        if SOLAR_AVAILABLE:
            self.fetch_solar_data()
            # Refresh solar data every 15 minutes
            self.solar_timer = QTimer()
            self.solar_timer.timeout.connect(self.fetch_solar_data)
            self.solar_timer.start(15 * 60 * 1000)  # 15 minutes
        
        # Check for updates on startup (non-blocking, silent).
        # v2.5.5: Skip for MSIX/Store installs — the Store handles update
        # delivery for those users; an in-app GitHub-based notification would
        # only confuse them (they cannot install from GitHub over an MSIX).
        if not is_packaged_install():
            self.update_checker.start_check(manual=False)

        # v2.1.1: Periodic data health check (detects UDP/MQTT data loss)
        self.health_monitor.start_periodic_check()

        # Check for unconfigured callsign/grid on startup
        QTimer.singleShot(500, self._check_first_run_config)
    
    def _check_first_run_config(self):
        """Warn user if callsign/grid haven't been configured."""
        my_call = self.config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
        my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='FN00aa')
        
        if my_call == 'N0CALL' or my_grid == 'FN00aa':
            QMessageBox.information(
                self,
                "Welcome to QSO Predictor!",
                "Please configure your callsign and grid square "
                "for accurate predictions.\n\n"
                "Go to Edit → Settings to set them up."
            )

    def _init_local_intelligence(self):
        """Initialize Local Intelligence v2.0 features."""
        try:
            my_callsign = self.config.get('ANALYSIS', 'my_callsign', fallback='')
            if not my_callsign:
                logger.info("Local Intelligence: No callsign configured, some features disabled")
                my_callsign = 'N0CALL'
            
            self.local_intel = LocalIntelligence(my_callsign=my_callsign)
            logger.info("Local Intelligence initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Local Intelligence: {e}")
            self.local_intel = None
    

    def _init_ionis(self):
        """Initialize IONIS propagation engine v2.4.0."""
        try:
            ionis_enabled = self.config.get('IONIS', 'enabled', fallback='true') == 'true'
            if not ionis_enabled:
                logger.info("IONIS propagation engine disabled in settings")
                return
            
            self._ionis_engine = IonisEngine()
            if self._ionis_engine.is_available():
                logger.info("IONIS propagation engine initialized")
            else:
                logger.warning("IONIS engine created but model not available")
                self._ionis_engine = None
        except Exception as e:
            logger.error(f"Failed to initialize IONIS engine: {e}")
            self._ionis_engine = None

    solar_update_signal = pyqtSignal(dict)

    def init_ui(self):
        # --- v2.1.0: DOCK LAYOUT ---
        # Central widget: Decode Table (with info bar and toolbar)
        # Bottom dock: Target View (Dashboard + Band Map) - can undock
        # Right dock: Insights panel - can undock, spans full height
        #
        # setCorner: Right dock owns the corners, so it spans full height
        # and the bottom dock (Target View) only spans left of it.
        # This prevents Local Intel from pushing down the band map.
        
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # v2.1.0: Size policy - allow central widget to shrink so bottom dock gets space
        # This is critical on Windows where Qt is more aggressive about central widget expansion
        main_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)
        
        # 1. Info Bar (clickable for updates)
        self.info_bar = ClickableLabel("Waiting for WSJT-X...")
        self.info_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_bar.setFixedHeight(25) 
        self.info_bar.setStyleSheet("background-color: #2A2A2A; color: #AAA; padding: 4px;")
        main_layout.addWidget(self.info_bar)

        # --- v2.0.3: TOOLBAR WITH CLEAR TARGET ---
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("main_toolbar")  # Required for saveState
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar { 
                background-color: #2A2A2A; 
                border: none; 
                padding: 2px;
                spacing: 5px;
            }
            QPushButton {
                background-color: #444;
                color: #DDD;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #333;
            }
            QCheckBox {
                color: #AAA;
                font-size: 9pt;
                padding-left: 10px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
        """)
        
        # Clear Target button
        self.btn_clear_target = QPushButton("Clear Target")
        self.btn_clear_target.setToolTip("Clear current target selection (Ctrl+R)")
        self.btn_clear_target.clicked.connect(self.clear_target)
        toolbar.addWidget(self.btn_clear_target)
        
        # v2.0.6: Fetch target from JTDX (pulls THEIR selection into QSOP)
        self.btn_sync_jtdx = QPushButton("← Fetch Target")
        self.btn_sync_jtdx.setToolTip("Set QSOP target to match WSJT-X/JTDX selection (Ctrl+Y)")
        self.btn_sync_jtdx.clicked.connect(self.sync_to_jtdx)
        toolbar.addWidget(self.btn_sync_jtdx)
        
        # Auto-clear checkbox
        self.chk_auto_clear = QCheckBox("Auto-clear on QSO")
        self.chk_auto_clear.setToolTip("Automatically clear target after logging a QSO")
        auto_clear_enabled = self.config.get('BEHAVIOR', 'auto_clear_on_log', fallback='false') == 'true'
        self.chk_auto_clear.setChecked(auto_clear_enabled)
        self.chk_auto_clear.stateChanged.connect(self._on_auto_clear_changed)
        toolbar.addWidget(self.chk_auto_clear)
        
        # v2.1.0: Auto-clear on band change checkbox (Brian's request)
        self.chk_auto_clear_band = QCheckBox("Auto-clear on QSY")
        self.chk_auto_clear_band.setToolTip("Automatically clear target when you change bands")
        auto_clear_band = self.config.get('BEHAVIOR', 'auto_clear_on_band', fallback='false') == 'true'
        self.chk_auto_clear_band.setChecked(auto_clear_band)
        self.chk_auto_clear_band.stateChanged.connect(self._on_auto_clear_band_changed)
        toolbar.addWidget(self.chk_auto_clear_band)
        
        toolbar.addSeparator()
        
        # v2.3.0: Fox/Hound mode selector (Off / F/H / SuperF/H)
        self.cmb_fh_mode = QComboBox()
        self.cmb_fh_mode.addItems(["F/H Off", "F/H", "SuperF/H"])
        self.cmb_fh_mode.setToolTip(
            "Fox/Hound mode:\n"
            "  F/H — Old-style: clamps TX to 1000+ Hz\n"
            "  SuperF/H — SuperFox: full band, no clamping\n"
            "Auto-detected from WSJT-X or decode patterns when possible."
        )
        self.cmb_fh_mode.setCurrentIndex(0)
        self.cmb_fh_mode.currentIndexChanged.connect(self._on_fh_combo_changed)
        self.cmb_fh_mode.setStyleSheet("""
            QComboBox {
                color: #CCCCCC;
                background: #2A2A2A;
                border: 1px solid #555;
                padding: 2px 6px;
                min-width: 80px;
            }
            QComboBox:hover { border-color: #00FFFF; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                color: #CCCCCC;
                background: #2A2A2A;
                selection-background-color: #444;
            }
        """)
        toolbar.addWidget(self.cmb_fh_mode)
        
        # Spacer to push items to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        
        self.addToolBar(toolbar)
        
        # --- DECODE TABLE (Central Widget) ---
        cols = ["UTC", "dB", "DT", "Freq", "Call", "Grid", "Message", "Score", "Path"]
        self.model = DecodeTableModel(cols, self.config)
        
        # v2.1.0: Give model access to hunt manager for highlighting
        if self.hunt_manager:
            self.model.hunt_manager = self.hunt_manager
            logger.info(f"Hunt Mode: Assigned hunt_manager to model (list={self.hunt_manager.get_list()})")
            # Refresh table when hunt list changes (e.g., via dialog)
            def refresh_hunt_highlighting():
                """Force full table repaint when hunt list changes."""
                if self.model.rowCount() > 0:
                    self.model.dataChanged.emit(
                        self.model.index(0, 0),
                        self.model.index(self.model.rowCount() - 1, self.model.columnCount() - 1),
                        [Qt.ItemDataRole.BackgroundRole]
                    )
            self.hunt_manager.hunt_list_changed.connect(refresh_hunt_highlighting)
        else:
            logger.warning("Hunt Mode: hunt_manager is None, highlighting disabled")
        
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        
        # v2.1.0: Size policy - allow table to shrink to make room for dock widgets
        self.table_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table_view.setMinimumHeight(100)  # Ensure table never disappears completely
        
        # v2.1.0: Custom delegate for hunt highlighting (bypasses stylesheet override)
        self.table_view.setItemDelegate(HuntHighlightDelegate(self.table_view))
        
        # v2.1.0: Enable context menu for hunt mode
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.hunt_coordinator.show_table_context_menu)
        
        self.table_view.setAlternatingRowColors(False)  # Let model control backgrounds
        self.table_view.setStyleSheet("""
            QTableView { 
                background-color: #121212; 
                gridline-color: #333; 
                color: #EEE;
                outline: 0; 
                border: none;
            }
            QTableView::item {
                border: none;
                padding: 2px;
            }
            QTableView::item:selected { 
                background-color: #1a3a5c; 
                color: #FFFFFF; 
            }
            QHeaderView::section { 
                background-color: #222; 
                color: #DDD; 
                padding: 4px; 
                border: 1px solid #444; 
            }
        """)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSortIndicatorShown(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.clicked.connect(self.on_row_click)
        
        # --- v2.0.3: Restore column widths ---
        self._restore_column_widths()
        
        # v2.2.0: Tactical observation toast bar (between info bar and table)
        self.tactical_toast = TacticalToast()
        main_layout.addWidget(self.tactical_toast)
        
        # Table is the central content
        main_layout.addWidget(self.table_view)
        
        # --- TARGET VIEW DOCK (Dashboard + Band Map) ---
        self.target_dock = QDockWidget("Target View", self)
        self.target_dock.setObjectName("target_dock")
        
        # Container for Dashboard + Band Map
        target_container = QWidget()
        target_container.setMinimumHeight(380)  # Ensure band map shows all sections including local decodes
        # Note: No maximum height - setCorner() fix handles layout, user can resize freely
        target_layout = QVBoxLayout(target_container)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(0)
        
        # Dashboard
        self.dashboard = TargetDashboard()
        self.dashboard.sync_requested.connect(self.sync_to_jtdx)  # v2.0.6
        self.dashboard.status_message.connect(self.update_status_msg)  # v2.1.0: clipboard feedback
        self.dashboard.manual_target_requested.connect(self._on_manual_target)  # v2.4.4
        target_layout.addWidget(self.dashboard)
        
        # Band Map
        self.band_map = BandMapWidget()
        self.band_map.recommendation_changed.connect(self.on_recommendation)
        self.band_map.status_message.connect(self.update_status_msg)  # v2.1.0: clipboard feedback
        target_layout.addWidget(self.band_map)
        
        self.target_dock.setWidget(target_container)
        self.target_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.target_dock)
        
        # Menu
        # v2.2.2: Force menu bar inside app window on Linux (prevents GNOME/Ubuntu
        # global menu integration from swallowing Edit/View/Tools menus).
        # Not needed on macOS (native menu bar works correctly) or Windows (no global menu bar).
        if sys.platform.startswith('linux'):
            self.menuBar().setNativeMenuBar(False)
        menu = self.menuBar()
        
        # --- FILE MENU ---
        file_menu = menu.addMenu("File")
        refresh_action = QAction("Force Refresh Spots", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self.analyzer.force_refresh)
        file_menu.addAction(refresh_action)
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # --- EDIT MENU (NEW for v2.0.3) ---
        edit_menu = menu.addMenu("Edit")
        
        # v2.0.3: Clear Target action with Ctrl+R shortcut
        clear_target_action = QAction("Clear Target", self)
        clear_target_action.setShortcut(QKeySequence("Ctrl+R"))
        clear_target_action.triggered.connect(self.clear_target)
        edit_menu.addAction(clear_target_action)
        
        # v2.0.6: Fetch target from logging app with Ctrl+Y shortcut
        sync_jtdx_action = QAction("Fetch Target from WSJT-X/JTDX", self)
        sync_jtdx_action.setShortcut(QKeySequence("Ctrl+Y"))
        sync_jtdx_action.triggered.connect(self.sync_to_jtdx)
        edit_menu.addAction(sync_jtdx_action)
        
        # --- v2.1.0: VIEW MENU ---
        view_menu = menu.addMenu("View")
        
        # Panel visibility toggles - both docks work the same way
        view_menu.addAction(self.target_dock.toggleViewAction())
        # Insights dock toggle will be added after Insights panel setup
        self._view_menu = view_menu  # Store reference for adding insights toggle later
        
        view_menu.addSeparator()
        
        # Reset Layout action
        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.setToolTip("Restore default window layout")
        reset_layout_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout_action)
        
        # --- TOOLS MENU ---
        tools_menu = menu.addMenu("Tools")
        
        # v2.1.0: Hunt Mode
        if self.hunt_manager:
            hunt_list_action = QAction("Hunt List...", self)
            hunt_list_action.setShortcut(QKeySequence("Ctrl+H"))
            hunt_list_action.setToolTip("Manage stations you're hunting")
            hunt_list_action.triggered.connect(self.hunt_coordinator.show_list_dialog)
            tools_menu.addAction(hunt_list_action)
            tools_menu.addSeparator()
        
        # Add Insights menu items if available
        if self.local_intel:
            self.local_intel.add_menu_items(tools_menu)
        else:
            disabled_action = QAction("Insights (not available)", self)
            disabled_action.setEnabled(False)
            tools_menu.addAction(disabled_action)
        
        # Help Menu
        help_menu = menu.addMenu("Help")
        guide_action = QAction("User Guide", self)
        guide_action.setShortcut(QKeySequence("F1"))
        guide_action.triggered.connect(self.open_user_guide)
        help_menu.addAction(guide_action)
        
        # v2.0.9: Connection Help menu item
        connection_help_action = QAction("Connection Help...", self)
        connection_help_action.triggered.connect(self.health_monitor.show_connection_help)
        help_menu.addAction(connection_help_action)
        
        help_menu.addSeparator()
        
        # v2.0.9: Debug Logging toggle
        self.debug_logging_action = QAction("Enable Debug Logging", self)
        self.debug_logging_action.setCheckable(True)
        self.debug_logging_action.setChecked(False)
        self.debug_logging_action.setToolTip("Enable verbose logging for troubleshooting")
        self.debug_logging_action.triggered.connect(self._toggle_debug_logging)
        help_menu.addAction(self.debug_logging_action)
        
        # v2.0.9: Open Log Folder
        open_log_action = QAction("Open Log Folder...", self)
        open_log_action.setToolTip("Open the folder containing log files")
        open_log_action.triggered.connect(self._open_log_folder)
        help_menu.addAction(open_log_action)
        
        help_menu.addSeparator()
        
        # v2.5.5: Hide "Check for Updates" on MSIX/Store installs.
        # Store-installed users get updates through the Store, not GitHub.
        if not is_packaged_install():
            check_update_action = QAction("Check for Updates", self)
            check_update_action.triggered.connect(lambda: self.update_checker.start_check(manual=True))
            help_menu.addAction(check_update_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        # --- ICON SETUP ---
        app_icon = QIcon("icon.ico")
        self.setWindowIcon(app_icon) # Top-left of window & Taskbar

        # --- SYSTEM TRAY ---
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(app_icon) 
        
        # Tray Menu
        tray_menu = QMenu()
        show_action = QAction("Show Dashboard", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # --- LOCAL INTELLIGENCE PANEL SETUP ---
        if self.local_intel:
            try:
                self.local_intel.setup(self)
                
                # v2.1.0: Connect Phase 2 Path Intelligence analysis request
                if self.local_intel.insights_panel:
                    self.local_intel.insights_panel.path_analyze_requested.connect(
                        self._on_path_analyze_requested
                    )
                
                # v2.1.0: Add insights panel toggle to View menu
                if self.local_intel.insights_dock and hasattr(self, '_view_menu'):
                    # Insert before the separator (position 2, after decode and target toggles)
                    actions = self._view_menu.actions()
                    if len(actions) >= 2:
                        self._view_menu.insertAction(actions[2], self.local_intel.insights_dock.toggleViewAction())
                
                # --- v2.1.0: Restore dock widget positions (must be after all docks are created) ---
                dock_state = self.config.get('WINDOW', 'dock_state')
                if dock_state:
                    self.restoreState(QByteArray.fromHex(dock_state.encode()))
                    
                    # v2.1.0: Re-apply corner ownership AFTER restoreState
                    # On Windows, restoreState can override setCorner, causing bottom dock 
                    # to span full width instead of right dock spanning full height
                    self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
                    self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
            except Exception as e:
                logger.error(f"Failed to setup Local Intelligence panel: {e}")
    
    # --- v2.0.3: Column width persistence ---
    def _restore_column_widths(self):
        """Restore saved column widths from config."""
        widths_str = self.config.get('WINDOW', 'column_widths', fallback='')
        if widths_str:
            try:
                widths = [int(w) for w in widths_str.split(',')]
                for i, width in enumerate(widths):
                    if i < self.model.columnCount() and width > 0:
                        self.table_view.setColumnWidth(i, width)
            except (ValueError, IndexError) as e:
                logger.debug(f"Could not restore column widths: {e}")
    
    def _save_column_widths(self):
        """Save current column widths to config."""
        widths = []
        for i in range(self.model.columnCount()):
            widths.append(str(self.table_view.columnWidth(i)))
        self.config.save_setting('WINDOW', 'column_widths', ','.join(widths))
    
    # --- v2.1.0: Reset Layout functionality ---
    def _reset_layout(self):
        """Reset dock widgets to their default positions.
        
        Shows all panels, un-floats them, and restores default positions.
        Also ensures window fits on screen.
        """
        # v2.1.0: CRITICAL - Re-apply corner ownership BEFORE re-docking
        # This makes right dock span full height, bottom dock only spans left of it
        # Without this, Windows reverts to bottom dock spanning full width
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        
        # Remove docks first to reset their state completely
        self.removeDockWidget(self.target_dock)
        if self.local_intel and self.local_intel.insights_dock:
            self.removeDockWidget(self.local_intel.insights_dock)
        
        # Re-add docks in correct order: RIGHT dock first (so it claims corners), then BOTTOM
        if self.local_intel and self.local_intel.insights_dock:
            self.local_intel.insights_dock.show()
            self.local_intel.insights_dock.setFloating(False)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.local_intel.insights_dock)
        
        self.target_dock.show()
        self.target_dock.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.target_dock)
        
        # Ensure window fits on screen
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            # Reset to reasonable size that fits on screen
            new_width = min(1200, available.width() - 100)
            new_height = min(850, available.height() - 100)
            self.resize(new_width, new_height)
            # Center on screen
            self.move(
                available.x() + (available.width() - new_width) // 2,
                available.y() + (available.height() - new_height) // 2
            )
        
        # Clear saved dock state so next restart also uses defaults
        self.config.save_setting('WINDOW', 'dock_state', '')
        self.config.save_setting('WINDOW', 'geometry', '')  # Also clear saved geometry
        
        logger.info("Layout reset to defaults")
    
    # --- v2.0.3: Auto-clear setting handler ---
    def _on_auto_clear_changed(self, state):
        """Handle auto-clear checkbox state change."""
        enabled = 'true' if state == Qt.CheckState.Checked.value else 'false'
        self.config.save_setting('BEHAVIOR', 'auto_clear_on_log', enabled)
    
    # --- v2.1.0: Auto-clear on band change handler (Brian's request) ---
    def _on_auto_clear_band_changed(self, state):
        """Handle auto-clear on band change checkbox state change."""
        enabled = 'true' if state == Qt.CheckState.Checked.value else 'false'
        self.config.save_setting('BEHAVIOR', 'auto_clear_on_band', enabled)
    
    def _freq_to_band(self, freq):
        """Convert frequency in Hz to band string."""
        f = freq / 1_000_000
        if 1.8 <= f <= 2.0: return "160m"
        if 3.5 <= f <= 4.0: return "80m"
        if 5.3 <= f <= 5.4: return "60m"
        if 7.0 <= f <= 7.3: return "40m"
        if 10.1 <= f <= 10.15: return "30m"
        if 14.0 <= f <= 14.35: return "20m"
        if 18.068 <= f <= 18.168: return "17m"
        if 21.0 <= f <= 21.45: return "15m"
        if 24.89 <= f <= 24.99: return "12m"
        if 28.0 <= f <= 29.7: return "10m"
        if 50.0 <= f <= 54.0: return "6m"
        return "?"

    def setup_connections(self):
        self.udp.new_decode.connect(self.handle_decode)
        self.udp.status_update.connect(self.handle_status_update)
        # v2.0.3: Connect QSO Logged signal
        self.udp.qso_logged.connect(self.on_qso_logged)
        # Note: Removed cache_updated -> refresh_analysis connection
        # With target perspective, re-analyzing all 500 rows every 2 seconds is too expensive.
        # Reconnect cache_updated to lightweight path refresh (not full analysis)
        self.analyzer.cache_updated.connect(self.refresh_paths)
        self.analyzer.status_message.connect(self.update_status_msg)
        
        # v2.1.0: Hunt Mode - check MQTT spots against hunt list
        if self.hunt_manager:
            self.analyzer.spot_received.connect(self.hunt_coordinator.check_spot)
    
    # --- v2.3.3: Unified target-change handler ---
    def _set_new_target(self, call, grid="", freq=0, row_data=None):
        """Unified target-change handler. All target changes flow through here.
        
        v2.3.3: Centralized to fix inconsistent state updates across four
        separate code paths (clear_target, sync_to_jtdx, on_status,
        on_row_click). Previously, some paths missed updating analyzer grid,
        activity state, F/H state, tactical toast, or perspective display.
        
        Args:
            call: Target callsign (empty string to clear)
            grid: Target grid square
            freq: Target audio frequency offset
            row_data: Decode table row dict (if available; otherwise searched)
        """
        is_clearing = not call
        
        # --- Find row data if not provided ---
        if call and not row_data:
            for row in self.model._data:
                if row.get('call') == call:
                    row_data = row
                    if not grid:
                        grid = row.get('grid', '')
                    if not freq:
                        freq = row.get('freq', 0)
                    break
        
        prev_target = self.current_target_call
        logger.info(f"Target: '{prev_target}' → '{call or '(cleared)'}'")
        
        # --- OUTCOME RECORDER: Record outcome for previous target BEFORE state resets ---
        # Must happen here — after this point, scoring state gets cleared.
        # Safe to call if no active target (recorder checks has_active_target).
        if prev_target:
            trigger = 'CLEARED' if is_clearing else 'TARGET_CHANGED'
            self._record_outcome_for_current_target(trigger)
        
        # --- 1. Core state ---
        self.current_target_call = call
        self.current_target_grid = grid
        self.analyzer.current_target_grid = grid
        
        # --- 2. Reset per-target tracking ---
        self._target_activity_state = 'unknown'
        self._target_activity_other = None
        self._target_activity_time = 0
        self._inferred_competitors.clear()
        self.dashboard.update_activity('unknown')  # v2.3.5: Reset dashboard cached state too
        
        # --- 3. F/H per-target state (keep manual/UDP mode setting) ---
        self._fh_fox_qso = False
        self._fh_dialog_shown = False
        self.band_map.set_fox_qso(False)
        if self._fh_source == 'inferred':
            self._set_fox_hound_active(False, None, None)
        
        # --- 4. Table highlighting ---
        self.model.set_target_call(call if call else None)
        
        # --- 5. Dashboard ---
        if is_clearing:
            self._is_manual_target = False
            self.dashboard.update_data(None)
        elif row_data:
            # Station is in decode table — not a manual target anymore
            if self._is_manual_target:
                self._is_manual_target = False
                logger.info(f"Manual target {call} found in decode table — switching to normal mode")
            # Re-analyze with full perspective before displaying
            self.analyzer.analyze_decode(row_data, use_perspective=True)
            row_data['manual_target'] = False
            self.dashboard.update_data(row_data)
        else:
            # Have call but no row data — may be manual target or early UDP target
            # v2.4.4: Show minimal dashboard with manual indicator
            manual_data = {
                'call': call,
                'time': '',
                'snr': '--',
                'dt': '--',
                'freq': 0,
                'message': '',
                'grid': grid or '--',
                'prob': '--',
                'path': '--',
                'competition': '--',
                'manual_target': self._is_manual_target,
            }
            self.dashboard.update_data(manual_data)
        
        # --- 6. Band map ---
        self.band_map.set_target_freq(freq)
        self.band_map.set_target_call(call)
        self.band_map.set_target_grid(grid)
        if is_clearing:
            self.band_map.update_perspective({
                'tier1': [], 'tier2': [], 'tier3': [], 'global': []
            })
        
        # --- 7. Local Intelligence ---
        if self.local_intel:
            try:
                self.local_intel.set_target(call if call else "", grid, 
                                           manual=self._is_manual_target)
                if row_data and not is_clearing:
                    self._update_local_intel_path_status(row_data)
                    comp_str = str(row_data.get('competition', ''))
                    if hasattr(self.local_intel, 'insights_panel'):
                        self.local_intel.insights_panel.set_target_competition(comp_str)
            except Exception as e:
                logger.debug(f"Error updating local intel target: {e}")
        
        # --- 8. Tactical toast ---
        self.tactical_toast.reset_state()
        
        # --- 9. Perspective update (fetches PSK Reporter data for new target) ---
        if not is_clearing:
            self._update_perspective_display()
        
        # --- 10. IONIS propagation prediction (v2.4.0) ---
        self._ionis_shown = False
        if is_clearing:
            self._clear_ionis_prediction()
        elif self._ionis_engine:
            self._update_ionis_prediction()
        
        # --- 11. OUTCOME RECORDER: Register new target ---
        if self.outcome_recorder and call:
            sfi = 0
            k = 0
            if hasattr(self, '_solar_data') and self._solar_data:
                sfi = self._solar_data.get('sfi', 0)
                k = self._solar_data.get('k', 0)
            # Capture path status BEFORE we start calling — this is predictive
            # (non-tautological). Path established during the QSO exchange
            # will show in the outcome snapshot's 'path' field instead.
            path_now = str(row_data.get('path', '')) if row_data else ''
            self.outcome_recorder.on_target_selected(
                call, grid,
                band=getattr(self, '_current_band', ''),
                sfi=sfi, k=k,
                path_at_select=path_now
            )
    
    # --- v2.0.3: Clear Target functionality (suggested by KC0GU) ---
    
    def _build_outcome_snapshot(self) -> dict:
        """Build a snapshot of QSOP's ephemeral state for OutcomeRecorder.
        
        MUST be called BEFORE any state-clearing code runs, otherwise
        scoring context will be lost.
        
        Returns dict with all keys expected by OutcomeRecorder.record_outcome().
        """
        # Recommended frequency and score
        rec_freq = getattr(self.band_map, 'best_offset', 0) or 0
        rec_score = 0
        if hasattr(self.band_map, 'score_map') and 0 <= rec_freq < len(self.band_map.score_map):
            rec_score = float(self.band_map.score_map[rec_freq])
        
        # Actual TX frequency and score
        tx_freq = getattr(self.band_map, 'current_tx_freq', 0) or 0
        tx_score = 0
        score_reason = 0
        if hasattr(self.band_map, 'score_map') and 0 < tx_freq < len(self.band_map.score_map):
            tx_score = float(self.band_map.score_map[tx_freq])
        if hasattr(self.band_map, 'score_reason') and 0 < tx_freq < len(self.band_map.score_reason):
            score_reason = int(self.band_map.score_reason[tx_freq])
        
        # Path and competition from current target row
        path = ''
        competition = 0
        if self.current_target_call:
            for row in self.model._data:
                if row.get('call') == self.current_target_call:
                    path = str(row.get('path', ''))
                    comp_str = str(row.get('competition', ''))
                    try:
                        competition = int(comp_str.split()[0])  # "3 local" → 3
                    except (ValueError, IndexError):
                        competition = 0
                    break
        
        # Reporter count from scoring context
        reporters = 0
        if hasattr(self.band_map, '_scoring_context'):
            reporters = self.band_map._scoring_context.get('regional_coverage', 0)
        
        # IONIS status — read from propagation widget label
        ionis = ''
        try:
            if (self.local_intel and
                    hasattr(self.local_intel, 'insights_panel') and
                    self.local_intel.insights_panel and
                    hasattr(self.local_intel.insights_panel, 'propagation_widget')):
                pw = self.local_intel.insights_panel.propagation_widget
                if pw.isVisible():
                    label_text = pw.prediction_label.text()
                    # Label format: "20m PM95→FN42 OPEN" — status is last word
                    for status in ('STRONG', 'OPEN', 'MARGINAL', 'CLOSED'):
                        if status in label_text:
                            ionis = status
                            break
        except Exception:
            pass
        
        # F/H mode
        fh_mode = 'normal'
        if self._fh_active:
            fh_mode = self._fh_type or 'fh'
        
        # Solar data
        sfi = 0
        k = 0
        if hasattr(self, '_solar_data') and self._solar_data:
            sfi = self._solar_data.get('sfi', 0)
            k = self._solar_data.get('k', 0)
        
        return {
            'rec_freq': rec_freq,
            'rec_score': rec_score,
            'tx_freq': tx_freq,
            'tx_score': tx_score,
            'score_reason': score_reason,
            'path': path,
            'competition': competition,
            'reporters': reporters,
            'ionis': ionis,
            'fh_mode': fh_mode,
            'band': getattr(self, '_current_band', ''),
            'sfi': sfi,
            'k': k,
            'a': None,  # A-index not yet implemented
        }
    
    def _record_outcome_for_current_target(self, trigger: str):
        """Record outcome for the current target if OutcomeRecorder is active.
        
        Safe to call multiple times — the recorder resets after recording,
        so subsequent calls are no-ops (has_active_target returns False).
        
        Args:
            trigger: 'QSO_LOGGED', 'CLEARED', 'TARGET_CHANGED', 
                     'BAND_CHANGED', 'APP_CLOSED'
        """
        if not self.outcome_recorder or not self.outcome_recorder.has_active_target:
            return
        try:
            snapshot = self._build_outcome_snapshot()
            self.outcome_recorder.record_outcome(trigger, snapshot)
        except Exception as e:
            logger.debug(f"OutcomeRecorder: error recording outcome: {e}")

    def clear_target(self):
        """Clear the current target selection.
        
        Resets all target-related state and UI to "NO TARGET" mode.
        Can be triggered via Ctrl+R shortcut or Clear Target button.
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        self._set_new_target("", "", 0, None)
    
    # --- v2.0.3: QSO Logged handler (suggested by KC0GU) ---
    def on_qso_logged(self, data):
        """Handle QSO Logged notification from WSJT-X/JTDX.
        
        When a QSO is logged, optionally clear the target if:
        1. Auto-clear is enabled
        2. The logged callsign matches our current target
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        logged_call = data.get('dx_call', '').upper()
        current_upper = self.current_target_call.upper() if self.current_target_call else ''
        
        # OUTCOME RECORDER: Record QSO_LOGGED BEFORE auto-clear resets state.
        # This must fire first so the snapshot captures scoring context.
        if logged_call and logged_call == current_upper:
            self._record_outcome_for_current_target('QSO_LOGGED')
        
        # Check if auto-clear is enabled
        if self.chk_auto_clear.isChecked():
            # Only clear if we logged the station we were targeting
            if logged_call and logged_call == current_upper:
                logger.info(f"Auto-clear: Target cleared after logging {logged_call}")
                self.clear_target()

    # --- v2.0.6: Fetch target from JTDX (suggested by KC0GU) ---
    def sync_to_jtdx(self):
        """Fetch target from WSJT-X/JTDX into QSO Predictor.
        
        When user has selected a different station in QSO Predictor,
        double-clicking in JTDX won't re-send the UDP message (JTDX
        thinks it's already on that station). This button forces
        QSO Predictor to match JTDX's selection.
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        if not self.jtdx_last_dx_call:
            return
        if self.jtdx_last_dx_call == self.current_target_call:
            return
        
        logger.info(f"Sync: Syncing to JTDX target: {self.jtdx_last_dx_call}")
        self._is_manual_target = False  # v2.4.4: Not a manual target
        self._set_new_target(self.jtdx_last_dx_call)

    # --- v2.4.4: Manual target entry ---
    
    # Common DXCC prefix → approximate grid centroid (fallback when no other source)
    _PREFIX_GRIDS = {
        # Japan
        'JA': 'PM95', 'JH': 'PM95', 'JR': 'PM95', 'JE': 'PM95', 'JF': 'PM95',
        'JG': 'PM95', 'JI': 'PM95', 'JJ': 'PM95', 'JK': 'PM95', 'JL': 'PM95',
        'JM': 'PM95', 'JN': 'PM95', 'JO': 'PM95', 'JP': 'PM95', 'JQ': 'PM95',
        'JS': 'PM95',
        # Central/East Asia
        'JT': 'ON48',  # Mongolia
        'HL': 'PM37', 'DS': 'PM37',  # South Korea
        'BV': 'PL05',  # Taiwan
        'BY': 'OM89', 'BA': 'OM89', 'BD': 'OM89', 'BG': 'OM89',  # China
        'VU': 'MK82', 'AT': 'MK82',  # India
        # CIS / Former Soviet
        'UA': 'KO85', 'RA': 'KO85', 'RV': 'KO85', 'RW': 'KO85', 'RX': 'KO85',
        'R': 'KO85',  # Russia (single letter prefix)
        'UN': 'MN53', 'UP': 'MN53', 'UL': 'MN53',  # Kazakhstan
        'UK': 'MM39', 'UJ': 'MM39',  # Uzbekistan
        'EX': 'MM72', 'EZ': 'MM72',  # Kyrgyzstan / Turkmenistan
        'UR': 'KN28', 'UT': 'KN28', 'UX': 'KN28', 'US': 'KN28',  # Ukraine
        'EU': 'KO33', 'EW': 'KO33',  # Belarus
        'LY': 'KO24',  # Lithuania
        'YL': 'KO26',  # Latvia
        'ES': 'KO29',  # Estonia
        'ER': 'KN47',  # Moldova
        '4L': 'LN21',  # Georgia
        '4J': 'LM49',  # Azerbaijan
        'EK': 'LN20',  # Armenia
        # Oceania
        'VK': 'QF56', 'AX': 'QF56',  # Australia
        'ZL': 'RF73',  # New Zealand
        'DU': 'PK04', 'DV': 'PK04',  # Philippines
        'YB': 'OI33', 'YC': 'OI33', 'YD': 'OI33',  # Indonesia
        '9M': 'OJ11', '9W': 'OJ11',  # Malaysia
        'HS': 'OK03', 'E2': 'OK03',  # Thailand
        'XV': 'OK30', '3W': 'OK30',  # Vietnam
        'XW': 'NK97',  # Laos
        'V8': 'OJ95',  # Brunei
        'FK': 'RG37',  # New Caledonia
        'FO': 'BH51',  # French Polynesia
        'KH6': 'BL11', 'KL7': 'BP51', 'KP4': 'FK68',
        'NH6': 'BL11', 'NL7': 'BP51', 'NP4': 'FK68',
        'WH6': 'BL11', 'WL7': 'BP51', 'WP4': 'FK68',
        'AH6': 'BL11', 'AL7': 'BP51',
        # Canada
        'VE': 'FN03', 'VA': 'FN03', 'VY': 'FN03', 'VO': 'GN37',
        # Europe
        'G': 'IO91', 'M': 'IO91', '2E': 'IO91',
        'GI': 'IO65', 'GW': 'IO71', 'GM': 'IO86', 'GD': 'IO74',
        'DL': 'JO51', 'DA': 'JO51', 'DB': 'JO51', 'DC': 'JO51', 'DD': 'JO51',
        'DF': 'JO51', 'DG': 'JO51', 'DH': 'JO51', 'DJ': 'JO51', 'DK': 'JO51',
        'DO': 'JO51',
        'F': 'JN18', 'ON': 'JO20', 'PA': 'JO22', 'PH': 'JO22',
        'I': 'JN61', 'IK': 'JN61', 'IZ': 'JN61',
        'EA': 'IN80', 'EB': 'IN80', 'EC': 'IN80',
        'CT': 'IM58', 'CS': 'IM58',
        'SM': 'JO89', 'SA': 'JO89', 'OH': 'KP20', 'OZ': 'JO55',
        'LA': 'JO59', 'LB': 'JO59',
        'SP': 'JO91', 'SQ': 'JO91', 'OK': 'JN79', 'OL': 'JN79',
        'HA': 'JN97', 'HG': 'JN97',
        'YU': 'KN04', 'YT': 'KN04',
        'OE': 'JN78',  # Austria
        'HB': 'JN47',  # Switzerland
        'OY': 'IP62',  # Faroe Islands
        'TF': 'HP94',  # Iceland
        'SV': 'KM18', 'SW': 'KM18',  # Greece
        '9A': 'JN75',  # Croatia
        'S5': 'JN76',  # Slovenia
        'Z3': 'KN01',  # North Macedonia
        'ZA': 'KN01',  # Albania
        'LZ': 'KN22',  # Bulgaria
        'YO': 'KN25',  # Romania
        'E7': 'JN84',  # Bosnia
        # Middle East
        'TA': 'KN30', 'TC': 'KN30',  # Turkey
        '5B': 'KM65',  # Cyprus
        'A4': 'LL93', 'A6': 'LL65', 'A7': 'LL55',
        'A9': 'LL46', 'HZ': 'KL41', '9K': 'LL49',
        'OD': 'KM73',  # Lebanon
        '4X': 'KM72', '4Z': 'KM72',  # Israel
        'YK': 'KM74',  # Syria
        'YI': 'LM13',  # Iraq
        'EP': 'LL48', 'EQ': 'LL48',  # Iran
        'AP': 'ML44',  # Pakistan
        # Africa
        '3B8': 'MH87', '5H': 'KI73', '5Z': 'KI88',
        '9J': 'KH25', '7Q': 'KH74', 'ZD8': 'II22',
        'CN': 'IM63',  # Morocco
        '7X': 'JM16',  # Algeria
        'SU': 'KL30',  # Egypt
        'ST': 'KK55',  # Sudan
        'ET': 'KJ19',  # Ethiopia
        '5A': 'JM73',  # Libya
        'TU': 'IJ56',  # Ivory Coast
        '6W': 'IK14',  # Senegal
        '5N': 'JJ17',  # Nigeria
        'TR': 'JI31',  # Gabon
        '9X': 'KI49',  # Rwanda
        'V5': 'JG87',  # Namibia
        'ZS': 'KG33', 'ZR': 'KG33',  # South Africa
        # Central America / Caribbean
        'TI': 'EJ89', 'HP': 'FJ09', 'HK': 'FJ34', 'YV': 'FJ66',
        'XE': 'EK09', 'XA': 'EK09',  # Mexico
        'VP9': 'FM72', 'V3': 'EK57', '8P': 'GK03',
        'HI': 'FK58',  # Dominican Republic
        'CO': 'FL11', 'CM': 'FL11',  # Cuba
        'YS': 'EK53',  # El Salvador
        'TG': 'EK44',  # Guatemala
        'HR': 'EK64',  # Honduras
        'PJ': 'FK52',  # Netherlands Antilles
        'J3': 'FK92',  # Grenada
        'J6': 'FK93',  # St Lucia
        'VP2': 'FK87',  # Anguilla/Montserrat
        'FG': 'FK96',  # Guadeloupe
        'FM': 'FK94',  # Martinique
        # South America
        'LU': 'GF05', 'LW': 'GF05',  # Argentina
        'PY': 'GG87', 'PP': 'GG87', 'PR': 'GG87', 'PS': 'GG87', 'PT': 'GG87',
        'PU': 'GG87',  # Brazil
        'CE': 'FF46', 'CA': 'FF46',  # Chile
        'HC': 'FI09',  # Ecuador
        'OA': 'FH17',  # Peru
        'CP': 'FH33',  # Bolivia
        'ZP': 'GG14',  # Paraguay
        'CX': 'GF15',  # Uruguay
    }
    
    def _lookup_grid(self, call):
        """v2.4.4: Grid lookup cascade — local sources first, then prefix fallback.
        
        Priority:
        1. Analyzer's call_grid_map (recent MQTT/PSK Reporter data)
        2. Decode table (currently displayed stations)
        3. DXCC prefix centroid (approximate, always available)
        
        Returns:
            tuple: (grid_str, source_str) e.g. ('PM95', 'PSK Reporter') or ('', 'none')
        """
        call = call.upper().strip()
        
        # 1. Analyzer's call_grid_map (populated from local decodes)
        grid = self.analyzer.call_grid_map.get(call, '')
        if grid and len(grid) >= 2:
            logger.info(f"Manual target grid lookup: {call} → {grid} (call_grid_map)")
            return grid, 'local decode'
        
        # 2. Receiver cache — if station uploads to PSK Reporter, their grid
        #    is in every spot they reported (the 'grid' field = receiver's grid)
        with self.analyzer.lock:
            if call in self.analyzer.receiver_cache:
                spots = self.analyzer.receiver_cache[call]
                if spots:
                    grid = spots[-1].get('grid', '')  # Most recent spot
                    if grid and len(grid) >= 2:
                        logger.info(f"Manual target grid lookup: {call} → {grid} (PSK Reporter receiver)")
                        return grid, 'PSK Reporter'
        
        # 3. Decode table rows
        for row in self.model._data:
            if row.get('call') == call:
                grid = row.get('grid', '')
                if grid and len(grid) >= 2:
                    logger.info(f"Manual target grid lookup: {call} → {grid} (decode table)")
                    return grid, 'local decode'
        
        # 4. DXCC prefix fallback — try longest prefix match first
        # Handle special prefixes like KH6, KL7, KP4 before single-letter
        for prefix_len in (3, 2, 1):
            prefix = call[:prefix_len]
            if prefix in self._PREFIX_GRIDS:
                grid = self._PREFIX_GRIDS[prefix]
                logger.info(f"Manual target grid lookup: {call} → {grid} (DXCC prefix '{prefix}', approximate)")
                return grid, f'DXCC prefix (approx)'
        
        # 5. US callsign heuristic — W/K/N/AA-AL + digit gives rough area
        if len(call) >= 2 and call[0] in ('W', 'K', 'N'):
            logger.info(f"Manual target grid lookup: {call} → no grid (US call, too broad)")
            return '', 'none'
        
        logger.info(f"Manual target grid lookup: {call} → no grid found")
        return '', 'none'
    
    def _on_manual_target(self, call):
        """v2.4.4: Handle manually entered target callsign.
        
        Looks up grid from local caches and DXCC prefix table,
        then sets target with manual indicator.
        """
        call = call.upper().strip()
        if not call:
            return
        
        # Don't re-target if already targeting this station
        if call == self.current_target_call:
            logger.info(f"Manual target: {call} already targeted")
            return
        
        # Look up grid
        grid, source = self._lookup_grid(call)
        
        logger.info(f"Manual target: {call}, grid={grid or '(unknown)'} via {source}")
        
        # Set the manual target flag BEFORE calling _set_new_target
        self._is_manual_target = True
        
        # Call unified target handler
        self._set_new_target(call, grid=grid)
        
        # Show feedback in status bar
        if grid:
            self.update_status_msg(f"Manual target: {call} (grid {grid} via {source})")
        else:
            self.update_status_msg(f"Manual target: {call} (grid unknown — will resolve from spots)")

    def handle_decode(self, data):
        self.buffer.append(data)
        # Track decode rate
        if self._decode_start_time is None:
            from datetime import datetime
            self._decode_start_time = datetime.now()
        self._decode_count += 1

    def process_buffer(self):
        if not self.buffer: return
        
        # Check if we're at the bottom before adding rows
        scrollbar = self.table_view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 20
        
        chunk = self.buffer[:50]
        del self.buffer[:50]
        for item in chunk:
            self.analyzer.analyze_decode(item)
            
            # --- LOCAL INTELLIGENCE: Process decode ---
            if self.local_intel:
                self.local_intel.process_decode({
                    'callsign': item.get('call'),
                    'snr': item.get('snr'),
                    'frequency': item.get('freq'),
                    'message': item.get('message'),
                    'dt': item.get('dt', 0.0),
                    'mode': 'FT8',
                })
            
            # --- v2.3.0: TARGET ACTIVITY STATE ---
            if self.current_target_call:
                my_call = self.config.get('ANALYSIS', 'my_callsign', fallback='')
                state, other = parse_target_activity(
                    item.get('message', ''),
                    self.current_target_call.upper(),
                    my_call.upper()
                )
                if state:
                    self._update_target_activity(state, other)
            
            # --- OUTCOME RECORDER: Check for target response (RESPONDED detection) ---
            if self.outcome_recorder and self.current_target_call:
                self.outcome_recorder.on_decode(
                    item.get('call', ''),
                    item.get('message', '')
                )
            
            # v2.3.0: SuperFox auto-detection from decode content
            self._check_superfox_from_decodes(item.get('message', ''))
        
        # Disable sorting during batch add to prevent jitter
        self.table_view.setSortingEnabled(False)
        self.model.add_batch(chunk)
        self.table_view.setSortingEnabled(True)
        
        self.band_map.update_signals(chunk)
        
        # Auto-scroll to bottom if user was already there
        if at_bottom:
            self.table_view.scrollToBottom()

    def refresh_paths(self):
        """Lightweight refresh - just update path status for all rows."""
        # Throttle: only refresh every 2 seconds max
        now = time.time()
        if hasattr(self, '_last_path_refresh') and (now - self._last_path_refresh) < 2.0:
            return
        self._last_path_refresh = now
        
        # Disable sorting during update to prevent jitter
        self.table_view.setSortingEnabled(False)
        self.model.update_data_in_place(self.analyzer.update_path_only)
        self.table_view.setSortingEnabled(True)

    def refresh_analysis(self):
        self.model.update_data_in_place(self.analyzer.analyze_decode)

    def handle_status_update(self, status):
        now = time.time()
        
        # --- TARGET HANDLING (before throttle) ---
        # dx_call changes must be processed immediately — double-clicking a station
        # in WSJT-X/JTDX should update QSOP's target without waiting for the next
        # un-throttled status message. This is just a string comparison, no perf cost.
        dx_call = status.get('dx_call', '')
        if dx_call != self.jtdx_last_dx_call:
            self.jtdx_last_dx_call = dx_call
            if dx_call and dx_call != self.current_target_call:
                # v2.4.4: Pass DX grid from UDP status (was previously discarded)
                dx_grid = status.get('dx_grid', '')
                self._is_manual_target = False  # v2.4.4: Not a manual target
                self._set_new_target(dx_call, grid=dx_grid)
            # Note: If JTDX clears dx_call, we don't clear our target
            # (user may have manually selected something in the table)
        
        # --- OUTCOME RECORDER: Track TX cycle edges (before throttle) ---
        # Must run on every status update for reliable rising-edge detection.
        # Single boolean comparison — zero cost.
        if self.outcome_recorder:
            self.outcome_recorder.on_status_update(status.get('transmitting', False))
        
        # Throttle remaining UI updates: JTDX sends status many times per second
        if hasattr(self, '_last_status_time') and (now - self._last_status_time) < 0.5:
            return
        self._last_status_time = now
        
        dial = status.get('dial_freq', 0)
        if dial > 0:
            # v2.1.0: Check for band change before updating (Brian's request)
            try:
                old_band = getattr(self, '_current_band', None)
                new_band = self._freq_to_band(dial)
                
                if old_band and new_band != old_band:
                    # Band changed!
                    logger.info(f"Band change detected: {old_band} -> {new_band}")
                    chk_enabled = hasattr(self, 'chk_auto_clear_band') and self.chk_auto_clear_band.isChecked()
                    logger.info(f"Auto-clear QSY: checkbox={chk_enabled}, target={self.current_target_call}")
                    if chk_enabled:
                        logger.info(f"Auto-clearing decode table, band map, and target due to band change")
                        self.model.clear()  # Clear decode table
                        self.band_map.clear()  # Clear band map signals
                        self.clear_target()  # Clear target selection
                
                self._current_band = new_band
                
                # v2.4.0: Re-predict IONIS on band change (if target still set)
                if (self.current_target_call and self._ionis_engine and
                        old_band and new_band != old_band):
                    self._update_ionis_prediction()
                    
            except Exception as e:
                logger.error(f"Error in band change detection: {e}")
            
            self.analyzer.set_dial_freq(dial)
        
        # Update Band Map (Yellow Line)
        cur_tx = status.get('tx_df', 0)
        self.band_map.set_current_tx_freq(cur_tx)
        
        # v2.3.0: Fox/Hound mode detection from UDP Special Operation Mode
        special_mode = status.get('special_mode', 0)
        # Hound mode: value 6 (older WSJT-X) or 7 (newer with WW DIGI)
        # Note: WSJT-X sends 7 for BOTH Hound and SuperHound — can't distinguish
        is_hound = special_mode in (6, 7)
        if is_hound and not self._fh_active:
            logger.info(f"Fox/Hound: UDP special_mode={special_mode} — showing disambiguation dialog")
            self._show_fh_disambiguation_dialog('udp')
        elif not is_hound and self._fh_source == 'udp':
            logger.info(f"Fox/Hound: UDP special_mode={special_mode} — deactivating (was udp-triggered)")
            self._set_fox_hound_active(False, None, None)
        
        # --- LOCAL INTELLIGENCE: Update TX status ---
        if self.local_intel:
            # Check for TX enabled (transmitting or tx_enabled field)
            tx_enabled = status.get('transmitting', False) or status.get('tx_enabled', False)
            dx_call = status.get('dx_call', '')
            # Pass who we're calling so pileup status knows if we're calling THIS target
            self.local_intel.set_tx_status(tx_enabled, calling=dx_call)
        
        # Update Dashboard Text Immediately
        rec = self.band_map.best_offset
        self.dashboard.update_rec(rec, cur_tx)

 
    def on_row_click(self, index):
        logger.debug(f"on_row_click: row {index.row()}")
        row = index.row()
        if row < len(self.model._data):
            data = self.model._data[row]
            target_call = data.get('call', '')
            
            # Skip if clicking same target (avoid redundant processing)
            if target_call == self.current_target_call:
                logger.debug(f"Same target {target_call}, skipping")
                return
            
            self._is_manual_target = False  # v2.4.4: Not a manual target
            self._set_new_target(
                target_call,
                data.get('grid', ''),
                data.get('freq', 0),
                data
            )

    def _update_target_activity(self, state, other_call):
        """v2.3.0: Update target activity state from decoded message.
        
        Called when a local decode reveals what the target is doing.
        
        Args:
            state: Activity state from parse_target_activity()
            other_call: Callsign of station target is interacting with
        """
        import time as _time
        now = _time.time()
        prev_state = self._target_activity_state
        
        self._target_activity_state = state
        self._target_activity_other = other_call
        self._target_activity_time = now
        
        # Track inferred competitors (stations we know are competing because 
        # the target responded to them, even if we never saw them call)
        if state in ('working_other', 'completing_with_other') and other_call:
            self._inferred_competitors[other_call] = now
        
        # Clean up old inferred competitors (>2 minutes)
        cutoff = now - 120
        self._inferred_competitors = {
            c: t for c, t in self._inferred_competitors.items() if t > cutoff
        }
        
        # Update dashboard display
        self.dashboard.update_activity(state, other_call)
        
        # Toast triggers for significant state transitions
        target = self.current_target_call
        if state == 'cqing' and prev_state in ('working_other', 'completing_with_other', 'idle', 'unknown'):
            self.tactical_toast.show_toast(
                f"🎯 {target} is now CQing — call now!", 'success'
            )
        elif state == 'working_you' and prev_state != 'working_you':
            self.tactical_toast.show_toast(
                f"📡 {target} is responding to YOU!", 'success'
            )
        elif state == 'working_other' and prev_state == 'cqing':
            self.tactical_toast.show_toast(
                f"📡 {target} working {other_call} — competition confirmed", 'info'
            )
        
        # v2.3.0: Fox QSO detection — when F/H active and Fox responds to us
        if self._fh_active:
            if state in ('working_you', 'completing_with_you'):
                self._set_fox_qso_active(True)
            elif self._fh_fox_qso and state not in ('working_you', 'completing_with_you'):
                # Fox stopped responding to us — restore click-to-set
                self._set_fox_qso_active(False)
    
    def _check_target_activity_idle(self):
        """v2.3.0: Check if target activity should transition to idle.
        Called from refresh_target_perspective timer."""
        import time as _time
        if (self._target_activity_state not in ('idle', 'unknown') and 
            self._target_activity_time > 0 and
            _time.time() - self._target_activity_time > self._activity_idle_timeout):
            self._target_activity_state = 'idle'
            self._target_activity_other = None
            self.dashboard.update_activity('idle')

    # =========================================================================
    # v2.3.0: FOX/HOUND MODE MANAGEMENT
    # =========================================================================
    
    def _on_fh_combo_changed(self, index):
        """Handle F/H combo box selection: 0=Off, 1=F/H, 2=SuperF/H."""
        labels = ['Off', 'F/H', 'SuperF/H']
        logger.info(f"Fox/Hound: Combo box changed to {labels[index]} (index={index})")
        if index == 0:
            self._set_fox_hound_active(False, None, None)
        elif index == 1:
            self._set_fox_hound_active(True, 'manual', 'fh')
        elif index == 2:
            self._set_fox_hound_active(True, 'manual', 'superfh')
    
    def _show_fh_disambiguation_dialog(self, source):
        """Show dialog asking user to choose between old F/H and SuperF/H.
        
        Called when UDP detects Hound mode but can't tell which type.
        Only shown once per session (reset on target change or manual override).
        
        Args:
            source: 'udp' — what triggered the detection
        """
        if self._fh_dialog_shown:
            return
        self._fh_dialog_shown = True
        
        logger.info(f"Fox/Hound: Disambiguation dialog triggered (source={source})")
        
        title = "Hound Mode Detected"
        text = "WSJT-X reports Hound mode is active."
        
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(f"{text}\n\nWhich type of operation?")
        msg.setInformativeText(
            "Fox/Hound — TX clamped to 1000+ Hz, Fox controls your TX during QSO\n\n"
            "SuperFox/Hound — Full band (200-2800 Hz), you keep your calling frequency"
        )
        msg.setIcon(QMessageBox.Icon.Question)
        
        btn_fh = msg.addButton("Fox/Hound", QMessageBox.ButtonRole.AcceptRole)
        btn_sfh = msg.addButton("SuperFox/Hound", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg.addButton("Ignore", QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        
        clicked = msg.clickedButton()
        if clicked == btn_fh:
            logger.info("Fox/Hound: User selected Fox/Hound (old-style)")
            self._set_fox_hound_active(True, source, 'fh')
        elif clicked == btn_sfh:
            logger.info("Fox/Hound: User selected SuperFox/Hound")
            self._set_fox_hound_active(True, source, 'superfh')
        else:
            logger.info("Fox/Hound: User clicked Ignore")
    
    def _set_fox_hound_active(self, active, source, fh_type):
        """Master F/H state setter — called by all triggers.
        
        Args:
            active: True to enable F/H mode
            source: 'manual', 'udp', or 'inferred'
            fh_type: 'fh' (old-style, clamp 1000+) or 'superfh' (full band)
        """
        if active == self._fh_active and source == self._fh_source and fh_type == self._fh_type:
            return  # No change
        
        prev_active = self._fh_active
        prev_type = self._fh_type
        self._fh_active = active
        self._fh_source = source if active else None
        self._fh_type = fh_type if active else None
        
        # Only clamp to 1000+ Hz for old-style F/H, not SuperFox
        use_clamping = active and fh_type == 'fh'
        self.band_map.set_hound_mode(use_clamping)
        
        # Update combo box (without re-triggering signal)
        self.cmb_fh_mode.blockSignals(True)
        if not active:
            self.cmb_fh_mode.setCurrentIndex(0)  # Off
        elif fh_type == 'fh':
            self.cmb_fh_mode.setCurrentIndex(1)  # F/H
        elif fh_type == 'superfh':
            self.cmb_fh_mode.setCurrentIndex(2)  # SuperF/H
        self.cmb_fh_mode.blockSignals(False)
        
        # Toast on state change
        if active and not prev_active:
            if fh_type == 'fh':
                self.tactical_toast.show_toast(
                    "🦊 F/H mode — recommendations clamped to 1000+ Hz", 'info'
                )
            elif fh_type == 'superfh':
                self.tactical_toast.show_toast(
                    "🦊 SuperFox mode — full band available, finding best frequency", 'info'
                )
            logger.info(f"Fox/Hound: ACTIVATED (source={source}, type={fh_type})")
        elif active and prev_active and fh_type != prev_type:
            # Type changed while active
            logger.info(f"Fox/Hound: Type changed to {fh_type}")
        elif not active and prev_active:
            self.tactical_toast.show_toast(
                "F/H mode disabled — full frequency range restored", 'info'
            )
            # Reset Fox QSO state
            self._fh_fox_qso = False
            self.band_map.set_fox_qso(False)
            self._fh_dialog_shown = False
            logger.info("Fox/Hound: DEACTIVATED")
    
    def _check_superfox_from_decodes(self, message):
        """v2.3.0: Detect SuperFox from decode content.
        
        Looks for "verified" or "$VERIFY$" tokens in decoded messages,
        which are definitive SuperFox indicators. Only works with WSJT-X
        (JTDX cannot decode SuperFox).
        
        Note: Layer 2 F/H inference (frequency counting) was removed in v2.3.2.
        On standard frequencies nobody runs Fox, and on non-standard frequencies
        the frequency itself is sufficient — the counting logic was either
        wrong (false positive on standard freq) or redundant (non-standard freq).
        F/H detection now relies on manual combo box and UDP field 18 only.
        
        Args:
            message: Raw decoded message string
        """
        if not self.current_target_call or not message:
            return
        
        msg_lower = message.lower()
        if (('verified' in msg_lower or '$verify$' in msg_lower) and 
            self.current_target_call.upper() in message.upper() and
            self._fh_type != 'superfh'):
            logger.info(f"Fox/Hound: SuperFox detected — 'verified' in decode for {self.current_target_call}")
            self._set_fox_hound_active(True, 'inferred', 'superfh')
            self.tactical_toast.show_toast(
                f"🦊 {self.current_target_call} is verified SuperFox — full band available", 'info'
            )
    
    def _set_fox_qso_active(self, active):
        """v2.3.0: Set Fox QSO state — Fox is controlling our TX frequency.
        
        When active, click-to-set is disabled and recommendation line hidden.
        Called when activity state detects Fox responding to us.
        """
        if active == self._fh_fox_qso:
            return
        
        self._fh_fox_qso = active
        self.band_map.set_fox_qso(active)
        
        if active:
            if self._fh_type == 'superfh':
                self.tactical_toast.show_toast(
                    "🎯 Fox is calling you — stay on your frequency!", 'success'
                )
            else:
                self.tactical_toast.show_toast(
                    "🎯 Fox is calling you — TX frequency under Fox control!", 'success'
                )
            logger.info("Fox/Hound: Fox QSO active — click-to-set disabled")
        else:
            logger.info("Fox/Hound: Fox QSO ended — click-to-set restored")

    def _update_local_intel_path_status(self, row_data):
        """Update Local Intelligence with current path status."""
        if not self.local_intel:
            return

        status = PathStatus.from_display(str(row_data.get('path', '')))
        my_snr = row_data.get('my_snr_at_target', None)
        my_snr_reporter = row_data.get('my_snr_reporter', None)

        if status in (PathStatus.HEARD_BY_TARGET, PathStatus.REPORTED_IN_REGION):
            self.local_intel.set_path_status(status, my_snr=my_snr, reporter=my_snr_reporter)
        else:
            self.local_intel.set_path_status(status)

    def refresh_target_perspective(self):
        """Called periodically by timer to keep target perspective current."""
        if self.current_target_call:
            # v2.3.0: Check if target activity should transition to idle
            self._check_target_activity_idle()
            
            # Find and re-analyze the selected target with full perspective
            for row in self.model._data:
                if row.get('call') == self.current_target_call:
                    # v2.4.4: Station decoded locally — clear manual target indicator
                    if self._is_manual_target:
                        self._is_manual_target = False
                        logger.info(f"Manual target {self.current_target_call} now decoded locally")
                        # Update insights panel to remove ⚠ indicator
                        if self.local_intel and hasattr(self.local_intel, 'insights_panel'):
                            self.local_intel.insights_panel._is_manual_target = False
                            ip = self.local_intel.insights_panel
                            ip.target_label.setText(f"Target: {self.current_target_call}")
                    
                    # v2.4.0: Backfill grid if it wasn't available on target set
                    if not self.current_target_grid and row.get('grid'):
                        self.current_target_grid = row['grid']
                        self.analyzer.current_target_grid = row['grid']
                        logger.debug(f"Backfilled target grid: {row['grid']}")
                    
                    self.analyzer.analyze_decode(row, use_perspective=True)
                    
                    # v2.3.0: Augment competition with inferred competitors
                    # (stations we know about from target responses, not visible callers)
                    if self._inferred_competitors:
                        comp = row.get('competition', '')
                        inferred_count = len(self._inferred_competitors)
                        if comp in ('Clear', 'Unknown'):
                            # Replace with inferred data
                            if inferred_count == 1:
                                row['competition'] = f"Low ({inferred_count}) inferred"
                            else:
                                row['competition'] = f"Moderate ({inferred_count}) inferred"
                    
                    row['manual_target'] = False  # v2.4.4: Decoded = not manual
                    self.dashboard.update_data(row)
                    
                    # --- LOCAL INTELLIGENCE: Update path status ---
                    if self.local_intel:
                        self._update_local_intel_path_status(row)
                    
                    # --- v2.2.0: TACTICAL TOAST TRIGGERS ---
                    # Check competition changes
                    competition_str = str(row.get('competition', ''))
                    local_callers = 0
                    if self.local_intel and hasattr(self.local_intel, 'insights_panel'):
                        pw = self.local_intel.insights_panel.pileup_widget
                        if hasattr(pw, '_last_caller_count'):
                            local_callers = pw._last_caller_count
                    self.tactical_toast.check_competition_change(competition_str, local_callers)
                    
                    # v2.2.0: Forward target-side competition to Insights panel
                    # This bridges PSK Reporter intelligence → Insights for:
                    # - Pileup contrast alert (local vs target competition)
                    # - Strategy recommendation (accounts for hidden pileup)
                    # - Success prediction (effective competition = max of local, target)
                    if self.local_intel and hasattr(self.local_intel, 'insights_panel'):
                        self.local_intel.insights_panel.set_target_competition(competition_str)
                    
                    # Check path changes
                    path_str = str(row.get('path', ''))
                    self.tactical_toast.check_path_change(path_str, self.current_target_call)
                    
                    break
            
            # Update band map perspective
            self._update_perspective_display()
            
            # v2.4.4: Retry grid resolution for manual targets
            # (receiver_cache may have populated since initial target set)
            if not self.current_target_grid or len(self.current_target_grid) < 2:
                grid, source = self._lookup_grid(self.current_target_call)
                if grid and len(grid) >= 2:
                    self.current_target_grid = grid
                    self.analyzer.current_target_grid = grid
                    self.band_map.set_target_grid(grid)
                    logger.info(f"Manual target grid resolved: {self.current_target_call} → {grid} via {source}")
            
            # v2.4.0: Re-attempt IONIS prediction if not yet shown
            # (grid may not have been available when target was first set)
            if self._ionis_engine and not self._ionis_shown:
                self._update_ionis_prediction()

    def _update_perspective_display(self):
        """Fetch and display target perspective data on band map."""
        if self.analyzer.current_dial_freq > 0 and self.current_target_call:
            dial = self.analyzer.current_dial_freq
            
            # Get tiered perspective data
            perspective = self.analyzer.get_target_perspective(
                self.current_target_call, 
                self.current_target_grid
            )
            
            # Convert RF frequencies to audio offsets for each tier
            converted = {}
            for tier_name in ['tier1', 'tier2', 'tier3', 'global']:
                tier_spots = perspective.get(tier_name, [])
                converted[tier_name] = []
                for spot in tier_spots:
                    rf_freq = int(spot.get('freq', 0))
                    offset = rf_freq - dial
                    if 0 <= offset <= 3000:
                        converted[tier_name].append({
                            'freq': offset,
                            'snr': int(spot.get('snr', -10)),
                            'receiver': spot.get('receiver', ''),
                            'sender': spot.get('sender', ''),          # v2.1.1: for tooltip
                            'sender_grid': spot.get('sender_grid', ''),  # v2.1.1: for tooltip
                            'tier': spot.get('tier', 4)
                        })
            
            # Update band map with tiered perspective
            self.band_map.update_perspective(converted)
            
            # Diagnostic: log what we're sending to band map
            total_converted = sum(len(v) for v in converted.values())
            if total_converted == 0 and not hasattr(self, '_empty_perspective_logged'):
                logger.warning(
                    f"Perspective display EMPTY for target={self.current_target_call}, "
                    f"grid='{self.current_target_grid}', dial={dial}"
                )
                self._empty_perspective_logged = True
            elif total_converted > 0:
                self._empty_perspective_logged = False  # Reset so we log if it goes empty again
            
            # v2.1.0: Path Intelligence - find stations near me getting through
            my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='')
            my_call = self.config.get('ANALYSIS', 'my_callsign', fallback='')
            if my_grid and self.local_intel:
                near_me_data = self.analyzer.find_near_me_stations(
                    self.current_target_call,
                    self.current_target_grid,
                    my_grid,
                    my_call  # Exclude my own callsign from the list
                )
                self.local_intel.update_near_me(near_me_data)
            
        else:
            # No dial freq or no target - clear perspective
            self.band_map.update_perspective({
                'tier1': [], 'tier2': [], 'tier3': [], 'global': []
            })
            # v2.1.0: Clear near-me display
            if self.local_intel:
                self.local_intel.update_near_me(None)


    def on_recommendation(self, freq):
        cur = self.band_map.current_tx_freq
        self.dashboard.update_rec(freq, cur)

    def update_status_msg(self, msg):
        # v2.1.1: Save non-warning messages so we can restore after health warnings clear
        if msg and not msg.startswith("⚠"):
            self._normal_status = msg
        self.str_status = msg
        self.update_header()

    def update_header(self):
        update_available = self.update_checker.update_available
        s_update = ""
        if update_available:
            s_update = f"⬆ v{update_available} available — click to download   |   "
            self.info_bar.update_url = "https://github.com/wu2c-peter/qso-predictor/releases"
            self.info_bar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.info_bar.update_url = None
            self.info_bar.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        s_solar = getattr(self, 'str_solar', "")
        s_status = getattr(self, 'str_status', "")
        self.info_bar.setText(f"{s_update}{s_solar}   |   {s_status}")

        # Update styling based on state
        if update_available:
            # Gold/amber for update available
            self.info_bar.setStyleSheet(
                "background-color: #3D3D00; color: #FFD700; padding: 4px; font-weight: bold;"
            )
        elif hasattr(self, 'str_solar') and self.str_solar:
            # Solar-based coloring
            bg_color = "#2A2A2A"
            # Check K index from stored data
            if hasattr(self, '_solar_data'):
                k = self._solar_data.get('k', 0)
                sfi = self._solar_data.get('sfi', 0)
                if k >= 5: bg_color = "#880000"
                elif k >= 4: bg_color = "#884400"
                elif sfi >= 100: bg_color = "#004400"
            self.info_bar.setStyleSheet(
                f"background-color: {bg_color}; color: #FFF; padding: 4px; font-weight: bold;"
            )
        else:
            self.info_bar.setStyleSheet(
                "background-color: #2A2A2A; color: #AAA; padding: 4px;"
            )

    def update_solar_ui(self, data):
        self._solar_data = data  # Store for header styling
        self.str_solar = f"Solar: SFI {data['sfi']} | K {data['k']} ({data['condx']})"
        self.update_header()
        
        # v2.4.0: Re-predict IONIS when solar conditions change
        if self.current_target_call and self._ionis_engine:
            self._update_ionis_prediction()

    
    
    

    def open_settings(self):
        # Calculate UDP status for settings dialog
        udp_status = self.health_monitor.get_udp_status()
        dlg = SettingsDialog(self.config, self, udp_status=udp_status)
        if dlg.exec():
            self.udp.stop()
            self.udp = UDPHandler(self.config)
            self.udp.start()
            self.setup_connections()
            # Reset decode tracking after settings change
            self._decode_count = 0
            self._decode_start_time = None
    

    def open_user_guide(self):
        """Open the User Guide on GitHub (renders markdown nicely)."""
        webbrowser.open("https://github.com/wu2c-peter/qso-predictor/blob/main/docs/USER_GUIDE.md")
    
    # v2.0.9: Debug logging menu handlers
    def _toggle_debug_logging(self, checked):
        """Toggle debug logging on/off.
        
        When enabled, verbose DEBUG level messages are written to log.
        When disabled, only INFO and above are logged.
        """
        set_debug_mode(checked)
        if checked:
            logger.info("Debug logging enabled by user")
            # Show confirmation with log file location
            QMessageBox.information(
                self,
                "Debug Logging Enabled",
                f"Verbose logging is now enabled.\n\n"
                f"Log file location:\n{get_log_file_path()}\n\n"
                f"Note: Debug logging will be disabled on next restart."
            )
        else:
            logger.info("Debug logging disabled by user")
    
    def _open_log_folder(self):
        """Open the log folder in system file browser."""
        open_log_folder()
        logger.info(f"Opened log folder: {get_log_file_path().parent}")
    
    def show_about(self):
        """Show about dialog."""
        version = get_version()
        local_intel_status = "Enabled" if self.local_intel else "Not available"
        ionis_status = "Enabled" if self._ionis_engine else "Not available"
        log_path = str(get_log_file_path())
        QMessageBox.about(self, "About QSO Predictor",
            f"<h2>QSO Predictor v{version}</h2>"
            f"<p>Real-Time Tactical Assistant for FT8 & FT4</p>"
            f"<p>Copyright © 2025-2026 Peter Hirst (WU2C)</p>"
            f"<p>Licensed under GNU GPL v3</p>"
            f"<p>Insights Engine: {local_intel_status}</p>"
            f"<p>Propagation: {ionis_status}"
            f" — <a href='https://ionis-ai.com'>IONIS</a> by KI7MT</p>"
            f"<p>Log file: <small>{log_path}</small></p>"
            f"<p><a href='https://github.com/wu2c-peter/qso-predictor'>GitHub Repository</a></p>"
            f"<p><a href='https://github.com/wu2c-peter/qso-predictor/blob/main/PRIVACY.md'>Privacy Policy</a>"
            f" — no telemetry, no tracking</p>"
        )

    def fetch_solar_data(self):
        if not SOLAR_AVAILABLE: return
        t = threading.Thread(target=self._solar_worker, daemon=True)
        t.start()
        
    def _solar_worker(self):
        if self.solar:
            data = self.solar.get_solar_data()
            self.solar_update_signal.emit(data)
    
    # --- v2.4.0: IONIS PROPAGATION METHODS ---
    
    def _update_ionis_prediction(self):
        """Recompute IONIS propagation prediction for current target.
        
        Called on: target change, band change, solar data refresh.
        Pushes results to PropagationWidget in Insights Panel.
        """
        if not self._ionis_engine or not self._ionis_engine.is_available():
            return
        
        # Need target grid and current band
        if not self.current_target_grid:
            self._show_ionis_waiting("Awaiting target grid…")
            return
        band = getattr(self, '_current_band', None)
        # v2.4.4: Derive band from MQTT dial frequency if UDP not connected
        if not band and self.analyzer.current_dial_freq > 0:
            band = self._freq_to_band(self.analyzer.current_dial_freq)
        if not band:
            self._show_ionis_waiting("Awaiting band info…")
            return
        
        # Need our own grid
        my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='')
        if not my_grid or my_grid == 'FN00aa':
            return
        
        # Get solar conditions (default to safe values if not yet fetched)
        sfi = 100
        kp = 2
        if hasattr(self, '_solar_data') and self._solar_data:
            sfi = self._solar_data.get('sfi', 100)
            kp = self._solar_data.get('k', 2)
        
        try:
            # Single prediction for current conditions
            prediction = self._ionis_engine.predict(
                my_grid, self.current_target_grid, band, sfi, kp
            )
            
            if prediction:
                prediction['tx_grid'] = my_grid[:4].upper()
                prediction['rx_grid'] = self.current_target_grid[:4].upper()
            
            # 12-hour forecast
            forecast = self._ionis_engine.predict_range(
                my_grid, self.current_target_grid, band, sfi, kp, hours=12
            )
            
            # vs-reality comparison
            vs_reality = self._compute_ionis_vs_reality(prediction)
            
            # Push to widget
            if (self.local_intel and
                    hasattr(self.local_intel, 'insights_panel') and
                    self.local_intel.insights_panel):
                panel = self.local_intel.insights_panel
                panel.propagation_widget.show()
                panel.propagation_widget.update_display(
                    prediction, forecast, vs_reality)
                panel.propagation_widget.set_conditions(sfi, kp)
                self._ionis_shown = True
                
        except Exception as e:
            logger.debug(f"IONIS prediction error: {e}")
    
    def _compute_ionis_vs_reality(self, prediction: dict) -> str:
        """Compare IONIS prediction against PSK Reporter observations.
        
        Checks whether there are recent spots from our field arriving
        at the target's area — not just any activity at the target.
        This confirms the specific path IONIS is predicting.
        
        Args:
            prediction: dict from IonisEngine.predict()
            
        Returns:
            One of: confirmed, unconfirmed, better_than_expected,
                    closed, unexpected_opening, unknown
        """
        if not prediction:
            return 'unknown'
        
        ionis_open = prediction.get('ft8_open', False)
        ionis_snr = prediction.get('snr_db', -40)
        
        # Check PSK Reporter data: are there spots FROM OUR AREA
        # arriving at the target's area? Filter tier 1-3 spots by
        # sender grid matching our field (first 2 chars).
        psk_has_path_spots = False
        try:
            my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='')
            my_field = my_grid[:2].upper() if len(my_grid) >= 2 else ''
            
            if my_field and hasattr(self, 'analyzer') and self.analyzer:
                perspective = self.analyzer.get_target_perspective(
                    self.current_target_call, self.current_target_grid
                )
                if perspective:
                    # Count spots where sender is from our field
                    for tier_key in ('tier1', 'tier2', 'tier3'):
                        for spot in perspective.get(tier_key, []):
                            sender_grid = spot.get('sender_grid', '')
                            if (len(sender_grid) >= 2 and
                                    sender_grid[:2].upper() == my_field):
                                psk_has_path_spots = True
                                break
                        if psk_has_path_spots:
                            break
        except Exception:
            pass
        
        MARGINAL_THRESHOLD = -25.0
        
        if ionis_open and psk_has_path_spots:
            return 'confirmed'
        elif ionis_open and not psk_has_path_spots:
            return 'unconfirmed'
        elif not ionis_open and ionis_snr >= MARGINAL_THRESHOLD and psk_has_path_spots:
            return 'better_than_expected'
        elif not ionis_open and not psk_has_path_spots:
            return 'closed'
        elif not ionis_open and psk_has_path_spots:
            return 'unexpected_opening'
        return 'unknown'
    
    def _clear_ionis_prediction(self):
        """Clear and hide the IONIS propagation display."""
        if (self.local_intel and
                hasattr(self.local_intel, 'insights_panel') and
                self.local_intel.insights_panel):
            panel = self.local_intel.insights_panel
            panel.propagation_widget.clear()
            panel.propagation_widget.hide()
    
    def _show_ionis_waiting(self, message: str):
        """Show a waiting message in the IONIS widget."""
        if (self.local_intel and
                hasattr(self.local_intel, 'insights_panel') and
                self.local_intel.insights_panel):
            panel = self.local_intel.insights_panel
            panel.propagation_widget.show()
            panel.propagation_widget.prediction_label.setText(message)
            panel.propagation_widget.prediction_label.setStyleSheet("color: #888888;")
    
    # --- v2.1.0: HUNT MODE METHODS ---
    
    
    
    
    
    
    def _on_path_analyze_requested(self, stations: list):
        """
        Handle Phase 2 Path Intelligence analysis request.
        
        v2.1.0: Called when user clicks "Analyze" button in Path Intelligence panel.
        Performs reverse PSK Reporter lookups and directional analysis.
        
        Args:
            stations: List of near-me station dicts to analyze
        """
        if not stations:
            return
        
        # Get current target grid
        target_call = self.current_target_call if hasattr(self, 'current_target_call') else ''
        target_grid = self.current_target_grid if hasattr(self, 'current_target_grid') else ''
        
        logger.info(f"Path Intelligence Phase 2: Analyzing {len(stations)} station(s)")
        
        # Perform analysis for each station
        results = []
        for station in stations[:3]:  # Limit to 3 to avoid too many API calls
            try:
                result = self.analyzer.analyze_near_me_station(
                    station=station,
                    all_near_me=stations,
                    target_grid=target_grid
                )
                results.append(result)
                logger.debug(f"Analyzed {station.get('call', '?')}: {result.get('insights', [])}")
            except Exception as e:
                logger.error(f"Phase 2 analysis error for {station.get('call', '?')}: {e}")
                results.append({
                    'call': station.get('call', '?'),
                    'error': str(e),
                    'insights': [f"⚠️ Analysis failed: {e}"]
                })
        
        # Send results back to insights panel
        if self.local_intel and self.local_intel.insights_panel:
            self.local_intel.insights_panel.update_path_analysis_results(results)
    

    def closeEvent(self, event):
        # --- v2.1.0: Flag to prevent notifications during shutdown ---
        self._closing = True
        
        # --- OUTCOME RECORDER: Flush pending outcome and end session ---
        # Must happen BEFORE analyzer/UDP shutdown — snapshot needs live state.
        if self.outcome_recorder:
            try:
                self._record_outcome_for_current_target('APP_CLOSED')
                self.outcome_recorder.on_app_close()
            except Exception as e:
                logger.debug(f"OutcomeRecorder shutdown error: {e}")
        
        # --- LOCAL INTELLIGENCE: Clean shutdown ---
        if self.local_intel:
            try:
                self.local_intel.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down Local Intelligence: {e}")
        
        self.analyzer.stop()
        self.udp.stop()
        
        # --- v2.1.0: Hide and cleanup tray icon to stop notifications ---
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.setVisible(False)
        
        # --- v2.0.3: Save window geometry ---
        geo = self.saveGeometry().toHex().data().decode()
        self.config.save_setting('WINDOW', 'geometry', geo)
        
        # --- v2.1.0: Save dock widget positions ---
        dock_state = self.saveState().toHex().data().decode()
        self.config.save_setting('WINDOW', 'dock_state', dock_state)
        
        # --- v2.0.3: Save column widths ---
        self._save_column_widths()
        
        event.accept()

if __name__ == "__main__":
    # Set Windows taskbar app ID (Windows only)
    if sys.platform == 'win32':
        try:
            myappid = 'wu2c.qsopredictor.v2.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # v2.1.1: Explicit QToolTip styling — prevents black-on-black on dark widgets (Windows)
    app.setStyleSheet("""
        QToolTip {
            background-color: #2A2A2A;
            color: #00FFFF;
            border: 1px solid #555;
            padding: 4px;
            font-family: Consolas, monospace;
            font-size: 9pt;
        }
    """)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
