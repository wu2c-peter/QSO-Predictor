# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import numpy as np
import time
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF

class BandMapWidget(QWidget):
    recommendation_changed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(260) 
        self.setStyleSheet("background-color: #101010;")
        self.bandwidth = 3000
        
        self.active_signals = []
        self.best_offset = 1500
        self.current_tx_freq = 0
        self.target_freq = 0
        self.remote_qrm = []
        
        self.occupied_mask = np.zeros(self.bandwidth, dtype=bool)

        self.timer = QTimer()
        self.timer.timeout.connect(self._cleanup_and_repaint)
        self.timer.start(50)

    def update_signals(self, signals):
        now = time.time()
        for sig in signals:
            try:
                freq = int(sig.get('freq', 0))
                snr = int(sig.get('snr', -20))
                if freq > 0 and freq < self.bandwidth:
                    self.active_signals.append({
                        'freq': freq,
                        'snr': snr,
                        'seen': now
                    })
            except: pass

    def set_target_freq(self, freq):
        self.target_freq = freq
        self.update()
        
    def set_current_tx_freq(self, freq):
        self.current_tx_freq = freq
        self.update()

    def set_remote_qrm(self, qrm_list):
        self.remote_qrm = qrm_list
        self.update()
        
    def _cleanup_and_repaint(self):
        # --- CHANGED: Keep signals for 45 seconds (3 cycles) ---
        # This ensures we see "Even" stations while we transmit on "Even"
        now = time.time()
        self.active_signals = [s for s in self.active_signals if now - s['seen'] < 45]
        self._calculate_recommendation()
        self.update()

    def _calculate_recommendation(self):
        self.occupied_mask.fill(False)
        
        for s in self.active_signals:
            f = s['freq']
            width = 50 
            start = max(0, f - width//2)
            end = min(self.bandwidth, f + width//2)
            self.occupied_mask[start:end] = True
        
        for qrm in self.remote_qrm:
            try:
                f = int(qrm['freq'])
                start = max(0, f - 30)
                end = min(self.bandwidth, f + 30)
                self.occupied_mask[start:end] = True
            except: pass

        best_gap_len = 0
        best_gap_center = 1500 
        current_gap_len = 0
        current_gap_start = 0
        
        for f in range(300, 2700):
            if not self.occupied_mask[f]:
                if current_gap_len == 0:
                    current_gap_start = f
                current_gap_len += 1
            else:
                if current_gap_len > best_gap_len:
                    best_gap_len = current_gap_len
                    best_gap_center = current_gap_start + (current_gap_len // 2)
                current_gap_len = 0
        
        if current_gap_len > best_gap_len:
            best_gap_len = current_gap_len
            best_gap_center = current_gap_start + (current_gap_len // 2)
            
        if abs(self.best_offset - best_gap_center) > 10:
            self.best_offset = best_gap_center
            self.recommendation_changed.emit(self.best_offset)

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # Background
        qp.fillRect(0, 0, w, h, QColor("#101010"))
        
        # Draw Frequency Ticks
        qp.setPen(QColor("#444"))
        qp.setFont(QFont("Segoe UI", 8))
        for f in range(0, 3001, 500):
            x = (f / 3000) * w
            qp.drawLine(int(x), 0, int(x), h)
            qp.drawText(int(x)+2, h-5, str(f))

        # --- DRAW ACTIVE SIGNALS ---
        for s in self.active_signals:
            x = (s['freq'] / 3000) * w
            
            px_width = (50 / 3000) * w
            px_width = max(2, px_width) 
            
            snr = s['snr']
            if snr > 0: col = QColor("#00FF00")
            elif snr > -10: col = QColor("#FFFF00")
            else: col = QColor("#FF5555")
            
            # Fade Logic (adjusted for longer life)
            age = time.time() - s['seen']
            # Fade over 45 seconds, but keep min 50 alpha
            alpha = max(50, 255 - int(age * 4.5)) 
            col.setAlpha(alpha)
            
            display_snr = max(-30, min(10, snr))
            norm = (display_snr + 30) / 40 
            bar_h = int(norm * (h - 30)) 
            bar_h = max(4, bar_h) 
            
            qp.fillRect(int(x - px_width/2), h - 20 - bar_h, int(px_width), bar_h, col)

        # --- DRAW REMOTE QRM ---
        qp.setBrush(QBrush(QColor(0, 100, 255, 150))) 
        qp.setPen(Qt.PenStyle.NoPen)
        for qrm in self.remote_qrm:
            try:
                f = int(qrm['freq'])
                snr = int(qrm.get('snr', -10))
                x = (f / 3000) * w
                
                width = (35 / 3000) * w 
                
                display_snr = max(-30, min(10, snr))
                norm = (display_snr + 30) / 40 
                bar_h = int(norm * (h - 30))
                bar_h = max(4, bar_h)

                qp.drawRect(int(x - width/2), h - 20 - bar_h, int(width), bar_h)
            except: pass

        # Draw Target (Magenta Line)
        if self.target_freq > 0:
            x = (self.target_freq / 3000) * w
            pen = QPen(QColor("#FF00FF"), 2)
            qp.setPen(pen)
            qp.drawLine(int(x), 0, int(x), h)

        # Draw Current TX (Yellow Dotted)
        if self.current_tx_freq > 0:
            x = (self.current_tx_freq / 3000) * w
            pen = QPen(QColor("#FFFF00"), 2, Qt.PenStyle.DotLine)
            qp.setPen(pen)
            qp.drawLine(int(x), 0, int(x), h)

        # Draw Recommendation (Green Arrow/Line)
        x_rec = (self.best_offset / 3000) * w
        pen = QPen(QColor("#00FF00"), 2)
        qp.setPen(pen)
        qp.drawLine(int(x_rec), 0, int(x_rec), h)
        
        # --- LEGEND ROW 1 ---
        qp.setPen(QColor("#AAA"))
        qp.setFont(QFont("Segoe UI", 9))
        qp.drawText(10, 20, "Band Activity & QRM Map")
        
        qp.setPen(QColor("#FF00FF")); qp.drawText(10, 40, "― Target")
        qp.setPen(QColor("#FFFF00")); qp.drawText(80, 40, "··· Current TX")
        qp.setPen(QColor("#00FF00")); qp.drawText(180, 40, "― Recommended")
        
        qp.setBrush(QBrush(QColor(0, 100, 255, 150)))
        qp.setPen(Qt.PenStyle.NoPen)
        qp.drawRect(300, 30, 12, 12)
        qp.setPen(QColor("#AAA"))
        qp.drawText(318, 40, "Remote QRM")

        # --- LEGEND ROW 2 ---
        y_row2 = 60
        qp.fillRect(10, y_row2-8, 10, 10, QColor("#00FF00"))
        qp.setPen(QColor("#AAA"))
        qp.drawText(25, y_row2, "Strong (>0dB)")
        
        qp.fillRect(115, y_row2-8, 10, 10, QColor("#FFFF00"))
        qp.drawText(130, y_row2, "Avg (-10dB)")
        
        qp.fillRect(215, y_row2-8, 10, 10, QColor("#FF5555"))
        qp.drawText(230, y_row2, "Weak (<-10dB)")