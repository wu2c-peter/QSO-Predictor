"""
Model Manager for QSO Predictor v2.0

Manages loading, saving, and staleness checking of ML models.
Models are stored locally in the user's home directory.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

from .models import ModelMetadata

logger = logging.getLogger(__name__)


# Try to import ML libraries (optional)
try:
    import joblib
    HAS_JOBLIB = True
except ImportError:
    HAS_JOBLIB = False
    logger.warning("joblib not installed - ML model loading disabled")


# =============================================================================
# Model Wrapper Classes (must be at module level for pickling)
# =============================================================================

class ScaledClassifier:
    """Wrapper that applies scaling before classification."""
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


class ScaledRegressor:
    """Wrapper that applies scaling before regression."""
    def __init__(self, model, scaler):
        self._model = model
        self._scaler = scaler
    
    def predict(self, X):
        X_scaled = self._scaler.transform(X)
        return self._model.predict(X_scaled)


# =============================================================================
# Model Manager
# =============================================================================

class ModelManager:
    """
    Manage local ML models for prediction.
    
    Responsibilities:
    - Load trained models from disk
    - Check model staleness
    - Provide prediction interface
    - Track model performance
    """
    
    # Default model directory
    DEFAULT_MODEL_DIR = Path.home() / '.qso-predictor' / 'models'
    
    # Expected model files
    MODEL_NAMES = [
        'success_model',      # Predict P(QSO success)
        'target_behavior',    # Classify target picking patterns
        'frequency_model',    # Recommend TX frequency
    ]
    
    def __init__(self, model_dir: Path = None):
        """
        Initialize model manager.
        
        Args:
            model_dir: Directory containing model files
        """
        self.model_dir = model_dir or self.DEFAULT_MODEL_DIR
        self.models: Dict[str, Any] = {}
        self.metadata: Dict[str, ModelMetadata] = {}
        self._loaded = False
    
    def ensure_directory(self):
        """Create model directory if it doesn't exist."""
        self.model_dir.mkdir(parents=True, exist_ok=True)
    
    def load_models(self, force: bool = False) -> bool:
        """
        Load all available models from disk.
        
        Args:
            force: Reload even if already loaded
            
        Returns:
            True if any models were loaded
        """
        if self._loaded and not force:
            return bool(self.models)
        
        if not HAS_JOBLIB:
            logger.warning("Cannot load models: joblib not installed")
            return False
        
        self.models.clear()
        self.metadata.clear()
        
        if not self.model_dir.exists():
            logger.info(f"Model directory does not exist: {self.model_dir}")
            return False
        
        loaded_count = 0
        
        for model_name in self.MODEL_NAMES:
            model_path = self.model_dir / f'{model_name}.pkl'
            meta_path = self.model_dir / f'{model_name}.meta.json'
            
            if not model_path.exists():
                logger.debug(f"Model not found: {model_path}")
                continue
            
            try:
                # Load model
                self.models[model_name] = joblib.load(model_path)
                
                # Load metadata
                if meta_path.exists():
                    self.metadata[model_name] = ModelMetadata.load(meta_path)
                else:
                    # Create basic metadata if missing
                    self.metadata[model_name] = ModelMetadata(
                        name=model_name,
                        path=model_path,
                        trained_at=datetime.fromtimestamp(model_path.stat().st_mtime),
                        training_samples=0,
                        feature_version='unknown'
                    )
                
                loaded_count += 1
                logger.info(f"Loaded model: {model_name}")
                
            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
        
        self._loaded = True
        logger.info(f"Loaded {loaded_count} models")
        return loaded_count > 0
    
    def reload_models(self) -> bool:
        """Force reload all models from disk."""
        return self.load_models(force=True)
    
    def has_model(self, name: str) -> bool:
        """Check if a model is available."""
        if not self._loaded:
            self.load_models()
        return name in self.models
    
    def get_model(self, name: str) -> Optional[Any]:
        """Get a loaded model by name."""
        if not self._loaded:
            self.load_models()
        return self.models.get(name)
    
    def get_metadata(self, name: str) -> Optional[ModelMetadata]:
        """Get metadata for a model."""
        if not self._loaded:
            self.load_models()
        return self.metadata.get(name)
    
    def get_stale_models(self, current_qso_count: int) -> List[str]:
        """
        Check which models need retraining.
        
        Args:
            current_qso_count: Current number of QSOs in log files
            
        Returns:
            List of model names that are stale
        """
        if not self._loaded:
            self.load_models()
        
        stale = []
        
        for name in self.MODEL_NAMES:
            if name not in self.metadata:
                # Model doesn't exist - definitely needs training
                stale.append(name)
                continue
            
            meta = self.metadata[name]
            staleness = meta.staleness_score(current_qso_count)
            
            if staleness > 0.8:
                stale.append(name)
                logger.debug(f"Model {name} is stale (score: {staleness:.2f})")
        
        return stale
    
    def get_model_status(self) -> List[Dict]:
        """
        Get status of all models.
        
        Returns:
            List of dicts with model status info
        """
        if not self._loaded:
            self.load_models()
        
        status = []
        
        for name in self.MODEL_NAMES:
            if name in self.models and name in self.metadata:
                meta = self.metadata[name]
                status.append({
                    'name': name,
                    'exists': True,
                    'trained_at': meta.trained_at,
                    'training_samples': meta.training_samples,
                    'age_days': (datetime.now() - meta.trained_at).days,
                    'metrics': meta.performance_metrics,
                    'is_stale': meta.is_stale,
                })
            else:
                status.append({
                    'name': name,
                    'exists': False,
                    'trained_at': None,
                    'training_samples': 0,
                    'age_days': None,
                    'metrics': {},
                    'is_stale': True,  # Non-existent = stale
                })
        
        return status
    
    def predict(self, 
                model_name: str, 
                features: Dict) -> Optional[Dict]:
        """
        Make a prediction using a trained model.
        
        Args:
            model_name: Name of model to use
            features: Dict of feature values
            
        Returns:
            Dict with prediction results, or None if model unavailable
        """
        model = self.get_model(model_name)
        if model is None:
            return None
        
        try:
            # Convert features to array in expected order
            feature_array = self._features_to_array(model_name, features)
            if feature_array is None:
                return None
            
            import numpy as np
            X = np.array([feature_array])
            
            # Get prediction
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(X)[0]
                prediction = model.classes_[proba.argmax()]
                confidence = proba.max()
            else:
                prediction = model.predict(X)[0]
                confidence = None
            
            return {
                'prediction': prediction,
                'confidence': confidence,
                'model': model_name,
            }
            
        except Exception as e:
            logger.error(f"Prediction failed for {model_name}: {e}")
            return None
    
    def _features_to_array(self, model_name: str, features: Dict) -> Optional[List]:
        """Convert feature dict to array in correct order."""
        # Feature orders for each model
        FEATURE_ORDERS = {
            'success_model': [
                'target_snr', 'your_snr', 'band_encoded', 'hour_utc',
                'competition', 'region_encoded', 'calls_made'
            ],
            'target_behavior': [
                'snr_correlation', 'freq_correlation', 'region_entropy',
                'timing_variance', 'sample_size'
            ],
            'frequency_model': [
                'band_encoded', 'hour_utc', 'pileup_size', 'avg_freq',
                'your_typical_freq'
            ],
        }
        
        if model_name not in FEATURE_ORDERS:
            logger.warning(f"Unknown feature order for model: {model_name}")
            return None
        
        order = FEATURE_ORDERS[model_name]
        
        try:
            return [features.get(f, 0) for f in order]
        except Exception as e:
            logger.error(f"Feature conversion failed: {e}")
            return None
    
    def save_model(self, 
                   name: str, 
                   model: Any, 
                   metadata: ModelMetadata) -> bool:
        """
        Save a trained model to disk.
        
        Args:
            name: Model name
            model: Trained model object
            metadata: Model metadata
            
        Returns:
            True if saved successfully
        """
        if not HAS_JOBLIB:
            logger.error("Cannot save model: joblib not installed")
            return False
        
        self.ensure_directory()
        
        try:
            model_path = self.model_dir / f'{name}.pkl'
            meta_path = self.model_dir / f'{name}.meta.json'
            
            # Save model
            joblib.dump(model, model_path)
            
            # Save metadata
            metadata.path = model_path
            metadata.save(meta_path)
            
            # Update in-memory state
            self.models[name] = model
            self.metadata[name] = metadata
            
            logger.info(f"Saved model: {name} to {model_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save model {name}: {e}")
            return False
    
    def delete_model(self, name: str) -> bool:
        """
        Delete a model from disk.
        
        Args:
            name: Model name to delete
            
        Returns:
            True if deleted (or didn't exist)
        """
        model_path = self.model_dir / f'{name}.pkl'
        meta_path = self.model_dir / f'{name}.meta.json'
        
        try:
            if model_path.exists():
                model_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            
            # Remove from memory
            self.models.pop(name, None)
            self.metadata.pop(name, None)
            
            logger.info(f"Deleted model: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete model {name}: {e}")
            return False


class PredictionCache:
    """
    Cache predictions to avoid repeated model inference.
    
    Caches are invalidated when underlying data changes.
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: float = 60.0):
        """
        Initialize cache.
        
        Args:
            max_size: Maximum number of cached predictions
            ttl_seconds: Time-to-live for cache entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, tuple] = {}  # key -> (result, timestamp)
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached prediction if still valid."""
        if key not in self._cache:
            return None
        
        result, timestamp = self._cache[key]
        age = (datetime.now() - timestamp).total_seconds()
        
        if age > self.ttl_seconds:
            del self._cache[key]
            return None
        
        return result
    
    def set(self, key: str, value: Any):
        """Cache a prediction."""
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_size:
            oldest = min(self._cache.items(), key=lambda x: x[1][1])
            del self._cache[oldest[0]]
        
        self._cache[key] = (value, datetime.now())
    
    def invalidate(self, pattern: str = None):
        """
        Invalidate cache entries.
        
        Args:
            pattern: If provided, only invalidate keys containing this string.
                    If None, invalidate all.
        """
        if pattern is None:
            self._cache.clear()
        else:
            to_delete = [k for k in self._cache if pattern in k]
            for k in to_delete:
                del self._cache[k]
    
    def make_key(self, model_name: str, features: Dict) -> str:
        """Create cache key from model name and features."""
        # Sort features for consistent key
        sorted_features = sorted(features.items())
        feature_str = ','.join(f'{k}={v}' for k, v in sorted_features)
        return f"{model_name}:{feature_str}"
