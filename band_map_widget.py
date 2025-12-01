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
        
        # Debug visualization for "Occupied" zones
        self.occupied_mask = np.zeros(self.bandwidth, dtype=bool)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    def set_target_freq(self, freq):
        self.target_freq = freq
        self.update()
        
    def set_current_tx_freq(self, freq):
        self.current_tx_freq = freq
        self.update()

    def set_remote_qrm(self, qrm_list):
        self.remote_qrm = qrm_list
        # If list is cleared, we immediately recalc to free up those spots
        self.calculate_best_offset() 
        self.update()

    def process_decodes(self, decodes):
        current_time = time.time()
        
        for d in decodes:
            try:
                raw_f = float(d['freq'])
                if raw_f > 100000: continue 
                     
                freq = int(raw_f)
                snr = int(d['snr'])
                
                if freq < 0 or freq >= self.bandwidth: continue
                # Relaxed filter to catch faint signals that might still cause QRM
                if snr < -40: continue 

                found = False
                for sig in self.active_signals:
                    if abs(sig['freq'] - freq) < 10: 
                        sig['snr'] = max(sig['snr'], snr)
                        sig['last_seen'] = current_time
                        found = True
                        break
                
                if not found:
                    self.active_signals.append({
                        'freq': freq,
                        'snr': snr,
                        'last_seen': current_time
                    })

            except: pass
            
        self.calculate_best_offset()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        legend_h = 45 
        graph_h = h - legend_h
        
        painter.fillRect(0, 0, w, h, QColor("#101010"))
        
        self.draw_legend(painter, w, legend_h)
        painter.translate(0, legend_h)
        
        bar_width = w / self.bandwidth

        # LAYER 0: Debug "Occupied" Zones (Faint Red Background)
        # This shows exactly what the calculator considers "Busy"
        # If the Green Line is over red, it's a bug.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(50, 0, 0, 150))
        
        # Optimize drawing: scan mask
        if self.occupied_mask.any():
            # Draw runs of True
            start = -1
            for i in range(len(self.occupied_mask)):
                if self.occupied_mask[i]:
                    if start == -1: start = i
                else:
                    if start != -1:
                        # End of run
                        x = start * bar_width
                        bw = (i - start) * bar_width
                        painter.drawRect(QRectF(x, 0, bw, graph_h))
                        start = -1
            if start != -1:
                 x = start * bar_width
                 bw = (self.bandwidth - start) * bar_width
                 painter.drawRect(QRectF(x, 0, bw, graph_h))

        # LAYER 1: Active Signals (Background)
        current_time = time.time()
        self.active_signals = [s for s in self.active_signals if current_time - s['last_seen'] < 28.0]
        
        for sig in self.active_signals:
            x = sig['freq'] * bar_width
            age = current_time - sig['last_seen']
            
            if age < 14: opacity = 255
            else: opacity = max(0, 255 - ((age - 14) * 18))
            
            norm_snr = np.interp(sig['snr'], [-24, 15], [0.2, 1.0])
            bar_h = graph_h * norm_snr * 0.9
            
            r = int(np.interp(sig['snr'], [-20, 5], [255, 0]))
            g = int(np.interp(sig['snr'], [-20, 5], [0, 255]))
            
            color = QColor(r, g, 0, int(opacity))
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            w_px = max(3, 50 * bar_width)
            painter.drawRoundedRect(QRectF(x - w_px/2, graph_h - bar_h, w_px, bar_h), 2, 2)

        # LAYER 2: Remote QRM (Foreground)
        for qrm in self.remote_qrm:
            x = qrm['offset'] * bar_width
            age = qrm.get('age', 0)
            opacity = max(60, 200 - (age * 0.3)) 
            snr = qrm.get('snr', -15)
            norm_h = np.interp(snr, [-24, 10], [0.2, 1.0])
            bar_h = graph_h * norm_h
            
            painter.setPen(QPen(QColor(255, 255, 255, 100), 1))
            painter.setBrush(QColor(100, 100, 255, int(opacity))) 
            painter.drawRect(QRectF(x - 4, graph_h - bar_h, 8, bar_h))

        # LAYER 3: Lines
        if self.current_tx_freq > 0:
             cur_x = self.current_tx_freq * bar_width
             pen = QPen(QColor("yellow"), 2, Qt.PenStyle.DotLine)
             painter.setPen(pen)
             painter.drawLine(int(cur_x), 0, int(cur_x), int(graph_h))

        rec_x = self.best_offset * bar_width
        painter.setPen(QPen(QColor("#00FF00"), 2, Qt.PenStyle.DashLine))
        painter.drawLine(int(rec_x), 0, int(rec_x), int(graph_h))
        
        if self.target_freq > 0:
            tx = self.target_freq * bar_width
            painter.setPen(QPen(QColor("#FF00FF"), 3))
            painter.drawLine(int(tx), 0, int(tx), int(graph_h))

    def draw_legend(self, p, w, h):
        p.fillRect(0, 0, w, h, QColor("#1A1A1A"))
        p.setPen(QColor("#444"))
        p.drawLine(0, h, w, h)
        font = p.font()
        font.setPointSize(9)
        p.setFont(font)
        
        row1 = [
            ("Strong (> 0dB)", QColor(0, 255, 0)),
            ("Avg (-10dB)", QColor(255, 255, 0)),
            ("Weak (< -20dB)", QColor(255, 0, 0)),
        ]
        row2 = [
            ("Cur. DF", QColor("yellow")),
            ("Rec. DF", QColor("#00FF00")),
            ("QRM", QColor(100, 100, 255)),
            ("Target", QColor("#FF00FF")),
        ]
        
        x = 10; y = 16
        for text, col in row1:
            p.setBrush(col); p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(x, 6, 12, 12)
            p.setPen(QColor("#DDD")); p.drawText(x + 18, y, text)
            x += 110
            
        x = 10; y = 36
        for text, col in row2:
            p.setBrush(col); p.setPen(Qt.PenStyle.NoPen)
            if "Rec" in text:
                p.setBrush(Qt.BrushStyle.NoBrush); pen = QPen(col); pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen); p.drawRect(x, 26, 12, 12)
            elif "Cur" in text:
                p.setBrush(Qt.BrushStyle.NoBrush); pen = QPen(col); pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen); p.drawRect(x, 26, 12, 12)
            elif "QRM" in text:
                 p.setPen(QPen(QColor(255, 255, 255, 100), 1)); p.drawRect(x, 26, 12, 12)
            else:
                 p.drawRect(x, 26, 12, 12)
            p.setPen(QColor("#DDD")); p.drawText(x + 18, y, text)
            x += 110

    def calculate_best_offset(self):
        # Reset mask
        self.occupied_mask = np.zeros(self.bandwidth, dtype=bool)
        current_time = time.time()
        
        # 1. Mark LOCAL signals (Always blocked)
        for sig in self.active_signals:
            if current_time - sig['last_seen'] < 28.0:
                f = sig['freq']
                # +/- 70Hz block around every local signal
                start = max(0, f - 70)
                end = min(self.bandwidth, f + 70)
                self.occupied_mask[start:end] = True
        
        # 2. Mark REMOTE QRM (Blocked ONLY if target is set/QRM exists)
        # The QRM list is only populated if a row is selected.
        for qrm in self.remote_qrm:
            f = qrm['offset']
            # +/- 70Hz block around QRM
            start = max(0, f - 70)
            end = min(self.bandwidth, f + 70)
            self.occupied_mask[start:end] = True

        # 3. Find widest gap
        # We look for continuous runs of 'False' in the mask
        best_gap_len = 0
        best_gap_center = 1500 # Default
        
        current_gap_len = 0
        current_gap_start = 0
        
        # Scan safe range 300-2700Hz
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
        
        # Check end of band gap
        if current_gap_len > best_gap_len:
            best_gap_len = current_gap_len
            best_gap_center = current_gap_start + (current_gap_len // 2)

        # Update if changed
        if best_gap_center != self.best_offset:
            self.best_offset = best_gap_center
            self.recommendation_changed.emit(self.best_offset)