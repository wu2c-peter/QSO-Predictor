"""
Bayesian Behavior Predictor for QSO Predictor v2.0

Combines:
1. Historical patterns (have we seen this DX before?)
2. ML model predictions (trained on your log history)
3. Live Bayesian updates (refine as we observe)

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
from collections import defaultdict

import numpy as np

from local_intel.models import PickingStyle, AnsweredCall

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BehaviorPrior:
    """Prior belief about a station's picking behavior."""
    style_probs: Dict[str, float]  # style_name -> probability
    confidence: float  # 0-1, how confident we are
    source: str  # 'historical', 'ml_model', 'default'
    observations: int = 0  # How many QSOs contributed to this
    metadata: Optional[Dict] = None  # Extra info (e.g., prefix stats)
    
    @property
    def most_likely_style(self) -> str:
        if not self.style_probs:
            return 'unknown'
        return max(self.style_probs, key=self.style_probs.get)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'BehaviorPrior':
        return cls(**d)


@dataclass 
class HistoricalRecord:
    """Historical behavior record for a specific callsign."""
    callsign: str
    
    # Picking style observations
    observations: int = 0
    loudest_first_count: int = 0
    methodical_count: int = 0
    random_count: int = 0
    last_seen: Optional[str] = None  # ISO datetime
    
    # Activity traits for persona matching
    sessions_seen: int = 0          # Number of distinct operating sessions
    total_qsos: int = 0             # Total QSOs observed (started)
    completed_qsos: int = 0         # QSOs that ended with 73/RR73
    abandoned_qsos: int = 0         # QSOs started but not completed
    total_cqs: int = 0              # Total CQ calls observed
    total_session_seconds: float = 0  # Total time across all sessions
    
    # Picking detail (who they pick when abandoning)
    rare_prefix_picks: int = 0      # Times they picked a rarer prefix mid-QSO
    
    @property
    def style_distribution(self) -> Dict[str, float]:
        """Get normalized probability distribution."""
        total = self.loudest_first_count + self.methodical_count + self.random_count
        if total == 0:
            return {'loudest_first': 0.33, 'methodical': 0.33, 'random': 0.34}
        return {
            'loudest_first': self.loudest_first_count / total,
            'methodical': self.methodical_count / total,
            'random': self.random_count / total,
        }
    
    @property
    def qso_rate(self) -> float:
        """QSOs per minute (0 if no session data)."""
        if self.total_session_seconds <= 0:
            return 0.0
        return (self.total_qsos / self.total_session_seconds) * 60
    
    @property
    def completion_rate(self) -> float:
        """Fraction of QSOs completed (0-1)."""
        if self.total_qsos <= 0:
            return 0.0
        return self.completed_qsos / self.total_qsos
    
    @property
    def cq_to_qso_ratio(self) -> float:
        """How many CQs per QSO (higher = less efficient/more patient)."""
        if self.total_qsos <= 0:
            return 0.0
        return self.total_cqs / self.total_qsos
    
    @property
    def avg_session_minutes(self) -> float:
        """Average session duration in minutes."""
        if self.sessions_seen <= 0:
            return 0.0
        return (self.total_session_seconds / self.sessions_seen) / 60
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'HistoricalRecord':
        # Handle legacy records without new fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)


# =============================================================================
# Persona Definitions
# =============================================================================

@dataclass
class Persona:
    """
    Behavioral persona representing a cluster of similar operating styles.
    
    Used to predict picking behavior for unknown stations based on
    observable activity traits.
    """
    name: str
    description: str
    
    # Trait thresholds for matching (None = don't care)
    min_qso_rate: Optional[float] = None      # QSOs/minute
    max_qso_rate: Optional[float] = None
    min_completion_rate: Optional[float] = None  # 0-1
    max_completion_rate: Optional[float] = None
    min_cq_ratio: Optional[float] = None      # CQs per QSO
    max_cq_ratio: Optional[float] = None
    
    # Expected picking behavior for this persona
    picking_probs: Dict[str, float] = field(default_factory=dict)
    
    def matches(self, record: HistoricalRecord) -> Tuple[bool, float]:
        """
        Check if a station's behavior matches this persona.
        
        Returns:
            (matches: bool, score: float) - score is 0-1 quality of match
        """
        if record.sessions_seen == 0 or record.total_qsos < 3:
            return False, 0.0
        
        score = 0.0
        checks = 0
        
        # Check QSO rate
        if self.min_qso_rate is not None or self.max_qso_rate is not None:
            checks += 1
            rate = record.qso_rate
            if self.min_qso_rate and rate < self.min_qso_rate:
                return False, 0.0
            if self.max_qso_rate and rate > self.max_qso_rate:
                return False, 0.0
            score += 1.0
        
        # Check completion rate
        if self.min_completion_rate is not None or self.max_completion_rate is not None:
            checks += 1
            comp = record.completion_rate
            if self.min_completion_rate and comp < self.min_completion_rate:
                return False, 0.0
            if self.max_completion_rate and comp > self.max_completion_rate:
                return False, 0.0
            score += 1.0
        
        # Check CQ ratio
        if self.min_cq_ratio is not None or self.max_cq_ratio is not None:
            checks += 1
            ratio = record.cq_to_qso_ratio
            if self.min_cq_ratio and ratio < self.min_cq_ratio:
                return False, 0.0
            if self.max_cq_ratio and ratio > self.max_cq_ratio:
                return False, 0.0
            score += 1.0
        
        if checks == 0:
            return True, 0.5  # No constraints = weak match
        
        return True, score / checks


# Pre-defined personas based on common operating styles
PERSONAS = [
    Persona(
        name="contest_op",
        description="High-rate contester, picks loudest for efficiency",
        min_qso_rate=2.0,
        min_completion_rate=0.70,
        picking_probs={'loudest_first': 0.75, 'methodical': 0.15, 'random': 0.10},
    ),
    Persona(
        name="auto_seq_runner",
        description="Steady runner using auto-sequence, fair/first-decoded",
        min_qso_rate=1.0,
        max_qso_rate=2.5,
        min_completion_rate=0.80,
        picking_probs={'loudest_first': 0.30, 'methodical': 0.40, 'random': 0.30},
    ),
    Persona(
        name="dx_hunter",
        description="Chases rare DX, abandons QSOs for better catches",
        max_completion_rate=0.50,
        picking_probs={'loudest_first': 0.40, 'methodical': 0.20, 'random': 0.40},
    ),
    Persona(
        name="casual_op",
        description="Relaxed pace, finishes QSOs, fair/methodical picking",
        max_qso_rate=1.0,
        min_completion_rate=0.75,
        picking_probs={'loudest_first': 0.25, 'methodical': 0.50, 'random': 0.25},
    ),
    Persona(
        name="big_gun",
        description="High power/antenna, big pileups, tends toward loudest",
        min_qso_rate=1.5,
        min_cq_ratio=1.5,  # Lots of CQs = big pileup each time
        picking_probs={'loudest_first': 0.65, 'methodical': 0.25, 'random': 0.10},
    ),
]


def find_best_persona(record: HistoricalRecord) -> Optional[Tuple[Persona, float]]:
    """
    Find the best matching persona for a station's behavior.
    
    Args:
        record: Historical record with activity traits
        
    Returns:
        (persona, score) tuple or None if no match
    """
    best_match = None
    best_score = 0.0
    
    for persona in PERSONAS:
        matches, score = persona.matches(record)
        if matches and score > best_score:
            best_match = persona
            best_score = score
    
    if best_match:
        return best_match, best_score
    return None


# =============================================================================
# Main Predictor Class
# =============================================================================

class BehaviorPredictor:
    """
    Bayesian behavior predictor combining historical, ML, and live data.
    
    Usage:
        predictor = BehaviorPredictor(model_manager)
        
        # Get initial prediction for a DX station
        prior = predictor.get_prior("JA1ABC")
        
        # Update with live observations
        posterior = predictor.update_with_observation(
            "JA1ABC",
            answered_call=answered,
            pileup_snapshot=pileup
        )
    """
    
    # Default prior when no other info available
    DEFAULT_PRIOR = {
        'loudest_first': 0.50,  # Most common behavior
        'methodical': 0.30,
        'random': 0.20,
    }
    
    # Likelihood of picking the loudest given each style
    # P(picked_loudest | style)
    LOUDEST_PICK_LIKELIHOOD = {
        'loudest_first': 0.85,
        'methodical': 0.40,  # Sometimes aligns with sweep
        'random': 0.33,      # Equal chance
    }
    
    # Likelihood of sequential frequency pick given each style
    SEQUENTIAL_PICK_LIKELIHOOD = {
        'loudest_first': 0.30,
        'methodical': 0.80,
        'random': 0.33,
    }
    
    def __init__(self, 
                 model_manager=None,
                 history_path: Path = None):
        """
        Args:
            model_manager: ModelManager for ML predictions
            history_path: Where to store/load historical data
        """
        self.model_manager = model_manager
        self.history_path = history_path or (
            Path.home() / '.qso-predictor' / 'behavior_history.json'
        )
        
        # Track bootstrap state
        self._bootstrap_timestamp_path = self.history_path.parent / 'behavior_bootstrap.timestamp'
        
        # Cache log sources (avoid rediscovering each lookup)
        self._cached_log_sources = None
        self._log_sources_cache_time = None
        
        # In-memory history cache
        self._history: Dict[str, HistoricalRecord] = {}
        
        # Current session beliefs (reset per session)
        self._session_beliefs: Dict[str, BehaviorPrior] = {}
        
        # Accumulated observations for future training
        self._pending_observations: List[Dict] = []
        
        # Prefix statistics cache (built from history)
        self._prefix_stats: Dict[str, Dict] = {}
        self._prefix_stats_dirty = True  # Rebuild when history changes
        
        # Load historical data
        self._load_history()
    
    def _extract_prefix(self, callsign: str) -> str:
        """
        Extract country prefix from callsign for aggregation.
        
        Examples:
            W1ABC -> W
            JA1ABC -> JA
            DL5ABC -> DL
            VK2ABC -> VK
            9A1ABC -> 9A
            3DA0ABC -> 3DA
        """
        import re
        callsign = callsign.upper().strip()
        
        # Match prefix pattern: optional digit, 1-2 letters (stop before trailing digit)
        # This captures country prefix without call area: W, JA, DL, VK, 9A, 3DA, etc.
        match = re.match(r'^(\d?[A-Z]{1,2})(?:[A-Z]|\d)', callsign)
        if match:
            return match.group(1)
        
        # Fallback: just letters (and leading digit if present)
        match = re.match(r'^(\d?[A-Z]{1,2})', callsign)
        if match:
            return match.group(1)
            
        return callsign[:2]  # Last resort: first 2 chars
    
    def _build_prefix_stats(self):
        """Build aggregate statistics by call prefix from history."""
        if not self._prefix_stats_dirty:
            return
        
        self._prefix_stats = {}
        
        for callsign, record in self._history.items():
            if record.observations < 2:
                continue
                
            prefix = self._extract_prefix(callsign)
            
            if prefix not in self._prefix_stats:
                self._prefix_stats[prefix] = {
                    'loudest_first': 0,
                    'methodical': 0,
                    'random': 0,
                    'total_stations': 0,
                    'total_observations': 0,
                }
            
            stats = self._prefix_stats[prefix]
            stats['total_stations'] += 1
            stats['total_observations'] += record.observations
            
            # Add weighted by observations
            stats['loudest_first'] += record.loudest_first_count
            stats['methodical'] += record.methodical_count
            stats['random'] += record.random_count
        
        self._prefix_stats_dirty = False
        print(f"[prefix] Built prefix stats: {len(self._prefix_stats)} prefixes from {len(self._history)} stations")
        logger.debug(f"Built prefix stats for {len(self._prefix_stats)} prefixes")
    
    def _get_prefix_prior(self, callsign: str) -> Optional[BehaviorPrior]:
        """
        Get prediction based on call prefix statistics.
        
        If we've seen other stations with same prefix, use their
        aggregate behavior to predict this unknown station.
        """
        self._build_prefix_stats()
        
        prefix = self._extract_prefix(callsign)
        
        if prefix not in self._prefix_stats:
            print(f"[prefix] {callsign} -> {prefix}: no stations with this prefix yet")
            return None
        
        stats = self._prefix_stats[prefix]
        
        # Need meaningful sample (at least 2 stations with this prefix)
        if stats['total_stations'] < 2:
            print(f"[prefix] {callsign} -> {prefix}: only {stats['total_stations']} station(s), need 2+")
            return None
        
        total = stats['loudest_first'] + stats['methodical'] + stats['random']
        if total == 0:
            return None
        
        # Calculate probabilities
        probs = {
            'loudest_first': stats['loudest_first'] / total,
            'methodical': stats['methodical'] / total,
            'random': stats['random'] / total,
        }
        
        # Confidence based on sample size (cap at 0.7 for prefix-based)
        confidence = min(0.7, stats['total_stations'] / 20)
        
        most_likely = max(probs, key=probs.get)
        print(f"[prefix] {callsign} -> {prefix}: {most_likely} ({probs[most_likely]:.0%}) from {stats['total_stations']} stations")
        
        return BehaviorPrior(
            style_probs=probs,
            confidence=confidence,
            source='ml_model',  # Use ml_model source for UI display
            observations=0,
            metadata={
                'prefix': prefix,
                'sample_stations': stats['total_stations'],
                'sample_observations': stats['total_observations'],
            }
        )
    
    def _get_persona_prior(self, callsign: str) -> Optional[BehaviorPrior]:
        """
        Get prediction based on persona matching.
        
        If we have enough activity data on this station (sessions, QSOs),
        match them to a behavioral persona and use that persona's
        typical picking behavior as our prior.
        """
        if callsign not in self._history:
            return None
        
        record = self._history[callsign]
        
        # Need activity data (not just picking observations)
        if record.sessions_seen == 0 or record.total_qsos < 3:
            return None
        
        result = find_best_persona(record)
        if not result:
            return None
        
        persona, score = result
        
        # Confidence based on match quality and sample size
        base_confidence = 0.5 + (score * 0.3)  # 0.5-0.8 based on match
        sample_factor = min(1.0, record.total_qsos / 20)  # Scale by sample
        confidence = base_confidence * sample_factor
        
        print(f"[persona] {callsign}: {persona.name} (score={score:.2f}, conf={confidence:.0%})")
        print(f"         rate={record.qso_rate:.1f}/min, completion={record.completion_rate:.0%}")
        
        return BehaviorPrior(
            style_probs=persona.picking_probs.copy(),
            confidence=confidence,
            source='ml_model',  # Use ml_model source for UI
            observations=0,
            metadata={
                'persona': persona.name,
                'persona_description': persona.description,
                'match_score': score,
                'qso_rate': record.qso_rate,
                'completion_rate': record.completion_rate,
            }
        )
    
    def needs_bootstrap(self) -> bool:
        """Check if bootstrap is needed (no history or stale)."""
        # No history at all
        if not self._history:
            return True
        
        # Check if we've ever bootstrapped
        if not self._bootstrap_timestamp_path.exists():
            return True
        
        # Could add: check if ALL.TXT is newer than last bootstrap
        # For now, just bootstrap once
        return False
    
    def mark_bootstrap_complete(self):
        """Mark that bootstrap has been done."""
        try:
            self._bootstrap_timestamp_path.parent.mkdir(parents=True, exist_ok=True)
            self._bootstrap_timestamp_path.write_text(datetime.now().isoformat())
        except Exception as e:
            logger.warning(f"Could not save bootstrap timestamp: {e}")
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    def get_prior(self, callsign: str, features: Dict = None) -> BehaviorPrior:
        """
        Get prior belief about a station's behavior.
        
        Checks in order:
        1. Current session belief (if we've been updating)
        2. Historical record - picking observations (if we've seen this DX picking)
        3. Persona match - activity traits (if we've seen this DX operating)
        4. Prefix-based prediction (aggregate stats for similar calls)
        5. Default prior ("Observing...")
        
        Args:
            callsign: Target callsign
            features: Optional features (reserved for future ML model)
            
        Returns:
            BehaviorPrior with probabilities and confidence
        """
        callsign = callsign.upper()
        
        # Check session cache first
        if callsign in self._session_beliefs:
            return self._session_beliefs[callsign]
        
        # Check historical record for this exact station (picking observations)
        if callsign in self._history:
            record = self._history[callsign]
            if record.observations >= 3:  # Need picking data
                prior = BehaviorPrior(
                    style_probs=record.style_distribution,
                    confidence=min(0.9, record.observations / 20),  # Cap at 0.9
                    source='historical',
                    observations=record.observations
                )
                self._session_beliefs[callsign] = prior
                return prior
        
        # Try persona match (activity traits without picking data)
        persona_prior = self._get_persona_prior(callsign)
        if persona_prior:
            self._session_beliefs[callsign] = persona_prior
            return persona_prior
        
        # Try prefix-based prediction (aggregated from similar calls)
        prefix_prior = self._get_prefix_prior(callsign)
        if prefix_prior:
            self._session_beliefs[callsign] = prefix_prior
            return prefix_prior
        
        # Default prior
        prior = BehaviorPrior(
            style_probs=self.DEFAULT_PRIOR.copy(),
            confidence=0.3,
            source='default',
            observations=0
        )
        self._session_beliefs[callsign] = prior
        return prior
    
    def update_with_observation(self,
                                callsign: str,
                                answered_call: AnsweredCall,
                                pileup_snapshot: Dict[str, Dict] = None) -> BehaviorPrior:
        """
        Update beliefs with a new observation using Bayes' rule.
        
        Args:
            callsign: Target DX callsign
            answered_call: Who they answered
            pileup_snapshot: State of pileup when answer happened
                             {callsign: {'snr': -10, 'freq': 1234}, ...}
        
        Returns:
            Updated BehaviorPrior (posterior)
        """
        callsign = callsign.upper()
        
        # Get current prior
        prior = self.get_prior(callsign)
        
        # Calculate likelihoods for this observation
        likelihoods = self._calculate_likelihoods(answered_call, pileup_snapshot)
        
        # Bayesian update: posterior ∝ likelihood × prior
        posterior_probs = {}
        total = 0.0
        
        for style in prior.style_probs:
            likelihood = likelihoods.get(style, 0.33)
            prior_prob = prior.style_probs[style]
            unnormalized = likelihood * prior_prob
            posterior_probs[style] = unnormalized
            total += unnormalized
        
        # Normalize
        if total > 0:
            for style in posterior_probs:
                posterior_probs[style] /= total
        
        # Create updated prior
        new_confidence = min(0.95, prior.confidence + 0.05)  # Increase with each observation
        
        posterior = BehaviorPrior(
            style_probs=posterior_probs,
            confidence=new_confidence,
            source='bayesian',
            observations=prior.observations + 1
        )
        
        # Cache it
        self._session_beliefs[callsign] = posterior
        
        # Record for future training
        self._record_observation(callsign, answered_call, pileup_snapshot, posterior)
        
        logger.debug(f"Updated {callsign} behavior: {posterior.most_likely_style} "
                    f"(conf={posterior.confidence:.2f})")
        
        return posterior
    
    def get_style_prediction(self, callsign: str) -> Tuple[str, float]:
        """
        Get simple style prediction with confidence.
        
        Returns:
            (style_name, confidence)
        """
        prior = self.get_prior(callsign)
        return prior.most_likely_style, prior.confidence
    
    def end_session(self, callsign: str):
        """
        End observation session for a target.
        Saves accumulated data to history.
        """
        callsign = callsign.upper()
        
        if callsign not in self._session_beliefs:
            return
        
        belief = self._session_beliefs[callsign]
        
        if belief.observations >= 3:
            # Update historical record
            self._update_history(callsign, belief)
        
        # Clear session cache for this call
        del self._session_beliefs[callsign]
    
    def clear_session(self):
        """Clear all session beliefs (e.g., when changing bands)."""
        self._session_beliefs.clear()
    
    def get_pending_training_data(self) -> List[Dict]:
        """Get accumulated observations for training."""
        return self._pending_observations.copy()
    
    def clear_pending_data(self):
        """Clear pending observations after training."""
        self._pending_observations.clear()
    
    # =========================================================================
    # Bayesian Calculations
    # =========================================================================
    
    def _calculate_likelihoods(self,
                               answered: AnsweredCall,
                               pileup: Dict[str, Dict]) -> Dict[str, float]:
        """
        Calculate P(observation | style) for each style.
        """
        likelihoods = {
            'loudest_first': 0.33,
            'methodical': 0.33,
            'random': 0.33,
        }
        
        if not pileup or len(pileup) < 2:
            return likelihoods
        
        # Was the answered station the loudest?
        snr_sorted = sorted(pileup.items(), key=lambda x: x[1].get('snr', -30), reverse=True)
        loudest_call = snr_sorted[0][0] if snr_sorted else None
        was_loudest = (answered.callsign.upper() == loudest_call.upper()) if loudest_call else False
        
        # Was the pick sequential by frequency? (methodical indicator)
        freq_sorted = sorted(pileup.items(), key=lambda x: x[1].get('freq', 1500))
        freq_position = next((i for i, (c, _) in enumerate(freq_sorted) 
                             if c.upper() == answered.callsign.upper()), -1)
        is_freq_edge = freq_position in [0, 1, len(freq_sorted)-1, len(freq_sorted)-2]
        
        # Apply likelihood based on observations
        if was_loudest:
            likelihoods['loudest_first'] = self.LOUDEST_PICK_LIKELIHOOD['loudest_first']
            likelihoods['methodical'] = self.LOUDEST_PICK_LIKELIHOOD['methodical']
            likelihoods['random'] = self.LOUDEST_PICK_LIKELIHOOD['random']
        else:
            # Picked someone other than loudest
            likelihoods['loudest_first'] = 1.0 - self.LOUDEST_PICK_LIKELIHOOD['loudest_first']
            likelihoods['methodical'] = 0.50  # Neutral
            likelihoods['random'] = 0.40
        
        # Adjust for frequency position if applicable
        if is_freq_edge:
            likelihoods['methodical'] *= 1.3
            likelihoods['methodical'] = min(0.95, likelihoods['methodical'])
        
        # Normalize so they sum to ~1 (for numerical stability)
        total = sum(likelihoods.values())
        if total > 0:
            for k in likelihoods:
                likelihoods[k] /= total
        
        return likelihoods
    
    def _get_ml_prior(self, features: Dict) -> Optional[BehaviorPrior]:
        """Get prior from trained ML model."""
        if not self.model_manager:
            return None
        
        try:
            result = self.model_manager.predict('target_behavior', features)
            if result and 'probabilities' in result:
                return BehaviorPrior(
                    style_probs=result['probabilities'],
                    confidence=0.6,  # Moderate confidence from ML
                    source='ml_model',
                    observations=0
                )
        except Exception as e:
            logger.warning(f"ML prediction failed: {e}")
        
        return None
    
    # =========================================================================
    # History Management
    # =========================================================================
    
    def _load_history(self):
        """Load historical behavior records."""
        if not self.history_path.exists():
            logger.info("No behavior history file found, starting fresh")
            return
        
        try:
            with open(self.history_path, 'r') as f:
                data = json.load(f)
            
            for call, record_dict in data.get('records', {}).items():
                self._history[call] = HistoricalRecord.from_dict(record_dict)
            
            logger.info(f"Loaded behavior history for {len(self._history)} stations")
            
        except Exception as e:
            logger.error(f"Failed to load behavior history: {e}")
    
    def _save_history(self):
        """Save historical behavior records."""
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'version': '1.0',
                'updated': datetime.now().isoformat(),
                'records': {call: rec.to_dict() for call, rec in self._history.items()}
            }
            
            with open(self.history_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Invalidate prefix cache so it gets rebuilt
            self._prefix_stats_dirty = True
            
            logger.debug(f"Saved behavior history for {len(self._history)} stations")
            
        except Exception as e:
            logger.error(f"Failed to save behavior history: {e}")
    
    def _update_history(self, callsign: str, belief: BehaviorPrior):
        """Update historical record for a callsign."""
        if callsign not in self._history:
            self._history[callsign] = HistoricalRecord(callsign=callsign)
        
        record = self._history[callsign]
        
        # Increment the most likely style count
        most_likely = belief.most_likely_style
        if most_likely == 'loudest_first':
            record.loudest_first_count += 1
        elif most_likely == 'methodical':
            record.methodical_count += 1
        else:
            record.random_count += 1
        
        record.observations += 1
        record.last_seen = datetime.now().isoformat()
        
        # Save periodically
        if len(self._history) % 10 == 0:
            self._save_history()
    
    def _record_observation(self, 
                           callsign: str,
                           answered: AnsweredCall,
                           pileup: Dict,
                           posterior: BehaviorPrior):
        """Record observation for future training."""
        obs = {
            'timestamp': datetime.now().isoformat(),
            'dx_callsign': callsign,
            'answered_callsign': answered.callsign,
            'answered_snr': answered.snr,
            'answered_freq': answered.frequency,
            'answered_snr_rank': answered.snr_rank,
            'pileup_size': len(pileup) if pileup else 0,
            'inferred_style': posterior.most_likely_style,
            'style_confidence': posterior.confidence,
        }
        self._pending_observations.append(obs)
        
        # Auto-save pending data periodically
        if len(self._pending_observations) >= 100:
            self._save_pending_observations()
    
    def _save_pending_observations(self):
        """Save pending observations for future training."""
        if not self._pending_observations:
            return
        
        try:
            pending_path = self.history_path.parent / 'pending_observations.jsonl'
            with open(pending_path, 'a') as f:
                for obs in self._pending_observations:
                    f.write(json.dumps(obs) + '\n')
            
            logger.info(f"Saved {len(self._pending_observations)} pending observations")
            
        except Exception as e:
            logger.error(f"Failed to save pending observations: {e}")
    
    # =========================================================================
    # Historical Bootstrap
    # =========================================================================
    
    def lookup_station(self, callsign: str, timeout_ms: int = 3000) -> bool:
        """
        On-demand lookup for a specific station.
        
        Called when user clicks a DX we don't have history for.
        Quick targeted search of logs for just this callsign.
        
        Args:
            callsign: DX callsign to look up
            timeout_ms: Max time to spend searching
            
        Returns:
            True if found data, False otherwise
        """
        import time
        from datetime import datetime, timedelta
        from local_intel.log_discovery import LogFileDiscovery
        from local_intel.log_parser import LogParser
        
        callsign = callsign.upper()
        
        # Already have sufficient history?
        if callsign in self._history:
            record = self._history[callsign]
            has_picking = record.observations >= 2
            has_activity = record.sessions_seen >= 1 and record.total_qsos >= 3
            
            if has_picking or has_activity:
                print(f"[lookup] {callsign}: CACHE HIT - {record.observations} picking obs, {record.total_qsos} QSOs, {record.sessions_seen} sessions")
                logger.info(f"[lookup] {callsign}: cache hit")
                return True
        
        start_time = time.time()
        timeout_sec = timeout_ms / 1000.0
        
        # Look back 14 days to handle monthly boundaries
        cutoff_date = datetime.now() - timedelta(days=14)
        
        logger.info(f"[lookup] {callsign}: searching logs (timeout={timeout_ms}ms)")
        print(f"[lookup] {callsign}: searching logs... (cutoff={cutoff_date.strftime('%Y-%m-%d')})")
        
        # Use cached log sources (refresh every 5 minutes)
        if (self._cached_log_sources is None or 
            self._log_sources_cache_time is None or
            (datetime.now() - self._log_sources_cache_time).total_seconds() > 300):
            discovery = LogFileDiscovery()
            self._cached_log_sources = discovery.discover_all_files()
            self._log_sources_cache_time = datetime.now()
            print(f"[lookup] {callsign}: refreshed log sources cache")
        
        sources = list(self._cached_log_sources)  # Copy to avoid modifying cache
        
        if not sources:
            logger.info(f"[lookup] {callsign}: no log files found")
            print(f"[lookup] {callsign}: NO LOG FILES FOUND")
            return False
        
        # Filter and prioritize files:
        # 1. Skip files entirely before cutoff date
        # 2. Prefer files with more recent data
        valid_sources = []
        for s in sources:
            if s.date_range:
                first_date, last_date = s.date_range
                if last_date < cutoff_date:
                    print(f"[lookup] {callsign}: skipping {s.path.name} (ends {last_date.strftime('%Y-%m-%d')}, before cutoff)")
                    continue
            valid_sources.append(s)
        
        if not valid_sources:
            print(f"[lookup] {callsign}: no files with recent data")
            return False
        
        # Sort by recency (most recent last_date first)
        def file_sort_key(s):
            if s.date_range:
                return s.date_range[1]  # last_date
            return s.modified  # Fallback to modified time
        
        valid_sources.sort(key=file_sort_key, reverse=True)
        print(f"[lookup] {callsign}: scanning {len(valid_sources)} files: {[s.path.name for s in valid_sources]}")
        
        parser = LogParser()
        
        SESSION_GAP_SECONDS = 300  # 5 minutes = new session
        
        # Track this DX's activity (both picking AND activity traits)
        callers = {}  # caller -> snr (current pileup)
        answers = []  # list of was_loudest (picking behavior)
        
        # Activity tracking for persona
        messages = []  # (timestamp, is_cq, partner)
        qsos = []  # (partner, completed)
        cq_count = 0
        current_qso_partner = None
        
        decodes_scanned = 0
        matches_found = 0
        
        for source in valid_sources:
            elapsed = time.time() - start_time
            if elapsed > timeout_sec:
                print(f"[lookup] {callsign}: TIMEOUT after {elapsed:.1f}s")
                break
            
            print(f"[lookup] {callsign}: scanning {source.path.name}...")
            file_decodes = 0
            
            try:
                for d in parser.parse_file(source, start_date=cutoff_date, rx_only=False):
                    decodes_scanned += 1
                    file_decodes += 1
                    
                    # Check timeout every 10000 decodes
                    if file_decodes % 10000 == 0:
                        if time.time() - start_time > timeout_sec:
                            print(f"[lookup] {callsign}: timeout mid-file at {file_decodes} decodes")
                            break
                    
                    # Is this our target DX?
                    if d.callsign and d.callsign.upper() == callsign:
                        matches_found += 1
                        
                        if d.is_cq:
                            # DX calling CQ
                            cq_count += 1
                            messages.append((d.timestamp, True, None))
                            callers.clear()  # New CQ = reset pileup
                            current_qso_partner = None
                            
                        elif d.replying_to:
                            # DX answering/working someone
                            answered = d.replying_to.upper()
                            messages.append((d.timestamp, False, answered))
                            
                            msg_upper = (d.message or '').upper()
                            is_73 = '73' in msg_upper or 'RR73' in msg_upper
                            
                            # Track QSO
                            if current_qso_partner == answered:
                                # Continuing same QSO - check for completion
                                if is_73 and qsos:
                                    # Mark last QSO as completed
                                    qsos[-1] = (answered, True)
                            else:
                                # New QSO starting
                                qsos.append((answered, is_73))
                                current_qso_partner = answered
                                
                                # Track picking behavior
                                if callers:
                                    answered_snr = callers.get(answered, -20)
                                    max_snr = max(callers.values())
                                    was_loudest = answered_snr >= max_snr - 1
                                    answers.append(was_loudest)
                                callers.clear()
                    
                    # Someone calling our target?
                    elif d.replying_to and d.replying_to.upper() == callsign:
                        matches_found += 1
                        caller = d.callsign.upper() if d.callsign else None
                        if caller:
                            callers[caller] = d.snr
                
                print(f"[lookup] {callsign}: {source.path.name} -> {file_decodes} decodes, {matches_found} matches")
                
                # If we have enough observations, stop early
                if len(answers) >= 10 and len(qsos) >= 5:
                    print(f"[lookup] {callsign}: have {len(answers)} picking obs, {len(qsos)} QSOs, stopping early")
                    break
                    
            except Exception as e:
                print(f"[lookup] {callsign}: ERROR parsing {source.path.name}: {e}")
        
        # Calculate session info from timestamps
        sessions = []
        current_session_start = None
        current_session_end = None
        
        for ts, is_cq, partner in messages:
            if ts is None:
                continue
            if current_session_start is None:
                current_session_start = ts
                current_session_end = ts
            else:
                gap = (ts - current_session_end).total_seconds()
                if gap > SESSION_GAP_SECONDS:
                    # Save previous session
                    duration = (current_session_end - current_session_start).total_seconds()
                    sessions.append(duration)
                    current_session_start = ts
                current_session_end = ts
        
        # Don't forget last session
        if current_session_start and current_session_end:
            duration = (current_session_end - current_session_start).total_seconds()
            sessions.append(duration)
        
        # Calculate stats
        total_qsos = len(qsos)
        completed_qsos = sum(1 for _, completed in qsos if completed)
        total_session_seconds = sum(sessions)
        sessions_seen = len(sessions)
        
        print(f"[lookup] {callsign}: total {decodes_scanned} decodes, {matches_found} matches, {len(answers)} picking obs")
        print(f"[lookup] {callsign}: activity: {cq_count} CQs, {total_qsos} QSOs ({completed_qsos} completed), {sessions_seen} sessions")
        
        # Build history from what we found (need EITHER picking data OR activity data)
        has_picking_data = len(answers) >= 2
        has_activity_data = total_qsos >= 3 and sessions_seen >= 1
        
        if has_picking_data or has_activity_data:
            if callsign not in self._history:
                self._history[callsign] = HistoricalRecord(callsign=callsign)
            
            record = self._history[callsign]
            record.last_seen = datetime.now().isoformat()
            
            # Activity traits (for persona matching)
            record.sessions_seen = sessions_seen
            record.total_qsos = total_qsos
            record.completed_qsos = completed_qsos
            record.abandoned_qsos = total_qsos - completed_qsos
            record.total_cqs = cq_count
            record.total_session_seconds = total_session_seconds
            
            # Picking behavior
            if has_picking_data:
                loudest_ratio = sum(answers) / len(answers)
                record.observations = len(answers)
                
                if loudest_ratio > 0.7:
                    record.loudest_first_count = len(answers)
                    style = "loudest_first"
                elif loudest_ratio < 0.3:
                    record.random_count = len(answers)
                    style = "random"
                else:
                    record.methodical_count = len(answers)
                    style = "methodical"
            else:
                style = "no picking data"
            
            # Clear session cache to pick up new data
            if callsign in self._session_beliefs:
                del self._session_beliefs[callsign]
            
            self._save_history()
            
            # Check persona match
            persona_result = find_best_persona(record)
            persona_info = ""
            if persona_result:
                persona, score = persona_result
                persona_info = f", persona={persona.name} ({score:.0%})"
            
            print(f"[lookup] {callsign}: SUCCESS! picking={style}, rate={record.qso_rate:.1f}/min, completion={record.completion_rate:.0%}{persona_info}")
            logger.info(f"[lookup] {callsign}: SUCCESS - {len(answers)} picking obs, {total_qsos} QSOs")
            return True
        
        print(f"[lookup] {callsign}: not enough data (picking={len(answers)}, qsos={total_qsos})")
        logger.info(f"[lookup] {callsign}: not enough data")
        return False

    def fast_bootstrap(self, 
                       max_days: int = 14,
                       max_decodes: int = 500000,
                       timeout_seconds: float = 30.0) -> int:
        """
        Fast bootstrap for startup - process recent data only.
        
        Tracks both picking behavior AND activity traits for persona matching:
        - Sessions (5+ min gap = new session)
        - QSO completion rate (look for 73/RR73)
        - QSO rate (QSOs per minute)
        - CQ frequency
        
        Designed to complete within ~30 seconds.
        
        Args:
            max_days: Only look at last N days of data
            max_decodes: Maximum decodes to process
            timeout_seconds: Stop after this many seconds
            
        Returns:
            Number of stations processed
        """
        import time
        from datetime import datetime, timedelta
        from local_intel.log_discovery import LogFileDiscovery
        from local_intel.log_parser import LogParser
        
        SESSION_GAP_SECONDS = 300  # 5 minutes = new session
        
        start_time = time.time()
        cutoff_date = datetime.now() - timedelta(days=max_days)
        
        logger.info(f"Fast bootstrap: last {max_days} days, max {max_decodes} decodes")
        print(f"[bootstrap] Starting: last {max_days} days, max {max_decodes} decodes")
        
        # Discover log files
        discovery = LogFileDiscovery()
        sources = discovery.discover_all_files()
        
        if not sources:
            logger.info("No log files found for bootstrap")
            return 0
        
        # Parse decodes (newest first, with limits)
        parser = LogParser()
        all_decodes = []
        
        # Sources are sorted newest first
        for source in sources:
            if time.time() - start_time > timeout_seconds * 0.3:  # Use 30% of time for parsing
                break
                
            for decode in parser.parse_file(source, start_date=cutoff_date, rx_only=False):
                all_decodes.append(decode)
                if len(all_decodes) >= max_decodes:
                    break
            
            if len(all_decodes) >= max_decodes:
                break
        
        if not all_decodes:
            logger.info("No recent decodes found")
            return 0
        
        logger.info(f"Parsed {len(all_decodes)} decodes in {time.time() - start_time:.1f}s")
        print(f"[bootstrap] Parsed {len(all_decodes)} decodes in {time.time() - start_time:.1f}s")
        
        # Sort by timestamp for session detection
        all_decodes.sort(key=lambda d: d.timestamp or datetime.min)
        
        # First pass: find DX stations (anyone who CQ'd)
        dx_stations = set()
        for d in all_decodes:
            if d.is_cq and d.callsign:
                dx_stations.add(d.callsign.upper())
        
        if not dx_stations:
            logger.info("No DX stations found")
            return 0
        
        print(f"[bootstrap] Found {len(dx_stations)} DX stations")
        
        # Track activity per DX station
        # dx_data[call] = {
        #   'messages': [(timestamp, message, replying_to)],
        #   'callers': {caller: snr},  # Current callers in pileup
        #   'answers': [was_loudest],  # Picking observations
        #   'qsos': [(partner, completed)],  # QSOs tracked
        #   'cqs': int,
        # }
        dx_data = {call: {
            'messages': [],
            'callers': {},
            'answers': [],
            'qsos': [],
            'cqs': 0,
        } for call in dx_stations}
        
        # Second pass: collect all activity
        for d in all_decodes:
            if time.time() - start_time > timeout_seconds * 0.7:  # Stop at 70% of time
                break
            
            # Track CQs
            if d.is_cq and d.callsign:
                call = d.callsign.upper()
                if call in dx_data:
                    dx_data[call]['cqs'] += 1
                    dx_data[call]['messages'].append((d.timestamp, d.message, None))
                    dx_data[call]['callers'].clear()  # New CQ = reset pileup
            
            # Track callers to DX
            elif d.replying_to:
                dx_call = d.replying_to.upper()
                caller = d.callsign.upper() if d.callsign else None
                
                if dx_call in dx_data and caller:
                    dx_data[dx_call]['callers'][caller] = d.snr
                
                # Check if sender is DX answering someone
                if d.callsign:
                    sender = d.callsign.upper()
                    if sender in dx_data:
                        answered = d.replying_to.upper()
                        data = dx_data[sender]
                        
                        # Record message
                        data['messages'].append((d.timestamp, d.message, answered))
                        
                        # Check if this is a new QSO or continuation
                        msg_upper = (d.message or '').upper()
                        is_73 = '73' in msg_upper or 'RR73' in msg_upper
                        
                        # Find if we have an ongoing QSO with this partner
                        ongoing_qso = None
                        for i, (partner, completed) in enumerate(data['qsos']):
                            if partner == answered and not completed:
                                ongoing_qso = i
                                break
                        
                        if ongoing_qso is not None:
                            # Continuation - check for completion
                            if is_73:
                                data['qsos'][ongoing_qso] = (answered, True)
                        else:
                            # New QSO starting
                            data['qsos'].append((answered, is_73))
                            
                            # Track picking behavior
                            callers = data['callers']
                            if callers:
                                answered_snr = callers.get(answered, -20)
                                max_snr = max(callers.values()) if callers else answered_snr
                                was_loudest = answered_snr >= max_snr - 1
                                data['answers'].append(was_loudest)
        
        print(f"[bootstrap] Activity tracking done in {time.time() - start_time:.1f}s")
        
        # Third pass: calculate sessions and build history
        stations_processed = 0
        
        for dx_call, data in dx_data.items():
            if time.time() - start_time > timeout_seconds * 0.95:
                break
            
            messages = data['messages']
            if len(messages) < 3:  # Need some activity
                continue
            
            # Detect sessions based on time gaps
            sessions = []
            current_session_start = None
            current_session_end = None
            
            for ts, msg, partner in messages:
                if ts is None:
                    continue
                    
                if current_session_start is None:
                    current_session_start = ts
                    current_session_end = ts
                else:
                    gap = (ts - current_session_end).total_seconds()
                    if gap > SESSION_GAP_SECONDS:
                        # Save previous session
                        duration = (current_session_end - current_session_start).total_seconds()
                        sessions.append(duration)
                        # Start new session
                        current_session_start = ts
                    current_session_end = ts
            
            # Don't forget last session
            if current_session_start and current_session_end:
                duration = (current_session_end - current_session_start).total_seconds()
                sessions.append(duration)
            
            # Calculate stats
            total_qsos = len(data['qsos'])
            completed_qsos = sum(1 for _, completed in data['qsos'] if completed)
            total_session_seconds = sum(sessions)
            sessions_seen = len(sessions)
            cqs = data['cqs']
            answers = data['answers']
            
            if total_qsos < 2:  # Need minimum activity
                continue
            
            # Update or create history record
            if dx_call not in self._history:
                self._history[dx_call] = HistoricalRecord(callsign=dx_call)
            
            record = self._history[dx_call]
            record.last_seen = datetime.now().isoformat()
            
            # Activity traits
            record.sessions_seen += sessions_seen
            record.total_qsos += total_qsos
            record.completed_qsos += completed_qsos
            record.abandoned_qsos += (total_qsos - completed_qsos)
            record.total_cqs += cqs
            record.total_session_seconds += total_session_seconds
            
            # Picking behavior
            if answers:
                record.observations += len(answers)
                loudest_ratio = sum(answers) / len(answers)
                
                if loudest_ratio > 0.7:
                    record.loudest_first_count += len(answers)
                elif loudest_ratio < 0.3:
                    record.random_count += len(answers)
                else:
                    record.methodical_count += len(answers)
            
            stations_processed += 1
        
        # Save
        self._save_history()
        self._prefix_stats_dirty = True  # Rebuild prefix stats
        
        elapsed = time.time() - start_time
        logger.info(f"Fast bootstrap complete: {stations_processed} stations in {elapsed:.1f}s")
        print(f"[bootstrap] Complete: {stations_processed} stations in {elapsed:.1f}s")
        
        # Print some stats
        total_with_persona = sum(1 for r in self._history.values() 
                                  if r.sessions_seen > 0 and r.total_qsos >= 3)
        print(f"[bootstrap] {total_with_persona} stations have persona traits")
        
        return stations_processed

    def bootstrap_from_history(self, 
                               decodes: List,
                               progress_callback: Callable[[int, int], None] = None) -> int:
        """
        Bootstrap behavior priors from historical ALL.TXT data.
        
        Replays historical DX sessions through the Bayesian updater
        to build up priors for stations we've observed before.
        
        Args:
            decodes: List of Decode objects from ALL.TXT
            progress_callback: Optional callback(processed, total) for progress
            
        Returns:
            Number of DX stations processed
        """
        from training.feature_builders import HistoricalSessionReconstructor
        
        logger.info(f"Bootstrapping behavior history from {len(decodes)} decodes...")
        
        # Reconstruct DX sessions
        reconstructor = HistoricalSessionReconstructor(
            min_qsos_per_session=3,  # Lower threshold for bootstrap
            session_gap_minutes=10
        )
        sessions = reconstructor.reconstruct_sessions(decodes)
        
        logger.info(f"Found {len(sessions)} DX sessions to process")
        
        if not sessions:
            return 0
        
        # Process each session
        stations_processed = set()
        
        for i, session in enumerate(sessions):
            if progress_callback and i % 100 == 0:
                progress_callback(i, len(sessions))
            
            dx_call = session.callsign.upper()
            stations_processed.add(dx_call)
            
            # Build pileup snapshot from session's caller data
            # (we don't have full pileup data from history, so approximate)
            
            # Process each answered call through Bayesian updater
            for answered in session.answered_calls:
                # Create approximate pileup snapshot
                # In historical data, we only know who was answered
                # Use SNR rank as proxy for pileup state
                pileup_snapshot = {
                    answered.callsign: {
                        'snr': answered.snr,
                        'freq': answered.frequency,
                    }
                }
                
                # Add phantom "other callers" based on pileup_size
                # This gives the Bayesian updater something to work with
                if answered.pileup_size > 1:
                    for j in range(min(answered.pileup_size - 1, 5)):
                        phantom_call = f"_CALLER{j}"
                        # If answered wasn't rank 1, there were louder stations
                        if answered.snr_rank > 1 and j < answered.snr_rank - 1:
                            phantom_snr = answered.snr + (answered.snr_rank - j - 1) * 3
                        else:
                            phantom_snr = answered.snr - (j + 1) * 3
                        pileup_snapshot[phantom_call] = {
                            'snr': phantom_snr,
                            'freq': answered.frequency + (j + 1) * 50,
                        }
                
                # Update beliefs
                self.update_with_observation(
                    dx_call,
                    answered,
                    pileup_snapshot
                )
            
            # End session to save to history
            self.end_session(dx_call)
        
        # Save final history
        self._save_history()
        
        # Clear pending observations (we don't need to retrain on bootstrap data)
        self._pending_observations.clear()
        
        logger.info(f"Bootstrapped behavior history for {len(stations_processed)} stations")
        
        return len(stations_processed)
    
    def get_history_stats(self) -> Dict:
        """Get statistics about the behavior history."""
        if not self._history:
            return {'stations': 0, 'total_observations': 0, 'prefixes': 0, 'with_persona': 0}
        
        total_obs = sum(r.observations for r in self._history.values())
        
        style_counts = {
            'loudest_first': 0,
            'methodical': 0,
            'random': 0,
        }
        
        # Count stations with persona data
        with_persona = 0
        persona_counts = {}
        
        for r in self._history.values():
            style = max(r.style_distribution, key=r.style_distribution.get)
            style_counts[style] += 1
            
            # Check for persona data
            if r.sessions_seen > 0 and r.total_qsos >= 3:
                with_persona += 1
                result = find_best_persona(r)
                if result:
                    persona, _ = result
                    persona_counts[persona.name] = persona_counts.get(persona.name, 0) + 1
        
        # Build prefix stats if needed
        self._build_prefix_stats()
        
        return {
            'stations': len(self._history),
            'total_observations': total_obs,
            'style_distribution': style_counts,
            'prefixes': len(self._prefix_stats),
            'with_persona': with_persona,
            'persona_distribution': persona_counts,
        }
    
    def reload_history(self):
        """Reload behavior history from disk."""
        self._history.clear()
        self._session_beliefs.clear()
        self._load_history()
        logger.info(f"Reloaded behavior history: {len(self._history)} stations")


# =============================================================================
# Online Learning Support
# =============================================================================

class OnlineBehaviorLearner:
    """
    Incremental learning for behavior classification.
    
    Uses SGDClassifier which supports partial_fit for online learning.
    Can update model with new observations without full retraining.
    """
    
    def __init__(self, model_path: Path = None):
        self.model_path = model_path or (
            Path.home() / '.qso-predictor' / 'models' / 'behavior_online.pkl'
        )
        self.model = None
        self.scaler = None
        self._classes = ['loudest_first', 'methodical', 'random']
        
    def initialize(self):
        """Initialize or load the online model."""
        try:
            from sklearn.linear_model import SGDClassifier
            from sklearn.preprocessing import StandardScaler
            import joblib
            
            if self.model_path.exists():
                data = joblib.load(self.model_path)
                self.model = data['model']
                self.scaler = data['scaler']
                logger.info("Loaded online behavior model")
            else:
                # Create new model
                self.model = SGDClassifier(
                    loss='log_loss',  # For probability estimates
                    penalty='l2',
                    alpha=0.0001,
                    max_iter=1000,
                    warm_start=True,
                    random_state=42
                )
                self.scaler = StandardScaler()
                logger.info("Created new online behavior model")
                
        except ImportError:
            logger.warning("sklearn not available for online learning")
    
    def partial_fit(self, features: np.ndarray, labels: np.ndarray):
        """
        Incrementally update model with new observations.
        
        Args:
            features: Feature matrix (n_samples, n_features)
            labels: Style labels (n_samples,)
        """
        if self.model is None:
            self.initialize()
        
        if self.model is None:
            return
        
        try:
            # Update scaler incrementally
            self.scaler.partial_fit(features)
            features_scaled = self.scaler.transform(features)
            
            # Update model
            self.model.partial_fit(features_scaled, labels, classes=self._classes)
            
            logger.debug(f"Updated online model with {len(features)} samples")
            
        except Exception as e:
            logger.error(f"Online learning update failed: {e}")
    
    def predict_proba(self, features: np.ndarray) -> Dict[str, float]:
        """Get probability distribution over styles."""
        if self.model is None:
            return {'loudest_first': 0.33, 'methodical': 0.33, 'random': 0.34}
        
        try:
            features_scaled = self.scaler.transform(features.reshape(1, -1))
            probs = self.model.predict_proba(features_scaled)[0]
            return dict(zip(self._classes, probs))
        except Exception as e:
            logger.warning(f"Online prediction failed: {e}")
            return {'loudest_first': 0.33, 'methodical': 0.33, 'random': 0.34}
    
    def save(self):
        """Save model to disk."""
        if self.model is None:
            return
        
        try:
            import joblib
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump({
                'model': self.model,
                'scaler': self.scaler,
            }, self.model_path)
            logger.info(f"Saved online behavior model to {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to save online model: {e}")
