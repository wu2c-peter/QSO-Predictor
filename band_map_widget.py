# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]
#
# Performance optimized version (v2.0.5)
# - Timer reduced from 50ms to 250ms (20Hz -> 4Hz)
# - Changed repaint() to update() for Qt batching
# - Cached all paint objects (QColor, QFont, QPen, QBrush) to avoid per-frame allocation

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
        
        # Score visualization
        self.score_map = np.zeros(self.bandwidth, dtype=float)
        
        # Manual override (click-to-set)
        self.manual_override = False
        self.manual_override_time = 0
        self.manual_override_duration = 3.0  # seconds
        
        # === PERFORMANCE FIX: Cache all paint objects ===
        self._init_paint_cache()
        
        # === PERFORMANCE FIX: Slower timer (was 50ms = 20Hz, now 250ms = 4Hz) ===
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(250)

    def _init_paint_cache(self):
        """Pre-create all paint objects to avoid per-frame allocation overhead."""
        
        # Colors
        self._colors = {
            'background': QColor("#101010"),
            'background_dark': QColor("#0A0A0A"),
            'grid': QColor("#222"),
            'divider': QColor("#333"),
            'placeholder': QColor("#555"),
            'label_dim': QColor("#666"),
            'label_medium': QColor("#888"),
            'label_light': QColor("#DDD"),
            
            # Tier colors
            'tier1_bright': QColor(0, 255, 255),       # Cyan - 1-3 signals
            'tier1_medium': QColor(0, 200, 220),      # Cyan-blue - 4-5 signals
            'tier1_dim': QColor(100, 150, 200),       # Dim - 6+ signals
            'tier2': QColor(170, 100, 255),           # Purple - same grid
            'tier3': QColor(130, 70, 200),            # Violet - same field
            'tier4': QColor(90, 90, 120),             # Gray-purple - global
            
            # Score graph colors
            'score_excellent': QColor(0, 255, 0),      # Green
            'score_good': QColor(180, 255, 0),         # Yellow-green
            'score_moderate': QColor(255, 255, 0),     # Yellow
            'score_poor': QColor(255, 128, 0),         # Orange
            'score_avoid': QColor(255, 50, 50),        # Red
            
            # Local signal colors
            'local_strong': QColor(0, 255, 0),         # Green >0dB
            'local_medium': QColor(255, 255, 0),       # Yellow >-10dB
            'local_weak': QColor(255, 50, 50),         # Red <-10dB
            
            # Overlay colors
            'target_line': QColor("#FF00FF"),
            'target_fill': QColor(255, 0, 255, 20),
            'tx_line': QColor("#FFFF00"),
            'rec_line': QColor("#00FF00"),
            
            # Text colors
            'text_cyan': QColor("#00FFFF"),
            'text_yellow': QColor("#FFFF00"),
            'text_orange': QColor("#FF8800"),
            'text_green': QColor("#00FF00"),
            'text_magenta': QColor("#FF00FF"),
        }
        
        # Fonts
        self._fonts = {
            'normal': QFont("Segoe UI", 11),
            'small': QFont("Segoe UI", 8),
            'small_bold': QFont("Segoe UI", 8, QFont.Weight.Bold),
            'medium': QFont("Segoe UI", 9),
            'medium_bold': QFont("Segoe UI", 9, QFont.Weight.Bold),
        }
        
        # Pens
        self._pens = {
            'none': Qt.PenStyle.NoPen,
            'grid': QPen(QColor("#222"), 1),
            'divider': QPen(QColor("#333"), 1),
            'baseline_dot': QPen(QColor("#333"), 1, Qt.PenStyle.DotLine),
            'target': QPen(QColor("#FF00FF"), 2),
            'tx': QPen(QColor("#FFFF00"), 2, Qt.PenStyle.DotLine),
            'rec': QPen(QColor("#00FF00"), 2),
            'score_solid_green': QPen(QColor(0, 255, 0), 2, Qt.PenStyle.SolidLine),
            'score_solid_yellow_green': QPen(QColor(180, 255, 0), 2, Qt.PenStyle.SolidLine),
            'score_solid_yellow': QPen(QColor(255, 255, 0), 2, Qt.PenStyle.SolidLine),
            'score_solid_orange': QPen(QColor(255, 128, 0), 2, Qt.PenStyle.SolidLine),
            'score_solid_red': QPen(QColor(255, 50, 50), 2, Qt.PenStyle.SolidLine),
            'score_dot_green': QPen(QColor(0, 255, 0), 3, Qt.PenStyle.DotLine),
            'score_dot_yellow_green': QPen(QColor(180, 255, 0), 3, Qt.PenStyle.DotLine),
            'score_dot_yellow': QPen(QColor(255, 255, 0), 3, Qt.PenStyle.DotLine),
            'score_dot_orange': QPen(QColor(255, 128, 0), 3, Qt.PenStyle.DotLine),
            'score_dot_red': QPen(QColor(255, 50, 50), 3, Qt.PenStyle.DotLine),
        }
        
        # Brushes for legend
        self._brushes = {
            'tier1_bright': QBrush(QColor(0, 255, 255)),
            'tier1_medium': QBrush(QColor(0, 200, 220)),
            'tier1_dim': QBrush(QColor(100, 150, 200)),
            'tier2': QBrush(QColor(170, 100, 255)),
            'tier3': QBrush(QColor(130, 70, 200)),
            'tier4': QBrush(QColor(90, 90, 120)),
            'local_strong': QBrush(QColor(0, 255, 0)),
            'local_medium': QBrush(QColor(255, 255, 0)),
            'local_weak': QBrush(QColor(255, 50, 50)),
        }
        
        # Pre-create alpha variants for common colors (indexed by alpha 0-255)
        # We'll create them on-demand and cache
        self._alpha_color_cache = {}

    def _get_alpha_color(self, base_color_key, alpha):
        """Get a cached color with specific alpha value."""
        cache_key = (base_color_key, alpha)
        if cache_key not in self._alpha_color_cache:
            base = self._colors[base_color_key]
            color = QColor(base.red(), base.green(), base.blue(), alpha)
            self._alpha_color_cache[cache_key] = color
        return self._alpha_color_cache[cache_key]

    def _get_score_pen(self, score, has_tier1_data):
        """Get cached pen for score graph based on score value and data availability."""
        if score >= 85:
            return self._pens['score_solid_green'] if has_tier1_data else self._pens['score_dot_green']
        elif score >= 60:
            return self._pens['score_solid_yellow_green'] if has_tier1_data else self._pens['score_dot_yellow_green']
        elif score >= 40:
            return self._pens['score_solid_yellow'] if has_tier1_data else self._pens['score_dot_yellow']
        elif score >= 20:
            return self._pens['score_solid_orange'] if has_tier1_data else self._pens['score_dot_orange']
        else:
            return self._pens['score_solid_red'] if has_tier1_data else self._pens['score_dot_red']

    def set_target_call(self, call):
        self.target_call = call.strip().upper()
        self.update()  # PERFORMANCE FIX: was repaint()

    def set_target_grid(self, grid):
        self.target_grid = (grid or "").strip().upper()
        self.update()  # PERFORMANCE FIX: was repaint()

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
        
        self.update()  # PERFORMANCE FIX: was repaint()

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
        self.update()  # PERFORMANCE FIX: was repaint()

    def set_target_freq(self, freq):
        self.target_freq = freq
        self.update()  # PERFORMANCE FIX: was repaint()

    def _tick(self):
        self._cleanup_data()
        
        # Check if manual override has expired
        if self.manual_override:
            if time.time() - self.manual_override_time > self.manual_override_duration:
                self.manual_override = False
        
        # Only auto-calculate if not in manual override
        if not self.manual_override:
            self._calculate_best_frequency()
        
        self.update()  # PERFORMANCE FIX: was repaint()

    def mousePressEvent(self, event):
        """Handle click to manually set frequency."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Calculate frequency from click position
            x = event.position().x()
            w = self.width()
            freq = int((x / w) * self.bandwidth)
            
            # Clamp to valid range
            freq = max(200, min(2800, freq))
            
            # Set manual override
            self.best_offset = freq
            self.manual_override = True
            self.manual_override_time = time.time()
            
            # Emit signal so dashboard updates
            self.recommendation_changed.emit(freq)
            
            self.update()  # PERFORMANCE FIX: was repaint()

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
        """
        Smart frequency recommendation based on K1JT's decoder research:
        - Frequencies where target IS decoding (tier1/cyan) are PROVEN to work
        - 1-3 overlapping signals decode well (subtraction algorithm handles it)
        - 4+ signals = crowded, decode probability drops
        - Empty frequencies = unproven (could be clear OR could have local QRM at target)
        
        Priority: Proven (1-3 signals) > Proven (4+ crowded) > Empty gaps
        
        Also populates score_map for visualization.
        """
        
        # Reset score map
        self.score_map = np.full(self.bandwidth, 50.0)  # Default: unproven = 50
        
        # === STEP 1: Build local busy map (things WE hear - avoid our own QRM) ===
        local_busy = np.zeros(self.bandwidth, dtype=bool)
        for s in self.active_signals:
            if s['decay'] > 0.4:
                f = s['freq']
                start = max(0, f - 30)
                end = min(self.bandwidth, f + 30)
                local_busy[start:end] = True
        
        # Avoid edges - mark as zero score
        local_busy[0:200] = True
        local_busy[2800:3000] = True
        self.score_map[0:200] = 0
        self.score_map[2800:3000] = 0
        
        # Mark locally busy areas as low score
        for i in range(self.bandwidth):
            if local_busy[i]:
                self.score_map[i] = 10  # Can't use - local QRM
        
        # === STEP 2: Analyze tier1 (cyan) - frequencies where target IS decoding ===
        tier1_spots = self.perspective_data.get('tier1', [])
        tier1_freqs = [
            s.get('freq', 0) for s in tier1_spots 
            if s.get('decay', 0) > 0.4 and 200 < s.get('freq', 0) < 2800
        ]
        
        # === STEP 3: Bucket tier1 frequencies to count density ===
        bucket_size = 60  # ~signal width + margin
        tier1_buckets = {}  # bucket_center -> count
        for freq in tier1_freqs:
            bucket = round(freq / bucket_size) * bucket_size
            tier1_buckets[bucket] = tier1_buckets.get(bucket, 0) + 1
        
        # === STEP 4: Score proven frequencies and populate score_map ===
        proven_candidates = []  # (freq, score, count)
        
        for bucket, count in tier1_buckets.items():
            if 1 <= count <= 3:
                # IDEAL: Proven decode frequency, not saturated
                score = 100 - (count - 1) * 5  # 1=100, 2=95, 3=90
            else:
                # Crowded but still proven - better than unproven
                score = 70 - (count - 4) * 10  # 4=70, 5=60, 6=50...
                score = max(30, score)  # Floor
            
            # Apply score to the score_map around this bucket
            for i in range(max(0, bucket - 30), min(self.bandwidth, bucket + 30)):
                if not local_busy[i]:
                    self.score_map[i] = max(self.score_map[i], score)
            
            # Skip if locally busy (we'd interfere with our own decodes)
            if local_busy[max(0, min(self.bandwidth-1, bucket))]:
                continue
            
            proven_candidates.append((bucket, score, count))
        
        # Sort by score
        proven_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # === STEP 5: Score based on tier2/tier3/global congestion ===
        # Penalize areas with activity (these are potential hazards)
        # But BOOST clear gaps to show them as good options
        tier_penalties = {'tier2': 20, 'tier3': 15, 'global': 8}
        congestion_map = np.zeros(self.bandwidth, dtype=float)
        
        for tier_name, penalty in tier_penalties.items():
            for s in self.perspective_data.get(tier_name, []):
                if s.get('decay', 0) > 0.3:
                    f = s.get('freq', 0)
                    if 200 < f < 2800:
                        for i in range(max(0, f - 30), min(self.bandwidth, f + 30)):
                            congestion_map[i] += penalty
        
        # Apply congestion penalties and gap bonuses to score_map
        for i in range(200, 2800):
            if local_busy[i]:
                continue  # Already marked as 10
            
            # Check if this frequency is in a tier1 proven bucket
            bucket_for_i = round(i / bucket_size) * bucket_size
            if bucket_for_i in tier1_buckets:
                continue  # Already scored based on tier1
            
            # Score based on congestion: less congestion = higher score
            congestion = congestion_map[i]
            if congestion == 0:
                # Clear gap - boost above baseline
                self.score_map[i] = 70  # Good - clear of activity
            elif congestion < 15:
                self.score_map[i] = 55  # Slightly better than baseline
            elif congestion < 30:
                self.score_map[i] = 45  # Slightly worse than baseline
            elif congestion < 50:
                self.score_map[i] = 35  # Busy area
            else:
                self.score_map[i] = 25  # Very congested
        
        # === STEP 6: Check current position status ===
        current_idx = max(200, min(2800, self.best_offset))
        current_bucket = round(current_idx / bucket_size) * bucket_size
        current_is_proven = current_bucket in tier1_buckets
        current_count = tier1_buckets.get(current_bucket, 0)
        current_locally_clear = not local_busy[current_idx]
        
        # === STEP 7: Decision logic ===
        
        # If we have good proven candidates
        if proven_candidates:
            best_candidate = proven_candidates[0]
            best_freq, best_score, best_count = best_candidate
            
            # Calculate current score for comparison
            if current_is_proven and current_locally_clear:
                if 1 <= current_count <= 3:
                    current_score = 100 - (current_count - 1) * 5
                else:
                    current_score = max(30, 70 - (current_count - 4) * 10)
            else:
                current_score = 50 if current_locally_clear else 0  # Unproven or blocked
            
            # Hysteresis: only move if significantly better
            should_move = False
            if not current_locally_clear:
                # Current spot blocked by local signal - must move
                should_move = True
            elif best_score > current_score + 15:
                # Significantly better option exists
                should_move = True
            elif not current_is_proven and best_score >= 85:
                # We're in unproven territory, good proven spot available
                should_move = True
            
            if should_move:
                # Smooth transition
                self.best_offset = int((self.best_offset * 0.6) + (best_freq * 0.4))
                return
            elif current_is_proven:
                # Stay in current proven spot
                return
        
        # === STEP 8: Fallback - no proven data, use gap-finding ===
        # This handles the case where target has no tier1 data
        
        # Build full busy map including perspective data
        busy_map = local_busy.copy()
        
        # Mark tier2/tier3/global as potential hazards (but not tier1 - those are good!)
        tier_weights = {'tier2': 0.8, 'tier3': 0.5, 'global': 0.3}
        for tier_name, weight in tier_weights.items():
            for s in self.perspective_data.get(tier_name, []):
                if s.get('decay', 0) > 0.4 * weight:
                    f = s.get('freq', 0)
                    if 0 < f < self.bandwidth:
                        start = max(0, f - 20)
                        end = min(self.bandwidth, f + 20)
                        busy_map[start:end] = True
        
        # Find current gap width
        current_gap_width = 0
        if not busy_map[current_idx]:
            left = current_idx
            while left > 0 and not busy_map[left - 1]:
                left -= 1
            right = current_idx
            while right < self.bandwidth - 1 and not busy_map[right + 1]:
                right += 1
            current_gap_width = right - left
        
        # Find all gaps
        gaps = []
        gap_start = -1
        for i in range(len(busy_map)):
            if not busy_map[i]:
                if gap_start == -1:
                    gap_start = i
            else:
                if gap_start != -1:
                    gaps.append((gap_start, i))
                    gap_start = -1
        if gap_start != -1:
            gaps.append((gap_start, self.bandwidth))
        
        if not gaps:
            return
        
        gaps.sort(key=lambda x: x[1] - x[0], reverse=True)
        best_gap = gaps[0]
        best_gap_width = best_gap[1] - best_gap[0]
        best_center = (best_gap[0] + best_gap[1]) // 2
        
        # Hysteresis for gap-based movement
        should_move = False
        current_still_clear = not busy_map[current_idx]
        
        if not current_still_clear:
            should_move = True
        elif current_gap_width < 50:
            should_move = True
        elif best_gap_width > current_gap_width * 1.5:
            should_move = True
        
        if should_move:
            self.best_offset = int((self.best_offset * 0.7) + (best_center * 0.3))

    def _normalize_call(self, call):
        if not call: return ""
        call = call.replace('<', '').replace('>', '').upper()
        if '/' in call: return max(call.split('/'), key=len)
        return call

    def paintEvent(self, event):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        
        # Layout: Top (40%) | Score Graph (15%) | Bottom (45%)
        top_h = int(h * 0.40)
        score_h = int(h * 0.15)
        bottom_h = h - top_h - score_h
        score_top = top_h
        bottom_top = top_h + score_h
        
        # 1. Background - use cached color
        qp.fillRect(0, 0, w, h, self._colors['background'])
        
        # Grid lines - use cached pen
        qp.setPen(self._pens['grid'])
        for i in range(0, 3000, 500):
            x = (i / 3000) * w
            qp.drawLine(int(x), 0, int(x), h)
        
        # Section dividers - use cached pen
        qp.setPen(self._pens['divider'])
        qp.drawLine(0, top_h, w, top_h)
        qp.drawLine(0, bottom_top, w, bottom_top)

        # 2. PLACEHOLDER TEXT if no target selected (top section)
        if not self.target_call:
            qp.setPen(self._colors['placeholder'])
            qp.setFont(self._fonts['normal'])
            qp.drawText(
                QRectF(0, 0, w, top_h),
                Qt.AlignmentFlag.AlignCenter,
                "Select a target station to see their perspective\nClick a row above or double-click in WSJT-X"
            )
        else:
            # 3. DRAW PERSPECTIVE LAYERS (Top Section) - Back to Front
            qp.setPen(Qt.PenStyle.NoPen)
            
            # Layer 4: Global (dimmest) - Gray-purple
            for spot in self.perspective_data.get('global', []):
                self._draw_perspective_bar(qp, spot, w, top_h, 0, 'tier4', 0.3)
            
            # Layer 3: Same Field - Violet
            for spot in self.perspective_data.get('tier3', []):
                self._draw_perspective_bar(qp, spot, w, top_h, 0, 'tier3', 0.5)
            
            # Layer 2: Same Grid Square - Purple
            for spot in self.perspective_data.get('tier2', []):
                self._draw_perspective_bar(qp, spot, w, top_h, 0, 'tier2', 0.8)
            
            # Layer 1: Direct from Target - Cyan (highest priority)
            # First, bucket them to count density
            tier1_spots = self.perspective_data.get('tier1', [])
            bucket_size = 60
            tier1_buckets = {}  # bucket -> list of spots
            for spot in tier1_spots:
                if spot.get('decay', 0) > 0.3:
                    freq = spot.get('freq', 0)
                    if 200 < freq < 2800:
                        bucket = round(freq / bucket_size) * bucket_size
                        if bucket not in tier1_buckets:
                            tier1_buckets[bucket] = []
                        tier1_buckets[bucket].append(spot)
            
            # Draw each tier1 spot with color based on bucket density
            for bucket, spots in tier1_buckets.items():
                count = len(spots)
                for spot in spots:
                    if count <= 3:
                        color_key = 'tier1_bright'
                    elif count <= 5:
                        color_key = 'tier1_medium'
                    else:
                        color_key = 'tier1_dim'
                    self._draw_perspective_bar(qp, spot, w, top_h, 0, color_key, 1.0)
                
                # Draw count label at the bucket center
                x = int((bucket / 3000) * w)
                qp.setFont(self._fonts['small_bold'])
                if count <= 3:
                    qp.setPen(self._colors['text_cyan'])
                elif count <= 5:
                    qp.setPen(self._colors['text_yellow'])
                else:
                    qp.setPen(self._colors['text_orange'])
                qp.drawText(x - 4, top_h - 3, str(count))

        # 5. DRAW SCORE GRAPH (Middle Section)
        self._draw_score_graph(qp, w, score_h, score_top)

        # 6. DRAW LOCAL LAYERS (Bottom Section)
        for s in self.active_signals:
            freq = s['freq']
            snr = s['snr']
            decay = s['decay']
            x = (freq / 3000) * w
            bar_width = (50 / 3000) * w 
            alpha = int(255 * decay)
            
            # Use cached colors with alpha
            if snr > 0:
                color_key = 'local_strong'
            elif snr > -10:
                color_key = 'local_medium'
            else:
                color_key = 'local_weak'
            
            col = self._get_alpha_color(color_key, alpha)
            norm = max(0, min(1, (snr + 24) / 44))
            bar_h = bottom_h * 0.9 * norm
            
            qp.setBrush(QBrush(col))
            qp.setPen(Qt.PenStyle.NoPen)
            qp.drawRect(QRectF(x - (bar_width/2), h - bar_h, bar_width, bar_h))

        # 7. VERTICAL OVERLAYS (span full height)
        # Target frequency marker
        if self.target_freq > 0:
            x = (self.target_freq / 3000) * w
            qp.setPen(self._pens['target'])
            qp.drawLine(int(x), 0, int(x), h)
            qp.setBrush(self._colors['target_fill'])
            qp.setPen(Qt.PenStyle.NoPen)
            qp.drawRect(QRectF(x-15, 0, 30, h))

        # Current TX frequency (yellow dotted)
        if self.current_tx_freq > 0:
            x = (self.current_tx_freq / 3000) * w
            qp.setPen(self._pens['tx'])
            qp.drawLine(int(x), 0, int(x), h)
        
        # Recommended frequency (green solid)
        if self.best_offset > 0:
            x = (self.best_offset / 3000) * w
            qp.setPen(self._pens['rec'])
            qp.drawLine(int(x), 0, int(x), h)
            # Arrow markers at top and bottom
            qp.drawLine(int(x)-5, 0, int(x)+5, 0)
            qp.drawLine(int(x)-5, h-1, int(x)+5, h-1)
            
            # If in manual override, show countdown
            if self.manual_override:
                remaining = self.manual_override_duration - (time.time() - self.manual_override_time)
                if remaining > 0:
                    qp.setFont(self._fonts['medium_bold'])
                    qp.setPen(self._colors['text_green'])
                    qp.drawText(int(x) + 8, score_top + score_h - 5, f"{remaining:.1f}s")
            
        # 8. LEGEND
        self._draw_legend(qp)

    def _draw_perspective_bar(self, qp, spot, w, section_h, section_top, color_key, opacity_mult):
        """Draw a bar in the perspective section representing target's view."""
        freq = spot.get('freq', 0)
        snr = spot.get('snr', -20)
        decay = spot.get('decay', 1.0)
        
        if freq <= 0 or freq >= self.bandwidth:
            return
        
        alpha = int(255 * decay * opacity_mult)
        color = self._get_alpha_color(color_key, alpha)
        
        x = (freq / 3000) * w
        bar_width = (40 / 3000) * w
        
        # Height based on SNR
        norm = max(0.1, min(1.0, (snr + 25) / 35))
        bar_h = section_h * 0.9 * norm
        
        qp.setBrush(QBrush(color))
        qp.drawRect(QRectF(x - (bar_width/2), section_top, bar_width, bar_h))

    def _draw_score_graph(self, qp, w, section_h, section_top):
        """Draw the score visualization graph in the middle section."""
        
        # Background for score section
        qp.fillRect(0, section_top, w, section_h, self._colors['background_dark'])
        
        # Label
        qp.setFont(self._fonts['small'])
        qp.setPen(self._colors['label_dim'])
        qp.drawText(5, section_top + 12, "Score")
        
        # 50% line (unproven baseline)
        y_50 = section_top + section_h * 0.5
        qp.setPen(self._pens['baseline_dot'])
        qp.drawLine(0, int(y_50), w, int(y_50))
        
        # Check if we have tier1 data (proven frequencies)
        tier1_spots = self.perspective_data.get('tier1', [])
        has_tier1_data = len([s for s in tier1_spots if s.get('decay', 0) > 0.3]) > 0
        
        # Draw score line
        if len(self.score_map) > 0:
            # Downsample for performance (draw every 3rd pixel)
            step = max(1, self.bandwidth // w) * 3
            
            prev_x = None
            prev_y = None
            
            for i in range(0, self.bandwidth, step):
                # Get average score in this bucket
                end_i = min(i + step, self.bandwidth)
                avg_score = np.mean(self.score_map[i:end_i])
                
                x = int((i / self.bandwidth) * w)
                # Map score 0-100 to section height (inverted - high score = top)
                y = int(section_top + section_h * (1.0 - avg_score / 100.0))
                y = max(section_top + 2, min(section_top + section_h - 2, y))
                
                # Draw line segment using cached pen
                if prev_x is not None:
                    qp.setPen(self._get_score_pen(avg_score, has_tier1_data))
                    qp.drawLine(prev_x, prev_y, x, y)
                
                prev_x = x
                prev_y = y
        
        # Show "No perspective data" message if no tier1
        if not has_tier1_data:
            qp.setFont(self._fonts['small'])
            qp.setPen(self._colors['label_medium'])
            qp.drawText(w - 130, section_top + 12, "(gap-based scoring)")
        
        # Show score at current recommendation
        if self.best_offset > 0:
            idx = max(0, min(len(self.score_map) - 1, self.best_offset))
            score = self.score_map[idx]
            qp.setFont(self._fonts['medium_bold'])
            qp.setPen(self._colors['text_green'])
            x = int((self.best_offset / self.bandwidth) * w)
            qp.drawText(x + 8, section_top + section_h - 3, f"{int(score)}")

    def _draw_legend(self, qp):
        qp.setFont(self._fonts['medium'])
        
        # Row 1: Lines
        qp.setPen(self._colors['text_magenta']); qp.drawText(10, 20, "— Target")
        qp.setPen(self._colors['text_yellow']); qp.drawText(80, 20, "··· TX")
        qp.setPen(self._colors['text_green']); qp.drawText(140, 20, "— Rec")
        
        # Row 2: Perspective Tiers (Top Half - What Target Hears)
        qp.setPen(Qt.PenStyle.NoPen)
        
        qp.setBrush(self._brushes['tier1_bright'])
        qp.drawRect(10, 30, 8, 8)
        qp.setPen(self._colors['text_cyan']); qp.drawText(22, 38, "1-3")
        
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['tier1_medium'])
        qp.drawRect(50, 30, 8, 8)
        qp.setPen(self._colors['text_yellow']); qp.drawText(62, 38, "4-5")
        
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['tier1_dim'])
        qp.drawRect(95, 30, 8, 8)
        qp.setPen(self._colors['text_orange']); qp.drawText(107, 38, "6+")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['tier2'])
        qp.drawRect(140, 30, 8, 8)
        qp.setPen(self._colors['label_light']); qp.drawText(152, 38, "Grid")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['tier3'])
        qp.drawRect(190, 30, 8, 8)
        qp.setPen(self._colors['label_light']); qp.drawText(202, 38, "Field")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['tier4'])
        qp.drawRect(245, 30, 8, 8)
        qp.setPen(self._colors['label_light']); qp.drawText(257, 38, "Global")
        
        # Row 3: Local Signals (Bottom Half - What You Hear)
        qp.setPen(self._colors['label_medium']); qp.drawText(10, 52, "Local:")
        
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['local_strong'])
        qp.drawRect(50, 44, 8, 8)
        qp.setPen(self._colors['label_light']); qp.drawText(62, 52, ">0dB")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['local_medium'])
        qp.drawRect(100, 44, 8, 8)
        qp.setPen(self._colors['label_light']); qp.drawText(112, 52, ">-10")

        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(self._brushes['local_weak'])
        qp.drawRect(155, 44, 8, 8)
        qp.setPen(self._colors['label_light']); qp.drawText(167, 52, "Weak")
