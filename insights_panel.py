"""
Insights Panel for QSO Predictor v2.0

UI widget displaying local intelligence:
- Pileup status
- Target behavior patterns
- Success predictions
- Strategy recommendations

Copyright (C) 2025 Peter Hirst (WU2C)
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
    
    def clear(self):
        """Clear the display."""
        self._current_call = None
        self.setTitle("Behavior")
        self.pattern_label.setText("—")
        self.pattern_label.setStyleSheet("")
        self.confidence_bar.setValue(0)
        self.advice_label.setText("Select a target")


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
        
        # Target header (white for visibility on any background)
        self.target_label = QLabel("Target: —")
        self.target_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.target_label.setStyleSheet("color: #ffffff; background-color: #333333; padding: 4px; border-radius: 3px;")
        self.target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.target_label)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #444444;")
        layout.addWidget(line)
        
        # Pileup status
        self.pileup_widget = PileupStatusWidget()
        layout.addWidget(self.pileup_widget)
        
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
        
        # Get prediction
        if self.predictor and self._current_target:
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
        else:
            self.prediction_widget.clear()
            self.strategy_widget.clear()
    
    def clear(self):
        """Clear all displays."""
        self._current_target = None
        self.target_label.setText("Target: —")
        self.pileup_widget.clear()
        self.behavior_widget.clear()
        self.prediction_widget.clear()
        self.strategy_widget.clear()
    
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
