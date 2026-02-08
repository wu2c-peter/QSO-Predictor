# QSO Predictor v2.1.3
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.1.3 Changes:
# - Added: Click-to-copy target callsign (click target in either panel)
# - Added: Local decode evidence for path detection (works without PSK Reporter)
# - Changed: Path status labels clarified (Heard by Target, Heard in Region, etc.)
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
# - Added: Local Intelligence as undockable panel (right side, full height)
# - Added: View menu with panel toggles and Reset Layout option
# - Added: Hunt Mode - track stations/prefixes/countries, alert when active (suggested by Warren KC0GU)
#   - Hunt List dialog (Tools → Hunt List, Ctrl+H)
#   - Right-click context menu to add/remove from hunt list
#   - Gold highlighting for hunted stations in decode table
#   - System tray alerts when hunted station active
#   - "Working nearby" alerts when hunted station works your region
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
# - Added: Dock widget (Local Intelligence panel) position persistence
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
from collections import deque

# Initialize logging FIRST before other imports
from logging_config import setup_logging, set_debug_mode, get_log_file_path, open_log_folder
setup_logging(console=True, file=True)

logger = logging.getLogger(__name__)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableView, QLabel, QHeaderView, QDockWidget,
                             QMessageBox, QProgressBar, QAbstractItemView, QFrame, QSizePolicy, 
                             QSystemTrayIcon, QMenu, QToolBar, QPushButton, QCheckBox,
                             QStyledItemDelegate)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QAbstractTableModel, QModelIndex, QByteArray
from PyQt6.QtGui import QColor, QAction, QKeySequence, QFont, QIcon, QCursor, QBrush

# v2.1.0: Hunt Mode imports
try:
    from hunt_manager import HuntManager
    from hunt_dialog import HuntListDialog
    HUNT_MODE_AVAILABLE = True
except ImportError as e:
    HUNT_MODE_AVAILABLE = False
    logger.warning(f"Hunt Mode not available: {e}")


def get_version():
    """Get version from git tag or VERSION file."""
    # Determine base path (handles PyInstaller frozen exe)
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        base_path = Path(sys._MEIPASS)
    else:
        # Running as script
        base_path = Path(__file__).parent
    
    # Try git first (works for developers running from repo)
    if not getattr(sys, 'frozen', False):
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                capture_output=True, text=True, cwd=base_path
            )
            if result.returncode == 0:
                return result.stdout.strip().lstrip('v')
        except:
            pass
    
    # Fall back to VERSION file (works for zip downloads and frozen exe)
    try:
        return (base_path / "VERSION").read_text().strip()
    except:
        return "dev"


def compare_versions(current, latest):
    """Compare version strings. Returns True if latest > current."""
    try:
        # Handle versions like "1.2.3" or "1.2.3-5-gabcdef"
        def parse(v):
            # Take only the numeric part before any dash
            v = v.split('-')[0]
            return [int(x) for x in v.split('.')]
        
        curr_parts = parse(current)
        latest_parts = parse(latest)
        
        # Pad shorter list with zeros
        max_len = max(len(curr_parts), len(latest_parts))
        curr_parts += [0] * (max_len - len(curr_parts))
        latest_parts += [0] * (max_len - len(latest_parts))
        
        return latest_parts > curr_parts
    except:
        # If parsing fails, do simple string comparison
        return latest != current and latest > current


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

# --- LOCAL INTELLIGENCE v2.0 ---
try:
    from local_intel_integration import LocalIntelligence
    from local_intel import PathStatus
    LOCAL_INTEL_AVAILABLE = True
except ImportError as e:
    LOCAL_INTEL_AVAILABLE = False
    logger.warning(f"Local Intelligence not available: {e}")


# --- WIDGET: TARGET DASHBOARD ---
class TargetDashboard(QFrame):
    # v2.0.6: Signal when user wants to sync target to JTDX
    sync_requested = pyqtSignal()
    # v2.1.0: Signal for status bar messages (e.g., clipboard feedback)
    status_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(120) 
        self.setStyleSheet("""
            QFrame { 
                background-color: #003333; 
                border-top: 2px solid #00AAAA; 
                border-bottom: 1px solid #000;
            }
            QLabel { color: #DDD; font-size: 11pt; border: none; padding: 0 5px; }
            QLabel#header { color: #888; font-size: 8pt; font-weight: bold; }
            QLabel#data { font-weight: bold; color: #FFF; }
            QLabel#target { color: #FF00FF; font-size: 16pt; font-weight: bold; padding-right: 5px; }
            QPushButton#target {
                color: #FF00FF;
                font-size: 16pt;
                font-weight: bold;
                padding-right: 5px;
                background: transparent;
                border: none;
                text-align: left;
            }
            QPushButton#target:hover {
                color: #FF66FF;
            }
            QLabel#rec { 
                font-family: Consolas, monospace; 
                font-weight: bold; 
                border: 1px solid #444; 
                border-radius: 4px; 
                padding: 4px; 
                background-color: #001100; 
            }
            QPushButton#sync {
                background-color: #444;
                color: #DDD;
                border: 1px solid #555;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
                padding: 2px;
            }
            QPushButton#sync:hover {
                background-color: #555;
            }
            QPushButton#sync:pressed {
                background-color: #333;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        # v2.1.3: Target label is clickable — copies callsign to clipboard
        self.lbl_target = QPushButton("NO TARGET")
        self.lbl_target.setObjectName("target")
        self.lbl_target.setFlat(True)
        self.lbl_target.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_target.setToolTip("Click to copy callsign to clipboard")
        self.lbl_target.clicked.connect(self._copy_target_to_clipboard)
        layout.addWidget(self.lbl_target)
        
        # v2.0.6: Fetch button — pulls target from WSJT-X/JTDX
        self.btn_sync = QPushButton("⟳")
        self.btn_sync.setObjectName("sync")
        self.btn_sync.setToolTip("Fetch target from WSJT-X/JTDX (Ctrl+Y)")
        self.btn_sync.setFixedSize(28, 28)
        self.btn_sync.clicked.connect(self.sync_requested.emit)
        layout.addWidget(self.btn_sync)
        
        def add_field(label_text, width=None, stretch=False):
            container = QWidget()
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0,0,0,0)
            vbox.setSpacing(0)
            lbl_title = QLabel(label_text)
            lbl_title.setObjectName("header")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_val = QLabel("--")
            lbl_val.setObjectName("data")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(lbl_title)
            vbox.addWidget(lbl_val)
            if width: container.setFixedWidth(width)
            layout.addWidget(container)
            if stretch: layout.setStretchFactor(container, 1)
            return lbl_val

        self.val_utc = add_field("UTC", 50)
        self.val_snr = add_field("dB", 40)
        self.val_dt = add_field("DT", 40)
        self.val_freq = add_field("Freq", 50)
        self.val_msg = add_field("Message", stretch=True) 
        self.val_msg.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.val_grid = add_field("Grid", 60)
        self.val_prob = add_field("Prob %", 70)
        
        # Stacked Path / Competition field
        path_comp_container = QWidget()
        path_comp_vbox = QVBoxLayout(path_comp_container)
        path_comp_vbox.setContentsMargins(0,0,0,0)
        path_comp_vbox.setSpacing(2)
        
        # Path row
        path_row = QWidget()
        path_hbox = QHBoxLayout(path_row)
        path_hbox.setContentsMargins(0,0,0,0)
        path_hbox.setSpacing(4)
        lbl_path_title = QLabel("Path")
        lbl_path_title.setObjectName("header")
        lbl_path_title.setFixedWidth(70)
        self.val_path = QLabel("--")
        self.val_path.setObjectName("data")
        path_hbox.addWidget(lbl_path_title)
        path_hbox.addWidget(self.val_path)
        path_comp_vbox.addWidget(path_row)
        
        # Competition row
        comp_row = QWidget()
        comp_hbox = QHBoxLayout(comp_row)
        comp_hbox.setContentsMargins(0,0,0,0)
        comp_hbox.setSpacing(4)
        lbl_comp_title = QLabel("Competition")
        lbl_comp_title.setObjectName("header")
        lbl_comp_title.setFixedWidth(75)
        self.val_comp = QLabel("--")
        self.val_comp.setObjectName("data")
        comp_hbox.addWidget(lbl_comp_title)
        comp_hbox.addWidget(self.val_comp)
        path_comp_vbox.addWidget(comp_row)
        
        path_comp_container.setFixedWidth(210)
        layout.addWidget(path_comp_container)

        layout.addSpacing(10)
        # v2.1.0: Use ClickableCopyLabel so user can click to copy frequency
        self.lbl_rec = ClickableCopyLabel()
        self.lbl_rec.setObjectName("rec")
        self.lbl_rec.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_rec.copied.connect(self.status_message.emit)  # Bubble up to main window
        self.update_rec("----", "----") 
        layout.addWidget(self.lbl_rec)

    def _copy_target_to_clipboard(self):
        """Copy current target callsign to clipboard."""
        text = self.lbl_target.text()
        if text and text != "NO TARGET":
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            # Brief visual feedback
            original_text = text
            self.lbl_target.setText(f"✓ Copied!")
            self.status_message.emit(f"Copied to clipboard: {text}")
            # Restore after 1 second
            QTimer.singleShot(1000, lambda: self.lbl_target.setText(original_text))

    def update_data(self, data):
        if not data:
            self.lbl_target.setText("NO TARGET")
            self.val_utc.setText("--")
            self.val_snr.setText("--")
            self.val_dt.setText("--")
            self.val_freq.setText("--")
            self.val_msg.setText("")
            self.val_grid.setText("--")
            self.val_prob.setText("--")
            self.val_path.setText("--")
            self.val_path.setStyleSheet("")
            self.val_comp.setText("--")
            self.val_comp.setStyleSheet("")
            return

        self.lbl_target.setText(data.get('call', '???'))
        self.val_utc.setText(str(data.get('time', '')))
        
        snr = str(data.get('snr', '--'))
        self.val_snr.setText(snr)
        try:
            val = int(snr)
            col = "#00FF00" if val >= 0 else ("#FFFF00" if val >= -10 else "#FF5555")
            self.val_snr.setStyleSheet(f"color: {col}; font-weight: bold;")
        except: self.val_snr.setStyleSheet("")

        self.val_dt.setText(str(data.get('dt', '')))
        self.val_freq.setText(str(data.get('freq', '')))
        self.val_msg.setText(str(data.get('message', '')))
        self.val_grid.setText(str(data.get('grid', '')))
        
        prob = str(data.get('prob', '--'))
        self.val_prob.setText(prob)
        try:
            val = int(prob.replace('%', ''))
            col = "#00FF00" if val > 75 else ("#FF5555" if val < 30 else "#DDDDDD")
            self.val_prob.setStyleSheet(f"color: {col}; font-weight: bold;")
        except: self.val_prob.setStyleSheet("")
        
        # Path status
        path = str(data.get('path', '--'))
        self.val_path.setText(path)
        if "Heard by Target" in path:
            self.val_path.setStyleSheet("color: #00FFFF; font-weight: bold;")  # Cyan
        elif "Heard in Region" in path:
            self.val_path.setStyleSheet("color: #00FF00; font-weight: bold;")  # Green
        elif "Not Heard in Region" in path:
            self.val_path.setStyleSheet("color: #FFA500; font-weight: bold;")  # Orange
        elif "Not Transmitting" in path:
            self.val_path.setStyleSheet("color: #888888; font-weight: bold;")  # Gray
        elif "No Reporters" in path:
            self.val_path.setStyleSheet("color: #666666; font-weight: bold;")  # Dark gray
        else:
            self.val_path.setStyleSheet("color: #DDDDDD;")
        
        comp = str(data.get('competition', ''))
        self.val_comp.setText(comp)
        # Color-code competition status
        if "Heard by Target" in comp:
            self.val_comp.setStyleSheet("color: #00FFFF; font-weight: bold;")  # Cyan
        elif "PILEUP" in comp:
            self.val_comp.setStyleSheet("color: #FF5555; font-weight: bold;")  # Red
        elif "High" in comp:
            self.val_comp.setStyleSheet("color: #FFA500; font-weight: bold;")  # Orange
        elif "Unknown" in comp:
            self.val_comp.setStyleSheet("color: #888888; font-weight: bold;")  # Gray
        elif "Clear" in comp:
            self.val_comp.setStyleSheet("color: #00FF00; font-weight: bold;")  # Green
        else:
            self.val_comp.setStyleSheet("color: #DDDDDD;")

    def update_rec(self, rec_freq, cur_freq):
        if str(rec_freq) == str(cur_freq) and str(rec_freq) != "----":
            cur_color = "#00FF00"  # Green
        elif str(rec_freq) == "----":
            cur_color = "#BBBBBB"  # Grey
        else:
            cur_color = "#FF5555"  # Red
            
        html_text = f"""
        <html>
        <head><style>td {{ padding-right: 12px; }}</style></head>
        <body>
            <table cellspacing="0" cellpadding="0">
                <tr><td style="color: #BBBBBB;">Rec:</td> <td style="color: #00FF00; font-weight: bold;">{rec_freq} Hz</td></tr>
                <tr><td style="color: #BBBBBB;">Cur:</td> <td style="color: {cur_color}; font-weight: bold;">{cur_freq} Hz</td></tr>
            </table>
        </body>
        </html>
        """
        self.lbl_rec.setText(html_text)
        
        # v2.1.0: Set copy value for click-to-clipboard
        if str(rec_freq) != "----":
            self.lbl_rec.set_copy_value(rec_freq)


# --- DELEGATE: Custom painting for hunt highlighting ---
class HuntHighlightDelegate(QStyledItemDelegate):
    """Custom delegate to paint background colors from model data.
    
    Qt stylesheets override model BackgroundRole, so we need a delegate
    to respect the model's background colors for hunt highlighting.
    """
    def paint(self, painter, option, index):
        # Get background color from model
        bg_color = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg_color and isinstance(bg_color, QColor):
            painter.fillRect(option.rect, QBrush(bg_color))
        # Call default painting for text, selection, etc.
        super().paint(painter, option, index)


# --- MODEL: DECODE TABLE ---
class DecodeTableModel(QAbstractTableModel):
    def __init__(self, headers, config):
        super().__init__()
        self._headers = headers
        self._data = []
        self.config = config
        self.target_call = None
        self.hunt_manager = None  # v2.1.0: Set by MainWindow after init

    def set_target_call(self, callsign):
        self.target_call = callsign
        self.layoutChanged.emit()
    
    def clear(self):
        """Clear all decode data from the table."""
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        row_item = self._data[index.row()]
        col_name = self._headers[index.column()]

        key_map = {
            "UTC": "time", "Call": "call", "Grid": "grid", "dB": "snr",
            "DT": "dt", "Freq": "freq", "Message": "message",
            "Prob %": "prob", "Competition": "competition", "Global Activity": "competition",
            "Path": "path"
        }
        key = key_map.get(col_name, col_name.lower())
        
        if role == Qt.ItemDataRole.DisplayRole:
            return str(row_item.get(key, ""))
            
        # --- FIX: ALIGNMENT LOGIC ---
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            # Left align specified columns
            if key in ['call', 'message']:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            # Center align everything else (UTC, dB, DT, Freq, Grid, Prob, Path)
            return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter

        elif role == Qt.ItemDataRole.ForegroundRole:
            if key == "snr":
                try:
                    val = int(row_item.get('snr', -99))
                    if val >= 0: return QColor("#00FF00")       
                    elif val >= -10: return QColor("#FFFF00")   
                    return QColor("#FF5555")                    
                except: pass
            if key == "prob":
                try:
                    val_str = str(row_item.get('prob', '0')).replace('%', '')
                    val = int(val_str)
                    if val > 75: return QColor("#00FF00")
                    elif val < 30: return QColor("#FF5555")
                except: pass
            if key == "path":
                path = str(row_item.get('path', ''))
                if "Heard by Target" in path:
                    return QColor("#00FFFF")  # Cyan - target hears you!
                elif "Heard in Region" in path:
                    return QColor("#00FF00")  # Green - path to region confirmed
                elif "Not Heard in Region" in path:
                    return QColor("#FFA500")  # Orange - reporters exist but don't hear you
                elif "Not Transmitting" in path:
                    return QColor("#888888")  # Gray - not transmitting recently
                elif "No Reporters" in path:
                    return QColor("#666666")  # Dark gray - no data available

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Highlight rows based on path status and hunt mode
            path = str(row_item.get('path', ''))
            
            # Heard by Target = highest priority (target hears you!)
            if "Heard by Target" in path:
                return QColor("#004040")  # Teal background
            
            # Heard in Region = propagation confirmed to region
            if "Heard in Region" in path:
                return QColor("#002800")  # Dark green background
            
            # v2.1.0: Hunt Mode - highlight hunted stations with gold background
            call = row_item.get('call', '')
            
            # Debug: Log hunt_manager status once
            if not hasattr(self, '_hunt_debug_done'):
                self._hunt_debug_done = True
                logger.info(f"Hunt highlight debug: hunt_manager={self.hunt_manager is not None}")
                if self.hunt_manager:
                    logger.info(f"Hunt list contents: {self.hunt_manager.get_list()}")
            
            if self.hunt_manager and call:
                is_hunted = self.hunt_manager.is_hunted(call)
                if is_hunted:
                    return QColor("#7A5500")  # Visible gold/amber background for hunted
            
            if self.target_call and row_item.get('call') == self.target_call:
                return QColor("#004444")  # Teal for selected target
            
            # Default alternating row colors (visible contrast)
            if index.row() % 2 == 0:
                return QColor("#141414")  # Dark for even rows
            else:
                return QColor("#1c1c1c")  # Lighter for odd rows

        return None

    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self._headers[section]
            # --- FIX: FORCE CENTER ALIGNMENT FOR HEADERS ---
            elif role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignCenter
        return None

    def sort(self, column, order):
        col_name = self._headers[column]
        key_map = {
            "UTC": "time", "Call": "call", "Grid": "grid", "dB": "snr",
            "DT": "dt", "Freq": "freq", "Message": "message", 
            "Prob %": "prob", "Competition": "competition", "Path": "path"
        }
        key = key_map.get(col_name, col_name.lower())
        reverse = (order == Qt.SortOrder.DescendingOrder)
        
        def sort_key(row):
            val = row.get(key, "")
            if key in ['snr', 'prob', 'freq', 'dt', 'time']:
                try: 
                    s = str(val).replace('%', '')
                    return float(s)
                except: return -99999.0
            return str(val).lower()

        self.layoutAboutToBeChanged.emit()
        self._data.sort(key=sort_key, reverse=reverse)
        
        if self.target_call:
            targets = [r for r in self._data if r.get('call') == self.target_call]
            others = [r for r in self._data if r.get('call') != self.target_call]
            self._data = targets + others
            
        self.layoutChanged.emit()

    def add_batch(self, new_rows):
        if not new_rows: return
        start = len(self._data)
        self.beginInsertRows(QModelIndex(), start, start + len(new_rows) - 1)
        self._data.extend(new_rows)
        self.endInsertRows()
        
        if len(self._data) > 500:
            remove_count = len(self._data) - 500
            self.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
            del self._data[:remove_count]
            self.endRemoveRows()

    def update_data_in_place(self, analyzer_func):
        if not self._data: return
        for item in self._data:
            analyzer_func(item)
        # Note: We emit dataChanged but sorting is controlled by view
        # The view should only re-sort on explicit user action, not data updates
        tl = self.index(0, 0)
        br = self.index(len(self._data)-1, len(self._headers)-1)
        self.dataChanged.emit(tl, br, [])  # Empty roles list = no sort trigger


# --- CLICKABLE LABEL FOR UPDATE NOTIFICATION ---
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_url = None
    
    def mousePressEvent(self, event):
        if self.update_url:
            webbrowser.open(self.update_url)
        self.clicked.emit()


# --- v2.1.0: CLICKABLE LABEL THAT COPIES VALUE TO CLIPBOARD ---
class ClickableCopyLabel(QLabel):
    """Label that copies a value to clipboard when clicked."""
    copied = pyqtSignal(str)  # Emits the copied value for status bar feedback
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._copy_value = ""
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    
    def set_copy_value(self, value):
        """Set the value that will be copied to clipboard on click."""
        self._copy_value = str(value)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._copy_value:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._copy_value)
            self.copied.emit(f"Copied to clipboard: {self._copy_value} Hz")


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
        
        # --- UPDATE CHECK STATE ---
        self.update_available = None  # Will hold version string if update available
        self._normal_status = ""     # v2.1.1: Last non-warning status message
        
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
        self.hunt_manager = None
        if HUNT_MODE_AVAILABLE:
            self._init_hunt_mode()
            
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
        
        # Check for updates on startup (non-blocking, silent)
        self.check_for_updates(manual=False)
        
        # v2.1.1: Periodic data health check (detects UDP/MQTT data loss)
        self._data_health_timer = QTimer()
        self._data_health_timer.timeout.connect(self._check_data_health)
        self._data_health_timer.start(10000)  # Check every 10 seconds
        self._last_health_warning = ""  # Track to avoid redundant status updates
        
        # Check for unconfigured callsign/grid on startup
        QTimer.singleShot(500, self._check_first_run_config)
        
        # v2.0.9: Start health check timer (checks for UDP data after 20 seconds)
        #self._start_health_check_timer()
    
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
    
    def _init_hunt_mode(self):
        """Initialize Hunt Mode v2.1.0 features."""
        try:
            self.hunt_manager = HuntManager(config_manager=self.config)
            
            # Set user's grid for "working nearby" detection
            my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='')
            self.hunt_manager.set_my_grid(my_grid)
            
            # Connect hunt alerts to notification handler
            self.hunt_manager.hunt_alert.connect(self._on_hunt_alert)
            
            logger.info(f"Hunt Mode initialized with {len(self.hunt_manager.get_list())} items")
        except Exception as e:
            logger.error(f"Failed to initialize Hunt Mode: {e}")
            self.hunt_manager = None

    solar_update_signal = pyqtSignal(dict)
    update_check_signal = pyqtSignal(str, bool)  # (version_or_status, was_manual)

    def init_ui(self):
        # --- v2.1.0: DOCK LAYOUT ---
        # Central widget: Decode Table (with info bar and toolbar)
        # Bottom dock: Target View (Dashboard + Band Map) - can undock
        # Right dock: Local Intelligence - can undock, spans full height
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
        
        # Connect update check signal
        self.update_check_signal.connect(self.on_update_check_result)
        
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
        
        # Spacer to push items to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        
        self.addToolBar(toolbar)
        
        # --- DECODE TABLE (Central Widget) ---
        cols = ["UTC", "dB", "DT", "Freq", "Call", "Grid", "Message", "Prob %", "Path"]
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
        self.table_view.customContextMenuRequested.connect(self._show_table_context_menu)
        
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
        # Insights dock toggle will be added after Local Intelligence setup
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
            hunt_list_action.triggered.connect(self._show_hunt_list_dialog)
            tools_menu.addAction(hunt_list_action)
            tools_menu.addSeparator()
        
        # Add Local Intelligence menu items if available
        if self.local_intel:
            self.local_intel.add_menu_items(tools_menu)
        else:
            disabled_action = QAction("Local Intelligence (not available)", self)
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
        connection_help_action.triggered.connect(self._show_connection_help)
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
        
        check_update_action = QAction("Check for Updates", self)
        check_update_action.triggered.connect(lambda: self.check_for_updates(manual=True))
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
            self.analyzer.spot_received.connect(self._check_hunt_spot)
    
    # --- v2.0.3: Clear Target functionality (suggested by KC0GU) ---
    def clear_target(self):
        """Clear the current target selection.
        
        Clears all target-related state and resets the UI to "NO TARGET" mode.
        Can be triggered via Ctrl+R shortcut or Clear Target button.
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        # Clear internal state
        self.current_target_call = ""
        self.current_target_grid = ""
        
        # Clear table highlight
        self.model.set_target_call(None)
        
        # Clear dashboard
        self.dashboard.update_data(None)
        
        # Clear band map target indicators
        self.band_map.set_target_call("")
        self.band_map.set_target_grid("")
        self.band_map.set_target_freq(0)
        self.band_map.update_perspective({
            'tier1': [], 'tier2': [], 'tier3': [], 'global': []
        })
        
        # Clear Local Intelligence target (use empty string, not None)
        if self.local_intel:
            try:
                self.local_intel.set_target("", "")
            except Exception as e:
                logger.debug(f"Error clearing local intel target: {e}")
    
    # --- v2.0.3: QSO Logged handler (suggested by KC0GU) ---
    def on_qso_logged(self, data):
        """Handle QSO Logged notification from WSJT-X/JTDX.
        
        When a QSO is logged, optionally clear the target if:
        1. Auto-clear is enabled
        2. The logged callsign matches our current target
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        logged_call = data.get('dx_call', '').upper()
        
        # Check if auto-clear is enabled
        if self.chk_auto_clear.isChecked():
            # Only clear if we logged the station we were targeting
            current_upper = self.current_target_call.upper() if self.current_target_call else ''
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
            # No DX call from JTDX yet
            return
        
        # If already on this target, nothing to do
        if self.jtdx_last_dx_call == self.current_target_call:
            return
        
        dx_call = self.jtdx_last_dx_call
        logger.info(f"Sync: Syncing to JTDX target: {dx_call}")
        
        # Set target (same logic as on_status)
        self.dashboard.lbl_target.setText(dx_call)
        self.model.set_target_call(dx_call)
        
        # Find grid from decode table if available
        target_grid = ""
        for row in self.model._data:
            if row.get('call') == dx_call:
                target_grid = row.get('grid', '')
                self.dashboard.update_data(row)
                break
        
        self.current_target_call = dx_call
        self.current_target_grid = target_grid
        
        # Update band map
        self.band_map.set_target_call(dx_call)
        if target_grid:
            self.band_map.set_target_grid(target_grid)
        
        # Update Local Intelligence
        if self.local_intel:
            self.local_intel.set_target(dx_call, target_grid)

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
        # Throttle: JTDX sends status many times per second, we only need ~2Hz
        now = time.time()
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
            except Exception as e:
                logger.error(f"Error in band change detection: {e}")
            
            self.analyzer.set_dial_freq(dial)
        
        # Update Band Map (Yellow Line)
        cur_tx = status.get('tx_df', 0)
        self.band_map.set_current_tx_freq(cur_tx)
        
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
        
        # --- TARGET HANDLING ---
        # Only update our target when JTDX sends a NEW dx_call
        # (not just repeating the same one, which would override manual table selection)
        dx_call = status.get('dx_call', '')
        
        if dx_call != self.jtdx_last_dx_call:
            # JTDX user selected something NEW (or cleared selection)
            self.jtdx_last_dx_call = dx_call
            
            # Also skip if it's the same as our current target (set via table click)
            if dx_call and dx_call == self.current_target_call:
                logger.debug(f"UDP dx_call {dx_call} matches current target, skipping")
                return
            
            if dx_call:
                # Update to the new JTDX target
                self.dashboard.lbl_target.setText(dx_call)
                self.model.set_target_call(dx_call)
                
                # Find target in decode list and analyze with full perspective
                target_grid = ""
                target_freq = 0
                target_row = None
                for row in self.model._data:
                    if row.get('call') == dx_call:
                        target_freq = row.get('freq', 0)
                        target_grid = row.get('grid', '')
                        # Re-analyze with full perspective for accurate competition
                        self.analyzer.analyze_decode(row, use_perspective=True)
                        self.dashboard.update_data(row)
                        target_row = row
                        break
                
                # Store target state for perspective refresh
                self.current_target_call = dx_call
                self.current_target_grid = target_grid
                
                # Update band map
                self.band_map.set_target_freq(target_freq)
                self.band_map.set_target_call(dx_call)
                self.band_map.set_target_grid(target_grid)
                
                # --- LOCAL INTELLIGENCE: Update target ---
                if self.local_intel:
                    self.local_intel.set_target(dx_call, target_grid)
                    if target_row:
                        self._update_local_intel_path_status(target_row)
                
                # Trigger immediate perspective update
                self._update_perspective_display()
            # Note: If JTDX clears dx_call, we don't clear our target
            # (user may have manually selected something in the table)

 
    def on_row_click(self, index):
        logger.debug(f"on_row_click: row {index.row()}")
        row = index.row()
        if row < len(self.model._data):
            data = self.model._data[row]
            
            target_call = data.get('call', '')
            target_grid = data.get('grid', '')
            target_freq = data.get('freq', 0)
            
            # Skip if clicking same target (avoid redundant processing)
            if target_call == self.current_target_call:
                logger.debug(f"Same target {target_call}, skipping")
                return
            
            # --- STORE TARGET STATE FOR PERIODIC REFRESH ---
            self.current_target_call = target_call
            self.current_target_grid = target_grid
            
            # Update dashboard and table highlighting
            self.dashboard.lbl_target.setText(target_call)
            self.model.set_target_call(target_call)
            
            # 1. Update Target Info on Band Map
            self.band_map.set_target_freq(target_freq)
            self.band_map.set_target_call(target_call)
            self.band_map.set_target_grid(target_grid)
            
            # 2. Re-analyze with FULL target perspective (for accurate competition)
            self.analyzer.analyze_decode(data, use_perspective=True)
            self.dashboard.update_data(data)
            
            # --- LOCAL INTELLIGENCE: Update target ---
            if self.local_intel:
                self.local_intel.set_target(target_call, target_grid)
                self._update_local_intel_path_status(data)
            
            # 3. Update band map perspective display
            self._update_perspective_display()

    def _update_local_intel_path_status(self, row_data):
        """Update Local Intelligence with current path status."""
        if not self.local_intel:
            return
        
        path = str(row_data.get('path', ''))
        
        if "Heard by Target" in path:
            self.local_intel.set_path_status(PathStatus.CONNECTED)
        elif "Heard in Region" in path:
            self.local_intel.set_path_status(PathStatus.PATH_OPEN)
        elif "Not Heard in Region" in path:
            self.local_intel.set_path_status(PathStatus.NO_PATH)
        else:
            self.local_intel.set_path_status(PathStatus.UNKNOWN)

    def refresh_target_perspective(self):
        """Called periodically by timer to keep target perspective current."""
        if self.current_target_call:
            # Find and re-analyze the selected target with full perspective
            for row in self.model._data:
                if row.get('call') == self.current_target_call:
                    self.analyzer.analyze_decode(row, use_perspective=True)
                    self.dashboard.update_data(row)
                    
                    # --- LOCAL INTELLIGENCE: Update path status ---
                    if self.local_intel:
                        self._update_local_intel_path_status(row)
                    break
            
            # Update band map perspective
            self._update_perspective_display()

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
        s_update = ""
        if self.update_available:
            s_update = f"⬆ v{self.update_available} available — click to download   |   "
            self.info_bar.update_url = "https://github.com/wu2c-peter/qso-predictor/releases"
            self.info_bar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.info_bar.update_url = None
            self.info_bar.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        
        s_solar = getattr(self, 'str_solar', "")
        s_status = getattr(self, 'str_status', "")
        self.info_bar.setText(f"{s_update}{s_solar}   |   {s_status}")
        
        # Update styling based on state
        if self.update_available:
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

    def check_for_updates(self, manual=False):
        """Check GitHub for newer release (runs in background thread)."""
        t = threading.Thread(target=self._update_check_worker, args=(manual,), daemon=True)
        t.start()
    
    def _update_check_worker(self, manual):
        """Worker thread for update check."""
        try:
            import requests  # Lazy import - app works without it
        except ImportError:
            if manual:
                self.update_check_signal.emit("NO_REQUESTS", manual)
            return
        
        try:
            r = requests.get(
                "https://api.github.com/repos/wu2c-peter/qso-predictor/releases/latest",
                timeout=10
            )
            if r.status_code == 200:
                latest = r.json().get('tag_name', '').lstrip('v')
                current = get_version()
                if latest and compare_versions(current, latest):
                    # Update available
                    self.update_check_signal.emit(latest, manual)
                elif manual:
                    # No update, but user asked - tell them they're up to date
                    self.update_check_signal.emit("UP_TO_DATE", manual)
            elif manual:
                # API error
                self.update_check_signal.emit("ERROR", manual)
        except Exception as e:
            if manual:
                self.update_check_signal.emit("ERROR", manual)
            # Fail silently for automatic checks
    
    def on_update_check_result(self, result, was_manual):
        """Handle update check result."""
        if result == "UP_TO_DATE":
            QMessageBox.information(
                self, 
                "Up to Date", 
                f"You're running the latest version (v{get_version()})."
            )
        elif result == "ERROR":
            QMessageBox.warning(
                self, 
                "Update Check Failed",
                "Couldn't reach GitHub to check for updates.\nPlease check your internet connection."
            )
        elif result == "NO_REQUESTS":
            QMessageBox.warning(
                self,
                "Update Check Unavailable",
                "The 'requests' module is not installed.\n\n"
                "To enable update checking, run:\n"
                "  pip install requests"
            )
        else:
            # It's a version number - update available
            self.update_available = result
            self.update_header()
            
            if was_manual:
                # User manually checked - show dialog with option to download
                reply = QMessageBox.information(
                    self,
                    "Update Available",
                    f"A new version is available: v{result}\n\n"
                    f"You're currently running v{get_version()}.\n\n"
                    f"Would you like to open the download page?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    webbrowser.open("https://github.com/wu2c-peter/qso-predictor/releases")

    # --- v2.1.1: Periodic Data Health Check ---
    def _check_data_health(self):
        """Check if UDP and MQTT data sources are flowing.
        
        Called every 10 seconds. Shows/clears status bar warnings when data
        sources go silent, without blocking the main thread.
        """
        warnings = []
        
        # Check UDP health
        if hasattr(self, 'udp') and self.udp:
            udp_ok, udp_msg = self.udp.check_data_health()
            if not udp_ok and udp_msg:
                warnings.append(udp_msg)
        
        # Check MQTT health
        if hasattr(self, 'mqtt') and self.mqtt:
            mqtt_ok, mqtt_msg = self.mqtt.check_data_health()
            if not mqtt_ok and mqtt_msg:
                warnings.append(mqtt_msg)
        
        # Update status bar if warning state changed
        warning_text = "   |   ".join(warnings) if warnings else ""
        if warning_text != self._last_health_warning:
            self._last_health_warning = warning_text
            if warning_text:
                self.update_status_msg(warning_text)
            else:
                # Clear warning - restore normal status
                self.update_status_msg(getattr(self, '_normal_status', ''))
    
    # --- v2.0.9: Startup Health Check ---
    def _start_health_check_timer(self):
        """Start a timer to check if data is being received after startup.
        
        Shows a help dialog if no UDP data detected after 20 seconds.
        Feature added based on user feedback from Doug McDonald.
        """
        # Check after 20 seconds - enough time for:
        # - MQTT to connect
        # - At least one FT8 cycle (15 sec) to complete
        # - Some buffer for slow startup
        QTimer.singleShot(20000, self._check_startup_health)
    
    def _check_startup_health(self):
        """Check if we're receiving data. Show help dialog if not."""
        # Check if user has disabled this popup
        skip_check = self.config.get('UI', 'skip_startup_health_check', fallback='false') == 'true'
        if skip_check:
            return
        
        # Check UDP status using the message counter on udp handler
        has_udp = False
        if hasattr(self, 'udp') and self.udp:
            has_udp = getattr(self.udp, 'messages_received', 0) > 0
        
        # Alternative check using decode count (should match)
        if not has_udp:
            has_udp = self._decode_count > 0
        
        # Check MQTT status - look for indication in status message
        has_mqtt = False
        if hasattr(self, 'str_status'):
            # If status contains "tracking X stations", MQTT is working
            has_mqtt = 'tracking' in self.str_status.lower() or 'stations' in self.str_status.lower()
        
        # If UDP is working, we're good - don't show popup
        if has_udp:
            return
        
        # Show the help dialog
        self._show_startup_health_dialog(has_udp, has_mqtt)
    
    def _show_startup_health_dialog(self, udp_ok, mqtt_ok):
        """Display the startup health check dialog."""
        if not STARTUP_HEALTH_AVAILABLE:
            # Fallback if dialog module not available
            configured_port = self.config.get('NETWORK', 'udp_port', fallback='2237')
            QMessageBox.warning(
                self,
                "No Data Detected",
                f"QSO Predictor isn't receiving data from WSJT-X or JTDX.\n\n"
                f"Please check:\n"
                f"• WSJT-X/JTDX Settings → Reporting → UDP Server\n"
                f"• Port in WSJT-X/JTDX matches QSO Predictor ({configured_port})\n"
                f"• 'Accept UDP Requests' is checked\n\n"
                f"See Help → Documentation for more details."
            )
            return
        
        # Get the configured port to show in dialog
        configured_port = int(self.config.get('NETWORK', 'udp_port', fallback='2237'))
        
        dialog = StartupHealthDialog(
            parent=self,
            udp_ok=udp_ok,
            mqtt_ok=mqtt_ok,
            configured_port=configured_port
        )
        
        result = dialog.exec()
        
        # Handle "don't show again"
        if dialog.dont_show_again:
            self.config.save_setting('UI', 'skip_startup_health_check', 'true')
        
        # Handle "Open Settings" button (custom return code 2)
        if result == 2:
            self.open_settings()
    
    def _show_connection_help(self):
        """Manually show the connection help dialog (from Help menu)."""
        # Get current status
        has_udp = False
        if hasattr(self, 'udp') and self.udp:
            has_udp = getattr(self.udp, 'messages_received', 0) > 0
        if not has_udp:
            has_udp = self._decode_count > 0
        
        has_mqtt = False
        if hasattr(self, 'str_status'):
            has_mqtt = 'tracking' in self.str_status.lower() or 'stations' in self.str_status.lower()
        
        self._show_startup_health_dialog(has_udp, has_mqtt)

    def open_settings(self):
        # Calculate UDP status for settings dialog
        udp_status = self._get_udp_status()
        dlg = SettingsDialog(self.config, self, udp_status=udp_status)
        if dlg.exec():
            self.udp.stop()
            self.udp = UDPHandler(self.config)
            self.udp.start()
            self.setup_connections()
            # Reset decode tracking after settings change
            self._decode_count = 0
            self._decode_start_time = None
    
    def _get_udp_status(self):
        """Get current UDP connection status."""
        from datetime import datetime
        
        if self._decode_start_time is None or self._decode_count == 0:
            return {'receiving': False, 'rate': 0}
        
        elapsed = (datetime.now() - self._decode_start_time).total_seconds()
        if elapsed < 1:
            elapsed = 1  # Avoid division by zero
        
        rate = (self._decode_count / elapsed) * 60  # decodes per minute
        
        return {
            'receiving': self._decode_count > 0,
            'rate': rate
        }

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
        log_path = str(get_log_file_path())
        QMessageBox.about(self, "About QSO Predictor",
            f"<h2>QSO Predictor v{version}</h2>"
            f"<p>Real-Time Tactical Assistant for FT8 & FT4</p>"
            f"<p>Copyright © 2025 Peter Hirst (WU2C)</p>"
            f"<p>Licensed under GNU GPL v3</p>"
            f"<p>Local Intelligence: {local_intel_status}</p>"
            f"<p>Log file: <small>{log_path}</small></p>"
            f"<p><a href='https://github.com/wu2c-peter/qso-predictor'>GitHub Repository</a></p>"
        )

    def fetch_solar_data(self):
        if not SOLAR_AVAILABLE: return
        t = threading.Thread(target=self._solar_worker, daemon=True)
        t.start()
        
    def _solar_worker(self):
        if self.solar:
            data = self.solar.get_solar_data()
            self.solar_update_signal.emit(data)
    
    # --- v2.1.0: HUNT MODE METHODS ---
    
    def _show_hunt_list_dialog(self):
        """Show the Hunt List management dialog."""
        if not self.hunt_manager:
            return
        dialog = HuntListDialog(self.hunt_manager, self)
        dialog.exec()
        # Refresh table to update highlighting
        self.model.layoutChanged.emit()
    
    def _show_table_context_menu(self, pos):
        """Show context menu for decode table with Hunt Mode options."""
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return
        
        # Get the callsign from the clicked row
        row_data = self.model._data[index.row()]
        callsign = row_data.get('call', '')
        
        if not callsign:
            return
        
        menu = QMenu(self)
        
        # Hunt Mode actions
        if self.hunt_manager:
            if self.hunt_manager.is_hunted(callsign):
                remove_action = menu.addAction(f"Remove {callsign} from Hunt List")
                remove_action.triggered.connect(lambda: self._remove_from_hunt(callsign))
            else:
                add_action = menu.addAction(f"Add {callsign} to Hunt List")
                add_action.triggered.connect(lambda: self._add_to_hunt(callsign))
            
            menu.addSeparator()
        
        # Set as Target action
        target_action = menu.addAction(f"Set {callsign} as Target")
        target_action.triggered.connect(lambda: self.on_row_click(index))
        
        menu.exec(self.table_view.viewport().mapToGlobal(pos))
    
    def _add_to_hunt(self, callsign):
        """Add callsign to hunt list from context menu."""
        if self.hunt_manager and self.hunt_manager.add(callsign):
            self.model.layoutChanged.emit()  # Refresh highlighting
            self.tray_icon.showMessage(
                "Hunt Mode",
                f"Added {callsign} to hunt list",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
    
    def _remove_from_hunt(self, callsign):
        """Remove callsign from hunt list from context menu."""
        if self.hunt_manager and self.hunt_manager.remove(callsign):
            self.model.layoutChanged.emit()  # Refresh highlighting
    
    def _check_hunt_spot(self, spot):
        """Check incoming MQTT spot against hunt list."""
        if not self.hunt_manager or self.hunt_manager.is_empty():
            return
        
        # Check spot against hunt list (handles cooldown internally)
        self.hunt_manager.check_spot(spot, time.time())
    
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
    
    def _on_hunt_alert(self, call, band, alert_type, details):
        """Handle hunt alert - show notification to user."""
        # Don't show notifications if we're closing
        if getattr(self, '_closing', False):
            return
        
        if alert_type == 'working_nearby':
            # High priority - they're working your region!
            title = f"🎯 {call} Working Nearby!"
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
        self.tray_icon.showMessage(title, message, icon, duration)
        
        # Also update status bar briefly
        self.update_status_msg(f"Hunt: {call} {alert_type} on {band}")

    def closeEvent(self, event):
        # --- v2.1.0: Flag to prevent notifications during shutdown ---
        self._closing = True
        
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
