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
        self.active_signals = []   # Local decodes (what WE hear)
        self.perspective_data = {  # Target perspective (tiered)
            'tier1': [],  # Direct from target
            'tier2': [],  # Same grid square
            'tier3': [],  # Same field
            'global': []  # Background
        }
        
        # State
        self.best_offset = 1500
        self.current_tx_freq = 0
        self.target_freq = 0
        self.target_call = ""
        self.target_grid = ""
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

    def set_target_call(self, call):
        self.target_call = call.strip().upper()
        self.repaint()

    def set_target_grid(self, grid):
        self.target_grid = (grid or "").strip().upper()
        self.repaint()

    def update_signals(self, signals):
        """Update local decode signals (what we hear)."""
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

    def update_perspective(self, perspective_data):
        """
        Update the target perspective data (tiered).
        
        perspective_data = {
            'tier1': [...],  # Direct from target
            'tier2': [...],  # Same grid square
            'tier3': [...],  # Same field
            'global': [...]  # Background
        }
        """
        now = time.time()
        
        # Process each tier
        for tier_name in ['tier1', 'tier2', 'tier3', 'global']:
            tier_spots = perspective_data.get(tier_name, [])
            processed = []
            for spot in tier_spots:
                try:
                    freq = spot.get('freq', 0)
                    snr = spot.get('snr', -20)
                    receiver = spot.get('receiver', '')
                    processed.append({
                        'freq': freq,
                        'snr': snr,
                        'receiver': receiver,
                        'seen': now,
                        'decay': 1.0,
                        'tier': spot.get('tier', 4)
                    })
                except: pass
            self.perspective_data[tier_name] = processed
        
        self.repaint()

    # Legacy method for backward compatibility
    def update_qrm(self, spots):
        """Legacy method - converts to global tier."""
        now = time.time()
        for s in spots:
            s['seen'] = now
            s['decay'] = 1.0
            s['tier'] = 4
        self.perspective_data['global'] = spots

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
        
        # 1. Local Signals - 60 second persistence with decay
        self.active_signals = [s for s in self.active_signals if now - s['seen'] < 60]
        for s in self.active_signals:
            age = now - s['seen']
            if age < 14:
                s['decay'] = 1.0
            elif age < 29:
                s['decay'] = 0.8
            else:
                s['decay'] = max(0, 0.8 - ((age - 29) / 30.0))
        
        # 2. Perspective data - same decay logic per tier
        for tier_name in ['tier1', 'tier2', 'tier3', 'global']:
            tier_list = self.perspective_data.get(tier_name, [])
            tier_list = [s for s in tier_list if now - s.get('seen', 0) < 60]
            for s in tier_list:
                age = now - s.get('seen', now)
                if age < 14:
                    s['decay'] = 1.0
                elif age < 29:
                    s['decay'] = 0.8
                else:
                    s['decay'] = max(0, 0.8 - ((age - 29) / 30.0))
            self.perspective_data[tier_name] = tier_list

    def _calculate_best_frequency(self):
        busy_map = np.zeros(self.bandwidth, dtype=bool)
        
        # Mark local signals
        for s in self.active_signals:
            if s['decay'] > 0.4:
                f = s['freq']
                start = max(0, f - 30); end = min(self.bandwidth, f + 30)
                busy_map[start:end] = True
        
        # Mark perspective data (weight by tier - tier1 matters most)
        tier_weights = {'tier1': 1.0, 'tier2': 0.8, 'tier3': 0.5, 'global': 0.3}
        for tier_name, weight in tier_weights.items():
            for s in self.perspective_data.get(tier_name, []):
                if s.get('decay', 0) > 0.4 * weight:
                    f = s.get('freq', 0)
                    if 0 < f < self.bandwidth:
                        start = max(0, f - 20); end = min(self.bandwidth, f + 20)
                        busy_map[start:end] = True
        
        # Avoid edges
        busy_map[0:200] = True
        busy_map[2800:3000] = True
        
        # Check if current position is still clear
        current_idx = max(0, min(self.bandwidth - 1, self.best_offset))
        current_still_clear = not busy_map[current_idx]
        
        # Find current gap width (if we're in one)
        current_gap_width = 0
        if current_still_clear:
            left = current_idx
            while left > 0 and not busy_map[left - 1]:
                left -= 1
            right = current_idx
            while right < self.bandwidth - 1 and not busy_map[right + 1]:
                right += 1
            current_gap_width = right - left
        
        # Find all gaps
        gaps = []
        current_gap_start = -1
        for i in range(len(busy_map)):
            if not busy_map[i]:
                if current_gap_start == -1: current_gap_start = i
            else:
                if current_gap_start != -1:
                    gaps.append((current_gap_start, i))
                    current_gap_start = -1
        # Handle gap at end
        if current_gap_start != -1:
            gaps.append((current_gap_start, self.bandwidth))
        
        if not gaps:
            return
        
        gaps.sort(key=lambda x: x[1] - x[0], reverse=True)
        best_gap = gaps[0]
        best_gap_width = best_gap[1] - best_gap[0]
        best_center = (best_gap[0] + best_gap[1]) // 2
        
        # Decision: only move if current spot is bad OR new gap is significantly wider
        should_move = False
        
        if not current_still_clear:
            # Current spot got busy - must move
            should_move = True
        elif current_gap_width < 50:
            # Current gap is too narrow - look for better
            should_move = True
        elif best_gap_width > current_gap_width * 1.5:
            # New gap is 50%+ wider - worth moving
            should_move = True
        
        if should_move:
            # Smooth transition to new position
            self.best_offset = int((self.best_offset * 0.7) + (best_center * 0.3))
        # Otherwise: stay put - don't chase marginal improvements

    def _normalize_call(self, call):
        if not call: return ""
        call = call.replace('<', '').replace('>', '').upper()
        if '/' in call: return max(call.split('/'), key=len)
        return call

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
            
        # Safety Gap (Center Line)
        qp.setPen(QColor("#1A1A1A"))
        qp.drawLine(0, int(h/2), w, int(h/2))

        # 2. DRAW PERSPECTIVE LAYERS (Top Half) - Back to Front
        qp.setPen(Qt.PenStyle.NoPen)
        
        # Layer 4: Global (dimmest) - Dark Blue
        for spot in self.perspective_data.get('global', []):
            self._draw_perspective_bar(qp, spot, w, h, QColor(40, 60, 100), 0.3)
        
        # Layer 3: Same Field - Blue
        for spot in self.perspective_data.get('tier3', []):
            self._draw_perspective_bar(qp, spot, w, h, QColor(60, 100, 180), 0.5)
        
        # Layer 2: Same Grid Square - Bright Blue
        for spot in self.perspective_data.get('tier2', []):
            self._draw_perspective_bar(qp, spot, w, h, QColor(80, 140, 255), 0.8)
        
        # Layer 1: Direct from Target - Cyan (highest priority)
        for spot in self.perspective_data.get('tier1', []):
            self._draw_perspective_bar(qp, spot, w, h, QColor(0, 255, 255), 1.0)

        # 3. DRAW COLLISION/THREAT OVERLAY
        # Any tier1/tier2 spot near target freq is a collision
        if self.target_freq > 0:
            for tier_name in ['tier1', 'tier2']:
                for spot in self.perspective_data.get(tier_name, []):
                    freq = spot.get('freq', 0)
                    if 0 < freq < self.bandwidth and abs(freq - self.target_freq) < 35:
                        self._draw_perspective_bar(qp, spot, w, h, QColor(255, 0, 0), 1.0)

        # 4. DRAW LOCAL LAYERS (Bottom Half)
        for s in self.active_signals:
            freq = s['freq']; snr = s['snr']; decay = s['decay']
            x = (freq / 3000) * w; width = (50 / 3000) * w 
            alpha = int(255 * decay)
            if snr > 0: col = QColor(0, 255, 0, alpha)      
            elif snr > -10: col = QColor(255, 255, 0, alpha)
            else: col = QColor(255, 50, 50, alpha)          
            
            norm = max(0, min(1, (snr + 24) / 44))
            bar_h = (h * 0.45) * norm
            
            qp.setBrush(QBrush(col))
            qp.drawRect(QRectF(x - (width/2), h - bar_h, width, bar_h))

        # 5. OVERLAYS
        if self.target_freq > 0:
            x = (self.target_freq / 3000) * w
            qp.setPen(QPen(QColor("#FF00FF"), 2))
            qp.drawLine(int(x), 0, int(x), h)
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

    def _draw_perspective_bar(self, qp, spot, w, h, base_color, opacity_mult):
        """Draw a bar in the top half representing target perspective."""
        freq = spot.get('freq', 0)
        snr = spot.get('snr', -20)
        decay = spot.get('decay', 1.0)
        
        if freq <= 0 or freq >= self.bandwidth:
            return
        
        alpha = int(255 * decay * opacity_mult)
        color = QColor(base_color)
        color.setAlpha(alpha)
        
        x = (freq / 3000) * w
        width = (40 / 3000) * w
        
        # Height based on SNR
        norm = max(0.1, min(1.0, (snr + 25) / 35))
        bar_h = (h * 0.45) * norm
        
        qp.setBrush(QBrush(color))
        qp.drawRect(QRectF(x - (width/2), 0, width, bar_h))

    def _draw_legend(self, qp):
        qp.setFont(QFont("Segoe UI", 9))
        
        # Row 1: Lines
        qp.setPen(QColor("#FF00FF")); qp.drawText(10, 20, "— Target")
        qp.setPen(QColor("#FFFF00")); qp.drawText(80, 20, "··· TX")
        qp.setPen(QColor("#00FF00")); qp.drawText(140, 20, "— Rec")
        
        # Row 2: Perspective Tiers (Top Half - What Target Hears)
        qp.setPen(Qt.PenStyle.NoPen)
        
        qp.setBrush(QColor(0, 255, 255))
        qp.drawRect(10, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(22, 38, "Target Hears")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(80, 140, 255))
        qp.drawRect(110, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(122, 38, "Grid")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(60, 100, 180))
        qp.drawRect(160, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(172, 38, "Field")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(40, 60, 100))
        qp.drawRect(210, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(222, 38, "Global")
        
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(255, 0, 0))
        qp.drawRect(270, 30, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(282, 38, "Collision")
        
        # Row 3: Local Signals (Bottom Half - What You Hear)
        qp.setPen(QColor("#888")); qp.drawText(10, 52, "Local:")
        
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(0, 255, 0))
        qp.drawRect(50, 44, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(62, 52, ">0dB")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(255, 255, 0))
        qp.drawRect(100, 44, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(112, 52, ">-10")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(255, 50, 50))
        qp.drawRect(155, 44, 8, 8)
        qp.setPen(QColor("#DDD")); qp.drawText(167, 52, "Weak")
