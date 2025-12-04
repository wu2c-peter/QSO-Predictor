#!/usr/bin/env python3
"""
ML Trainer Process for QSO Predictor v2.0

Runs as a separate process to train models without blocking the UI.
Communicates with parent process via JSON messages on stdout.

Usage:
    python -m training.trainer_process --config /path/to/config.json

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

# Setup path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from local_intel.log_discovery import LogFileDiscovery
from local_intel.log_parser import LogParser, QSOExtractor
from local_intel.models import ModelMetadata
from training.feature_builders import (
    SuccessFeatureBuilder, 
    BehaviorFeatureBuilder,
    StatsCalculator
)

# Configure logging to stderr (stdout is for JSON messages)
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


# =============================================================================
# Message Protocol
# =============================================================================

def emit_message(msg_type: str, **kwargs):
    """Send JSON message to parent process."""
    message = {'type': msg_type, **kwargs}
    print(json.dumps(message), flush=True)


def emit_progress(stage: str, percent: int, message: str):
    """Send progress update."""
    emit_message('progress', stage=stage, percent=percent, message=message)


def emit_model_complete(model_name: str, metrics: Dict):
    """Send model completion message."""
    emit_message('model_complete', model=model_name, metrics=metrics)


def emit_stats(stats: Dict):
    """Send statistics update."""
    emit_message('stats', **stats)


def emit_error(message: str):
    """Send error message."""
    emit_message('error', message=message)


def emit_done(success: bool, message: str = ""):
    """Send completion message."""
    emit_message('done', success=success, message=message)


# =============================================================================
# Model Trainers
# =============================================================================

def train_success_model(X: np.ndarray, 
                        y: np.ndarray,
                        feature_names: List[str]) -> Tuple[Any, Dict]:
    """
    Train the success prediction model.
    
    Args:
        X: Feature matrix
        y: Labels (0/1)
        feature_names: Names of features
        
    Returns:
        (model, metrics)
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler
    
    logger.info(f"Training success model with {len(X)} samples")
    
    if len(X) < 50:
        raise ValueError(f"Not enough samples for training: {len(X)} (need 50+)")
    
    # Handle class imbalance
    n_positive = sum(y)
    n_negative = len(y) - n_positive
    
    if n_positive < 10 or n_negative < 10:
        raise ValueError(f"Class imbalance too severe: {n_positive} positive, {n_negative} negative")
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train model
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_leaf=max(5, len(X) // 100),
        class_weight='balanced',
        n_jobs=-1,
        random_state=42
    )
    
    # Cross-validation
    cv_folds = min(5, max(2, len(X) // 50))
    cv_scores = cross_val_score(model, X_scaled, y, cv=cv_folds, scoring='roc_auc')
    
    # Final fit
    model.fit(X_scaled, y)
    
    # Feature importance
    importance = dict(zip(feature_names, model.feature_importances_.tolist()))
    
    metrics = {
        'cv_auc_mean': float(np.mean(cv_scores)),
        'cv_auc_std': float(np.std(cv_scores)),
        'n_samples': len(X),
        'n_positive': int(n_positive),
        'n_negative': int(n_negative),
        'feature_importance': importance,
    }
    
    # Wrap model with scaler for inference
    class ScaledModel:
        def __init__(self, model, scaler):
            self._model = model
            self._scaler = scaler
            self.classes_ = model.classes_
        
        def predict(self, X):
            X_scaled = self._scaler.transform(X)
            return self._model.predict(X_scaled)
        
        def predict_proba(self, X):
            X_scaled = self._scaler.transform(X)
            return self._model.predict_proba(X_scaled)
    
    wrapped_model = ScaledModel(model, scaler)
    
    return wrapped_model, metrics


def train_behavior_model(X: np.ndarray,
                         y: np.ndarray,
                         feature_names: List[str]) -> Tuple[Any, Dict]:
    """
    Train the target behavior classification model.
    
    Args:
        X: Feature matrix
        y: Labels (0=loudest, 1=methodical, 2=random)
        feature_names: Names of features
        
    Returns:
        (model, metrics)
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    
    logger.info(f"Training behavior model with {len(X)} samples")
    
    if len(X) < 30:
        raise ValueError(f"Not enough samples: {len(X)} (need 30+)")
    
    model = RandomForestClassifier(
        n_estimators=50,
        max_depth=8,
        min_samples_leaf=3,
        n_jobs=-1,
        random_state=42
    )
    
    cv_folds = min(5, max(2, len(X) // 20))
    cv_scores = cross_val_score(model, X, y, cv=cv_folds, scoring='accuracy')
    
    model.fit(X, y)
    
    metrics = {
        'cv_accuracy_mean': float(np.mean(cv_scores)),
        'cv_accuracy_std': float(np.std(cv_scores)),
        'n_samples': len(X),
        'class_distribution': {
            'loudest_first': int(sum(y == 0)),
            'methodical': int(sum(y == 1)),
            'random': int(sum(y == 2)),
        }
    }
    
    return model, metrics


# =============================================================================
# Main Trainer Class
# =============================================================================

class ModelTrainer:
    """
    Main training orchestrator.
    
    Loads data, trains models, and saves results.
    """
    
    def __init__(self, config: Dict):
        """
        Initialize trainer.
        
        Args:
            config: Training configuration dict with keys:
                - my_callsign: User's callsign
                - all_txt_files: List of paths to all.txt files
                - output_dir: Where to save models
                - models: List of model names to train (optional)
        """
        self.config = config
        self.my_callsign = config['my_callsign'].upper()
        self.all_txt_files = [Path(p) for p in config['all_txt_files']]
        self.output_dir = Path(config['output_dir'])
        self.models_to_train = config.get('models', ['success_model', 'target_behavior'])
        
        # Data storage
        self.decodes = []
        self.qsos = []
    
    def run(self) -> bool:
        """
        Run the full training pipeline.
        
        Returns:
            True if all models trained successfully
        """
        try:
            # Stage 1: Load data
            emit_progress('load', 0, 'Loading log files...')
            self._load_data()
            
            # Stage 2: Calculate stats
            emit_progress('stats', 0, 'Calculating statistics...')
            self._calculate_stats()
            
            # Stage 3: Train models
            total_models = len(self.models_to_train)
            success = True
            
            for i, model_name in enumerate(self.models_to_train):
                pct = int((i / total_models) * 100)
                emit_progress('train', pct, f'Training {model_name}...')
                
                try:
                    self._train_model(model_name)
                except Exception as e:
                    logger.error(f"Failed to train {model_name}: {e}")
                    emit_error(f"Failed to train {model_name}: {e}")
                    success = False
            
            emit_progress('complete', 100, 'Training complete')
            emit_done(success, 'All models trained' if success else 'Some models failed')
            
            return success
            
        except Exception as e:
            logger.exception("Training failed")
            emit_error(str(e))
            emit_done(False, str(e))
            return False
    
    def _load_data(self):
        """Load and parse all.txt files."""
        from local_intel.log_discovery import LogFileSource
        
        # Convert paths to LogFileSource objects
        sources = []
        for path in self.all_txt_files:
            if path.exists():
                sources.append(LogFileSource(
                    path=path,
                    program='WSJT-X' if 'wsjt' in str(path).lower() else 'JTDX',
                    modified=datetime.fromtimestamp(path.stat().st_mtime),
                    size_bytes=path.stat().st_size
                ))
        
        if not sources:
            raise ValueError("No valid log files found")
        
        emit_progress('load', 10, f'Found {len(sources)} log files')
        
        # Parse files
        parser = LogParser(self.my_callsign)
        
        all_decodes = []
        for i, source in enumerate(sources):
            pct = 10 + int((i / len(sources)) * 60)
            emit_progress('load', pct, f'Parsing {source.path.name}...')
            
            decodes = list(parser.parse_file(source))
            all_decodes.extend(decodes)
            logger.info(f"Parsed {len(decodes)} decodes from {source.path.name}")
        
        self.decodes = sorted(all_decodes, key=lambda d: d.timestamp)
        
        emit_progress('load', 75, 'Extracting QSOs...')
        
        # Extract QSOs
        extractor = QSOExtractor(self.my_callsign)
        self.qsos = extractor.extract_qsos(self.decodes)
        
        emit_progress('load', 100, 
                     f'Loaded {len(self.decodes):,} decodes, {len(self.qsos):,} QSOs')
        
        logger.info(f"Total: {len(self.decodes)} decodes, {len(self.qsos)} QSOs")
    
    def _calculate_stats(self):
        """Calculate and emit statistics."""
        from training.feature_builders import AttemptReconstructor
        
        reconstructor = AttemptReconstructor(self.my_callsign)
        attempts = reconstructor.reconstruct(self.decodes, self.qsos)
        
        calculator = StatsCalculator(self.my_callsign)
        
        stats = {
            'total_decodes': len(self.decodes),
            'total_qsos': len(self.qsos),
            'total_attempts': len(attempts),
            'overall_success_rate': len(self.qsos) / max(1, len(attempts)),
            'success_by_snr': calculator.success_rate_by_snr(attempts),
            'success_by_band': calculator.success_rate_by_band(attempts),
            'avg_calls_to_success': calculator.avg_calls_to_success(attempts),
        }
        
        emit_stats(stats)
        
        # Store for model training
        self._attempts = attempts
    
    def _train_model(self, model_name: str):
        """Train a specific model."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if model_name == 'success_model':
            self._train_success_model()
        elif model_name == 'target_behavior':
            self._train_behavior_model()
        else:
            logger.warning(f"Unknown model: {model_name}")
    
    def _train_success_model(self):
        """Train the success prediction model."""
        builder = SuccessFeatureBuilder(self.my_callsign)
        X, y = builder.build(self.decodes, self.qsos)
        
        if len(X) == 0:
            raise ValueError("No training data for success model")
        
        model, metrics = train_success_model(X, y, builder.feature_names)
        
        # Save model
        self._save_model('success_model', model, metrics, len(X))
        
        emit_model_complete('success_model', metrics)
    
    def _train_behavior_model(self):
        """Train the target behavior model."""
        # For behavior model, we need session data which is primarily
        # built from real-time observations. For historical training,
        # we'll use a simplified approach.
        
        # This is a placeholder - full implementation would reconstruct
        # sessions from historical decodes
        logger.warning("Behavior model training from historical data not yet implemented")
        
        metrics = {
            'status': 'skipped',
            'reason': 'Requires real-time session data'
        }
        
        emit_model_complete('target_behavior', metrics)
    
    def _save_model(self, name: str, model: Any, metrics: Dict, n_samples: int):
        """Save a trained model to disk."""
        try:
            import joblib
        except ImportError:
            raise ImportError("joblib required for model saving: python -m pip install joblib")
        
        model_path = self.output_dir / f'{name}.pkl'
        meta_path = self.output_dir / f'{name}.meta.json'
        
        # Save model
        joblib.dump(model, model_path)
        logger.info(f"Saved model to {model_path}")
        
        # Save metadata
        metadata = ModelMetadata(
            name=name,
            path=model_path,
            trained_at=datetime.now(),
            training_samples=n_samples,
            feature_version='2.0',
            performance_metrics=metrics
        )
        metadata.save(meta_path)
        logger.info(f"Saved metadata to {meta_path}")


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Main entry point when run as subprocess."""
    parser = argparse.ArgumentParser(
        description='Train ML models for QSO Predictor'
    )
    parser.add_argument(
        '--config', 
        required=True,
        help='Path to training config JSON file'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load config
    try:
        config_path = Path(args.config)
        if not config_path.exists():
            emit_error(f"Config file not found: {config_path}")
            sys.exit(1)
        
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        emit_error(f"Invalid config JSON: {e}")
        sys.exit(1)
    
    # Validate config
    required = ['my_callsign', 'all_txt_files', 'output_dir']
    missing = [k for k in required if k not in config]
    if missing:
        emit_error(f"Missing config keys: {missing}")
        sys.exit(1)
    
    # Run training
    trainer = ModelTrainer(config)
    success = trainer.run()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
