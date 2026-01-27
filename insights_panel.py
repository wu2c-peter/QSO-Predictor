"""
Insights Panel for QSO Predictor v2.0

UI widget displaying local intelligence:
- Pileup status
- Target behavior patterns
- Success predictions
- Strategy recommendations

Copyright (C) 2025 Peter Hirst (WU2C)

v2.0.6 Changes:
- Added: Sync button in target header (syncs to WSJT-X/JTDX selection)

v2.0.3 Changes:
- Fixed: Wrapped prediction calls in try/except to prevent console spam
- Fixed: Better error handling when ML models fail to load
"""

import logging
from typing import Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QGroupBox, QProgressBar, QFrame, QPushButton,
    QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette

from local_intel.models import (
    PickingStyle, PickingPattern, Prediction, 
    StrategyRecommendation, PathStatus
)
from local_intel.session_tracker import SessionTracker
from local_intel.predictor import BayesianPredictor, HeuristicPredictor

logger = logging.getLogger(__name__)


class PileupStatusWidget(QGroupBox):
    """Display current pileup status."""
    
    def __init__(self, parent=None):
        super().__init__("Pileup Status", parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Size indicator
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Callers:"))
        self.size_label = QLabel("—")
        self.size_label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        size_layout.addWidget(self.size_label)
        size_layout.addStretch()
        layout.addLayout(size_layout)
        
        # Your rank
        rank_layout = QHBoxLayout()
        rank_layout.addWidget(QLabel("Your rank:"))
        self.rank_label = QLabel("—")
        self.rank_label.setFont(QFont("Consolas", 12))
        rank_layout.addWidget(self.rank_label)
        rank_layout.addStretch()
        layout.addLayout(rank_layout)
        
        # Trend indicator
        trend_layout = QHBoxLayout()
        trend_layout.addWidget(QLabel("Trend:"))
        self.trend_label = QLabel("—")
        trend_layout.addWidget(self.trend_label)
        trend_layout.addStretch()
        layout.addLayout(trend_layout)
    
    def update_display(self, pileup_info: Optional[Dict], your_status: Dict):
        """Update the display with current pileup info."""
        if not pileup_info:
            self.size_label.setText("—")
            self.rank_label.setText("—")
            self.trend_label.setText("No target")
            return
        
        size = pileup_info.get('size', 0)
        
        # Size with color coding
        if size == 0:
            self.size_label.setText("0")
            self.size_label.setStyleSheet("color: #00ff00;")  # Green
        elif size <= 5:
            self.size_label.setText(str(size))
            self.size_label.setStyleSheet("color: #00ff00;")  # Green
        elif size <= 10:
            self.size_label.setText(str(size))
            self.size_label.setStyleSheet("color: #ffff00;")  # Yellow
        else:
            self.size_label.setText(str(size))
            self.size_label.setStyleSheet("color: #ff6600;")  # Orange
        
        # Your rank
        if your_status.get('in_pileup'):
            rank = your_status.get('rank', '?')
            total = your_status.get('total', size)
            
            if rank == '?':
                # We're calling but can't see ourselves
                if total == 0:
                    self.rank_label.setText("Calling (clear)")
                else:
                    self.rank_label.setText(f"Calling (+{total})")
                self.rank_label.setStyleSheet("color: #00ffff;")  # Cyan
            elif rank == 1:
                self.rank_label.setText(f"#1 of {total}")
                self.rank_label.setStyleSheet("color: #00ff00;")
            elif isinstance(rank, int) and rank <= 3:
                self.rank_label.setText(f"#{rank} of {total}")
                self.rank_label.setStyleSheet("color: #88ff88;")
            else:
                self.rank_label.setText(f"#{rank} of {total}")
                self.rank_label.setStyleSheet("color: #ffffff;")
        else:
            self.rank_label.setText("Not calling")
            self.rank_label.setStyleSheet("color: #888888;")
        
        # Trend (placeholder - would track over time)
        self.trend_label.setText("—")
    
    def clear(self):
        """Clear the display."""
        self.size_label.setText("—")
        self.size_label.setStyleSheet("")
        self.rank_label.setText("—")
        self.rank_label.setStyleSheet("")
        self.trend_label.setText("—")


class NearMeWidget(QGroupBox):
    """
    Display stations near the user that are being heard by the target.
    
    Phase 1 of Path Intelligence: "Is anyone from my area getting through?"
    
    v2.1.0
    """
    
    # Signal to request Phase 2 analysis (future)
    analyze_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__("Path Intelligence", parent)
        self._setup_ui()
        self._near_me_data = None
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Header row: clarify that this shows what target is hearing FROM your area
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("At target:"))
        self.status_label = QLabel("—")
        self.status_label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        header_layout.addWidget(self.status_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Source indicator (target uploading or using proxies)
        self.source_label = QLabel("")
        self.source_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.source_label)
        
        # Station list (up to 3 near-me stations)
        self.station_labels = []
        for i in range(3):
            station_label = QLabel("")
            station_label.setStyleSheet("color: #cccccc; font-size: 11px; padding-left: 8px;")
            station_label.setWordWrap(True)
            layout.addWidget(station_label)
            self.station_labels.append(station_label)
        
        # Insight/suggestion
        self.insight_label = QLabel("")
        self.insight_label.setStyleSheet("color: #88ccff; font-size: 11px;")
        self.insight_label.setWordWrap(True)
        layout.addWidget(self.insight_label)
        
        # Future: Analyze button for Phase 2
        # self.analyze_button = QPushButton("🔍 Analyze Why")
        # self.analyze_button.clicked.connect(self.analyze_requested.emit)
        # self.analyze_button.hide()
        # layout.addWidget(self.analyze_button)
    
    def update_display(self, near_me_data: Optional[Dict], path_status: 'PathStatus' = None):
        """
        Update display with near-me station data.
        
        Args:
            near_me_data: Dict from analyzer.find_near_me_stations()
                {
                    'stations': [...],
                    'target_uploading': bool,
                    'proxy_count': int,
                    'my_grid': str
                }
            path_status: Current path status (CONNECTED, PATH_OPEN, NO_PATH, UNKNOWN)
                         Used to customize insight text
        """
        self._near_me_data = near_me_data
        
        if not near_me_data or not near_me_data.get('my_grid'):
            self.status_label.setText("—")
            self.status_label.setStyleSheet("color: #888888;")
            self.source_label.setText("Configure your grid in Settings")
            for label in self.station_labels:
                label.setText("")
            self.insight_label.setText("")
            return
        
        stations = near_me_data.get('stations', [])
        target_uploading = near_me_data.get('target_uploading', False)
        proxy_count = near_me_data.get('proxy_count', 0)
        
        # Update source indicator - clarify WHO is hearing these stations
        if target_uploading:
            self.source_label.setText("✓ Target decoding these directly")
            self.source_label.setStyleSheet("color: #88ff88; font-size: 10px;")
        elif proxy_count > 0:
            self.source_label.setText(f"▲ Heard by {proxy_count} station(s) near target")
            self.source_label.setStyleSheet("color: #ffcc00; font-size: 10px;")
        else:
            self.source_label.setText("No reporters in target area")
            self.source_label.setStyleSheet("color: #888888; font-size: 10px;")
        
        # Update status based on station count
        count = len(stations)
        if count == 0:
            self.status_label.setText("None from your area")
            self.status_label.setStyleSheet("color: #ff6666;")  # Red
            if proxy_count > 0 or target_uploading:
                self.insight_label.setText("💡 No path from your area currently")
            else:
                self.insight_label.setText("💡 No data - target area not reporting")
        elif count >= 1:
            # We have near-me stations getting through
            if count == 1:
                self.status_label.setText("1 from your area heard")
                self.status_label.setStyleSheet("color: #ffcc00;")  # Yellow - marginal
            else:
                self.status_label.setText(f"{count} from your area heard")
                self.status_label.setStyleSheet("color: #00ff00;")  # Green - good
            
            # Customize insight based on path status
            # If Path column says "No Path" but we see near-me stations, clarify!
            if path_status == PathStatus.CONNECTED:
                self.insight_label.setText("💡 Target hears you too!")
            elif path_status == PathStatus.PATH_OPEN:
                self.insight_label.setText("💡 Path confirmed - keep calling!")
            elif path_status == PathStatus.NO_PATH:
                # This is the key insight: others are getting through, you should too!
                self.insight_label.setText("💡 Others getting through — you can too!")
            else:
                self.insight_label.setText("💡 Path is open! Keep calling")
        
        # Clear station labels first
        for label in self.station_labels:
            label.setText("")
        
        # Populate station details (up to 3)
        for i, station in enumerate(stations[:3]):
            call = station.get('call', '?')
            grid = station.get('grid', '?')
            snr = station.get('snr', -99)
            freq = station.get('freq', 0)
            distance = station.get('distance', 'field')
            heard_by = station.get('heard_by', 'proxy')
            
            # Format frequency as offset if small
            if freq > 10000:
                freq_str = f"{freq} Hz"
            else:
                freq_str = f"{freq} Hz"
            
            # Distance indicator
            dist_icon = "📍" if distance == 'grid' else "🗺️"
            
            # Format: "📍 W2XYZ (FN31) → -12 dB @ 1847 Hz"
            text = f"{dist_icon} {call} ({grid[:4] if len(grid) >= 4 else grid}) → {snr:+d} dB @ {freq_str}"
            self.station_labels[i].setText(text)
            
            # Color based on SNR
            if snr >= -10:
                self.station_labels[i].setStyleSheet("color: #00ff00; font-size: 11px; padding-left: 8px;")
            elif snr >= -18:
                self.station_labels[i].setStyleSheet("color: #ffcc00; font-size: 11px; padding-left: 8px;")
            else:
                self.station_labels[i].setStyleSheet("color: #ff8888; font-size: 11px; padding-left: 8px;")
    
    def clear(self):
        """Clear the display."""
        self.status_label.setText("—")
        self.status_label.setStyleSheet("color: #888888;")
        self.source_label.setText("")
        for label in self.station_labels:
            label.setText("")
        self.insight_label.setText("")
        self._near_me_data = None


class BehaviorWidget(QGroupBox):
    """Display target's picking behavior."""
    
    def __init__(self, parent=None):
        super().__init__("Behavior", parent)
        self._current_call = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Pattern
        pattern_layout = QHBoxLayout()
        pattern_layout.addWidget(QLabel("Pattern:"))
        self.pattern_label = QLabel("—")
        self.pattern_label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        pattern_layout.addWidget(self.pattern_label)
        pattern_layout.addStretch()
        layout.addLayout(pattern_layout)
        
        # Distribution bar (L/M/R proportions)
        dist_layout = QHBoxLayout()
        dist_layout.setSpacing(2)
        self.dist_label = QLabel("")
        self.dist_label.setStyleSheet("font-size: 9px; color: #888888;")
        dist_layout.addWidget(self.dist_label)
        dist_layout.addStretch()
        layout.addLayout(dist_layout)
        
        # Distribution bar widget
        self.dist_bar = QFrame()
        self.dist_bar.setFixedHeight(8)
        self.dist_bar.setStyleSheet("background: #333333; border-radius: 2px;")
        layout.addWidget(self.dist_bar)
        
        # Hidden by default until we have data
        self.dist_bar.hide()
        self.dist_label.hide()
        
        # Confidence
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Confidence:"))
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setFixedWidth(80)
        self.confidence_bar.setFixedHeight(16)
        conf_layout.addWidget(self.confidence_bar)
        conf_layout.addStretch()
        layout.addLayout(conf_layout)
        
        # Advice
        self.advice_label = QLabel("—")
        self.advice_label.setWordWrap(True)
        self.advice_label.setStyleSheet("color: #aaaaaa; font-style: italic;")
        layout.addWidget(self.advice_label)
    
    def set_loading(self, callsign: str):
        """Show immediate loading feedback when target changes."""
        self._current_call = callsign
        self.pattern_label.setText("Looking up...")
        self.pattern_label.setStyleSheet("color: #888888;")
        self.confidence_bar.setValue(0)
        self.advice_label.setText("Searching history...")
        self.dist_bar.hide()
        self.dist_label.hide()
    
    def _update_distribution_bar(self, distribution: dict):
        """Update the distribution bar showing L/M/R proportions."""
        if not distribution or distribution.get('total', 0) == 0:
            self.dist_bar.hide()
            self.dist_label.hide()
            return
        
        loudest = distribution.get('loudest', 0)
        methodical = distribution.get('methodical', 0)
        random = distribution.get('random', 0)
        total = distribution.get('total', 0)
        
        # Show distribution label
        self.dist_label.setText(f"L:{loudest:.0%} M:{methodical:.0%} R:{random:.0%} ({total} obs)")
        self.dist_label.show()
        
        # Create colored bar segments using stylesheet gradient
        # Orange for loudest, Blue for methodical, Green for random
        if loudest + methodical + random > 0:
            l_pct = loudest * 100
            m_pct = methodical * 100
            r_pct = random * 100
            
            # Build gradient stops
            # Orange (loudest) from 0 to l_pct
            # Blue (methodical) from l_pct to l_pct + m_pct
            # Green (random) from l_pct + m_pct to 100
            l_end = l_pct
            m_end = l_pct + m_pct
            
            gradient = f"""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff8800,
                    stop:{l_end/100:.3f} #ff8800,
                    stop:{l_end/100:.3f} #00aaff,
                    stop:{m_end/100:.3f} #00aaff,
                    stop:{m_end/100:.3f} #88ff88,
                    stop:1 #88ff88
                );
                border-radius: 2px;
            """
            self.dist_bar.setStyleSheet(gradient)
            self.dist_bar.show()
        else:
            self.dist_bar.hide()
    
    def update_display(self, behavior_info: Optional[Dict]):
        """Update with behavior analysis including Bayesian estimate."""
        if not behavior_info:
            self.clear()
            return
        
        pattern: Optional[PickingPattern] = behavior_info.get('pattern')
        
        # Style display names
        style_display = {
            'loudest_first': "Loudest First",
            'methodical': "Methodical",
            'methodical_low_high': "Low → High",
            'methodical_high_low': "High → Low", 
            'geographic': "Geographic",
            'random': "Random/Fair",
            'unknown': "Unknown",
            PickingStyle.LOUDEST_FIRST: "Loudest First",
            PickingStyle.METHODICAL_LOW_HIGH: "Low → High",
            PickingStyle.METHODICAL_HIGH_LOW: "High → Low",
            PickingStyle.GEOGRAPHIC: "Geographic",
            PickingStyle.RANDOM: "Random/Fair",
            PickingStyle.UNKNOWN: "Unknown",
        }
        
        # Check if we have live pattern analysis (5+ QSOs)
        if pattern:
            # Show live pattern (takes precedence)
            self.pattern_label.setText(style_display.get(pattern.style, "Unknown"))
            
            # Color by pattern type
            if pattern.style == PickingStyle.LOUDEST_FIRST:
                self.pattern_label.setStyleSheet("color: #ff8800;")  # Orange - signal matters
            elif pattern.style in [PickingStyle.METHODICAL_LOW_HIGH, PickingStyle.METHODICAL_HIGH_LOW]:
                self.pattern_label.setStyleSheet("color: #00aaff;")  # Blue - frequency matters
            else:
                self.pattern_label.setStyleSheet("color: #88ff88;")  # Green - fair
            
            # Confidence from live analysis
            conf_pct = int(pattern.confidence * 100)
            self.confidence_bar.setValue(conf_pct)
            self.advice_label.setText(pattern.advice or "—")
            
        elif behavior_info.get('bayesian_style'):
            # Show Bayesian estimate (ML/historical/default)
            style = behavior_info['bayesian_style']
            confidence = behavior_info.get('bayesian_confidence', 0.3)
            source = behavior_info.get('bayesian_source', 'default')
            qso_count = behavior_info.get('qso_count', 0)
            
            # If no real data, show "observing" instead of fake prediction
            if source == 'default' and qso_count == 0:
                self.pattern_label.setText("Observing...")
                self.pattern_label.setStyleSheet("color: #888888;")  # Gray
                self.confidence_bar.setValue(0)
                self.advice_label.setText("No history - watching for patterns")
            else:
                self.pattern_label.setText(style_display.get(style, style.title()))
                
                # Color by style
                if style == 'loudest_first':
                    self.pattern_label.setStyleSheet("color: #ff8800;")
                elif style == 'methodical':
                    self.pattern_label.setStyleSheet("color: #00aaff;")
                else:
                    self.pattern_label.setStyleSheet("color: #88ff88;")
                
                conf_pct = int(confidence * 100)
                self.confidence_bar.setValue(conf_pct)
                
                # Show source of estimate
                if source == 'historical':
                    self.advice_label.setText(f"From history ({qso_count} live QSOs)")
                elif source == 'ml_model':
                    metadata = behavior_info.get('bayesian_metadata') or {}
                    if 'persona' in metadata:
                        # Persona-based prediction
                        persona = metadata['persona'].replace('_', ' ').title()
                        self.advice_label.setText(f"Persona: {persona} ({qso_count} live)")
                    elif 'prefix' in metadata:
                        # Prefix-based prediction
                        prefix = metadata['prefix']
                        sample = metadata.get('sample_stations', 0)
                        self.advice_label.setText(f"Based on {sample} {prefix} stations ({qso_count} live)")
                    else:
                        self.advice_label.setText(f"ML prediction ({qso_count} live QSOs)")
                elif source == 'bayesian' and qso_count > 0:
                    self.advice_label.setText(f"Live estimate ({qso_count} QSOs observed)")
                else:
                    self.advice_label.setText(f"Watching ({qso_count} QSOs observed)")
            
        else:
            # No data at all
            self.pattern_label.setText("Analyzing...")
            self.pattern_label.setStyleSheet("")
            self.confidence_bar.setValue(0)
            self.advice_label.setText(f"Watching target ({behavior_info.get('qso_count', 0)} QSOs observed)")
        
        # Update distribution bar if we have distribution data
        distribution = behavior_info.get('distribution')
        self._update_distribution_bar(distribution)
    
    def clear(self):
        """Clear the display."""
        self._current_call = None
        self.setTitle("Behavior")
        self.pattern_label.setText("—")
        self.pattern_label.setStyleSheet("")
        self.confidence_bar.setValue(0)
        self.advice_label.setText("Select a target")
        self.dist_bar.hide()
        self.dist_label.hide()


class PredictionWidget(QGroupBox):
    """Display success prediction."""
    
    def __init__(self, parent=None):
        super().__init__("Success Prediction", parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Main probability display
        prob_layout = QHBoxLayout()
        self.prob_label = QLabel("—")
        self.prob_label.setFont(QFont("Consolas", 24, QFont.Weight.Bold))
        self.prob_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prob_layout.addWidget(self.prob_label)
        layout.addLayout(prob_layout)
        
        # Confidence indicator
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Confidence:"))
        self.confidence_label = QLabel("—")
        conf_layout.addWidget(self.confidence_label)
        conf_layout.addStretch()
        layout.addLayout(conf_layout)
        
        # Explanation
        self.explanation_label = QLabel("—")
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setStyleSheet("color: #aaaaaa; font-size: 10px;")
        layout.addWidget(self.explanation_label)
    
    def update_display(self, prediction: Optional[Prediction]):
        """Update with prediction result."""
        if not prediction:
            self.clear()
            return
        
        prob = prediction.probability
        prob_pct = int(prob * 100)
        
        self.prob_label.setText(f"{prob_pct}%")
        
        # Color by probability
        if prob >= 0.5:
            self.prob_label.setStyleSheet("color: #00ff00;")  # Green
        elif prob >= 0.3:
            self.prob_label.setStyleSheet("color: #ffff00;")  # Yellow
        elif prob >= 0.15:
            self.prob_label.setStyleSheet("color: #ff8800;")  # Orange
        else:
            self.prob_label.setStyleSheet("color: #ff4444;")  # Red
        
        # Confidence
        conf_colors = {
            'high': '#00ff00',
            'medium': '#ffff00',
            'low': '#ff8800',
        }
        conf = prediction.confidence
        self.confidence_label.setText(conf.capitalize())
        self.confidence_label.setStyleSheet(f"color: {conf_colors.get(conf, '#ffffff')};")
        
        # Explanation
        self.explanation_label.setText(prediction.explanation)
    
    def clear(self):
        """Clear the display."""
        self.prob_label.setText("—")
        self.prob_label.setStyleSheet("")
        self.confidence_label.setText("—")
        self.confidence_label.setStyleSheet("")
        self.explanation_label.setText("Select a target to see prediction")


class StrategyWidget(QGroupBox):
    """Display strategy recommendation."""
    
    def __init__(self, parent=None):
        super().__init__("Recommendation", parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Action
        action_layout = QHBoxLayout()
        self.action_label = QLabel("—")
        self.action_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        action_layout.addWidget(self.action_label)
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        # Reasons
        self.reasons_label = QLabel("—")
        self.reasons_label.setWordWrap(True)
        self.reasons_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(self.reasons_label)
    
    def update_display(self, strategy: Optional[StrategyRecommendation]):
        """Update with strategy recommendation."""
        if not strategy:
            self.clear()
            return
        
        # Action
        action = strategy.recommended_action
        action_display = {
            'call_now': '▶ CALL NOW',
            'wait': '⏸ WAIT',
            'try_later': '⏭ TRY LATER',
        }
        self.action_label.setText(action_display.get(action, action.upper()))
        
        # Color by action
        if action == 'call_now':
            self.action_label.setStyleSheet("color: #00ff00;")
        elif action == 'wait':
            self.action_label.setStyleSheet("color: #ffff00;")
        else:
            self.action_label.setStyleSheet("color: #ff8800;")
        
        # Reasons
        if strategy.reasons:
            reasons_text = " • ".join(strategy.reasons[:3])  # Max 3 reasons
            self.reasons_label.setText(reasons_text)
        else:
            self.reasons_label.setText("—")
    
    def clear(self):
        """Clear the display."""
        self.action_label.setText("—")
        self.action_label.setStyleSheet("")
        self.reasons_label.setText("Select a target for recommendations")


class InsightsPanel(QWidget):
    """
    Main insights panel combining all local intelligence displays.
    
    Designed to be docked in the main window or shown as a floating panel.
    """
    
    # Signal when user wants to retrain models
    retrain_requested = pyqtSignal()
    
    # v2.0.6: Signal when user wants to sync target to JTDX
    sync_requested = pyqtSignal()
    
    def __init__(self, 
                 session_tracker: SessionTracker = None,
                 predictor: BayesianPredictor = None,
                 parent=None):
        """
        Initialize insights panel.
        
        Args:
            session_tracker: SessionTracker for pileup data
            predictor: Predictor for success predictions
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.session_tracker = session_tracker
        self.predictor = predictor
        
        # v2.0.3: Track if predictor is working (for error suppression)
        self._predictor_failed = False
        self._predictor_error_logged = False
        
        self._setup_ui()
        
        # Update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh)
        
        # Current target
        self._current_target: Optional[str] = None
        self._path_status = PathStatus.UNKNOWN
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Dark background for the whole panel
        self.setStyleSheet("""
            InsightsPanel {
                background-color: #1a1a1a;
            }
            QGroupBox {
                background-color: #252525;
                border: 1px solid #444;
                border-radius: 4px;
                margin-top: 16px;
                padding: 8px;
                padding-top: 12px;
            }
            QGroupBox::title {
                color: #ffffff;
                background-color: #252525;
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                top: 4px;
                padding: 0 4px;
                font-weight: bold;
            }
            QLabel {
                color: #dddddd;
            }
        """)
        
        # Target header with Sync button (v2.0.6)
        target_header = QHBoxLayout()
        target_header.setSpacing(4)
        
        self.target_label = QLabel("Target: —")
        self.target_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.target_label.setStyleSheet("color: #ffffff; background-color: #333333; padding: 4px; border-radius: 3px;")
        self.target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        target_header.addWidget(self.target_label, stretch=1)
        
        # v2.0.6: Sync button - syncs QSO Predictor target to JTDX selection
        self.sync_button = QPushButton("⟳")
        self.sync_button.setToolTip("Sync target to WSJT-X/JTDX (Ctrl+Y)")
        self.sync_button.setFixedSize(28, 28)
        self.sync_button.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: #DDD;
                border: 1px solid #555;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #333;
            }
        """)
        self.sync_button.clicked.connect(self.sync_requested.emit)
        target_header.addWidget(self.sync_button)
        
        layout.addLayout(target_header)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #444444;")
        layout.addWidget(line)
        
        # Pileup status
        self.pileup_widget = PileupStatusWidget()
        layout.addWidget(self.pileup_widget)
        
        # v2.1.0: Path Intelligence - Near Me stations
        self.near_me_widget = NearMeWidget()
        layout.addWidget(self.near_me_widget)
        
        # Behavior
        self.behavior_widget = BehaviorWidget()
        layout.addWidget(self.behavior_widget)
        
        # Prediction
        self.prediction_widget = PredictionWidget()
        layout.addWidget(self.prediction_widget)
        
        # Strategy
        self.strategy_widget = StrategyWidget()
        layout.addWidget(self.strategy_widget)
        
        # Spacer
        layout.addStretch()
        
        # Model status bar
        self.model_status = QLabel("Models: Not loaded")
        self.model_status.setStyleSheet("color: #888888; font-size: 10px;")
        self.model_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.model_status)
        
        # Retrain button (shown when models are stale)
        self.retrain_button = QPushButton("⟳ Retrain Models")
        self.retrain_button.clicked.connect(self.retrain_requested.emit)
        self.retrain_button.hide()  # Hidden by default
        layout.addWidget(self.retrain_button)
    
    def set_session_tracker(self, tracker: SessionTracker):
        """Set the session tracker."""
        self.session_tracker = tracker
    
    def set_predictor(self, predictor: BayesianPredictor):
        """Set the predictor."""
        self.predictor = predictor
        # v2.0.3: Reset failure tracking when predictor changes
        self._predictor_failed = False
        self._predictor_error_logged = False
    
    def set_target(self, callsign: str, grid: str = None):
        """
        Set the current target station.
        
        Args:
            callsign: Target callsign
            grid: Target grid (if known)
        """
        self._current_target = callsign.upper() if callsign else None
        
        # Update target header
        if self._current_target:
            self.target_label.setText(f"Target: {self._current_target}")
        else:
            self.target_label.setText("Target: —")
        
        # Note: Don't call session_tracker.set_target here - 
        # LocalIntelIntegration already calls it before calling us
        self.refresh()
    
    def show_loading(self, callsign: str):
        """Show immediate loading feedback when target changes."""
        # Update header immediately
        if callsign:
            self.target_label.setText(f"Target: {callsign.upper()}")
        self.behavior_widget.set_loading(callsign)
        # Note: Removed QApplication.processEvents() - it can cause re-entrant 
        # calls to set_target if UDP events are queued, leading to oscillation/crashes
    
    def set_path_status(self, status: PathStatus):
        """Update path status (from main app's perspective)."""
        self._path_status = status
        self.refresh()
    
    def start_updates(self, interval_ms: int = 1000):
        """Start periodic updates."""
        self.update_timer.start(interval_ms)
    
    def stop_updates(self):
        """Stop periodic updates."""
        self.update_timer.stop()
    
    def refresh(self):
        """Refresh all displays with current data."""
        if not self.session_tracker:
            return
        
        # Get current data
        pileup_info = self.session_tracker.get_pileup_info()
        behavior_info = self.session_tracker.get_target_behavior()
        your_status = self.session_tracker.get_your_status()
        
        # Update widgets
        self.pileup_widget.update_display(pileup_info, your_status)
        self.behavior_widget.update_display(behavior_info)
        
        # v2.0.3: Wrapped prediction calls in try/except to prevent spam
        # when ML models fail to load (e.g., sklearn version mismatch)
        if self.predictor and self._current_target and not self._predictor_failed:
            try:
                # Build basic features
                features = {
                    'target_snr': -10,  # Would come from actual data
                    'your_snr': -10,
                    'band_encoded': 5,
                    'hour_utc': 12,
                    'competition': pileup_info.get('size', 0) if pileup_info else 0,
                    'region_encoded': 0,
                    'calls_made': your_status.get('calls_made', 0),
                }
                
                prediction = self.predictor.predict_success(
                    self._current_target, 
                    features,
                    self._path_status
                )
                self.prediction_widget.update_display(prediction)
                
                strategy = self.predictor.get_strategy(self._current_target, self._path_status)
                self.strategy_widget.update_display(strategy)
                
            except Exception as e:
                # Log error once, then suppress further attempts
                if not self._predictor_error_logged:
                    logger.warning(f"Predictor failed (likely sklearn version mismatch): {e}")
                    logger.info("Falling back to heuristic predictions. "
                               "To fix: delete .pkl files in ~/.qso-predictor/models/")
                    self._predictor_error_logged = True
                self._predictor_failed = True
                self.prediction_widget.clear()
                self.strategy_widget.clear()
        else:
            self.prediction_widget.clear()
            self.strategy_widget.clear()
    
    def clear(self):
        """Clear all displays."""
        self._current_target = None
        self.target_label.setText("Target: —")
        self.pileup_widget.clear()
        self.near_me_widget.clear()  # v2.1.0: Path Intelligence
        self.behavior_widget.clear()
        self.prediction_widget.clear()
        self.strategy_widget.clear()
    
    def update_near_me(self, near_me_data: Optional[Dict]):
        """
        Update Path Intelligence display with near-me station data.
        
        v2.1.0: Phase 1 of Path Intelligence.
        
        Args:
            near_me_data: Dict from analyzer.find_near_me_stations()
        """
        # Pass current path status so widget can give context-aware insights
        self.near_me_widget.update_display(near_me_data, self._path_status)
    
    def show_model_status(self, status: str, is_stale: bool = False):
        """Update model status display."""
        self.model_status.setText(status)
        
        # Hide completely if no status (e.g., frozen exe mode)
        if not status:
            self.model_status.hide()
            self.retrain_button.hide()
            return
        
        self.model_status.show()
        
        if is_stale:
            self.model_status.setStyleSheet("color: #ffaa00; font-size: 10px;")
            self.retrain_button.show()
        else:
            self.model_status.setStyleSheet("color: #888888; font-size: 10px;")
            self.retrain_button.hide()
    
    def sizeHint(self):
        """Preferred size."""
        from PyQt6.QtCore import QSize
        return QSize(250, 500)
