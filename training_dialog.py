"""
Training Dialog for QSO Predictor v2.0

Modal dialog showing ML training progress.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QTextEdit, QGroupBox,
    QCheckBox, QFrame, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

from training_manager import TrainingManager

logger = logging.getLogger(__name__)


class TrainingDialog(QDialog):
    """
    Dialog for managing and monitoring ML training.
    
    Shows:
    - Available log files
    - Models to train
    - Training progress
    - Results/metrics
    """
    
    def __init__(self, 
                 training_manager: TrainingManager,
                 parent=None):
        """
        Initialize training dialog.
        
        Args:
            training_manager: TrainingManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.training_manager = training_manager
        self._connect_signals()
        
        self.setWindowTitle("Train ML Models")
        self.setMinimumSize(500, 600)
        
        self._setup_ui()
        self._load_initial_data()
    
    def _connect_signals(self):
        """Connect training manager signals."""
        self.training_manager.progress_updated.connect(self._on_progress)
        self.training_manager.model_complete.connect(self._on_model_complete)
        self.training_manager.stats_calculated.connect(self._on_stats)
        self.training_manager.training_finished.connect(self._on_finished)
        self.training_manager.training_error.connect(self._on_error)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Log files section
        files_group = QGroupBox("Log Files")
        files_layout = QVBoxLayout(files_group)
        
        self.files_label = QLabel("Discovering log files...")
        files_layout.addWidget(self.files_label)
        
        layout.addWidget(files_group)
        
        # Models section
        models_group = QGroupBox("Models to Train")
        models_layout = QVBoxLayout(models_group)
        
        self.success_check = QCheckBox("Success Predictor")
        self.success_check.setChecked(True)
        self.success_check.setToolTip("Predict probability of QSO success")
        models_layout.addWidget(self.success_check)
        
        self.behavior_check = QCheckBox("Target Behavior")
        self.behavior_check.setChecked(True)
        self.behavior_check.setToolTip("Classify target picking patterns")
        models_layout.addWidget(self.behavior_check)
        
        self.frequency_check = QCheckBox("Frequency Recommender")
        self.frequency_check.setChecked(True)
        self.frequency_check.setToolTip("Learn optimal TX frequency based on your history")
        models_layout.addWidget(self.frequency_check)
        
        layout.addWidget(models_group)
        
        # Progress section
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.stage_label = QLabel("Ready to train")
        progress_layout.addWidget(self.stage_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888888;")
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(progress_group)
        
        # Results section
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        self.results_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        results_layout.addWidget(self.results_text)
        
        layout.addWidget(results_group)
        
        # Stats section (shown after training)
        self.stats_group = QGroupBox("Your Statistics")
        stats_layout = QVBoxLayout(self.stats_group)
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMaximumHeight(120)
        self.stats_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a2a1a;
                color: #88ff88;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        stats_layout.addWidget(self.stats_text)
        
        self.stats_group.hide()  # Hidden until stats available
        layout.addWidget(self.stats_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.train_button = QPushButton("Start Training")
        self.train_button.clicked.connect(self._start_training)
        button_layout.addWidget(self.train_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel_training)
        self.cancel_button.setEnabled(False)
        button_layout.addWidget(self.cancel_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
    
    def _load_initial_data(self):
        """Load log file and model info."""
        # Discover log files
        files = self.training_manager.discover_log_files()
        
        if files:
            file_text = []
            total_lines = 0
            for f in files:
                from pathlib import Path
                filename = Path(f['path']).name
                file_text.append(f"• {f['program']}: {filename}")
                total_lines += f.get('line_count', 0)
            
            file_text.append(f"\nTotal: {len(files)} files, {total_lines:,} lines")
            self.files_label.setText("\n".join(file_text))
        else:
            self.files_label.setText("No log files found.\n\nCheck that WSJT-X or JTDX is installed.")
            self.train_button.setEnabled(False)
        
        # Check model status
        model_status = self.training_manager.get_model_status()
        
        for status in model_status:
            if status['name'] == 'success_model':
                if status['exists']:
                    age = status['age_days']
                    self.success_check.setText(
                        f"Success Predictor (trained {age} days ago)"
                    )
                else:
                    self.success_check.setText("Success Predictor (not trained)")
            
            elif status['name'] == 'target_behavior':
                if status['exists']:
                    self.behavior_check.setText("Target Behavior (trained)")
                else:
                    self.behavior_check.setText("Target Behavior (not trained)")
            
            elif status['name'] == 'frequency_model':
                if status['exists']:
                    age = status['age_days']
                    self.frequency_check.setText(
                        f"Frequency Recommender (trained {age} days ago)"
                    )
                else:
                    self.frequency_check.setText("Frequency Recommender (not trained)")
    
    def _start_training(self):
        """Start the training process."""
        # Get selected models
        models = []
        if self.success_check.isChecked():
            models.append('success_model')
        if self.behavior_check.isChecked():
            models.append('target_behavior')
        if self.frequency_check.isChecked():
            models.append('frequency_model')
        
        if not models:
            self.status_label.setText("Select at least one model to train")
            return
        
        # Update UI
        self.train_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.success_check.setEnabled(False)
        self.behavior_check.setEnabled(False)
        self.frequency_check.setEnabled(False)
        
        self.results_text.clear()
        self.stage_label.setText("Starting...")
        self.progress_bar.setValue(0)
        
        # Start training
        success = self.training_manager.start_training(models=models)
        
        if not success:
            self._reset_ui()
    
    def _cancel_training(self):
        """Cancel training."""
        self.training_manager.cancel_training()
        self.status_label.setText("Cancelling...")
    
    def _reset_ui(self):
        """Reset UI to initial state."""
        self.train_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.success_check.setEnabled(True)
        self.behavior_check.setEnabled(True)
        self.frequency_check.setEnabled(True)
    
    @pyqtSlot(str, int, str)
    def _on_progress(self, stage: str, percent: int, message: str):
        """Handle progress update."""
        stage_names = {
            'load': 'Loading Data',
            'stats': 'Calculating Statistics',
            'train': 'Training Models',
            'complete': 'Complete',
        }
        
        self.stage_label.setText(stage_names.get(stage, stage.title()))
        self.progress_bar.setValue(percent)
        self.status_label.setText(message)
    
    @pyqtSlot(str, dict)
    def _on_model_complete(self, model_name: str, metrics: dict):
        """Handle model completion."""
        self.results_text.append(f"✓ {model_name}")
        
        # Format metrics
        for key, value in metrics.items():
            if key == 'feature_importance':
                continue  # Skip verbose data
            
            if isinstance(value, float):
                self.results_text.append(f"  {key}: {value:.3f}")
            else:
                self.results_text.append(f"  {key}: {value}")
        
        self.results_text.append("")
    
    @pyqtSlot(dict)
    def _on_stats(self, stats: dict):
        """Handle statistics update."""
        self.stats_group.show()
        
        lines = []
        
        # Overall stats
        total_qsos = stats.get('total_qsos', 0)
        total_attempts = stats.get('total_attempts', 0)
        success_rate = stats.get('overall_success_rate', 0)
        
        lines.append(f"Total QSOs: {total_qsos:,}")
        lines.append(f"Total Attempts: {total_attempts:,}")
        lines.append(f"Overall Success Rate: {success_rate:.1%}")
        lines.append("")
        
        # Avg calls to success
        avg_calls = stats.get('avg_calls_to_success', 0)
        if avg_calls > 0:
            lines.append(f"Avg Calls to Success: {avg_calls:.1f}")
        
        # Success by band (top 3)
        by_band = stats.get('success_by_band', {})
        if by_band:
            lines.append("\nBest Bands:")
            sorted_bands = sorted(
                by_band.items(), 
                key=lambda x: x[1].get('rate', 0), 
                reverse=True
            )[:3]
            for band, data in sorted_bands:
                rate = data.get('rate', 0)
                count = data.get('total', 0)
                lines.append(f"  {band}: {rate:.0%} ({count} attempts)")
        
        self.stats_text.setText("\n".join(lines))
    
    @pyqtSlot(str)
    def _on_error(self, message: str):
        """Handle error."""
        self.results_text.append(f"⚠ Error: {message}")
        self.status_label.setText(f"Error: {message}")
        self.status_label.setStyleSheet("color: #ff6666;")
    
    @pyqtSlot(bool, str)
    def _on_finished(self, success: bool, message: str):
        """Handle training completion."""
        self._reset_ui()
        
        if success:
            self.stage_label.setText("Training Complete")
            self.progress_bar.setValue(100)
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #88ff88;")
        else:
            self.stage_label.setText("Training Failed")
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #ff6666;")


class ModelStatusWidget(QWidget):
    """
    Compact widget showing model status, suitable for embedding in main window.
    
    Shows staleness and provides quick access to training.
    """
    
    retrain_clicked = pyqtSignal = None  # Will be connected externally
    
    def __init__(self, training_manager: TrainingManager, parent=None):
        super().__init__(parent)
        
        self.training_manager = training_manager
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        
        self.status_label = QLabel("Models: —")
        self.status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.status_label)
        
        self.retrain_button = QPushButton("⟳")
        self.retrain_button.setFixedSize(24, 24)
        self.retrain_button.setToolTip("Retrain models")
        self.retrain_button.hide()
        layout.addWidget(self.retrain_button)
    
    def update_status(self):
        """Update display with current model status."""
        status = self.training_manager.get_model_status()
        
        ready_count = sum(1 for s in status if s['exists'] and not s['is_stale'])
        stale_count = sum(1 for s in status if s['exists'] and s['is_stale'])
        missing_count = sum(1 for s in status if not s['exists'])
        
        if missing_count > 0:
            self.status_label.setText(f"Models: {missing_count} not trained")
            self.status_label.setStyleSheet("color: #ff8800; font-size: 11px;")
            self.retrain_button.show()
        elif stale_count > 0:
            self.status_label.setText(f"Models: {stale_count} stale")
            self.status_label.setStyleSheet("color: #ffff00; font-size: 11px;")
            self.retrain_button.show()
        elif ready_count > 0:
            self.status_label.setText(f"Models: {ready_count} ready")
            self.status_label.setStyleSheet("color: #88ff88; font-size: 11px;")
            self.retrain_button.hide()
        else:
            self.status_label.setText("Models: None")
            self.status_label.setStyleSheet("color: #888888; font-size: 11px;")
            self.retrain_button.show()


# Add missing import
from PyQt6.QtCore import pyqtSignal
