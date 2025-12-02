# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import sys
import threading
from collections import deque
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableView, QLabel, QHeaderView, QSplitter, 
                             QMessageBox, QProgressBar, QAbstractItemView, QFrame, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QAbstractTableModel, QModelIndex, QByteArray
from PyQt6.QtGui import QColor, QAction, QKeySequence, QFont

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

# --- WIDGET: TARGET DASHBOARD ---
# --- WIDGET: TARGET DASHBOARD ---
class TargetDashboard(QFrame):
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
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
        
        # 1. Target Call (The Anchor)
        self.lbl_target = QLabel("NO TARGET")
        self.lbl_target.setObjectName("target")
        layout.addWidget(self.lbl_target)
        
        # Helper to build fields
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

        # 2. Table Fields
        self.val_utc = add_field("UTC", 50)
        self.val_snr = add_field("dB", 40)
        self.val_dt = add_field("DT", 40)
        self.val_freq = add_field("Freq", 50)
        self.val_msg = add_field("Message", stretch=True) 
        self.val_msg.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.val_grid = add_field("Grid", 50)
        self.val_prob = add_field("Prob %", 60)
        self.val_comp = add_field("Competition", 100)

        # 3. Rec Tx (Far Right - Now with HTML Colors)
        layout.addSpacing(10)
        self.lbl_rec = QLabel()
        self.lbl_rec.setObjectName("rec")
        self.lbl_rec.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # Initialize with the table immediately so it doesn't jump later
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
            self.val_comp.setText("--")
            return

        # Update Target Call
        self.lbl_target.setText(data.get('call', '???'))
        
        # Update Fields
        self.val_utc.setText(str(data.get('time', '')))
        
        snr = str(data.get('snr', '--'))
        self.val_snr.setText(snr)
        # Color SNR
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
        # Color Prob
        try:
            val = int(prob.replace('%', ''))
            col = "#00FF00" if val > 75 else ("#FF5555" if val < 30 else "#DDDDDD")
            self.val_prob.setStyleSheet(f"color: {col}; font-weight: bold;")
        except: self.val_prob.setStyleSheet("")
            
        self.val_comp.setText(str(data.get('competition', '')))

    def update_rec(self, rec_freq, cur_freq):
        """
        Updates the Recommended vs Current frequency display using an HTML table
        for perfect vertical alignment.
        """
        # 1. Determine Color for Current Freq
        if str(rec_freq) == str(cur_freq) and str(rec_freq) != "----":
            cur_color = "#00FF00"  # Green
        elif str(rec_freq) == "----":
            cur_color = "#BBBBBB"  # Grey if no recommendation yet
        else:
            cur_color = "#FF5555"  # Red (Mismatch warning)
            
        # 2. Build the HTML Table
        html_text = f"""
        <html>
        <head>
            <style>
                td {{ padding-right: 12px; }}
            </style>
        </head>
        <body>
            <table cellspacing="0" cellpadding="0">
                <tr>
                    <td style="color: #BBBBBB;">Rec:</td> 
                    <td style="color: #00FF00; font-weight: bold;">{rec_freq} Hz</td>
                </tr>
                <tr>
                    <td style="color: #BBBBBB;">Cur:</td> 
                    <td style="color: {cur_color}; font-weight: bold;">{cur_freq} Hz</td>
                </tr>
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
        self.target_call = None  # <--- Added missing attribute

    def set_target_call(self, callsign):
        """Updates the target callsign to keep pinned at the top."""
        self.target_call = callsign
        # Trigger a re-sort to apply pinning immediately if needed
        # (Assuming default sort is by Time or SNR, but pinning overrides)
        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        row_item = self._data[index.row()]
        col_name = self._headers[index.column()]

        # Map Column Name to Data Key
        key_map = {
            "UTC": "time",
            "Call": "call",
            "Grid": "grid",
            "dB": "snr",
            "DT": "dt",
            "Freq": "freq",
            "Message": "message",
            "Prob %": "prob",
            "Competition": "competition"
        }
        
        key = key_map.get(col_name, col_name.lower())
        
        if role == Qt.ItemDataRole.DisplayRole:
            return str(row_item.get(key, ""))
            
        elif role == Qt.ItemDataRole.ForegroundRole:
            # Color logic for SNR and Probability
            if key == "snr":
                try:
                    val = int(row_item.get('snr', -99))
                    if val >= 0: return QColor("#00FF00")       # Green
                    elif val >= -10: return QColor("#FFFF00")   # Yellow
                    return QColor("#FF5555")                    # Red
                except: pass
            
            if key == "prob":
                try:
                    val_str = str(row_item.get('prob', '0')).replace('%', '')
                    val = int(val_str)
                    if val > 75: return QColor("#00FF00")
                    elif val < 30: return QColor("#FF5555")
                except: pass

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Highlight the Target Station Row
            if self.target_call and row_item.get('call') == self.target_call:
                return QColor("#004444") # Dark Cyan highlight for Target

        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def sort(self, column, order):
        """Sorts the table, but keeps Target Call pinned to top."""
        col_name = self._headers[column]
        
        key_map = {
            "UTC": "time", "Call": "call", "Grid": "grid", "dB": "snr",
            "DT": "dt", "Freq": "freq", "Message": "message", 
            "Prob %": "prob", "Competition": "competition"
        }
        key = key_map.get(col_name, col_name.lower())
        
        reverse = (order == Qt.SortOrder.DescendingOrder)
        
        def sort_key(row):
            val = row.get(key, "")
            # Numeric sort for specific columns
            if key in ['snr', 'prob', 'freq', 'dt', 'time']:
                try: 
                    # Strip % for probability
                    s = str(val).replace('%', '')
                    return float(s)
                except: return -99999.0
            return str(val).lower()

        self.layoutAboutToBeChanged.emit()
        
        # 1. Standard Sort
        self._data.sort(key=sort_key, reverse=reverse)
        
        # 2. Pin Target to Top (if exists)
        if self.target_call:
            targets = []
            others = []
            for row in self._data:
                if row.get('call') == self.target_call:
                    targets.append(row)
                else:
                    others.append(row)
            self._data = targets + others
            
        self.layoutChanged.emit()

    def add_batch(self, new_rows):
        if not new_rows: return
        start = len(self._data)
        self.beginInsertRows(QModelIndex(), start, start + len(new_rows) - 1)
        self._data.extend(new_rows)
        self.endInsertRows()
        
        # Keep buffer size manageable (Max 500 rows)
        if len(self._data) > 500:
            remove_count = len(self._data) - 500
            self.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
            del self._data[:remove_count]
            self.endRemoveRows()

    def update_data_in_place(self, analyzer_func):
        """Allows the analyzer to update Prob/Comp fields without adding new rows."""
        if not self._data: return
        
        for item in self._data:
            analyzer_func(item)
            
        # Refresh the whole table view
        tl = self.index(0, 0)
        br = self.index(len(self._data)-1, len(self._headers)-1)
        self.dataChanged.emit(tl, br)

class MainWindow(QMainWindow):
    solar_update_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.analyzer = QSOAnalyzer(self.config)
        self.udp = UDPHandler(self.config)
        self.solar = SolarClient() if SOLAR_AVAILABLE else None

        self.target_dx_call = ""
        self.current_tx_df = 0
        self.rec_tx_df = 0
        
        self.str_solar = "Solar: Loading..."
        self.str_dial = "Dial: Waiting..."
        self.str_status = "Status: Initializing..."
        
        self.raw_queue = deque()
        self.batch_timer = QTimer()
        self.batch_timer.setInterval(100)
        self.batch_timer.timeout.connect(self.process_batch)
        self.batch_timer.start()

        self.init_ui()
        self.setup_connections()
        self.udp.start()
        
        if SOLAR_AVAILABLE:
            self.fetch_solar_data()
            self.solar_timer = QTimer()
            self.solar_timer.timeout.connect(self.fetch_solar_data)
            self.solar_timer.start(900000) 

    def init_ui(self):
        self.setWindowTitle("QSO Predictor")
        self.resize(1000, 850)
        
        geom = self.config.get('WINDOW', 'geometry')
        if geom: self.restoreGeometry(QByteArray.fromHex(geom.encode()))
        
        font = self.config.get('APPEARANCE', 'font_family')
        size = self.config.get('APPEARANCE', 'font_size')
        self.setStyleSheet(f"font-family: {font}; font-size: {size}pt; background-color: #222; color: #EEE;")

        menubar = self.menuBar()
        menubar.setStyleSheet("background-color: #333; color: #FFF;")
        
        file_menu = menubar.addMenu('File')
        refresh_action = QAction('Refresh Spots', self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self.analyzer.force_refresh)
        file_menu.addAction(refresh_action)
        file_menu.addSeparator()
        settings_action = QAction('Settings', self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        help_menu = menubar.addMenu('Help')
        about_action = QAction('About', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        self.info_bar = QLabel("Initializing...")
        self.info_bar.setStyleSheet("background-color: #2A2A2A; color: #AAA; padding: 6px; font-weight: bold;")
        self.info_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_bar)
        
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0) 
        self.progress.setStyleSheet("QProgressBar { border: 0px; background-color: #2A2A2A; } QProgressBar::chunk { background-color: #00FF00; }")
        self.progress.hide()
        layout.addWidget(self.progress)

        self.update_header()

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Table
        self.table = QTableView()
        cols = ["UTC", "dB", "DT", "Freq", "Message", "Grid", "Prob %", "Competition"]
        self.model = DecodeTableModel(cols, self.config)
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("alternate-background-color: #333; background-color: #222; gridline-color: #444; color: #EEE; selection-background-color: #555500;")
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch) 
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        
        splitter.addWidget(self.table)

        # Dashboard & Map
        map_container = QWidget()
        map_layout = QVBoxLayout(map_container)
        map_layout.setContentsMargins(0,0,0,0)
        map_layout.setSpacing(0)
        
        self.dashboard = TargetDashboard()
        map_layout.addWidget(self.dashboard)
        
        self.band_map = BandMapWidget()
        map_layout.addWidget(self.band_map)
        splitter.addWidget(map_container)
        
        splitter.setSizes([600, 300])
        layout.addWidget(splitter)

    def update_header(self):
        self.info_bar.setText(f"{self.str_solar} | {self.str_dial} | {self.str_status}")

    def setup_connections(self):
        self.udp.new_decode.connect(self.handle_new_decode)
        self.udp.status_update.connect(self.handle_status_update)
        self.solar_update_signal.connect(self.update_solar_ui)
        self.band_map.recommendation_changed.connect(self.handle_rec_update)
        self.table.selectionModel().selectionChanged.connect(self.on_table_selection)
        
        self.analyzer.cache_updated.connect(self.refresh_table_data)
        self.analyzer.status_message.connect(self.handle_analyzer_status)

    def handle_analyzer_status(self, msg):
        self.str_status = msg
        self.update_header()
        if "Fetching" in msg: self.progress.show()
        else: self.progress.hide()

    def handle_rec_update(self, freq):
        self.rec_tx_df = freq
        self.dashboard.update_rec(self.rec_tx_df, self.current_tx_df)

    def handle_status_update(self, status):
        if 'dial_freq' in status:
            freq = status['dial_freq']
            self.analyzer.set_dial_freq(freq)
            freq_str = f"{freq/1000000:.3f} MHz"
            self.str_dial = f"Dial: {freq_str}"
            self.update_header()

        if 'dx_call' in status:
            raw_call = status['dx_call']
            new_call = raw_call.strip() if raw_call else ""
            if new_call != self.target_dx_call:
                self.target_dx_call = new_call
                # When WSJT-X changes target, allow a model scan to populate data
                self.populate_dashboard_from_model(new_call)
                # But also update model highlight
                self.model.set_target_call(new_call)
                
        if 'tx_df' in status:
            self.current_tx_df = int(status['tx_df'])
            self.band_map.set_current_tx_freq(self.current_tx_df)
            self.dashboard.update_rec(self.rec_tx_df, self.current_tx_df)

    def populate_dashboard_from_model(self, call):
        if not call:
            self.dashboard.update_data(None)
            return
        
        # Search for data
        rows = self.model._data
        found_data = None
        for i in range(len(rows)-1, -1, -1):
            row = rows[i]
            if call in row.get('message', '') or call == row.get('call', ''):
                found_data = row
                break
        
        if found_data:
            self.dashboard.update_data(found_data)
        else:
            self.dashboard.update_data({'call': call})

    def handle_new_decode(self, raw_data):
        self.raw_queue.append(raw_data)

    def process_batch(self):
        if not self.raw_queue: return
        if len(self.raw_queue) > 1000: self.raw_queue.clear(); return

        BATCH_LIMIT = 50
        batch = []
        while self.raw_queue and len(batch) < BATCH_LIMIT:
            batch.append(self.raw_queue.popleft())
        
        self.band_map.process_decodes(batch)
        best_offset = self.band_map.best_offset
        
        processed_rows = []
        target_update = None
        
        for raw_data in batch:
            raw_data['rec_offset'] = best_offset
            data = self.analyzer.analyze_decode(raw_data)
            processed_rows.append(data)
            
            if self.target_dx_call and (self.target_dx_call in data['message'] or self.target_dx_call == data['call']):
                target_update = data

        self.model.add_batch(processed_rows)
        
        if target_update:
            self.dashboard.update_data(target_update)
        
        if not self.table.model()._data or self.table.verticalHeader().sortIndicatorOrder() == -1:
             scrollbar = self.table.verticalScrollBar()
             if scrollbar.value() >= (scrollbar.maximum() - 20):
                self.table.scrollToBottom()

    def refresh_table_data(self):
        self.model.update_data_in_place(self.analyzer.get_analysis_immediate)
        self.populate_dashboard_from_model(self.target_dx_call)

    def on_table_selection(self, selected, deselected):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            self.band_map.set_target_freq(0)
            self.band_map.set_remote_qrm([])
            return
            
        row = indexes[0].row()
        item = self.model._data[row]
        
        # --- FIXED CLICK LOGIC ---
        # 1. Update Global Target
        call = item.get('call', '')
        if call:
            self.target_dx_call = call
            self.model.set_target_call(call) # Updates table highlight
            self.dashboard.update_data(item) # Updates dashboard immediately
        
        # 2. Update Map
        if 'freq' in item:
            try:
                self.band_map.set_target_freq(int(item['freq']))
            except: pass
            
        if 'remote_qrm' in item:
            self.band_map.set_remote_qrm(item['remote_qrm'])
        else:
            self.band_map.set_remote_qrm([])

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            font = self.config.get('APPEARANCE', 'font_family')
            size = self.config.get('APPEARANCE', 'font_size')
            self.setStyleSheet(f"font-family: {font}; font-size: {size}pt; background-color: #222; color: #EEE;")
            self.analyzer.my_call = self.config.get('ANALYSIS', 'my_callsign')
            self.analyzer.my_grid = self.config.get('ANALYSIS', 'my_grid')
            self.udp.forward_ports = self.config.get_forward_ports()

    def show_about(self):
        title = "About QSO Predictor"
        content = (
            "<h3>QSO Predictor v1.0</h3>"
            "<p>A real-time tactical assistant for digital modes (FT8/FT4).</p>"
            "<hr>"
            "<p><b>License:</b> GNU GPL v3<br>"
            "<b>Copyright:</b> © 2025 WU2C</p>"
            "<p>This program comes with ABSOLUTELY NO WARRANTY. "
            "This is free software, and you are welcome to redistribute it "
            "under certain conditions.</p>"
            "<p><i>Built with Python & PyQt6</i></p>"
        )
        QMessageBox.about(self, title, content)

    def fetch_solar_data(self):
        if not SOLAR_AVAILABLE: return
        t = threading.Thread(target=self._solar_worker, daemon=True)
        t.start()
        
    def _solar_worker(self):
        if self.solar:
            data = self.solar.get_solar_data()
            self.solar_update_signal.emit(data)

    def update_solar_ui(self, data):
        self.str_solar = f"Solar: SFI {data['sfi']} | K {data['k']} ({data['condx']})"
        self.update_header()
        bg_color = "#2A2A2A"
        if data['k'] >= 5: bg_color = "#880000"
        elif data['k'] >= 4: bg_color = "#884400"
        elif data['sfi'] >= 100: bg_color = "#004400"
        self.info_bar.setStyleSheet(f"background-color: {bg_color}; color: #FFF; padding: 4px; font-weight: bold;")

    def closeEvent(self, event):
        geom = self.saveGeometry().toHex().data().decode('ascii')
        self.config.save_setting('WINDOW', 'geometry', geom)
        self.udp.stop()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())