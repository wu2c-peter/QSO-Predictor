"""
Local Intelligence Engine for QSO Predictor v2.0

Provides offline analysis capabilities using only local data:
- all.txt log file parsing
- Real-time pileup tracking
- Target behavior analysis
- Your success pattern analysis
- ML-based predictions

Copyright (C) 2025 Peter Hirst (WU2C)
"""

from .models import (
    # Enums
    PickingStyle,
    PathStatus,
    
    # Log file models
    LogFileSource,
    Decode,
    QSOAttempt,
    QSO,
    
    # Real-time models
    PileupMember,
    AnsweredCall,
    TargetSession,
    
    # Analysis results
    PickingPattern,
    SuccessRateBucket,
    YourStats,
    TargetHistory,
    
    # ML models
    ModelMetadata,
    Prediction,
    StrategyRecommendation,
    
    # Configuration
    AnalysisConfig,
)

from .log_discovery import LogFileDiscovery, discover_log_files
from .log_parser import LogParser, MessageParser, QSOExtractor, parse_log_files
from .session_tracker import SessionTracker, MultiTargetTracker
from .model_manager import ModelManager, PredictionCache
from .predictor import BayesianPredictor, HeuristicPredictor

__all__ = [
    # Enums
    'PickingStyle',
    'PathStatus',
    
    # Log file models
    'LogFileSource',
    'Decode',
    'QSOAttempt',
    'QSO',
    
    # Real-time models
    'PileupMember',
    'AnsweredCall',
    'TargetSession',
    
    # Analysis results
    'PickingPattern',
    'SuccessRateBucket',
    'YourStats',
    'TargetHistory',
    
    # ML models
    'ModelMetadata',
    'Prediction',
    'StrategyRecommendation',
    
    # Configuration
    'AnalysisConfig',
    
    # Discovery & Parsing
    'LogFileDiscovery',
    'discover_log_files',
    'LogParser',
    'MessageParser',
    'QSOExtractor',
    'parse_log_files',
    
    # Session Tracking
    'SessionTracker',
    'MultiTargetTracker',
    
    # Model Management
    'ModelManager',
    'PredictionCache',
    
    # Prediction
    'BayesianPredictor',
    'HeuristicPredictor',
]
