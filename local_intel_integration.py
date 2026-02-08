"""
Local Intelligence Integration for QSO Predictor v2.0

Provides a clean interface to integrate local intelligence
features into the existing main application.

Copyright (C) 2025 Peter Hirst (WU2C)

v2.0.6 Changes:
- Added: Connect insights panel sync button to main window

v2.0.3 Changes:
- Fixed: set_target now handles None/empty callsign gracefully
- Added: Defensive checks throughout to prevent NoneType errors
"""

import logging
from typing import Optional, Callable
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtWidgets import QDockWidget, QMenu, QMessageBox

from local_intel import (
    SessionTracker, 
    ModelManager,
    BayesianPredictor,
    HeuristicPredictor,
    LogFileDiscovery,
    AnalysisConfig,
    PathStatus,
    Decode,
    BackgroundScanner,
)
from local_intel.log_parser import MessageParser
from training_manager import TrainingManager, TrainingStatusChecker
from insights_panel import InsightsPanel
from training_dialog import TrainingDialog

logger = logging.getLogger(__name__)


class LocalIntelligence(QObject):
    """
    Main integration class for Local Intelligence features.
    
    Manages all local intelligence components and provides
    a simple interface for the main application.
    
    Usage:
        # In main window __init__:
        self.local_intel = LocalIntelligence(my_callsign="W1ABC")
        self.local_intel.setup(self)  # Pass main window
        
        # When target changes:
        self.local_intel.set_target("JA1XYZ", "PM95")
        
        # When decode received (from UDP):
        self.local_intel.process_decode(decode_data)
        
        # When path status changes:
        self.local_intel.set_path_status(PathStatus.CONNECTED)
    """
    
    # Signals
    prediction_updated = pyqtSignal(dict)  # New prediction available
    strategy_updated = pyqtSignal(dict)    # New strategy recommendation
    models_stale = pyqtSignal(list)        # Models need retraining
    
    def __init__(self, 
                 my_callsign: str,
                 config: AnalysisConfig = None,
                 parent=None):
        """
        Initialize Local Intelligence.
        
        Args:
            my_callsign: User's callsign
            config: Analysis configuration (uses defaults if None)
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self.my_callsign = my_callsign.upper()
        self.config = config or AnalysisConfig()
        
        # Core components (model_manager first, needed by session_tracker)
        self.model_manager = ModelManager()
        self.session_tracker = SessionTracker(
            self.my_callsign, 
            self.config,
            model_manager=self.model_manager
        )
        self.log_discovery = LogFileDiscovery()
        
        # Predictors
        self.predictor: Optional[BayesianPredictor] = None
        self.heuristic_predictor = HeuristicPredictor(self.session_tracker)
        
        # Training
        self.training_manager = TrainingManager(
            self.my_callsign, 
            self.model_manager,
            parent=self
        )
        self.status_checker: Optional[TrainingStatusChecker] = None
        
        # Background scanner (created in setup())
        self.background_scanner: Optional[BackgroundScanner] = None
        
        # UI components (created in setup())
        self.insights_panel: Optional[InsightsPanel] = None
        self.insights_dock: Optional[QDockWidget] = None
        self._toggle_action = None  # Menu action for show/hide
        
        # State
        self._enabled = True
        self._purist_mode = False  # True = no PSK Reporter, local only
        self._current_target: Optional[str] = None
        
        # Connect internal signals
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect internal signal handlers."""
        # Session tracker callbacks
        self.session_tracker.on_pileup_update(self._on_pileup_update)
        self.session_tracker.on_answer_detected(self._on_answer_detected)
        self.session_tracker.on_pattern_detected(self._on_pattern_detected)
        
        # Training manager signals
        self.training_manager.training_finished.connect(self._on_training_finished)
    
    def setup(self, main_window) -> bool:
        """
        Set up local intelligence in the main window.
        
        Args:
            main_window: The main application window
            
        Returns:
            True if setup successful
        """
        try:
            # Load ML models
            self.model_manager.load_models()
            
            # Create predictor (Bayesian if models available, otherwise heuristic)
            if self.model_manager.has_model('success_model'):
                self.predictor = BayesianPredictor(
                    self.model_manager, 
                    self.session_tracker
                )
                logger.info("Using Bayesian predictor with trained models")
            else:
                self.predictor = None
                # User-friendly message based on build type
                import sys
                if getattr(sys, 'frozen', False):
                    logger.info("Using heuristic predictor (ML training not available in standalone build)")
                else:
                    logger.info("No trained models - using heuristic predictor")
            
            # Create insights panel
            self.insights_panel = InsightsPanel(
                session_tracker=self.session_tracker,
                predictor=self.predictor or self.heuristic_predictor,
                parent=main_window
            )
            self.insights_panel.retrain_requested.connect(self.show_training_dialog)
            
            # v2.0.6: Connect sync button to main window's sync method
            if hasattr(main_window, 'sync_to_jtdx'):
                self.insights_panel.sync_requested.connect(main_window.sync_to_jtdx)
            
            # v2.1.3: Connect clipboard feedback to status bar
            if hasattr(main_window, 'update_status_msg'):
                self.insights_panel.status_message.connect(main_window.update_status_msg)
            
            # Create dock widget
            self.insights_dock = QDockWidget("Local Intelligence", main_window)
            self.insights_dock.setObjectName("local_intel_dock")  # Required for saveState
            self.insights_dock.setWidget(self.insights_panel)
            self.insights_dock.setAllowedAreas(
                Qt.DockWidgetArea.LeftDockWidgetArea | 
                Qt.DockWidgetArea.RightDockWidgetArea |
                Qt.DockWidgetArea.TopDockWidgetArea |
                Qt.DockWidgetArea.BottomDockWidgetArea
            )
            
            # Enable floating/undocking
            self.insights_dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetMovable |
                QDockWidget.DockWidgetFeature.DockWidgetFloatable |
                QDockWidget.DockWidgetFeature.DockWidgetClosable
            )
            
            # Add to main window (right side by default)
            main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.insights_dock)
            
            # Update model status display
            self._update_model_status()
            
            # Start status checker
            self.status_checker = TrainingStatusChecker(
                self.training_manager,
                check_interval_hours=24,
                parent=self
            )
            self.status_checker.models_stale.connect(self._on_models_stale)
            self.status_checker.start()
            
            # Start background scanner for incremental log processing
            behavior_predictor = self.session_tracker._behavior_predictor
            self.background_scanner = BackgroundScanner(behavior_predictor, parent=self)
            self.background_scanner.scan_complete.connect(self._on_background_scan_complete)
            self.background_scanner.start()
            logger.info("Background scanner started")
            
            # Start panel updates
            self.insights_panel.start_updates(interval_ms=1000)
            
            logger.info("Local Intelligence setup complete")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to setup Local Intelligence: {e}")
            return False
    
    def add_menu_items(self, menu: QMenu):
        """
        Add Local Intelligence menu items.
        
        Args:
            menu: Menu to add items to (e.g., Tools menu)
        """
        menu.addSeparator()
        
        # Toggle panel
        toggle_action = menu.addAction("Show Local Intelligence Panel")
        toggle_action.setCheckable(True)
        toggle_action.setChecked(True)
        toggle_action.triggered.connect(self._toggle_panel)
        self._toggle_action = toggle_action  # Store reference
        
        # Sync menu when dock closed via X button
        if self.insights_dock:
            self.insights_dock.visibilityChanged.connect(
                lambda visible: toggle_action.setChecked(visible)
            )
        
        # Training dialog - label differs for exe vs source
        import sys
        if getattr(sys, 'frozen', False):
            train_action = menu.addAction("Bootstrap Behavior...")
        else:
            train_action = menu.addAction("Train Models...")
        train_action.triggered.connect(self.show_training_dialog)
        
        # Purist mode
        purist_action = menu.addAction("Purist Mode (Local Only)")
        purist_action.setCheckable(True)
        purist_action.setChecked(self._purist_mode)
        purist_action.triggered.connect(self._toggle_purist_mode)
        purist_action.setToolTip("Disable PSK Reporter, use only local data")
    
    def set_target(self, callsign: str, grid: str = None):
        """
        Set the current target station.
        
        Call this when user selects a new DX target.
        
        Args:
            callsign: Target callsign (empty string or None to clear)
            grid: Target grid square (if known)
        """
        # Guard against re-entrant calls (can happen with processEvents)
        if hasattr(self, '_setting_target') and self._setting_target:
            return
        
        self._setting_target = True
        try:
            # v2.0.3: Handle None/empty string to clear target
            if not callsign:
                self._current_target = None
                
                # v2.0.3: Clear session tracker state WITHOUT triggering slow lookup
                if hasattr(self.session_tracker, 'clear_target'):
                    self.session_tracker.clear_target()
                else:
                    # Fallback: clear internal state directly
                    self.session_tracker._current_target = None
                    if hasattr(self.session_tracker, '_target_session'):
                        self.session_tracker._target_session = None
                
                # Clear insights panel
                if self.insights_panel:
                    self.insights_panel.clear()
                
                return
            
            if not self._enabled:
                return
            
            self._current_target = callsign.upper()
            
            # Show loading state immediately (before slow lookup)
            if self.insights_panel:
                self.insights_panel.show_loading(callsign)
            
            # This does the slow lookup
            self.session_tracker.set_target(callsign, grid or "")
            
            # Now update with results
            if self.insights_panel:
                self.insights_panel.set_target(callsign, grid)
            
            logger.debug(f"Target set: {callsign}")
        finally:
            self._setting_target = False
    
    def set_path_status(self, status: PathStatus):
        """
        Update the path status to current target.
        
        Call this when path column changes in main app.
        
        Args:
            status: Current path status
        """
        if not self._enabled:
            return
        
        if self.insights_panel:
            self.insights_panel.set_path_status(status)
    
    def update_near_me(self, near_me_data: dict):
        """
        Update Path Intelligence display with near-me station data.
        
        v2.1.0: Phase 1 of Path Intelligence feature.
        
        Args:
            near_me_data: Dict from analyzer.find_near_me_stations() containing:
                - stations: List of stations near user being heard by target
                - target_uploading: Whether target directly reports to PSK Reporter
                - proxy_count: Number of proxy stations used
                - my_grid: User's grid
        """
        if not self._enabled:
            return
        
        if self.insights_panel:
            self.insights_panel.update_near_me(near_me_data)
    
    def set_tx_status(self, enabled: bool, calling: str = ""):
        """
        Update TX status from JTDX/WSJT-X.
        
        Call this when transmitting status changes.
        
        Args:
            enabled: True if TX is enabled/transmitting
            calling: Callsign we're calling (empty if CQing)
        """
        if not self._enabled:
            return
        
        self.session_tracker.set_tx_status(enabled, calling=calling)
    
    def process_decode(self, decode_data: dict):
        """
        Process a decode from UDP stream.
        
        Call this for each decode received from WSJT-X/JTDX.
        
        Args:
            decode_data: Dict with decode fields:
                - callsign: Transmitting station
                - snr: Signal strength
                - frequency: Audio offset Hz
                - message: Raw message text
                - dt: Time delta
                - mode: FT8/FT4/etc
        """
        if not self._enabled:
            return
        
        try:
            # Convert to Decode object
            from datetime import datetime
            
            decode = Decode(
                timestamp=datetime.now(),
                snr=decode_data.get('snr', 0),
                dt=decode_data.get('dt', 0.0),
                frequency=decode_data.get('frequency', 0),
                mode=decode_data.get('mode', 'FT8'),
                message=decode_data.get('message', ''),
                callsign=decode_data.get('callsign'),
                source='udp'
            )
            
            # Parse message for additional info
            if decode.message:
                parsed = MessageParser.parse(decode.message)
                decode.callsign = parsed.caller
                decode.grid = parsed.grid
                decode.is_cq = parsed.is_cq
                decode.is_reply = parsed.is_reply
                decode.replying_to = parsed.callee
            
            # Process in session tracker
            self.session_tracker.process_decode(decode)
            
        except Exception as e:
            logger.debug(f"Failed to process decode: {e}")
    
    def process_decode_batch(self, decodes: list):
        """
        Process multiple decodes at once.
        
        Args:
            decodes: List of decode dicts
        """
        for decode_data in decodes:
            self.process_decode(decode_data)
    
    def get_prediction(self) -> Optional[dict]:
        """
        Get current success prediction for target.
        
        Returns:
            Dict with prediction info, or None
        """
        if not self._current_target:
            return None
        
        predictor = self.predictor or self.heuristic_predictor
        if not predictor:
            return None
        
        try:
            # Build features from current state
            pileup = self.session_tracker.get_pileup_info()
            your_status = self.session_tracker.get_your_status()
            
            features = {
                'target_snr': -10,  # Would come from actual decode
                'your_snr': -10,
                'band_encoded': 5,
                'hour_utc': 12,
                'competition': pileup.get('size', 0) if pileup else 0,
                'region_encoded': 0,
                'calls_made': your_status.get('calls_made', 0),
            }
            
            prediction = predictor.predict_success(
                self._current_target,
                features,
                PathStatus.UNKNOWN
            )
            
            return {
                'probability': prediction.probability,
                'confidence': prediction.confidence,
                'explanation': prediction.explanation,
            }
        except Exception as e:
            logger.debug(f"Prediction failed: {e}")
            return None
    
    def get_strategy(self) -> Optional[dict]:
        """
        Get current strategy recommendation.
        
        Returns:
            Dict with strategy info, or None
        """
        if not self._current_target:
            return None
        
        predictor = self.predictor or self.heuristic_predictor
        if not predictor or not hasattr(predictor, 'get_strategy'):
            return None
        
        try:
            strategy = predictor.get_strategy(self._current_target)
            
            return {
                'action': strategy.recommended_action,
                'frequency': strategy.recommended_frequency,
                'reasons': strategy.reasons,
            }
        except Exception as e:
            logger.debug(f"Strategy failed: {e}")
            return None
    
    def show_training_dialog(self):
        """Show the training dialog."""
        if hasattr(self, '_main_window'):
            parent = self._main_window
        else:
            parent = None
        
        dialog = TrainingDialog(self.training_manager, parent)
        dialog.exec()
        
        # Refresh model status after dialog closes
        self._update_model_status()
        
        # Reload behavior history in case bootstrap was run
        self.session_tracker.reload_behavior_history()
    
    def clear_session(self):
        """Clear current session data."""
        self.session_tracker.clear_session()
        if self.insights_panel:
            self.insights_panel.clear()
    
    def shutdown(self):
        """Clean shutdown of local intelligence."""
        if self.background_scanner:
            logger.info("Stopping background scanner...")
            self.background_scanner.stop()
            self.background_scanner.wait(5000)  # Wait up to 5 seconds
            logger.info("Background scanner stopped")
        
        if self.status_checker:
            self.status_checker.stop()
        
        if self.insights_panel:
            self.insights_panel.stop_updates()
        
        if self.training_manager.is_training:
            self.training_manager.cancel_training()
        
        logger.info("Local Intelligence shutdown complete")
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @is_enabled.setter
    def is_enabled(self, value: bool):
        self._enabled = value
        if self.insights_dock:
            self.insights_dock.setVisible(value)
    
    @property
    def purist_mode(self) -> bool:
        return self._purist_mode
    
    @purist_mode.setter
    def purist_mode(self, value: bool):
        self._purist_mode = value
        logger.info(f"Purist mode: {'enabled' if value else 'disabled'}")
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _toggle_panel(self, checked: bool):
        """Toggle insights panel visibility."""
        if self.insights_dock:
            self.insights_dock.setVisible(checked)
    
    def _toggle_purist_mode(self, checked: bool):
        """Toggle purist mode."""
        self.purist_mode = checked
    
    def _update_model_status(self):
        """Update model status in insights panel."""
        import sys
        
        # Skip ML model status in frozen exe - users can only use Bootstrap
        if getattr(sys, 'frozen', False):
            if self.insights_panel:
                self.insights_panel.show_model_status("", False)  # Hide status
            return
        
        if not self.insights_panel:
            return
        
        # Force reload to pick up newly trained models
        self.model_manager.reload_models()
        status = self.model_manager.get_model_status()
        
        ready = sum(1 for s in status if s['exists'] and not s['is_stale'])
        stale = sum(1 for s in status if s['exists'] and s['is_stale'])
        missing = sum(1 for s in status if not s['exists'])
        
        if missing > 0:
            text = f"Models: {missing} not trained"
            is_stale = True
        elif stale > 0:
            text = f"Models: {stale} need retraining"
            is_stale = True
        elif ready > 0:
            text = f"Models: {ready} ready"
            is_stale = False
        else:
            text = "Models: None available"
            is_stale = True
        
        self.insights_panel.show_model_status(text, is_stale)
    
    def _on_pileup_update(self, session):
        """Handle pileup update from session tracker."""
        # Panel updates automatically via timer
        pass
    
    def _on_answer_detected(self, answered_call):
        """Handle target answering someone."""
        logger.debug(f"Target answered: {answered_call.callsign}")
    
    def _on_pattern_detected(self, pattern):
        """Handle picking pattern detection."""
        logger.info(f"Pattern detected: {pattern.style.value} "
                   f"(confidence: {pattern.confidence:.0%})")
    
    def _on_training_finished(self, success: bool, message: str):
        """Handle training completion."""
        if success:
            # Reload models
            self.model_manager.load_models(force=True)
            
            # Switch to Bayesian predictor if now available
            if self.model_manager.has_model('success_model'):
                self.predictor = BayesianPredictor(
                    self.model_manager,
                    self.session_tracker
                )
                if self.insights_panel:
                    self.insights_panel.set_predictor(self.predictor)
                logger.info("Switched to Bayesian predictor")
        
        self._update_model_status()
    
    def _on_background_scan_complete(self, stations_updated: int):
        """Handle background scan completion."""
        if stations_updated > 0:
            logger.info(f"Background scan: {stations_updated} stations updated")
            # Refresh insights panel if we have a target
            if self._current_target and self.insights_panel:
                self.insights_panel.refresh()
    
    def _on_models_stale(self, stale_models: list):
        """Handle stale models notification."""
        self.models_stale.emit(stale_models)
        self._update_model_status()
