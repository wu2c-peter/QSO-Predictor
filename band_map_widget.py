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
        
        # Data Containers
        self.active_signals = [] 
        self.remote_qrm = []     
        
        # State
        self.best_offset = 1500
        self.current_tx_freq = 0
        self.target_freq = 0
        self.target_call = ""    
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    def set_target_call(self, call):
        self.target_call = call.strip().upper()
        self.repaint()

    def update_signals(self, signals):
        now = time.time()
        for sig in signals:
            try:
                freq = int(sig.get('freq', 0))
                snr = int(sig.get('snr', -20))
                if freq > 0 and freq < self.bandwidth:
                    self.active_signals.append({
                        'freq': freq, 'snr': snr, 'seen': now, 'decay': 1.0
                    })
            except: pass

    def update_qrm(self, spots):
        now = time.time()
        self.remote_qrm = [s for s in self.remote_qrm if now - s['seen'] < 45]
        for s in spots:
            s['seen'] = now 
            s['decay'] = 1.0
            self.remote_qrm.append(s)

    def set_current_tx_freq(self, freq):
        self.current_tx_freq = freq
        self.repaint()

    def set_target_freq(self, freq):
        self.target_freq = freq
        self.repaint()

    def _tick(self):
        self._cleanup_data()
        self._calculate_best_frequency()
        self.repaint()

    def _cleanup_data(self):
        now = time.time()
        self.active_signals = [s for s in self.active_signals if now - s['seen'] < 15]
        for s in self.active_signals:
            s['decay'] = max(0, 1.0 - ((now - s['seen']) / 15.0))
        self.remote_qrm = [s for s in self.remote_qrm if now - s['seen'] < 45]
        for s in self.remote_qrm:
            s['decay'] = max(0, 1.0 - ((now - s['seen']) / 45.0))

    def _calculate_best_frequency(self):
        busy_map = np.zeros(self.bandwidth, dtype=bool)
        for s in self.active_signals:
            f = s['freq']
            start = max(0, f - 30); end = min(self.bandwidth, f + 30)
            busy_map[start:end] = True
        for s in self.remote_qrm:
            f = s['freq']
            start = max(0, f - 20); end = min(self.bandwidth, f + 20)
            busy_map[start:end] = True
        busy_map[0:200] = True; busy_map[2800:3000] = True
        
        gaps = []
        current_gap_start = -1
        for i in range(len(busy_map)):
            if not busy_map[i]:
                if current_gap_start == -1: current_gap_start = i
            else:
                if current_gap_start != -1:
                    gaps.append((current_gap_start, i))
                    current_gap_start = -1
        if not gaps: return
        gaps.sort(key=lambda x: x[1] - x[0], reverse=True)
        best_gap = gaps[0]
        center = (best_gap[0] + best_gap[1]) // 2
        self.best_offset = int((self.best_offset * 0.9) + (center * 0.1))

    # --- HELPER: Normalize Callsigns for Matching ---
    def _normalize_call(self, call):
        if not call: return ""
        call = call.replace('<', '').replace('>', '').upper()
        if '/' in call: return max(call.split('/'), key=len)
        return call
    # -----------------------------------------------

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width(); h = self.height()
        
        # 1. Background
        qp.fillRect(0, 0, w, h, QColor("#101010"))
        qp.setPen(QColor("#222"))
        for i in range(0, 3000, 500):
            x = (i / 3000) * w
            qp.drawLine(int(x), 0, int(x), h)
            
        # Draw the "Safety Gap" (Center Line)
        qp.setPen(QColor("#1A1A1A"))
        qp.drawLine(0, int(h/2), w, int(h/2))

        # 2. CATEGORIZE SIGNALS (Logic + Physics)
        blue_traffic = []
        orange_pileup = []
        red_threats = []
        cyan_confirmed = [] # <--- NEW COLOR (Cyan instead of Gold)

        def is_in_cluster(target_spot, all_spots):
            tf = target_spot['freq']
            count = 0
            for other in all_spots:
                if abs(other['freq'] - tf) < 40: count += 1
            return count >= 4

        target_core = self._normalize_call(self.target_call)

        for q in self.remote_qrm:
            freq = q.get('freq', 0)
            receiver = q.get('receiver', '')
            receiver_core = self._normalize_call(receiver)
            
            # 1. INTELLIGENCE CHECK: Is the Target hearing this?
            is_heard_by_target = False
            if len(target_core) > 2:
                if target_core == receiver_core: is_heard_by_target = True
                elif target_core in receiver: is_heard_by_target = True
            
            # 2. PHYSICS CHECK: Collision or Pileup?
            is_direct_hit = False
            if self.target_freq > 0 and abs(freq - self.target_freq) < 35:
                is_direct_hit = True
            
            is_dense = is_in_cluster(q, self.remote_qrm)
            
            # 3. ASSIGN PRIORITY
            if is_heard_by_target:
                cyan_confirmed.append(q)
            elif is_direct_hit:
                red_threats.append(q)
            elif is_dense:
                orange_pileup.append(q)
            else:
                blue_traffic.append(q)

        # 3. DRAW TOP LAYERS (Remote) - Max Height 45%
        
        # L1: Blue (Traffic) - Faint
        qp.setPen(Qt.PenStyle.NoPen)
        for q in blue_traffic:
            self._draw_bar(qp, q, w, h, QColor(0, 100, 255), 0.6, is_top=True)

        # L2: Orange (Pileup) - Opaque
        for q in orange_pileup:
            self._draw_bar(qp, q, w, h, QColor(255, 140, 0), 0.9, is_top=True)

        # L3: Red (Collision) - Bright
        for q in red_threats:
            self._draw_bar(qp, q, w, h, QColor(255, 0, 0), 1.0, is_top=True)
            
        # L4: Cyan (Confirmed Heard) - THE STAR
        for q in cyan_confirmed:
            self._draw_bar(qp, q, w, h, QColor(0, 255, 255), 1.0, is_top=True)

        # 4. DRAW BOTTOM LAYERS (Local) - Max Height 45%
        for s in self.active_signals:
            freq = s['freq']; snr = s['snr']; decay = s['decay']
            x = (freq / 3000) * w; width = (50 / 3000) * w 
            alpha = int(255 * decay)
            if snr > 0: col = QColor(0, 255, 0, alpha)      
            elif snr > -10: col = QColor(255, 255, 0, alpha)
            else: col = QColor(255, 50, 50, alpha)          
            
            # --- NEW HEIGHT LOGIC (Capped at 45%) ---
            norm = max(0, min(1, (snr + 24) / 44)) # 0.0 to 1.0
            bar_h = (h * 0.45) * norm
            
            qp.setBrush(QBrush(col))
            qp.drawRect(QRectF(x - (width/2), h - bar_h, width, bar_h))

        # 5. OVERLAYS
        if self.target_freq > 0:
            x = (self.target_freq / 3000) * w
            qp.setPen(QPen(QColor("#FF00FF"), 2))
            qp.drawLine(int(x), 0, int(x), h)
            # Collision Box
            qp.setBrush(QColor(255, 0, 0, 30)); qp.setPen(Qt.PenStyle.NoPen)
            qp.drawRect(QRectF(x-15, 0, 30, h))

        if self.current_tx_freq > 0:
            x = (self.current_tx_freq / 3000) * w
            pen = QPen(QColor("#FFFF00"), 2, Qt.PenStyle.DotLine)
            qp.setPen(pen)
            qp.drawLine(int(x), 0, int(x), h)
            
        if self.best_offset > 0:
            x = (self.best_offset / 3000) * w
            pen = QPen(QColor("#00FF00"), 2)
            qp.setPen(pen)
            qp.drawLine(int(x), 0, int(x), h)
            qp.drawLine(int(x)-4, 0, int(x)+4, 0)
            
        # 6. LEGEND
        self._draw_legend(qp)

    def _draw_bar(self, qp, q, w, h, base_color, opacity_mult, is_top=True):
        freq = q.get('freq', 0); snr = q.get('snr', -20)
        decay = q.get('decay', 1.0)
        if freq == 0: return
        
        alpha = int(255 * decay * opacity_mult)
        color = QColor(base_color)
        color.setAlpha(alpha)
        
        x = (freq / 3000) * w; width = (40 / 3000) * w 
        
        # --- NEW HEIGHT LOGIC (Capped at 45%) ---
        # Map -30dB...0dB...+10dB to 0.1...0.9 range, then scale to 45% of screen
        norm = max(0.1, min(1.0, (snr + 25) / 35))
        bar_h = (h * 0.45) * norm
        
        qp.setBrush(QBrush(color))
        qp.drawRect(QRectF(x - (width/2), 0, width, bar_h))

    def _draw_legend(self, qp):
        qp.setFont(QFont("Segoe UI", 9))
        
        # Row 1
        qp.setPen(QColor("#FF00FF")); qp.drawText(10, 20, "― Target")
        qp.setPen(QColor("#FFFF00")); qp.drawText(80, 20, "··· TX")
        qp.setPen(QColor("#00FF00")); qp.drawText(140, 20, "― Rec")
        
        # Row 2 (Tuned Legend)
        # Blue
        qp.setPen(Qt.PenStyle.NoPen); qp.setBrush(QColor(0, 100, 255))
        qp.drawRect(10, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(22, 38, "Traffic")

        # Orange
        qp.setPen(Qt.PenStyle.NoPen); qp.setBrush(QColor(255, 140, 0))
        qp.drawRect(70, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(82, 38, "Cluster")

        # Red
        qp.setPen(Qt.PenStyle.NoPen); qp.setBrush(QColor(255, 0, 0))
        qp.drawRect(130, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(142, 38, "Collision")

        # Cyan
        qp.setPen(Qt.PenStyle.NoPen); qp.setBrush(QColor(0, 255, 255))
        qp.drawRect(200, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(212, 38, "Confirmed")