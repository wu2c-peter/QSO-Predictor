"""
Data models for Local Intelligence Engine.

QSO Predictor v2.0
Copyright (C) 2025 Peter Hirst (WU2C)
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class PickingStyle(Enum):
    """How a target station picks callers from the pileup."""
    UNKNOWN = "unknown"
    LOUDEST_FIRST = "loudest_first"
    METHODICAL_LOW_HIGH = "methodical_low_high"
    METHODICAL_HIGH_LOW = "methodical_high_low"
    GEOGRAPHIC = "geographic"
    RANDOM = "random"


class PathStatus(Enum):
    """Your signal path status to a target."""
    CONNECTED = "connected"
    PATH_OPEN = "path_open"
    NO_PATH = "no_path"
    UNKNOWN = "unknown"


# =============================================================================
# Log File Models
# =============================================================================

@dataclass
class LogFileSource:
    """Represents a discovered all.txt log file."""
    path: Path
    program: str  # "WSJT-X" or "JTDX"
    modified: datetime
    size_bytes: int
    line_count: int = 0
    date_range: Optional[Tuple[datetime, datetime]] = None
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)
    
    @property
    def is_monthly(self) -> bool:
        """JTDX creates monthly files like all_jtdx_202512.txt"""
        return 'all_jtdx_' in self.path.name


@dataclass
class Decode:
    """A single decode from all.txt or live UDP."""
    timestamp: datetime
    snr: int
    dt: float  # Time delta
    frequency: int  # Audio offset Hz
    mode: str  # FT8, FT4, etc.
    message: str  # Raw message text
    
    # Parsed from message
    callsign: Optional[str] = None  # Transmitting station
    grid: Optional[str] = None
    is_cq: bool = False
    is_reply: bool = False
    replying_to: Optional[str] = None
    
    # Metadata
    source: str = "unknown"  # "udp", "all.txt", "jtdx"
    band: Optional[str] = None
    dial_freq: Optional[int] = None


@dataclass
class QSOAttempt:
    """An attempt to work a station (may or may not succeed)."""
    target_call: str
    target_grid: Optional[str]
    started: datetime
    ended: Optional[datetime] = None
    
    # Your parameters
    your_snr_at_target: Optional[int] = None  # Their report of you
    target_snr_at_you: Optional[int] = None  # Your report of them
    your_frequency: Optional[int] = None
    band: Optional[str] = None
    
    # Outcome
    succeeded: bool = False
    calls_made: int = 0
    
    # Context
    pileup_size: Optional[int] = None
    your_snr_rank: Optional[int] = None  # Where you ranked in pileup


@dataclass
class QSO:
    """A completed QSO."""
    timestamp: datetime
    callsign: str
    grid: Optional[str]
    band: str
    mode: str
    
    # Signal reports
    sent_snr: Optional[int] = None  # Report you sent
    rcvd_snr: Optional[int] = None  # Report you received
    
    # Additional context
    frequency: Optional[int] = None
    duration_seconds: Optional[int] = None
    calls_before_answer: Optional[int] = None


# =============================================================================
# Real-Time Session Models
# =============================================================================

@dataclass
class PileupMember:
    """A station calling the target in current pileup."""
    callsign: str
    frequency: int
    snr: int  # As YOU hear them
    first_seen: datetime
    last_seen: datetime
    call_count: int = 1
    grid: Optional[str] = None
    
    def update(self, snr: int, frequency: int):
        """Update with new observation."""
        self.snr = snr
        self.frequency = frequency
        self.last_seen = datetime.now()
        self.call_count += 1


@dataclass
class AnsweredCall:
    """Record of a station the target answered."""
    callsign: str
    frequency: int
    snr: int  # Their SNR as you heard them
    answered_at: datetime
    cycle_number: int
    calls_before_answer: int
    snr_rank: int  # Where they ranked (1 = loudest)
    pileup_size: int  # How many were calling
    
    @property
    def was_loudest(self) -> bool:
        return self.snr_rank == 1
    
    @property
    def position_description(self) -> str:
        if self.snr_rank == 1:
            return "loudest"
        elif self.snr_rank <= 3:
            return "top_3"
        elif self.snr_rank <= self.pileup_size // 2:
            return "upper_half"
        else:
            return "lower_half"


@dataclass
class TargetSession:
    """
    Tracking a specific target station during a session.
    Built from real-time observations.
    """
    callsign: str
    grid: Optional[str]
    started: datetime
    frequency: int  # Target's TX frequency
    
    # Counters
    cq_count: int = 0
    qso_count: int = 0
    cycle_count: int = 0
    
    # Current state
    callers: Dict[str, PileupMember] = field(default_factory=dict)
    
    # History
    answered_calls: List[AnsweredCall] = field(default_factory=list)
    
    # Derived
    last_activity: Optional[datetime] = None
    
    @property
    def pileup_size(self) -> int:
        return len(self.callers)
    
    @property
    def qso_rate_per_minute(self) -> float:
        if self.qso_count == 0:
            return 0.0
        elapsed = (datetime.now() - self.started).total_seconds() / 60
        return self.qso_count / max(0.1, elapsed)
    
    def add_caller(self, call: str, freq: int, snr: int, grid: str = None):
        """Add or update a caller in the pileup."""
        if call in self.callers:
            self.callers[call].update(snr, freq)
        else:
            self.callers[call] = PileupMember(
                callsign=call,
                frequency=freq,
                snr=snr,
                first_seen=datetime.now(),
                last_seen=datetime.now(),
                grid=grid
            )
    
    def record_answer(self, answered_call: str, cycle: int):
        """Record that target answered someone."""
        if answered_call not in self.callers:
            return
        
        caller = self.callers[answered_call]
        
        # Calculate SNR rank
        snr_ranking = sorted(
            self.callers.values(),
            key=lambda c: c.snr,
            reverse=True
        )
        snr_rank = next(
            (i + 1 for i, c in enumerate(snr_ranking) if c.callsign == answered_call),
            len(snr_ranking)
        )
        
        answered = AnsweredCall(
            callsign=answered_call,
            frequency=caller.frequency,
            snr=caller.snr,
            answered_at=datetime.now(),
            cycle_number=cycle,
            calls_before_answer=caller.call_count,
            snr_rank=snr_rank,
            pileup_size=len(self.callers)
        )
        self.answered_calls.append(answered)
        self.qso_count += 1
        
        # Remove from active callers
        del self.callers[answered_call]
    
    def prune_stale_callers(self, max_age_seconds: float = 60):
        """Remove callers we haven't seen recently."""
        now = datetime.now()
        stale = [
            call for call, member in self.callers.items()
            if (now - member.last_seen).total_seconds() > max_age_seconds
        ]
        for call in stale:
            del self.callers[call]


# =============================================================================
# Analysis Results
# =============================================================================

@dataclass
class PickingPattern:
    """Analysis result for target picking behavior."""
    style: PickingStyle
    confidence: float  # 0.0 to 1.0
    sample_size: int
    advice: str = ""
    
    # Supporting evidence
    loudest_pick_ratio: float = 0.0
    frequency_correlation: float = 0.0
    region_bias: Optional[str] = None


@dataclass
class SuccessRateBucket:
    """Success rate for a specific condition bucket."""
    bucket_name: str  # e.g., "-10 to -5 dB"
    attempts: int
    successes: int
    
    @property
    def rate(self) -> float:
        return self.successes / max(1, self.attempts)
    
    @property
    def rate_percent(self) -> float:
        return self.rate * 100


@dataclass
class YourStats:
    """Your historical performance statistics."""
    total_qsos: int
    total_attempts: int
    overall_success_rate: float
    
    # Bucketed stats
    success_by_snr: List[SuccessRateBucket] = field(default_factory=list)
    success_by_band: List[SuccessRateBucket] = field(default_factory=list)
    success_by_hour: List[SuccessRateBucket] = field(default_factory=list)
    success_by_continent: List[SuccessRateBucket] = field(default_factory=list)
    
    # Insights
    best_snr_bucket: Optional[str] = None
    best_band: Optional[str] = None
    best_hours: Optional[str] = None
    avg_calls_to_success: float = 0.0
    
    # Date range
    data_from: Optional[datetime] = None
    data_to: Optional[datetime] = None


@dataclass
class TargetHistory:
    """Your history with a specific target station."""
    callsign: str
    times_seen: int
    times_worked: int
    last_seen: Optional[datetime] = None
    last_worked: Optional[datetime] = None
    bands_worked: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        return self.times_worked / max(1, self.times_seen)


# =============================================================================
# ML Model Metadata
# =============================================================================

@dataclass
class ModelMetadata:
    """Metadata for a trained ML model."""
    name: str
    path: Path
    trained_at: datetime
    training_samples: int
    feature_version: str
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    
    # Staleness configuration
    max_age_days: int = 14
    min_new_samples_ratio: float = 0.2
    
    def staleness_score(self, current_samples: int) -> float:
        """
        Calculate staleness score.
        0.0 = fresh, 1.0 = definitely needs retraining.
        """
        # Age factor
        age_days = (datetime.now() - self.trained_at).days
        age_score = min(1.0, age_days / self.max_age_days)
        
        # New data factor
        new_samples = current_samples - self.training_samples
        if self.training_samples > 0:
            new_ratio = new_samples / self.training_samples
            data_score = min(1.0, new_ratio / self.min_new_samples_ratio)
        else:
            data_score = 1.0  # No training samples = stale
        
        return max(age_score, data_score)
    
    @property
    def is_stale(self) -> bool:
        # Can't calculate without current samples, so just check age
        age_days = (datetime.now() - self.trained_at).days
        return age_days > self.max_age_days
    
    def staleness_reason(self, current_samples: int) -> str:
        age_days = (datetime.now() - self.trained_at).days
        new_samples = current_samples - self.training_samples
        
        if age_days > self.max_age_days:
            return f"Model is {age_days} days old (max: {self.max_age_days})"
        elif new_samples > self.training_samples * self.min_new_samples_ratio:
            return f"{new_samples:,} new QSOs since last training"
        else:
            return "Model is current"
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'path': str(self.path),
            'trained_at': self.trained_at.isoformat(),
            'training_samples': self.training_samples,
            'feature_version': self.feature_version,
            'performance_metrics': self.performance_metrics,
            'max_age_days': self.max_age_days,
            'min_new_samples_ratio': self.min_new_samples_ratio,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ModelMetadata':
        return cls(
            name=data['name'],
            path=Path(data['path']),
            trained_at=datetime.fromisoformat(data['trained_at']),
            training_samples=data['training_samples'],
            feature_version=data['feature_version'],
            performance_metrics=data.get('performance_metrics', {}),
            max_age_days=data.get('max_age_days', 14),
            min_new_samples_ratio=data.get('min_new_samples_ratio', 0.2),
        )
    
    def save(self, path: Path):
        """Save metadata to JSON file."""
        import json
        path.write_text(json.dumps(self.to_dict(), indent=2))
    
    @classmethod
    def load(cls, path: Path) -> 'ModelMetadata':
        """Load metadata from JSON file."""
        import json
        data = json.loads(path.read_text())
        return cls.from_dict(data)


# =============================================================================
# Prediction Results
# =============================================================================

@dataclass
class Prediction:
    """A prediction with explanation."""
    probability: float  # 0.0 to 1.0
    model_contribution: float  # What the trained model said
    live_factors: Dict[str, float]  # Real-time adjustments
    explanation: str
    confidence: str = "medium"  # "low", "medium", "high"
    
    @property
    def probability_percent(self) -> float:
        return self.probability * 100


@dataclass
class StrategyRecommendation:
    """A recommended strategy for working a target."""
    target_call: str
    
    # Recommendation
    recommended_frequency: Optional[int] = None
    recommended_action: str = ""  # "call_now", "wait", "try_later"
    
    # Reasoning
    reasons: List[str] = field(default_factory=list)
    
    # Predictions
    success_probability: Optional[Prediction] = None
    estimated_wait_cycles: Optional[int] = None


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class AnalysisConfig:
    """Configuration for analysis windows and limits."""
    
    # Time windows for different analyses (days)
    target_behavior_days: int = 30
    success_rate_days: int = 180
    band_pattern_days: int = 365
    frequency_pattern_days: int = 90
    
    # Data limits
    max_decodes_in_memory: int = 500_000  # ~50MB RAM estimate
    max_qsos_for_analysis: int = 50_000
    
    # Incremental loading
    initial_load_days: int = 90
    background_load: bool = True
    
    # Real-time settings
    pileup_stale_seconds: float = 60.0
    session_timeout_minutes: float = 10.0
    
    def to_dict(self) -> dict:
        return {
            'target_behavior_days': self.target_behavior_days,
            'success_rate_days': self.success_rate_days,
            'band_pattern_days': self.band_pattern_days,
            'frequency_pattern_days': self.frequency_pattern_days,
            'max_decodes_in_memory': self.max_decodes_in_memory,
            'max_qsos_for_analysis': self.max_qsos_for_analysis,
            'initial_load_days': self.initial_load_days,
            'background_load': self.background_load,
            'pileup_stale_seconds': self.pileup_stale_seconds,
            'session_timeout_minutes': self.session_timeout_minutes,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AnalysisConfig':
        return cls(**data)
