# QSO Predictor v2.0
# Copyright (C) 2025 Peter Hirst (WU2C)

import ctypes
import subprocess
import sys
import threading
import webbrowser
import requests
from pathlib import Path
from collections import deque
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableView, QLabel, QHeaderView, QSplitter, 
                             QMessageBox, QProgressBar, QAbstractItemView, QFrame, QSizePolicy, QSystemTrayIcon, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QAbstractTableModel, QModelIndex, QByteArray
from PyQt6.QtGui import QColor, QAction, QKeySequence, QFont, QIcon, QCursor


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
    print(f"Local Intelligence not available: {e}")


# --- WIDGET: TARGET DASHBOARD ---
class TargetDashboard(QFrame):
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
            QLabel#target { color: #FF00FF; font-size: 16pt; font-weight: bold; padding-right: 15px; }
            QLabel#rec { 
                font-family: Consolas, monospace; 
                font-weight: bold; 
                border: 1px solid #444; 
                border-radius: 4px; 
                padding: 4px; 
                background-color: #001100; 
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        self.lbl_target = QLabel("NO TARGET")
        self.lbl_target.setObjectName("target")
        layout.addWidget(self.lbl_target)
        
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
        self.lbl_rec = QLabel()
        self.lbl_rec.setObjectName("rec")
        self.lbl_rec.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.update_rec("----", "----") 
        layout.addWidget(self.lbl_rec)

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
        if "CONNECTED" in path:
            self.val_path.setStyleSheet("color: #00FFFF; font-weight: bold;")  # Cyan
        elif "Path Open" in path:
            self.val_path.setStyleSheet("color: #00FF00; font-weight: bold;")  # Green
        elif "No Path" in path:
            self.val_path.setStyleSheet("color: #FFA500; font-weight: bold;")  # Orange
        elif "No Nearby" in path:
            self.val_path.setStyleSheet("color: #888888; font-weight: bold;")  # Gray
        else:
            self.val_path.setStyleSheet("color: #DDDDDD;")
        
        comp = str(data.get('competition', ''))
        self.val_comp.setText(comp)
        # Color-code competition status
        if "CONNECTED" in comp:
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

# --- MODEL: DECODE TABLE ---
class DecodeTableModel(QAbstractTableModel):
    def __init__(self, headers, config):
        super().__init__()
        self._headers = headers
        self._data = []
        self.config = config
        self.target_call = None

    def set_target_call(self, callsign):
        self.target_call = callsign
        self.layoutChanged.emit()

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
                if "CONNECTED" in path:
                    return QColor("#00FFFF")  # Cyan - target hears you!
                elif "Path Open" in path:
                    return QColor("#00FF00")  # Green - path to region confirmed
                elif "No Path" in path:
                    return QColor("#FFA500")  # Orange - reporters exist but don't hear you
                elif "No Nearby Reporters" in path:
                    return QColor("#888888")  # Gray - no data available

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Highlight CONNECTED rows with a subtle background
            path = str(row_item.get('path', ''))
            if "CONNECTED" in path:
                return QColor("#004040")  # Teal background for connected
            if self.target_call and row_item.get('call') == self.target_call:
                return QColor("#004444") 

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
        tl = self.index(0, 0)
        br = self.index(len(self._data)-1, len(self._headers)-1)
        self.dataChanged.emit(tl, br)


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


# --- MAIN APPLICATION WINDOW ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.setWindowTitle(f"QSO Predictor v{get_version()} by WU2C")
        self.resize(1100, 800)
        
        geo = self.config.get('WINDOW', 'geometry')
        if geo:
            self.restoreGeometry(QByteArray.fromHex(geo.encode()))

        self.analyzer = QSOAnalyzer(self.config)
        self.udp = UDPHandler(self.config)
        
        # --- TARGET TRACKING STATE ---
        self.current_target_call = ""
        self.current_target_grid = ""
        self.jtdx_last_dx_call = ""  # Track what JTDX last sent (separate from our selection)
        
        # --- UPDATE CHECK STATE ---
        self.update_available = None  # Will hold version string if update available
        
        if SOLAR_AVAILABLE:
            self.solar = SolarClient()
            self.solar_update_signal.connect(self.update_solar_ui)
        
        # --- LOCAL INTELLIGENCE v2.0 ---
        self.local_intel = None
        if LOCAL_INTEL_AVAILABLE:
            self._init_local_intelligence()
            
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
        
        if SOLAR_AVAILABLE:
            self.fetch_solar_data()
        
        # Check for updates on startup (non-blocking, silent)
        self.check_for_updates(manual=False)

    def _init_local_intelligence(self):
        """Initialize Local Intelligence v2.0 features."""
        try:
            my_callsign = self.config.get('ANALYSIS', 'my_callsign', fallback='')
            if not my_callsign:
                print("Local Intelligence: No callsign configured, some features disabled")
                my_callsign = 'N0CALL'
            
            self.local_intel = LocalIntelligence(my_callsign=my_callsign)
            print("Local Intelligence initialized")
        except Exception as e:
            print(f"Failed to initialize Local Intelligence: {e}")
            self.local_intel = None

    solar_update_signal = pyqtSignal(dict)
    update_check_signal = pyqtSignal(str, bool)  # (version_or_status, was_manual)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)
        
        # 1. Info Bar (now clickable for updates)
        self.info_bar = ClickableLabel("Waiting for WSJT-X...")
        self.info_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_bar.setFixedHeight(25) 
        self.info_bar.setStyleSheet("background-color: #2A2A2A; color: #AAA; padding: 4px;")
        main_layout.addWidget(self.info_bar)
        
        # Connect update check signal
        self.update_check_signal.connect(self.on_update_check_result)
        
        # --- SPLITTER START ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. TOP: Table View
        cols = ["UTC", "dB", "DT", "Freq", "Call", "Grid", "Message", "Prob %", "Path"]
        self.model = DecodeTableModel(cols, self.config)
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setStyleSheet("""
            QTableView { 
                background-color: #121212; 
                alternate-background-color: #1a1a1a;
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
                background-color: #004444; 
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
        
        # --- FIX: ENABLE SORTING ---
        self.table_view.setSortingEnabled(True)
        
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.clicked.connect(self.on_row_click)
        
        splitter.addWidget(self.table_view)
        
        # 2. BOTTOM: Container for Dashboard + Map
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0,0,0,0)
        bottom_layout.setSpacing(0)
        
        # Dashboard
        self.dashboard = TargetDashboard()
        bottom_layout.addWidget(self.dashboard)
        
        # Band Map
        self.band_map = BandMapWidget()
        self.band_map.recommendation_changed.connect(self.on_recommendation)
        bottom_layout.addWidget(self.band_map)
        
        splitter.addWidget(bottom_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # Menu
        menu = self.menuBar()
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
        
        # --- TOOLS MENU (NEW for v2.0) ---
        tools_menu = menu.addMenu("Tools")
        
        # Add Local Intelligence menu items if available
        if self.local_intel:
            self.local_intel.add_menu_items(tools_menu)
        else:
            disabled_action = QAction("Local Intelligence (not available)", self)
            disabled_action.setEnabled(False)
            tools_menu.addAction(disabled_action)
        
        # Help Menu
        help_menu = menu.addMenu("Help")
        wiki_action = QAction("Documentation (Wiki)", self)
        wiki_action.setShortcut(QKeySequence("F1"))
        wiki_action.triggered.connect(self.open_wiki)
        help_menu.addAction(wiki_action)
        
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
            except Exception as e:
                print(f"Failed to setup Local Intelligence panel: {e}")

    def setup_connections(self):
        self.udp.new_decode.connect(self.handle_decode)
        self.udp.status_update.connect(self.handle_status_update)
        # Note: Removed cache_updated -> refresh_analysis connection
        # With target perspective, re-analyzing all 500 rows every 2 seconds is too expensive.
        # Reconnect cache_updated to lightweight path refresh (not full analysis)
        self.analyzer.cache_updated.connect(self.refresh_paths)
        self.analyzer.status_message.connect(self.update_status_msg)

    def handle_decode(self, data):
        self.buffer.append(data)

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
        
        self.model.add_batch(chunk)
        self.band_map.update_signals(chunk)
        
        # Auto-scroll to bottom if user was already there
        if at_bottom:
            self.table_view.scrollToBottom()

    def refresh_paths(self):
        """Lightweight refresh - just update path status for all rows."""
        self.model.update_data_in_place(self.analyzer.update_path_only)

    def refresh_analysis(self):
        self.model.update_data_in_place(self.analyzer.analyze_decode)

    def handle_status_update(self, status):
        dial = status.get('dial_freq', 0)
        if dial > 0: self.analyzer.set_dial_freq(dial)
        
        # Update Band Map (Yellow Line)
        cur_tx = status.get('tx_df', 0)
        self.band_map.set_current_tx_freq(cur_tx)
        
        # --- LOCAL INTELLIGENCE: Update TX status ---
        if self.local_intel:
            # Check for TX enabled (transmitting or tx_enabled field)
            tx_enabled = status.get('transmitting', False) or status.get('tx_enabled', False)
            self.local_intel.set_tx_status(tx_enabled)
        
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
        row = index.row()
        if row < len(self.model._data):
            data = self.model._data[row]
            
            target_call = data.get('call', '')
            target_grid = data.get('grid', '')
            target_freq = data.get('freq', 0)
            
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
        
        if "CONNECTED" in path:
            self.local_intel.set_path_status(PathStatus.CONNECTED)
        elif "Path Open" in path:
            self.local_intel.set_path_status(PathStatus.PATH_OPEN)
        elif "No Path" in path:
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
                            'tier': spot.get('tier', 4)
                        })
            
            # Update band map with tiered perspective
            self.band_map.update_perspective(converted)
            
        else:
            # No dial freq or no target - clear perspective
            self.band_map.update_perspective({
                'tier1': [], 'tier2': [], 'tier3': [], 'global': []
            })



    def on_recommendation(self, freq):
        cur = self.band_map.current_tx_freq
        self.dashboard.update_rec(freq, cur)

    def update_status_msg(self, msg):
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

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.udp.stop()
            self.udp = UDPHandler(self.config)
            self.udp.start()
            self.setup_connections()

    def open_wiki(self):
        """Open the GitHub wiki in the default browser."""
        webbrowser.open("https://github.com/wu2c-peter/qso-predictor/wiki")
    
    def show_about(self):
        """Show about dialog."""
        version = get_version()
        local_intel_status = "Enabled" if self.local_intel else "Not available"
        QMessageBox.about(self, "About QSO Predictor",
            f"<h2>QSO Predictor v{version}</h2>"
            f"<p>Real-Time Tactical Assistant for FT8 & FT4</p>"
            f"<p>Copyright © 2025 Peter Hirst (WU2C)</p>"
            f"<p>Licensed under GNU GPL v3</p>"
            f"<p>Local Intelligence: {local_intel_status}</p>"
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

    def closeEvent(self, event):
        # --- LOCAL INTELLIGENCE: Clean shutdown ---
        if self.local_intel:
            try:
                self.local_intel.shutdown()
            except Exception as e:
                print(f"Error shutting down Local Intelligence: {e}")
        
        self.analyzer.stop()
        self.udp.stop()
        geo = self.saveGeometry().toHex().data().decode()
        self.config.save_setting('WINDOW', 'geometry', geo)
        event.accept()

if __name__ == "__main__":
    # --- SET APP ID FOR WINDOWS TASKBAR ---
    myappid = 'wu2c.qsopredictor.v2.0'  # Updated for v2.0
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        pass
    # ----------------------
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
