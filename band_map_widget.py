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


import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygon
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint

class BandMapWidget(QWidget):
    recommendation_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(200)
        self.setStyleSheet("background-color: #101010;")
        self.bandwidth = 3000
        
        self.current_spectrum = np.zeros(self.bandwidth, dtype=np.float32)
        self.remote_qrm_spectrum = np.zeros(self.bandwidth, dtype=np.float32)
        
        self.history_height = 100
        self.history = np.zeros((self.history_height, self.bandwidth), dtype=np.uint8)
        
        self.best_offset = 1500
        self.target_freq = None 
        
        self.decay_timer = QTimer()
        self.decay_timer.timeout.connect(self._decay_cycle)
        self.decay_timer.start(100) 
        
        self.hold_counter = 0

    def set_target_freq(self, freq):
        self.target_freq = int(freq)
        self.update()
        self._find_best_gap()

    def set_remote_qrm(self, qrm_data_list):
        self.remote_qrm_spectrum.fill(0)
        
        for item in qrm_data_list:
            freq = item['offset']
            snr = item['snr']
            age = item['age'] # Seconds
            
            # 1. Calculate Intensity based on SNR
            snr_factor = max(0.2, min(1.0, (snr + 25) / 35.0))
            
            # 2. Calculate Decay based on Age
            if age < 60:
                time_factor = 1.0
            elif age > 600:
                time_factor = 0.0
            else:
                time_factor = 1.0 - ((age - 60) / 540.0)
            
            final_intensity = 100 * snr_factor * time_factor
            
            start = max(0, freq - 25)
            end = min(self.bandwidth, freq + 25)
            
            current_slice = self.remote_qrm_spectrum[start:end]
            self.remote_qrm_spectrum[start:end] = np.maximum(current_slice, final_intensity)
            
        self._find_best_gap()
        self.update()

    def process_decodes(self, decode_list):
        self.hold_counter = 0
        for d in decode_list:
            freq = int(d['freq'])
            intensity = max(40, min(100, (d['snr'] + 30) * 3.0))
            start = max(0, freq - 25)
            end = min(self.bandwidth, freq + 25)
            self.current_spectrum[start:end] = np.maximum(self.current_spectrum[start:end], intensity)
        
        self._push_history()
        self._find_best_gap()
        self.update()

    def _decay_cycle(self):
        self.hold_counter += 1
        if self.hold_counter > 120:
            # Keep the slow fade (0.95 is good)
            self.current_spectrum *= 0.95 
            
            # FIX: Allow signals to go to zero! 
            # Anything below 5 is effectively silence, so we snap it to 0.
            self.current_spectrum[self.current_spectrum < 5] = 0 
            
            self.update()

    def _push_history(self):
        self.history = np.roll(self.history, 1, axis=0)
        self.history[0] = self.current_spectrum.astype(np.uint8)

    def _find_best_gap(self):
        SAFE_START = 300
        SAFE_END = 2600
        window_size = 60 
        window = np.ones(window_size)
        
        local_sums = np.convolve(self.current_spectrum, window, mode='valid')
        remote_sums = np.convolve(self.remote_qrm_spectrum, window, mode='valid')
        
        # Base Cost
        occupancy_sums = local_sums + (remote_sums * 2.0)
        
        # Center Bias
        indices = np.arange(len(occupancy_sums))
        freqs = SAFE_START + indices + (window_size // 2)
        dist_from_center = np.abs(freqs - 1500)
        center_penalty = dist_from_center * 0.02
        occupancy_sums += center_penalty

        # Simplex Protection
        if self.target_freq:
            avoid_start = max(0, self.target_freq - 150)
            avoid_end = min(self.bandwidth, self.target_freq + 150)
            idx_start = max(0, avoid_start)
            idx_end = min(len(occupancy_sums), avoid_end)
            if idx_end > idx_start:
                occupancy_sums[idx_start:idx_end] += 50000 

        # Find best hole
        search_start_idx = SAFE_START
        search_end_idx = min(len(occupancy_sums), SAFE_END)
        if search_start_idx >= search_end_idx: return
            
        safe_slice = occupancy_sums[search_start_idx:search_end_idx]
        best_local_idx = np.argmin(safe_slice)
        new_best = search_start_idx + best_local_idx + (window_size // 2)
        
        if abs(new_best - self.best_offset) > 20: 
            self.best_offset = int(new_best)
            self.recommendation_changed.emit(self.best_offset)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101010"))
        w, h = self.width(), self.height()
        bar_width = w / self.bandwidth

        # LAYER 1: LOCAL
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(0, self.bandwidth, 10):
            val = self.current_spectrum[i]
            if val > 5: # Threshold is fine now that we allow 0 values
                r = int(min(255, val * 2.5))
                g = int(min(255, (100 - val) * 2.5))
                painter.setBrush(QBrush(QColor(r, max(0, g), 0)))
                x = int(i * bar_width)
                painter.drawRect(x, 0, max(2, int(10 * bar_width)), 40)

        # LAYER 2: REMOTE (Using Intensity)
        for i in range(0, self.bandwidth, 10):
            val = self.remote_qrm_spectrum[i]
            if val > 5:
                alpha = int(min(255, val * 2.5))
                painter.setBrush(QBrush(QColor(255, 0, 255, alpha))) 
                
                x = int(i * bar_width)
                bar_h = int(val * 0.4) 
                painter.drawRect(x, 10, max(2, int(10 * bar_width)), bar_h)
                
                painter.setPen(QPen(QColor(255, 0, 255, alpha), 2))
                painter.drawLine(x, 0, x, 50)
                painter.setPen(Qt.PenStyle.NoPen)

        # LAYER 3: History
        pixel_h = (h - 50) / self.history_height
        for row_idx in range(self.history_height):
            row_data = self.history[row_idx]
            y = int(50 + (row_idx * pixel_h))
            active_indices = np.where(row_data > 15)[0]
            for freq in active_indices[::5]:
                intensity = row_data[freq]
                x = int(freq * bar_width)
                hist_r = 255
                hist_g = int(min(255, intensity * 2.0)) 
                painter.setPen(QColor(hist_r, hist_g, 0))
                painter.drawPoint(x, y)

        # LAYER 4: Zones
        painter.setBrush(QBrush(QColor(0, 0, 0, 200))) 
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, int(300 * bar_width), h)
        x_safe_end = int(2600 * bar_width)
        painter.drawRect(x_safe_end, 0, w - x_safe_end, h)

        # LAYER 5: Target & Rec
        if self.target_freq:
            x_target = int(self.target_freq * bar_width)
            painter.setPen(QPen(QColor("yellow"), 3)) 
            painter.drawLine(x_target, 0, x_target, h)
            arrow = QPolygon([QPoint(x_target, 0), QPoint(x_target - 8, 15), QPoint(x_target + 8, 15)])
            painter.setBrush(QBrush(QColor("yellow")))
            painter.drawPolygon(arrow)
            painter.drawText(x_target + 10, 20, "TARGET")

        x_best = int(self.best_offset * bar_width)
        painter.setPen(QPen(QColor("#00FF00"), 3, Qt.PenStyle.DashLine))
        painter.drawLine(x_best, 0, x_best, h)
        painter.drawText(x_best + 5, h - 10, f"Rec: {self.best_offset} Hz")
