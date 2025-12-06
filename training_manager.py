"""
Training Manager for QSO Predictor v2.0

Manages the background training subprocess from the main application.
Handles launching, progress tracking, and model reloading.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Callable

from PyQt6.QtCore import QObject, QProcess, pyqtSignal, QTimer

from local_intel.log_discovery import LogFileDiscovery
from local_intel.model_manager import ModelManager

logger = logging.getLogger(__name__)


class TrainingManager(QObject):
    """
    Manage background ML training process.
    
    Signals:
        progress_updated: (stage, percent, message)
        model_complete: (model_name, metrics_dict)
        stats_calculated: (stats_dict)
        training_finished: (success, message)
        training_error: (error_message)
    """
    
    # Signals
    progress_updated = pyqtSignal(str, int, str)
    model_complete = pyqtSignal(str, dict)
    stats_calculated = pyqtSignal(dict)
    training_finished = pyqtSignal(bool, str)
    training_error = pyqtSignal(str)
    
    def __init__(self, 
                 my_callsign: str,
                 model_manager: ModelManager = None,
                 parent=None):
        """
        Initialize training manager.
        
        Args:
            my_callsign: User's callsign
            model_manager: ModelManager instance (creates one if not provided)
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self.my_callsign = my_callsign.upper()
        self.model_manager = model_manager or ModelManager()
        self.log_discovery = LogFileDiscovery()
        
        self.process: Optional[QProcess] = None
        self._output_buffer = ""
        
        # Config directory
        self.config_dir = Path.home() / '.qso-predictor'
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def is_training(self) -> bool:
        """Check if training is currently in progress."""
        return self.process is not None and self.process.state() == QProcess.ProcessState.Running
    
    def discover_log_files(self) -> List[Dict]:
        """
        Discover available log files.
        
        Returns:
            List of dicts with file info
        """
        sources = self.log_discovery.discover_all_files(refresh=True)
        
        return [{
            'path': str(s.path),
            'program': s.program,
            'size_mb': s.size_mb,
            'line_count': s.line_count,
            'modified': s.modified.isoformat() if s.modified else None,
            'date_range': (
                s.date_range[0].isoformat() if s.date_range else None,
                s.date_range[1].isoformat() if s.date_range else None,
            ) if s.date_range else None,
        } for s in sources]
    
    def get_model_status(self) -> List[Dict]:
        """Get status of all models."""
        return self.model_manager.get_model_status()
    
    def check_staleness(self, qso_count: int = 0) -> List[str]:
        """
        Check which models need retraining.
        
        Args:
            qso_count: Current QSO count (for staleness calculation)
            
        Returns:
            List of stale model names
        """
        return self.model_manager.get_stale_models(qso_count)
    
    def start_training(self, 
                       models: List[str] = None,
                       log_files: List[str] = None) -> bool:
        """
        Start background training process.
        
        Args:
            models: List of model names to train (None = all)
            log_files: List of log file paths (None = auto-discover)
            
        Returns:
            True if training started successfully
        """
        if self.is_training:
            logger.warning("Training already in progress")
            return False
        
        # Get log files
        if log_files is None:
            sources = self.log_discovery.discover_all_files()
            log_files = [str(s.path) for s in sources]
        
        if not log_files:
            self.training_error.emit("No log files found")
            return False
        
        # Build config
        config = {
            'my_callsign': self.my_callsign,
            'all_txt_files': log_files,
            'output_dir': str(self.model_manager.model_dir),
            'models': models,
        }
        
        # Write config file
        config_path = self.config_dir / 'training_config.json'
        try:
            config_path.write_text(json.dumps(config, indent=2))
        except Exception as e:
            self.training_error.emit(f"Failed to write config: {e}")
            return False
        
        # Find trainer script
        trainer_script = Path(__file__).parent / 'training' / 'trainer_process.py'
        if not trainer_script.exists():
            self.training_error.emit(f"Trainer script not found: {trainer_script}")
            return False
        
        # Create process
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._handle_finished)
        self.process.errorOccurred.connect(self._handle_error)
        
        # Start process
        import sys
        python_exe = sys.executable
        
        args = [str(trainer_script), '--config', str(config_path)]
        
        logger.info(f"Starting training: {python_exe} {' '.join(args)}")
        self.process.start(python_exe, args)
        
        if not self.process.waitForStarted(5000):
            self.training_error.emit("Failed to start training process")
            self.process = None
            return False
        
        logger.info("Training process started")
        return True
    
    def cancel_training(self):
        """Cancel the running training process."""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            logger.info("Cancelling training process")
            self.process.terminate()
            
            # Give it a moment to terminate gracefully
            if not self.process.waitForFinished(3000):
                self.process.kill()
    
    def _handle_stdout(self):
        """Handle stdout from training process."""
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='replace')
        self._output_buffer += data
        
        # Process complete lines
        while '\n' in self._output_buffer:
            line, self._output_buffer = self._output_buffer.split('\n', 1)
            line = line.strip()
            if not line:
                continue
            
            self._process_message(line)
    
    def _process_message(self, line: str):
        """Process a JSON message from the training process."""
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON output: {line}")
            return
        
        msg_type = msg.get('type')
        
        if msg_type == 'progress':
            self.progress_updated.emit(
                msg.get('stage', ''),
                msg.get('percent', 0),
                msg.get('message', '')
            )
            
        elif msg_type == 'model_complete':
            self.model_complete.emit(
                msg.get('model', ''),
                msg.get('metrics', {})
            )
            
        elif msg_type == 'stats':
            # Remove 'type' key before emitting
            stats = {k: v for k, v in msg.items() if k != 'type'}
            self.stats_calculated.emit(stats)
            
        elif msg_type == 'error':
            self.training_error.emit(msg.get('message', 'Unknown error'))
            
        elif msg_type == 'done':
            # Will be handled by finished signal
            pass
            
        else:
            logger.debug(f"Unknown message type: {msg_type}")
    
    def _handle_stderr(self):
        """Handle stderr from training process (logging)."""
        data = self.process.readAllStandardError().data().decode('utf-8', errors='replace')
        for line in data.strip().split('\n'):
            if line:
                logger.debug(f"[trainer] {line}")
    
    def _handle_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        """Handle training process completion."""
        success = exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit
        
        if success:
            logger.info("Training completed successfully")
            # Reload models
            self.model_manager.load_models(force=True)
            self.training_finished.emit(True, "Training completed successfully")
        else:
            logger.error(f"Training failed: exit_code={exit_code}, status={exit_status}")
            self.training_finished.emit(False, f"Training failed (exit code {exit_code})")
        
        self.process = None
        self._output_buffer = ""
    
    def _handle_error(self, error: QProcess.ProcessError):
        """Handle process errors."""
        error_messages = {
            QProcess.ProcessError.FailedToStart: "Failed to start training process",
            QProcess.ProcessError.Crashed: "Training process crashed",
            QProcess.ProcessError.Timedout: "Training process timed out",
            QProcess.ProcessError.WriteError: "Write error",
            QProcess.ProcessError.ReadError: "Read error",
            QProcess.ProcessError.UnknownError: "Unknown error",
        }
        
        msg = error_messages.get(error, f"Process error: {error}")
        logger.error(msg)
        self.training_error.emit(msg)


class TrainingStatusChecker(QObject):
    """
    Periodically check model staleness and notify user.
    
    Signals:
        models_stale: (list of stale model names)
    """
    
    models_stale = pyqtSignal(list)
    
    def __init__(self, 
                 training_manager: TrainingManager,
                 check_interval_hours: float = 24,
                 parent=None):
        """
        Initialize status checker.
        
        Args:
            training_manager: TrainingManager instance
            check_interval_hours: How often to check (default 24 hours)
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self.training_manager = training_manager
        self.check_interval_ms = int(check_interval_hours * 60 * 60 * 1000)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check)
        
        self._last_qso_count = 0
    
    def start(self):
        """Start periodic checking."""
        # Check immediately
        self._check()
        # Then periodically
        self.timer.start(self.check_interval_ms)
    
    def stop(self):
        """Stop periodic checking."""
        self.timer.stop()
    
    def set_qso_count(self, count: int):
        """Update QSO count for staleness calculation."""
        self._last_qso_count = count
    
    def _check(self):
        """Check model staleness."""
        stale = self.training_manager.check_staleness(self._last_qso_count)
        if stale:
            self.models_stale.emit(stale)
