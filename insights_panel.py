"""
Insights Panel for QSO Predictor v2.0

UI widget displaying target and operational intelligence:
- Pileup status (local decodes)
- Path intelligence (PSK Reporter)
- Target behavior patterns (log history / live session)
- Success predictions (combined analysis)
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
    QToolTip, QApplication, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette, QPainter, QPen, QBrush

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
        self.setToolTip(
            "Callers visible in YOUR local decodes + target-side\n"
            "competition from PSK Reporter data.\n"
            "When there's a discrepancy, a contrast alert appears."
        )
        self._last_caller_count = 0  # v2.2.0: tracked for tactical toast
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Source badge
        self.source_badge = QLabel("📡 Your Decodes")
        self.source_badge.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.source_badge)
        
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
        
        # v2.2.0: Pileup contrast alert — shows target-side competition
        self.contrast_label = QLabel("")
        self.contrast_label.setStyleSheet(
            "color: #ffcc00; font-size: 11px; font-weight: bold; "
            "padding: 4px; margin-top: 2px;"
        )
        self.contrast_label.setWordWrap(True)
        self.contrast_label.hide()
        layout.addWidget(self.contrast_label)
    
    def update_display(self, pileup_info: Optional[Dict], your_status: Dict):
        """Update the display with current pileup info."""
        if not pileup_info:
            self._last_caller_count = 0  # v2.2.0: track for toast
            self.size_label.setText("—")
            self.rank_label.setText("—")
            self.trend_label.setText("No target")
            return
        
        size = pileup_info.get('size', 0)
        self._last_caller_count = size  # v2.2.0: track for toast
        
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
    
    def set_target_competition(self, competition_str: str):
        """
        v2.2.0: Show target-side competition from PSK Reporter data.
        
        Always shows the target competition when available.
        Highlights with warning styling when there's a discrepancy
        (you see few callers but target has heavy competition).
        
        v2.2.1: Skip hidden pileup warning when data is from local decodes
        (suffix "local") — by definition you CAN see local callers.
        """
        if not competition_str or competition_str == '--':
            self.contrast_label.hide()
            return
        
        # v2.2.1: Local decode data is never "hidden" — you can see it
        is_local_source = 'local' in competition_str.lower()
        
        # Parse local caller count from current display
        local_text = self.size_label.text()
        try:
            local_count = int(local_text)
        except (ValueError, TypeError):
            local_count = 0
        
        # Parse target count
        target_count = 0
        if '(' in competition_str:
            try:
                target_count = int(competition_str.split('(')[1].split(')')[0])
            except (ValueError, IndexError):
                pass
        
        # Check for meaningful discrepancy (hidden pileup)
        # Only applies when data is from PSK Reporter (target-side), not local decodes
        has_target_competition = any(kw in competition_str.upper() 
                                      for kw in ['HIGH', 'PILEUP', 'MODERATE'])
        is_hidden = local_count <= 2 and has_target_competition and not is_local_source
        
        if is_hidden:
            # Warning style — significant hidden pileup
            self.contrast_label.setText(
                f"⚠️ At target: {competition_str}\n"
                f"Hidden pileup — you can't hear your competition!"
            )
            self.contrast_label.setStyleSheet(
                "color: #ffcc00; font-size: 11px; font-weight: bold; "
                "padding: 4px; margin-top: 2px; "
                "background-color: #332200; border-radius: 3px;"
            )
            self.contrast_label.show()
        elif target_count > 0 and not is_local_source:
            # Informational — show target competition without alarm
            # v2.2.1: Skip for local decode data — already visible in Competition column
            self.contrast_label.setText(
                f"📡 At target: {competition_str}"
            )
            self.contrast_label.setStyleSheet(
                "color: #aaaaaa; font-size: 11px; "
                "padding: 4px; margin-top: 2px;"
            )
            self.contrast_label.show()
        else:
            self.contrast_label.hide()
    
    def clear(self):
        """Clear the display."""
        self.size_label.setText("—")
        self.size_label.setStyleSheet("")
        self.rank_label.setText("—")
        self.rank_label.setStyleSheet("")
        self.trend_label.setText("—")
        self.contrast_label.hide()


class NearMeWidget(QGroupBox):
    """
    Display stations near the user that are being heard by the target.
    
    Phase 1 of Path Intelligence: "Is anyone from my area getting through?"
    Phase 2: "Why are THEY getting through?" (on-demand analysis)
    
    v2.1.0
    """
    
    # Signal to request Phase 2 analysis (emits list of stations)
    analyze_requested = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__("Path Intelligence", parent)
        self.setToolTip(
            "Stations from your area being reported near the target.\n"
            "Source: PSK Reporter data.\n"
            "Helps confirm a propagation path exists from your location."
        )
        self._setup_ui()
        self._near_me_data = None
        self._analysis_results = {}  # call -> analysis result
        self._analysis_in_progress = False
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # v2.2.0: Source badge
        source_badge = QLabel("🌐 PSK Reporter")
        source_badge.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(source_badge)
        
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
        
        # Station list with analysis sublabels (up to 3 near-me stations)
        self.station_labels = []
        self.analysis_labels = []
        
        for i in range(3):
            station_label = QLabel("")
            station_label.setStyleSheet("color: #cccccc; font-size: 11px; padding-left: 8px;")
            station_label.setWordWrap(True)
            layout.addWidget(station_label)
            self.station_labels.append(station_label)
            
            # Analysis result (hidden until Phase 2 runs)
            analysis_label = QLabel("")
            analysis_label.setStyleSheet("color: #aaaaaa; font-size: 10px; padding-left: 16px;")
            analysis_label.setWordWrap(True)
            analysis_label.hide()
            layout.addWidget(analysis_label)
            self.analysis_labels.append(analysis_label)
        
        # Insight/suggestion
        self.insight_label = QLabel("")
        self.insight_label.setStyleSheet("color: #88ccff; font-size: 11px;")
        self.insight_label.setWordWrap(True)
        layout.addWidget(self.insight_label)
        
        # Phase 2: Analyze button
        self.analyze_button = QPushButton("🔍 Analyze")
        self.analyze_button.setToolTip("Check if nearby stations are beaming or have power advantage")
        self.analyze_button.setStyleSheet("""
            QPushButton {
                background-color: #2a4a6a;
                color: #cccccc;
                border: 1px solid #3a5a7a;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3a5a8a;
            }
            QPushButton:disabled {
                background-color: #333333;
                color: #666666;
            }
        """)
        self.analyze_button.clicked.connect(self._on_analyze_clicked)
        self.analyze_button.hide()  # Hidden until we have stations
        layout.addWidget(self.analyze_button)
        
        # Analysis status label
        self.analysis_status = QLabel("")
        self.analysis_status.setStyleSheet("color: #888888; font-size: 10px;")
        self.analysis_status.hide()
        layout.addWidget(self.analysis_status)
    
    def _on_analyze_clicked(self):
        """Handle analyze button click."""
        if self._near_me_data and self._near_me_data.get('stations'):
            self._analysis_in_progress = True
            self.analyze_button.setEnabled(False)
            self.analyze_button.setText("Analyzing...")
            self.analysis_status.setText("Fetching data from PSK Reporter...")
            self.analysis_status.show()
            
            # Emit signal with stations to analyze
            self.analyze_requested.emit(self._near_me_data['stations'])
    
    def update_analysis_results(self, results: list):
        """
        Update display with Phase 2 analysis results.
        
        Args:
            results: List of analysis result dicts from analyzer.analyze_near_me_station()
        """
        self._analysis_in_progress = False
        self.analyze_button.setEnabled(True)
        self.analyze_button.setText("🔍 Analyze")
        self.analysis_status.hide()
        
        # Store results by callsign
        for result in results:
            call = result.get('call', '')
            if call:
                self._analysis_results[call] = result
        
        # Update the display for each station
        if not self._near_me_data:
            return
            
        stations = self._near_me_data.get('stations', [])
        
        for i, station in enumerate(stations[:3]):
            call = station.get('call', '')
            if call in self._analysis_results:
                result = self._analysis_results[call]
                insights = result.get('insights', [])
                
                if insights:
                    # Show the analysis insights
                    insight_text = "\n".join(insights)
                    self.analysis_labels[i].setText(insight_text)
                    self.analysis_labels[i].show()
                elif result.get('error'):
                    self.analysis_labels[i].setText(f"⚠️ {result['error']}")
                    self.analysis_labels[i].show()
    
    def update_display(self, near_me_data: Optional[Dict], path_status: 'PathStatus' = None,
                       my_snr: int = None, snr_reporter: str = None):
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
            my_snr: SNR (dB) reported for our signal, if available
            snr_reporter: Callsign of station that reported our SNR
        """
        self._near_me_data = near_me_data
        
        if not near_me_data or not near_me_data.get('my_grid'):
            self.status_label.setText("—")
            self.status_label.setStyleSheet("color: #888888;")
            self.source_label.setText("Configure your grid in Settings")
            for label in self.station_labels:
                label.setText("")
            for label in self.analysis_labels:
                label.setText("")
                label.hide()
            self.insight_label.setText("")
            self.analyze_button.hide()
            return
        
        stations = near_me_data.get('stations', [])
        target_uploading = near_me_data.get('target_uploading', False)
        proxy_count = near_me_data.get('proxy_count', 0)
        
        # Update source indicator - shows DATA QUALITY (where our info comes from)
        # This is separate from whether stations from your area are being heard
        if target_uploading:
            self.source_label.setText("✓ Target uploads to PSK Reporter")
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
            # Check if path column already has evidence we don't
            if path_status == PathStatus.CONNECTED:
                self.status_label.setText("Your signal confirmed!")
                self.status_label.setStyleSheet("color: #00ffff;")  # Cyan
                if my_snr is not None:
                    snr_str = f"{my_snr:+d}" if isinstance(my_snr, int) else str(my_snr)
                    self.insight_label.setText(f"💡 Target decoded you at {snr_str} dB — call now!")
                else:
                    self.insight_label.setText("💡 Target decoded you — call now!")
                # Override source label — evidence came from PSK Reporter "who heard me" data
                self.source_label.setText("✓ Confirmed via PSK Reporter")
                self.source_label.setStyleSheet("color: #00ffff; font-size: 10px;")
            elif path_status == PathStatus.PATH_OPEN:
                self.status_label.setText("Your signal reported nearby")
                self.status_label.setStyleSheet("color: #00ff00;")  # Green
                if my_snr is not None and snr_reporter:
                    snr_str = f"{my_snr:+d}" if isinstance(my_snr, int) else str(my_snr)
                    self.insight_label.setText(f"💡 Spotted at {snr_str} dB by {snr_reporter} — path open!")
                else:
                    self.insight_label.setText("💡 Path is open! Keep calling")
                # Override source label — evidence came from PSK Reporter "who heard me" data
                self.source_label.setText("✓ Spotted by receiver in target's region")
                self.source_label.setStyleSheet("color: #88ff88; font-size: 10px;")
            elif proxy_count > 0 or target_uploading:
                self.status_label.setText("None from your area")
                self.status_label.setStyleSheet("color: #ff6666;")  # Red
                self.insight_label.setText("💡 No path from your area currently")
            else:
                self.status_label.setText("None from your area")
                self.status_label.setStyleSheet("color: #ff6666;")  # Red
                self.insight_label.setText("💡 No data - target area not reporting")
            # Hide analyze button when no stations
            self.analyze_button.hide()
        elif count >= 1:
            # We have near-me stations getting through
            if count == 1:
                self.status_label.setText("1 from your area reported")
                self.status_label.setStyleSheet("color: #ffcc00;")  # Yellow - marginal
            else:
                self.status_label.setText(f"{count} from your area reported")
                self.status_label.setStyleSheet("color: #00ff00;")  # Green - good
            
            # Customize insight based on path status
            # Path column now says "Not Reported in Region" which is clearer alongside this data
            if path_status == PathStatus.CONNECTED:
                self.insight_label.setText("💡 Target hears you too!")
            elif path_status == PathStatus.PATH_OPEN:
                self.insight_label.setText("💡 Path confirmed - keep calling!")
            elif path_status == PathStatus.NO_PATH:
                # This is the key insight: others are getting through, you should too!
                self.insight_label.setText("💡 Others getting through — you can too!")
            else:
                self.insight_label.setText("💡 Path is open! Keep calling")
            
            # Show analyze button when we have stations to analyze
            self.analyze_button.show()
        
        # Clear station labels and analysis labels first
        for label in self.station_labels:
            label.setText("")
        for label in self.analysis_labels:
            label.setText("")
            label.hide()
        
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
            
            # Show cached analysis if we have it for this station
            if call in self._analysis_results:
                result = self._analysis_results[call]
                insights = result.get('insights', [])
                if insights:
                    self.analysis_labels[i].setText("\n".join(insights))
                    self.analysis_labels[i].show()
    
    def clear(self):
        """Clear the display."""
        self.status_label.setText("—")
        self.status_label.setStyleSheet("color: #888888;")
        self.source_label.setText("")
        for label in self.station_labels:
            label.setText("")
        for label in self.analysis_labels:
            label.setText("")
            label.hide()
        self.insight_label.setText("")
        self._near_me_data = None
        self._analysis_results.clear()
        self.analyze_button.hide()
        self.analysis_status.hide()


class BehaviorWidget(QGroupBox):
    """Display target's picking behavior."""
    
    def __init__(self, parent=None):
        super().__init__("Behavior", parent)
        self.setToolTip(
            "How this station picks callers.\n"
            "Based on your WSJT-X/JTDX log history and live session observation."
        )
        self._current_call = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # v2.2.0: Source badge (dynamic — changes based on prediction source)
        self.source_badge = QLabel("📋 Log History")
        self.source_badge.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.source_badge)
        
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
        
        # v2.2.0: Update source badge based on prediction source
        pattern: Optional[PickingPattern] = behavior_info.get('pattern')
        source = behavior_info.get('bayesian_source', 'default')
        
        if pattern:
            self.source_badge.setText("👁 Live Session")
            self.source_badge.setStyleSheet("color: #88ff88; font-size: 10px;")
        elif source == 'historical':
            self.source_badge.setText("📋 Log History")
            self.source_badge.setStyleSheet("color: #888888; font-size: 10px;")
        elif source == 'ml_model':
            metadata = behavior_info.get('bayesian_metadata') or {}
            if 'persona' in metadata:
                self.source_badge.setText("🧩 Persona Match")
            else:
                self.source_badge.setText("📋 Log History")
            self.source_badge.setStyleSheet("color: #888888; font-size: 10px;")
        elif source == 'bayesian' and behavior_info.get('qso_count', 0) > 0:
            self.source_badge.setText("👁 Live Session")
            self.source_badge.setStyleSheet("color: #88ff88; font-size: 10px;")
        else:
            self.source_badge.setText("⏳ Observing...")
            self.source_badge.setStyleSheet("color: #666666; font-size: 10px;")
        
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
        super().__init__("Opportunity Score", parent)
        self.setToolTip(
            "Opportunity score combining signal strength,\n"
            "path status, competition, and behavior analysis.\n"
            "Higher = better prospect. Not a statistical probability."
        )
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
        
        self.prob_label.setText(f"{prob_pct}")
        
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
        self.setToolTip(
            "Tactical suggestion based on all available intelligence.\n"
            "Advisory only — you make the call."
        )
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
            'call_blind': '▶ CALL (no intel)',
            'wait': '⏸ WAIT',
            'try_later': '⏭ TRY LATER',
        }
        self.action_label.setText(action_display.get(action, action.upper()))
        
        # Color by action
        if action == 'call_now':
            self.action_label.setStyleSheet("color: #00ff00;")
        elif action == 'call_blind':
            self.action_label.setStyleSheet("color: #88bbff;")  # Muted blue — go ahead, but unguided
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


class ForecastStrip(QWidget):
    """Painted horizontal bar showing 12-hour propagation forecast.
    
    Each cell represents one hour, colored by predicted SNR:
        Strong open (>= -10 dB): bright green
        Open (>= -21 dB): green  
        Marginal (-21 to -25 dB): yellow
        Closed (< -25 dB): dark red/gray
    
    Tick marks at every hour, number labels every 3 hours.
    """
    
    BAR_HEIGHT = 20
    LABEL_HEIGHT = 14
    TICK_HEIGHT = 4
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # list of {hour_utc, snr_db, ft8_status}
        self.setFixedHeight(self.BAR_HEIGHT + self.LABEL_HEIGHT + self.TICK_HEIGHT + 2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def set_data(self, forecast: list[dict]):
        """Set forecast data and repaint."""
        self._data = forecast or []
        self.update()
    
    def clear(self):
        self._data = []
        self.update()
    
    @staticmethod
    def _snr_to_color(snr_db: float) -> QColor:
        """Map SNR in dB to a display color."""
        if snr_db >= -10:
            return QColor(0, 220, 0)       # Bright green — strong
        elif snr_db >= -17:
            return QColor(0, 180, 0)       # Green — solid open
        elif snr_db >= -21:
            return QColor(80, 160, 0)      # Yellow-green — open but weaker
        elif snr_db >= -25:
            return QColor(200, 180, 0)     # Yellow — marginal
        elif snr_db >= -28:
            return QColor(180, 80, 0)      # Orange — below FT8 threshold
        else:
            return QColor(80, 30, 30)      # Dark red — closed
    
    def paintEvent(self, event):
        if not self._data:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        w = self.width()
        n = len(self._data)
        if n == 0:
            painter.end()
            return
        
        cell_w = w / n
        bar_top = 0
        tick_top = bar_top + self.BAR_HEIGHT
        label_top = tick_top + self.TICK_HEIGHT + 1
        
        # Draw colored cells
        for i, entry in enumerate(self._data):
            x = int(i * cell_w)
            x_next = int((i + 1) * cell_w)
            color = self._snr_to_color(entry.get('snr_db', -40))
            painter.fillRect(x, bar_top, x_next - x, self.BAR_HEIGHT, color)
        
        # Draw cell borders (subtle)
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        for i in range(1, n):
            x = int(i * cell_w)
            painter.drawLine(x, bar_top, x, bar_top + self.BAR_HEIGHT)
        
        # "Now" marker — left edge highlight
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawLine(0, bar_top, 0, bar_top + self.BAR_HEIGHT)
        
        # Tick marks and hour labels
        painter.setPen(QPen(QColor(170, 170, 170), 1))
        label_font = painter.font()
        label_font.setPointSize(7)
        painter.setFont(label_font)
        
        for i, entry in enumerate(self._data):
            x = int(i * cell_w + cell_w / 2)  # Center of cell
            hour = int(entry.get('hour_utc', 0))
            
            # Tick mark at every hour
            tick_len = 3
            painter.setPen(QPen(QColor(120, 120, 120), 1))
            painter.drawLine(int(i * cell_w), tick_top,
                           int(i * cell_w), tick_top + tick_len)
            
            # Number label every 3 hours
            if hour % 3 == 0:
                painter.setPen(QPen(QColor(170, 170, 170), 1))
                # Taller tick for labeled hours
                painter.drawLine(int(i * cell_w), tick_top,
                               int(i * cell_w), tick_top + tick_len + 2)
                label = f"{hour:02d}"
                text_x = int(i * cell_w) + 2
                painter.drawText(text_x, label_top + 10, label)
        
        painter.end()


class PropagationWidget(QGroupBox):
    """Display IONIS propagation prediction for current target path.
    
    Shows:
    - Current prediction (band, path, status, SNR)
    - 12-hour forecast strip (painted color bar)
    - vs-reality comparison (IONIS prediction vs PSK Reporter data)
    - Current conditions (SFI, Kp)
    
    v2.4.0: IONIS integration — propagation model by Greg Beam (KI7MT)
    """
    
    # vs-reality display strings and colors
    VS_REALITY_DISPLAY = {
        'confirmed':          ('✓ Confirmed by spots',      '#00dd00'),
        'unconfirmed':        ('⚠ Predicted open, no spots', '#dddd00'),
        'better_than_expected': ('★ Better than expected',   '#00dddd'),
        'closed':             ('— Closed',                   '#666666'),
        'unexpected_opening': ('★ Unexpected opening!',      '#00ffff'),
        'unknown':            ('',                            '#888888'),
    }
    
    def __init__(self, parent=None):
        super().__init__("Path Prediction (IONIS)", parent)
        self.setToolTip(
            "HF path prediction from the IONIS V22-gamma model.\n"
            "Predicts whether FT8 signals can travel from your\n"
            "station to the selected target, using current SFI,\n"
            "Kp, and sun position.\n\n"
            "Forecast assumes current conditions hold.\n"
            "Model by Greg Beam, KI7MT — ionis-ai.com"
        )
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        
        # Main prediction line: "20m FN42 → JN48:  OPEN  (-12.1 dB)"
        self.prediction_label = QLabel("—")
        self.prediction_label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        layout.addWidget(self.prediction_label)
        
        # Solar/path context: "TX ☀ +38°  RX ☀ +36°   5,981 km"
        self.context_label = QLabel("")
        self.context_label.setStyleSheet("color: #999999; font-size: 10px;")
        layout.addWidget(self.context_label)
        
        # Forecast strip
        self.forecast_strip = ForecastStrip()
        layout.addWidget(self.forecast_strip)
        
        # vs-reality indicator
        self.vs_reality_label = QLabel("")
        self.vs_reality_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.vs_reality_label)
        
        # Conditions line
        self.conditions_label = QLabel("")
        self.conditions_label.setStyleSheet("color: #888888; font-size: 9px;")
        layout.addWidget(self.conditions_label)
    
    def update_display(self, prediction: dict = None,
                       forecast: list = None,
                       vs_reality: str = None):
        """Update with IONIS prediction results.
        
        Args:
            prediction: Single prediction dict from IonisEngine.predict()
            forecast: List of prediction dicts from IonisEngine.predict_range()
            vs_reality: One of: confirmed, unconfirmed, better_than_expected,
                        closed, unexpected_opening, unknown
        """
        if not prediction:
            self.clear()
            return
        
        band = prediction.get('band', '?')
        status = prediction.get('ft8_status', '?')
        snr_db = prediction.get('snr_db', 0)
        tx_solar = prediction.get('tx_solar_deg', 0)
        rx_solar = prediction.get('rx_solar_deg', 0)
        distance = prediction.get('distance_km', 0)
        tx_grid = prediction.get('tx_grid', '')
        rx_grid = prediction.get('rx_grid', '')
        
        # Main prediction line
        status_colors = {
            'STRONG': '#00ff00',
            'OPEN': '#00dd00',
            'MARGINAL': '#dddd00',
            'CLOSED': '#ff4444',
        }
        color = status_colors.get(status, '#ffffff')
        path_str = f"{tx_grid}→{rx_grid} " if tx_grid and rx_grid else ""
        self.prediction_label.setText(
            f"{band} {path_str}{status}"
        )
        self.prediction_label.setStyleSheet(f"color: {color};")
        
        # Context line
        tx_icon = "☀" if tx_solar > 0 else "☽"
        rx_icon = "☀" if rx_solar > 0 else "☽"
        self.context_label.setText(
            f"TX {tx_icon} {tx_solar:+.0f}°   "
            f"RX {rx_icon} {rx_solar:+.0f}°   "
            f"{distance:,.0f} km"
        )
        
        # Forecast strip
        if forecast:
            self.forecast_strip.set_data(forecast)
        else:
            self.forecast_strip.clear()
        
        # vs-reality
        if vs_reality and vs_reality in self.VS_REALITY_DISPLAY:
            text, vs_color = self.VS_REALITY_DISPLAY[vs_reality]
            self.vs_reality_label.setText(text)
            self.vs_reality_label.setStyleSheet(
                f"color: {vs_color}; font-size: 10px;"
            )
        else:
            self.vs_reality_label.setText("")
        
        # Conditions (set separately via set_conditions)
    
    def set_conditions(self, sfi: int, kp: int):
        """Update the conditions display line."""
        self.conditions_label.setText(f"SFI {sfi} · Kp {kp}")
    
    def clear(self):
        """Clear all displays."""
        self.prediction_label.setText("—")
        self.prediction_label.setStyleSheet("")
        self.context_label.setText("")
        self.forecast_strip.clear()
        self.vs_reality_label.setText("")
        self.conditions_label.setText("")


class InsightsPanel(QWidget):
    """
    Main insights panel combining all local intelligence displays.
    
    Designed to be docked in the main window or shown as a floating panel.
    """
    
    # Signal when user wants to retrain models
    retrain_requested = pyqtSignal()
    
    # v2.0.6: Signal when user wants to sync target to JTDX
    sync_requested = pyqtSignal()
    # v2.1.3: Status bar messages (e.g., clipboard feedback)
    status_message = pyqtSignal(str)
    
    # v2.1.0: Signal when user wants Phase 2 path analysis (emits stations list)
    path_analyze_requested = pyqtSignal(list)
    
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
        self._my_snr_at_target = None  # v2.3.0: SNR reported for our signal at target
        self._my_snr_reporter = None   # v2.3.0: Who reported our SNR
        self._target_competition: str = ""  # v2.2.0: target-side competition from PSK Reporter
        self._near_me_count: int = 0  # v2.1.5: near-me stations for effective path status
    
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
        
        # Target header with click-to-copy and Fetch button (v2.0.6, v2.1.3)
        target_header = QHBoxLayout()
        target_header.setSpacing(4)
        
        # v2.1.3: Target label is clickable — copies callsign to clipboard
        self.target_label = QPushButton("Target: —")
        self.target_label.setFont(QFont("Consolas", 12, QFont.Weight.Bold))
        self.target_label.setStyleSheet("""
            QPushButton {
                color: #ffffff;
                background-color: #333333;
                padding: 4px;
                border-radius: 3px;
                border: 1px solid #444;
                text-align: center;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                color: #FF66FF;
            }
        """)
        self.target_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target_label.setToolTip("Click to copy callsign to clipboard")
        self.target_label.clicked.connect(self._copy_target_to_clipboard)
        target_header.addWidget(self.target_label, stretch=1)
        
        # v2.0.6: Fetch button — pulls target from WSJT-X/JTDX into QSOP
        self.sync_button = QPushButton("⟳")
        self.sync_button.setToolTip("Fetch target from WSJT-X/JTDX (Ctrl+Y)")
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
        self.near_me_widget.analyze_requested.connect(self._on_path_analyze_requested)
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
        
        # v2.4.0: Propagation forecast (IONIS)
        self.propagation_widget = PropagationWidget()
        self.propagation_widget.hide()  # Hidden until IONIS is enabled and target selected
        layout.addWidget(self.propagation_widget)
        
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
    
    def _copy_target_to_clipboard(self):
        """v2.1.3: Copy current target callsign to clipboard."""
        if self._current_target:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._current_target)
            # Brief visual feedback
            original_text = self.target_label.text()
            self.target_label.setText("✓ Copied!")
            self.status_message.emit(f"Copied to clipboard: {self._current_target}")
            QTimer.singleShot(1000, lambda: self.target_label.setText(original_text))
    
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
    
    def set_path_status(self, status: PathStatus, my_snr: int = None, reporter: str = None):
        """Update path status (from main app's perspective).
        
        Args:
            status: Current path status enum
            my_snr: SNR reported for our signal (dB), if available
            reporter: Callsign of station that reported us
        """
        self._path_status = status
        self._my_snr_at_target = my_snr
        self._my_snr_reporter = reporter
        self.refresh()
    
    def set_target_competition(self, competition_str: str):
        """v2.2.0: Update target-side competition from PSK Reporter data.
        
        This bridges the gap between the analyzer (PSK Reporter intelligence)
        and the Insights panel (local decode intelligence). Without this,
        the Insights panel has no idea about competition at the target's end.
        
        Data flow: analyzer → main_v2 refresh_target_perspective → here → pileup_widget + strategy
        """
        self._target_competition = competition_str
        # Forward to pileup widget for contrast alert display
        self.pileup_widget.set_target_competition(competition_str)
    
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
                # v2.2.0: Use target-side competition if available (from PSK Reporter)
                # This is more accurate than local pileup since it shows what the TARGET sees
                # v2.2.1: If competition data is from local decodes (suffix "local"),
                # it's the same source as local_competition — don't double-count
                local_competition = pileup_info.get('size', 0) if pileup_info else 0
                is_local_source = 'local' in self._target_competition.lower() if self._target_competition else False
                target_competition_count = 0 if is_local_source else self._parse_competition_count(self._target_competition)
                effective_competition = max(local_competition, target_competition_count)
                
                # Build basic features
                features = {
                    'target_snr': -10,  # Would come from actual data
                    'your_snr': -10,
                    'band_encoded': 5,
                    'hour_utc': 12,
                    'competition': effective_competition,
                    'region_encoded': 0,
                    'calls_made': your_status.get('calls_made', 0),
                }
                
                # v2.1.5: Compute effective path status
                # If path column says NO_PATH but near-me stations from our area
                # ARE getting through, the path is open — we just aren't confirmed yet.
                # This resolves the contradiction between Path Intelligence showing
                # "Others getting through" and Recommendation saying "TRY LATER".
                effective_path = self._path_status
                if self._path_status == PathStatus.NO_PATH and self._near_me_count > 0:
                    effective_path = PathStatus.PATH_OPEN
                
                prediction = self.predictor.predict_success(
                    self._current_target, 
                    features,
                    effective_path
                )
                self.prediction_widget.update_display(prediction)
                
                strategy = self.predictor.get_strategy(
                    self._current_target, effective_path,
                    target_competition=self._target_competition
                )
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
    
    @staticmethod
    def _parse_competition_count(competition_str: str) -> int:
        """Extract numeric count from competition string like 'High (5)'."""
        if not competition_str or competition_str == '--':
            return 0
        try:
            if '(' in competition_str:
                return int(competition_str.split('(')[1].split(')')[0])
        except (ValueError, IndexError):
            pass
        return 0
    
    def clear(self):
        """Clear all displays."""
        self._current_target = None
        self._near_me_count = 0  # v2.1.5
        self.target_label.setText("Target: —")
        self.pileup_widget.clear()
        self.near_me_widget.clear()  # v2.1.0: Path Intelligence
        self.behavior_widget.clear()
        self.prediction_widget.clear()
        self.strategy_widget.clear()
        self.propagation_widget.clear()
    
    def update_near_me(self, near_me_data: Optional[Dict]):
        """
        Update Path Intelligence display with near-me station data.
        
        v2.1.0: Phase 1 of Path Intelligence.
        
        Args:
            near_me_data: Dict from analyzer.find_near_me_stations()
        """
        # v2.1.5: Store near-me count for effective path status calculation
        self._near_me_count = len(near_me_data.get('stations', [])) if near_me_data else 0
        
        # Pass current path status so widget can give context-aware insights
        self.near_me_widget.update_display(
            near_me_data, self._path_status,
            my_snr=self._my_snr_at_target, snr_reporter=self._my_snr_reporter
        )
    
    def _on_path_analyze_requested(self, stations: list):
        """
        Handle Phase 2 analysis request from NearMeWidget.
        
        v2.1.0: Forward to main window for processing.
        
        Args:
            stations: List of station dicts to analyze
        """
        # Forward the request up to main_v2.py
        self.path_analyze_requested.emit(stations)
    
    def update_path_analysis_results(self, results: list):
        """
        Update Path Intelligence display with Phase 2 analysis results.
        
        v2.1.0: Phase 2 of Path Intelligence.
        
        Args:
            results: List of analysis result dicts from analyzer.analyze_near_me_station()
        """
        self.near_me_widget.update_analysis_results(results)
    
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
