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


import sys
import threading
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QTableWidget, QTableWidgetItem, QLabel, QHeaderView, 
                             QSplitter, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QAction

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

class MainWindow(QMainWindow):
    update_row_signal = pyqtSignal(dict)
    solar_update_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.analyzer = QSOAnalyzer(self.config)
        self.udp = UDPHandler(self.config)
        self.solar = SolarClient() if SOLAR_AVAILABLE else None

        self.target_dx_call = "" 

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
        self.apply_styles()

        menubar = self.menuBar()
        menubar.setStyleSheet("background-color: #333; color: #FFF;")
        
        file_menu = menubar.addMenu('File')
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
        
        self.info_bar = QLabel("Solar: Loading... | Dial: Waiting...")
        self.info_bar.setStyleSheet("background-color: #2A2A2A; color: #AAA; padding: 4px; font-weight: bold; border-bottom: 1px solid #444;")
        self.info_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.info_bar)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.table = QTableWidget()
        cols = ["UTC", "dB", "DT", "Freq", "Message", "Grid", "Prob %", "Competition", "Rec. DF"]
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("alternate-background-color: #333; background-color: #222; gridline-color: #444; color: #EEE; selection-background-color: #555500;")
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
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
        
        self.solar_text = "Solar: Loading..."

    def apply_styles(self):
        font = self.config.get('APPEARANCE', 'font_family')
        size = self.config.get('APPEARANCE', 'font_size')
        self.setStyleSheet(f"font-family: {font}; font-size: {size}pt; background-color: #222; color: #EEE;")

    def setup_connections(self):
        self.udp.new_decode.connect(self.handle_new_decode)
        self.udp.status_update.connect(self.handle_status_update)
        self.update_row_signal.connect(self.update_row_async)
        self.solar_update_signal.connect(self.update_solar_ui)
        self.band_map.recommendation_changed.connect(lambda f: self.lbl_rec.setText(f"Recommended Tx Offset: {f} Hz"))
        self.table.itemSelectionChanged.connect(self.on_table_selection)
        
        # Listen for cache updates
        self.analyzer.cache_updated.connect(self.refresh_table_data)

    def handle_status_update(self, status):
        if 'dial_freq' in status:
            freq = status['dial_freq']
            self.analyzer.set_dial_freq(freq)
            dial_txt = f"{freq/1000000:.3f} MHz"
            target_txt = f" | Target: {self.target_dx_call}" if self.target_dx_call else ""
            self.info_bar.setText(f"{self.solar_text} | Dial: {dial_txt}{target_txt}")

        if 'dx_call' in status:
            raw_call = status['dx_call']
            new_call = raw_call.strip() if raw_call else ""
            if new_call != self.target_dx_call:
                self.target_dx_call = new_call
                self.refresh_pinning()

    def refresh_pinning(self):
        if not self.target_dx_call: return
        target_row = -1
        for r in range(self.table.rowCount()):
            msg_item = self.table.item(r, 4)
            if msg_item and self.target_dx_call in msg_item.text():
                target_row = r
                break
        if target_row > 0:
            self._move_row_to_top(target_row)

    def _move_row_to_top(self, old_row):
        items = [self.table.item(old_row, c).clone() for c in range(self.table.columnCount())]
        self.table.removeRow(old_row)
        self.table.insertRow(0)
        for c, item in enumerate(items):
            self.table.setItem(0, c, item)
        self._style_pinned_row(0)

    def _style_pinned_row(self, row):
        for c in range(self.table.columnCount()):
            item = self.table.item(row, c)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setBackground(QColor("#004444"))

    def handle_new_decode(self, raw_data):
        self.band_map.process_decodes([raw_data])
        raw_data['rec_offset'] = self.band_map.best_offset
        data = self.analyzer.analyze_decode(raw_data, self.trigger_async_update)
        self.add_table_row(data)

    def _apply_prob_color(self, item, text):
        try:
            val = int(text.replace('%', ''))
            if val > 75: 
                item.setForeground(QColor(self.config.get('APPEARANCE', 'high_prob_color')))
            elif val < 30: 
                item.setForeground(QColor(self.config.get('APPEARANCE', 'low_prob_color')))
            else:
                item.setForeground(QColor("#EEEEEE")) 
        except: pass

    def add_table_row(self, data):
        is_target = self.target_dx_call and (self.target_dx_call in data['message'] or self.target_dx_call == data['call'])
        insert_row = 0 if is_target else (1 if self.target_dx_call else 0)
        self.table.insertRow(insert_row)
        
        items = [data['time'], str(data['snr']), str(data['dt']), str(data['freq']),
                 data['message'], data['grid'], data['prob'], data['competition'], str(data['rec_offset'])]
        
        for i, text in enumerate(items):
            item = QTableWidgetItem(text)
            if i == 0 and 'remote_qrm' in data:
                item.setData(Qt.ItemDataRole.UserRole, data['remote_qrm'])
            
            # Store hidden callsign in Competition column
            if i == 7:
                 item.setData(Qt.ItemDataRole.UserRole, data['call'])

            if i == 6: self._apply_prob_color(item, text)
            
            self.table.setItem(insert_row, i, item)

        if is_target: self._style_pinned_row(insert_row)
        if self.table.rowCount() > 100: self.table.removeRow(100)

    def refresh_table_data(self):
        """
        FAST REFRESH: Updates table immediately without threading.
        This runs on the main thread, but since lookups are cached/instant,
        it won't freeze the UI.
        """
        for row in range(self.table.rowCount()):
            comp_item = self.table.item(row, 7)
            snr_item = self.table.item(row, 1)
            
            if comp_item and snr_item:
                call = comp_item.data(Qt.ItemDataRole.UserRole)
                if call:
                    try:
                        snr = int(snr_item.text())
                        # Get data synchronously
                        data = self.analyzer.get_analysis_immediate({
                            'call': call, 'snr': snr, 'prob': '15%' 
                        })
                        
                        # Direct Update
                        prob_item = QTableWidgetItem(data['prob'])
                        self._apply_prob_color(prob_item, data['prob'])
                        self.table.setItem(row, 6, prob_item)
                        self.table.setItem(row, 7, QTableWidgetItem(data['competition']))
                        
                        # Update remote QRM invisible data
                        t_item = self.table.item(row, 0)
                        if t_item and 'remote_qrm' in data:
                            t_item.setData(Qt.ItemDataRole.UserRole, data['remote_qrm'])
                            # If selected, update band map immediately
                            if self.table.currentRow() == row:
                                self.band_map.set_remote_qrm(data['remote_qrm'])
                                
                    except: pass

    def update_row_async(self, data):
        # Used by the threaded lookup for NEW decodes
        for row in range(self.table.rowCount()):
            t_item = self.table.item(row, 0)
            msg_item = self.table.item(row, 4)
            if t_item and msg_item and t_item.text() == data['time'] and data['call'] in msg_item.text():
                
                prob_item = QTableWidgetItem(data['prob'])
                self._apply_prob_color(prob_item, data['prob'])
                self.table.setItem(row, 6, prob_item)
                
                self.table.setItem(row, 7, QTableWidgetItem(data['competition']))
                
                if 'remote_qrm' in data:
                    t_item.setData(Qt.ItemDataRole.UserRole, data['remote_qrm'])
                    if self.table.currentRow() == row:
                        self.band_map.set_remote_qrm(data['remote_qrm'])
                
                if row == 0 and self.target_dx_call:
                     self._style_pinned_row(0)
                break

    def on_table_selection(self):
        items = self.table.selectedItems()
        if not items: 
            self.band_map.set_target_freq(0)
            self.band_map.set_remote_qrm([])
            return
        row = items[0].row()
        freq_item = self.table.item(row, 3) 
        if freq_item:
            try:
                freq = int(freq_item.text())
                self.band_map.set_target_freq(freq)
            except ValueError: pass
        time_item = self.table.item(row, 0)
        remote_data = time_item.data(Qt.ItemDataRole.UserRole)
        if remote_data: self.band_map.set_remote_qrm(remote_data)
        else: self.band_map.set_remote_qrm([])

    def trigger_async_update(self, data):
        self.update_row_signal.emit(data)

    def fetch_solar_data(self):
        if not SOLAR_AVAILABLE: return
        t = threading.Thread(target=self._solar_worker, daemon=True)
        t.start()
        
    def _solar_worker(self):
        if self.solar:
            data = self.solar.get_solar_data()
            self.solar_update_signal.emit(data)

    def update_solar_ui(self, data):
        self.solar_text = f"SFI: {data['sfi']} | K-Index: {data['k']} | Conditions: {data['condx']}"
        if "Dial" in self.info_bar.text():
            parts = self.info_bar.text().split("| Dial")
            dial_part = parts[1] if len(parts) > 1 else ""
            self.info_bar.setText(f"{self.solar_text} | Dial{dial_part}")
        else:
            self.info_bar.setText(self.solar_text)
        bg_color = "#2A2A2A"
        if data['k'] >= 5: bg_color = "#880000"
        elif data['k'] >= 4: bg_color = "#884400"
        elif data['sfi'] >= 100: bg_color = "#004400"
        self.info_bar.setStyleSheet(f"background-color: {bg_color}; color: #FFF; padding: 4px; font-weight: bold; border-bottom: 1px solid #666;")

    def open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            self.apply_styles()
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

    def closeEvent(self, event):
        self.udp.stop()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
