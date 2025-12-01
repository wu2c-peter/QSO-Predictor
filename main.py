# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import sys
import threading
from collections import deque
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QTableView, QLabel, QHeaderView, QSplitter, 
                             QMessageBox, QProgressBar, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QAbstractTableModel, QModelIndex, QByteArray
from PyQt6.QtGui import QColor, QAction, QKeySequence

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

class DecodeTableModel(QAbstractTableModel):
    def __init__(self, headers, config):
        super().__init__()
        self._data = []
        self._headers = headers
        self.config = config
        self.target_dx_call = ""
        
        self.col_high = QColor(config.get('APPEARANCE', 'high_prob_color'))
        self.col_low = QColor(config.get('APPEARANCE', 'low_prob_color'))
        self.col_def = QColor("#EEEEEE")
        self.col_pin = QColor("#004444")
        self.col_text = QColor("#EEEEEE")

    def set_target_call(self, call):
        self.target_dx_call = call
        if call:
            idx = -1
            for i, row in enumerate(self._data):
                if call in row.get('message', '') or call == row.get('call', ''):
                    idx = i
                    break
            if idx > 0:
                self.beginMoveRows(QModelIndex(), idx, idx, QModelIndex(), 0)
                item = self._data.pop(idx)
                self._data.insert(0, item)
                self.endMoveRows()
        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self._headers)

    def sort(self, column, order):
        self.layoutAboutToBeChanged.emit()
        
        keys = ['time', 'snr', 'dt', 'freq', 'message', 'grid', 'prob', 'competition']
        if column >= len(keys): return
        key = keys[column]
        reverse = (order == Qt.SortOrder.DescendingOrder)
        
        def sort_key(row):
            val = row.get(key, "")
            if key in ['snr', 'freq']:
                try: return float(val)
                except: return -9999
            if key == 'dt':
                try: return float(val)
                except: return 0.0
            if key == 'prob':
                try: return int(val.replace('%', ''))
                except: return -1
            return str(val).lower()

        self._data.sort(key=sort_key, reverse=reverse)
        
        if self.target_dx_call:
            target_idx = -1
            for i, row in enumerate(self._data):
                if self.target_dx_call in row.get('message', '') or self.target_dx_call == row.get('call', ''):
                    target_idx = i
                    break
            if target_idx > 0:
                item = self._data.pop(target_idx)
                self._data.insert(0, item)

        self.layoutChanged.emit()

    def data(self, index, role):
        if not index.isValid(): return None
        row_idx = index.row()
        col_idx = index.column()
        item = self._data[row_idx]

        if role == Qt.ItemDataRole.DisplayRole:
            keys = ['time', 'snr', 'dt', 'freq', 'message', 'grid', 'prob', 'competition']
            if col_idx < len(keys):
                return str(item.get(keys[col_idx], ""))

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col_idx == 4: 
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignCenter

        elif role == Qt.ItemDataRole.ForegroundRole:
            if col_idx == 6: 
                prob_str = item.get('prob', "0%")
                try:
                    val = int(prob_str.replace('%', ''))
                    if val > 75: return self.col_high
                    elif val < 30: return self.col_low
                except: pass
            return self.col_text

        elif role == Qt.ItemDataRole.BackgroundRole:
            if self.target_dx_call:
                msg = item.get('message', '')
                call = item.get('call', '')
                if self.target_dx_call in msg or self.target_dx_call == call:
                    return self.col_pin
        
        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def add_batch(self, new_rows):
        if not new_rows: return
        
        if self.target_dx_call:
            targets = []
            others = []
            for r in new_rows:
                if self.target_dx_call in r.get('message', '') or self.target_dx_call == r.get('call', ''):
                    targets.append(r)
                else:
                    others.append(r)
            
            has_pinned = False
            if self._data:
                top = self._data[0]
                if self.target_dx_call in top.get('message', '') or self.target_dx_call == top.get('call', ''):
                    has_pinned = True

            if targets:
                to_add = targets + others
                self.beginInsertRows(QModelIndex(), 0, len(to_add) - 1)
                self._data[0:0] = to_add
                self.endInsertRows()
            elif has_pinned:
                if others:
                    self.beginInsertRows(QModelIndex(), 1, len(others)) 
                    self._data[1:1] = others
                    self.endInsertRows()
            else:
                self.beginInsertRows(QModelIndex(), 0, len(new_rows) - 1)
                self._data[0:0] = new_rows
                self.endInsertRows()
        else:
            self.beginInsertRows(QModelIndex(), 0, len(new_rows) - 1)
            self._data[0:0] = new_rows
            self.endInsertRows()

        if len(self._data) > 200: 
            self.beginRemoveRows(QModelIndex(), 200, len(self._data)-1)
            del self._data[200:]
            self.endRemoveRows()

    def update_data_in_place(self, analyzer_func):
        if not self._data: return
        for item in self._data:
            analyzer_func(item)
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
        # --- FIXED COLUMN WIDTH ---
        # Set Competition (Col 7) to ResizeToContents
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        
        splitter.addWidget(self.table)

        map_container = QWidget()
        map_layout = QVBoxLayout(map_container)
        map_layout.setContentsMargins(0,0,0,0)
        self.lbl_rec = QLabel("Recommended Tx Offset: Calculating...")
        self.lbl_rec.setStyleSheet("font-weight: bold; color: #00FF00; padding: 5px;")
        self.band_map = BandMapWidget()
        map_layout.addWidget(self.lbl_rec)
        map_layout.addWidget(self.band_map)
        splitter.addWidget(map_container)
        
        splitter.setSizes([500, 300])
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
        self.update_info_label()
        
    def update_info_label(self):
        self.lbl_rec.setText(f"Recommended Tx Offset: {self.rec_tx_df} Hz (Current: {self.current_tx_df} Hz)")

    def handle_status_update(self, status):
        if 'dial_freq' in status:
            freq = status['dial_freq']
            self.analyzer.set_dial_freq(freq)
            freq_str = f"{freq/1000000:.3f} MHz"
            target_txt = f" (Target: {self.target_dx_call})" if self.target_dx_call else ""
            self.str_dial = f"Dial: {freq_str}{target_txt}"
            self.update_header()

        if 'dx_call' in status:
            raw_call = status['dx_call']
            new_call = raw_call.strip() if raw_call else ""
            if new_call != self.target_dx_call:
                self.target_dx_call = new_call
                self.model.set_target_call(new_call)
                self.refresh_pinning()
                
        if 'tx_df' in status:
            self.current_tx_df = int(status['tx_df'])
            self.band_map.set_current_tx_freq(self.current_tx_df)
            self.update_info_label()

    def refresh_pinning(self):
        self.table.viewport().update()

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
        for raw_data in batch:
            raw_data['rec_offset'] = best_offset
            data = self.analyzer.analyze_decode(raw_data)
            processed_rows.append(data)

        self.model.add_batch(processed_rows)
        
        if not self.table.model()._data or self.table.verticalHeader().sortIndicatorOrder() == -1:
             if self.table.verticalScrollBar().value() < 5:
                self.table.scrollToTop()

    def refresh_table_data(self):
        self.model.update_data_in_place(self.analyzer.get_analysis_immediate)

    def on_table_selection(self, selected, deselected):
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            self.band_map.set_target_freq(0)
            self.band_map.set_remote_qrm([])
            return
            
        row = indexes[0].row()
        item = self.model._data[row]
        
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