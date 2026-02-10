"""
Bayesian Predictor for QSO Predictor v2.0

Combines trained ML models (prior) with real-time observations (likelihood)
to produce updated predictions.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
from datetime import datetime
from typing import Dict, Optional, List

from .models import (
    Prediction, StrategyRecommendation, TargetSession,
    PickingStyle, PickingPattern, PathStatus
)
from .model_manager import ModelManager, PredictionCache
from .session_tracker import SessionTracker

logger = logging.getLogger(__name__)


class BayesianPredictor:
    """
    Combine trained model predictions with live observations.
    
    The trained model provides a prior probability based on historical patterns.
    Live observations (pileup state, target behavior, your position) provide
    likelihood factors that update the prediction.
    
    P(success | live_data) ∝ P(success | model) × P(live_data | success)
    """
    
    # Default prior when no model available
    DEFAULT_PRIOR = 0.20  # 20% base success rate
    
    # Live factor weights
    FACTOR_WEIGHTS = {
        'pileup': 1.0,
        'snr_rank': 1.0,
        'behavior_match': 1.0,
        'path': 1.5,  # Path status is particularly important
        'persistence': 0.8,
    }
    
    def __init__(self, 
                 model_manager: ModelManager,
                 session_tracker: SessionTracker):
        """
        Initialize predictor.
        
        Args:
            model_manager: Manager for trained models
            session_tracker: Real-time session tracker
        """
        self.model_manager = model_manager
        self.session_tracker = session_tracker
        self.cache = PredictionCache(max_size=500, ttl_seconds=30.0)
    
    def predict_success(self,
                        target_call: str,
                        features: Dict,
                        path_status: PathStatus = PathStatus.UNKNOWN) -> Prediction:
        """
        Predict probability of QSO success.
        
        Args:
            target_call: Target station callsign
            features: Features for model (target_snr, your_snr, band, etc.)
            path_status: Your current path status to target
            
        Returns:
            Prediction with probability and explanation
        """
        # Check cache
        cache_key = self.cache.make_key('success', {
            'target': target_call,
            'path': path_status.value,
            **features
        })
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        # Get model prediction (prior)
        model_prob = self._get_model_probability('success_model', features)
        
        # Get live session data
        pileup_info = self.session_tracker.get_pileup_info()
        behavior_info = self.session_tracker.get_target_behavior()
        your_status = self.session_tracker.get_your_status()
        
        # Calculate live factors
        live_factors = self._calculate_live_factors(
            pileup_info=pileup_info,
            behavior_info=behavior_info,
            your_status=your_status,
            path_status=path_status,
            features=features
        )
        
        # Bayesian update
        posterior = self._bayesian_update(model_prob, live_factors)
        
        # Determine confidence
        confidence = self._assess_confidence(
            model_available=self.model_manager.has_model('success_model'),
            live_data_available=pileup_info is not None,
            sample_size=behavior_info.get('qso_count', 0) if behavior_info else 0
        )
        
        # Generate explanation
        explanation = self._explain_prediction(
            model_prob, live_factors, posterior, path_status
        )
        
        result = Prediction(
            probability=posterior,
            model_contribution=model_prob,
            live_factors=live_factors,
            explanation=explanation,
            confidence=confidence
        )
        
        # Cache result
        self.cache.set(cache_key, result)
        
        return result
    
    def _get_model_probability(self, model_name: str, features: Dict) -> float:
        """Get prediction from trained model."""
        result = self.model_manager.predict(model_name, features)
        
        if result is None:
            logger.debug(f"No model available for {model_name}, using default prior")
            return self.DEFAULT_PRIOR
        
        # Handle binary classification
        prediction = result['prediction']
        confidence = result.get('confidence', 0.5)
        
        if prediction == 1 or prediction == True:
            return confidence
        else:
            return 1.0 - confidence
    
    def _calculate_live_factors(self,
                                pileup_info: Optional[Dict],
                                behavior_info: Optional[Dict],
                                your_status: Dict,
                                path_status: PathStatus,
                                features: Dict) -> Dict[str, float]:
        """
        Calculate factors from live observations.
        
        Each factor is a multiplier:
        - 1.0 = neutral (no change)
        - > 1.0 = boost probability
        - < 1.0 = reduce probability
        """
        factors = {}
        
        # Factor 1: Pileup size
        if pileup_info:
            size = pileup_info.get('size', 0)
            if size == 0:
                factors['pileup'] = 1.5  # No competition!
            elif size <= 3:
                factors['pileup'] = 1.2  # Light pileup
            elif size <= 6:
                factors['pileup'] = 1.0  # Normal
            elif size <= 10:
                factors['pileup'] = 0.7  # Busy
            else:
                factors['pileup'] = 0.4  # Heavy pileup
        
        # Factor 2: Your SNR rank in pileup
        if your_status.get('in_pileup') and your_status.get('rank'):
            rank = your_status['rank']
            total = your_status.get('total', 10)
            
            # Handle unknown rank (when TX but can't hear ourselves)
            if rank == '?' or not isinstance(rank, (int, float)):
                factors['snr_rank'] = 1.0  # Neutral - unknown
            elif rank == 1:
                factors['snr_rank'] = 1.4  # Loudest!
            elif rank <= 3:
                factors['snr_rank'] = 1.2  # Top 3
            elif rank <= total // 2:
                factors['snr_rank'] = 1.0  # Upper half
            else:
                factors['snr_rank'] = 0.7  # Lower half
        
        # Factor 3: Behavior pattern match
        if behavior_info and behavior_info.get('pattern'):
            pattern: PickingPattern = behavior_info['pattern']
            
            if pattern.style == PickingStyle.LOUDEST_FIRST:
                rank = your_status.get('rank', 99)
                # Handle unknown rank
                if rank == '?' or not isinstance(rank, (int, float)):
                    factors['behavior_match'] = 1.0  # Neutral
                elif rank == 1:
                    factors['behavior_match'] = 1.5
                elif rank <= 3:
                    factors['behavior_match'] = 1.1
                else:
                    factors['behavior_match'] = 0.6
                    
            elif pattern.style == PickingStyle.METHODICAL_LOW_HIGH:
                your_freq = your_status.get('your_frequency', 0)
                if pileup_info and pileup_info.get('frequency_range'):
                    low, high = pileup_info['frequency_range']
                    if your_freq <= low + (high - low) * 0.3:
                        factors['behavior_match'] = 1.3  # You're in the right position
                    else:
                        factors['behavior_match'] = 0.8
                        
            elif pattern.style == PickingStyle.METHODICAL_HIGH_LOW:
                your_freq = your_status.get('your_frequency', 0)
                if pileup_info and pileup_info.get('frequency_range'):
                    low, high = pileup_info['frequency_range']
                    if your_freq >= low + (high - low) * 0.7:
                        factors['behavior_match'] = 1.3
                    else:
                        factors['behavior_match'] = 0.8
                        
            elif pattern.style == PickingStyle.RANDOM:
                # Random = persistence matters
                calls_made = your_status.get('calls_made', 0)
                if calls_made >= 3:
                    factors['behavior_match'] = 1.1
                else:
                    factors['behavior_match'] = 1.0
        
        # Factor 4: Path status (most important)
        if path_status == PathStatus.CONNECTED:
            factors['path'] = 2.0  # They've heard you!
        elif path_status == PathStatus.PATH_OPEN:
            factors['path'] = 1.3  # Path exists
        elif path_status == PathStatus.NO_PATH:
            factors['path'] = 0.3  # Not reaching them
        else:
            factors['path'] = 1.0  # Unknown
        
        # Factor 5: Persistence (more calls = slightly lower per-call odds but cumulative helps)
        calls_made = your_status.get('calls_made', 0)
        if calls_made == 0:
            factors['persistence'] = 1.0
        elif calls_made <= 2:
            factors['persistence'] = 1.05
        elif calls_made <= 5:
            factors['persistence'] = 1.0  # Normal
        else:
            factors['persistence'] = 0.95  # Diminishing returns
        
        return factors
    
    def _bayesian_update(self, prior: float, factors: Dict[str, float]) -> float:
        """
        Combine prior with likelihood factors.
        
        Uses weighted geometric mean of factors.
        """
        # Start with prior
        log_odds = self._prob_to_log_odds(prior)
        
        # Apply each factor as a log-odds adjustment
        import math
        
        for factor_name, factor_value in factors.items():
            weight = self.FACTOR_WEIGHTS.get(factor_name, 1.0)
            # Convert factor to log-odds adjustment
            adjustment = math.log(factor_value) * weight
            log_odds += adjustment
        
        # Convert back to probability
        posterior = self._log_odds_to_prob(log_odds)
        
        # Clamp to reasonable range
        return max(0.01, min(0.99, posterior))
    
    @staticmethod
    def _prob_to_log_odds(p: float) -> float:
        """Convert probability to log-odds."""
        import math
        p = max(0.001, min(0.999, p))  # Avoid log(0)
        return math.log(p / (1 - p))
    
    @staticmethod
    def _log_odds_to_prob(log_odds: float) -> float:
        """Convert log-odds to probability."""
        import math
        return 1.0 / (1.0 + math.exp(-log_odds))
    
    def _assess_confidence(self,
                           model_available: bool,
                           live_data_available: bool,
                           sample_size: int) -> str:
        """Assess confidence in prediction."""
        if model_available and live_data_available and sample_size >= 5:
            return "high"
        elif model_available or (live_data_available and sample_size >= 3):
            return "medium"
        else:
            return "low"
    
    def _explain_prediction(self,
                            model_prob: float,
                            factors: Dict[str, float],
                            posterior: float,
                            path_status: PathStatus) -> str:
        """Generate human-readable explanation."""
        parts = []
        
        # Model contribution
        if self.model_manager.has_model('success_model'):
            parts.append(f"Model: {model_prob:.0%}")
        else:
            parts.append(f"Base: {model_prob:.0%}")
        
        # Significant factors
        for name, value in factors.items():
            if value < 0.7:
                parts.append(f"↓{name}")
            elif value > 1.3:
                parts.append(f"↑{name}")
        
        # Path status callout
        if path_status == PathStatus.CONNECTED:
            parts.append("★CONNECTED")
        elif path_status == PathStatus.NO_PATH:
            parts.append("⚠no_path")
        
        # Final probability
        parts.append(f"→ {posterior:.0%}")
        
        return " | ".join(parts)
    
    def get_strategy(self, target_call: str, path_status: PathStatus = PathStatus.UNKNOWN,
                     target_competition: str = "") -> StrategyRecommendation:
        """
        Get recommended strategy for working a target.
        
        Args:
            target_call: Target station callsign
            path_status: Current path status
            target_competition: v2.2.0 - Target-side competition string from PSK Reporter
                               e.g. "High (5)", "PILEUP (8)", "Low (1)"
            
        Returns:
            StrategyRecommendation with action and reasoning
        """
        pileup_info = self.session_tracker.get_pileup_info()
        behavior_info = self.session_tracker.get_target_behavior()
        your_status = self.session_tracker.get_your_status()
        
        reasons = []
        recommended_action = "call_now"
        recommended_frequency = None
        
        # Check path status first - most important factor
        if path_status == PathStatus.NO_PATH:
            recommended_action = "try_later"
            reasons.append("No path or no TX")
        elif path_status == PathStatus.CONNECTED:
            reasons.append("Target hears you!")
        elif path_status == PathStatus.PATH_OPEN:
            reasons.append("Path is open")
        
        # v2.2.0: Determine effective competition (max of local and target-side)
        local_size = pileup_info.get('size', 0) if pileup_info else 0
        target_count = self._parse_target_competition_count(target_competition)
        effective_size = max(local_size, target_count)
        
        # Check pileup state using effective competition (only if path is OK)
        if recommended_action != "try_later":
            if effective_size == 0:
                reasons.append("No competition")
            elif effective_size > 10:
                reasons.append(f"Heavy pileup ({effective_size} stations)")
                if path_status != PathStatus.CONNECTED:
                    recommended_action = "wait"
            elif effective_size >= 4:
                # v2.2.0: Moderate competition — flag it
                if target_count > local_size:
                    reasons.append(f"Hidden pileup at target ({target_count} stations)")
                else:
                    reasons.append(f"Moderate competition ({effective_size} stations)")
            elif effective_size >= 1:
                if target_count > local_size:
                    reasons.append(f"Competition at target ({target_count})")
                else:
                    reasons.append(f"Light competition ({effective_size})")
            
            # Your position
            if pileup_info and your_status.get('rank'):
                rank = your_status['rank']
                if rank == '?':
                    reasons.append("You're calling")
                elif rank == 1:
                    reasons.append("You're the loudest signal")
                elif isinstance(rank, int) and rank <= 3:
                    reasons.append(f"You're #{rank} by signal strength")
                elif isinstance(rank, int):
                    reasons.append(f"You're #{rank}/{local_size} - consider waiting")
        
        # Check behavior pattern
        if behavior_info and behavior_info.get('pattern') and recommended_action != "try_later":
            pattern: PickingPattern = behavior_info['pattern']
            
            if pattern.style == PickingStyle.LOUDEST_FIRST:
                reasons.append("Target picks loudest first")
                rank = your_status.get('rank', 99)
                if isinstance(rank, int) and rank > 3:
                    reasons.append("Consider QSYing when conditions improve")
                    
            elif pattern.style in [PickingStyle.METHODICAL_LOW_HIGH, 
                                   PickingStyle.METHODICAL_HIGH_LOW]:
                reasons.append(f"Target working {pattern.style.value.replace('_', ' ')}")
                # Suggest optimal frequency position
                if pileup_info and pileup_info.get('frequency_range'):
                    low, high = pileup_info['frequency_range']
                    if pattern.style == PickingStyle.METHODICAL_LOW_HIGH:
                        recommended_frequency = low - 60  # Below the pack
                        reasons.append("Position at lower frequency")
                    else:
                        recommended_frequency = high + 60  # Above the pack
                        reasons.append("Position at higher frequency")
                        
            elif pattern.style == PickingStyle.RANDOM:
                reasons.append("No clear pattern - persistence helps")
        
        # QSO rate insight
        if behavior_info and recommended_action != "try_later":
            rate = behavior_info.get('qso_rate', 0)
            if rate > 0:
                if rate >= 2.0:
                    reasons.append(f"Fast QSO rate ({rate:.1f}/min)")
                elif rate >= 1.0:
                    reasons.append(f"Steady QSO rate ({rate:.1f}/min)")
                else:
                    reasons.append(f"Slow QSO rate ({rate:.1f}/min)")
        
        return StrategyRecommendation(
            target_call=target_call,
            recommended_frequency=recommended_frequency,
            recommended_action=recommended_action,
            reasons=reasons,
        )
    
    @staticmethod
    def _parse_target_competition_count(competition_str: str) -> int:
        """Extract numeric count from competition string like 'High (5)'."""
        if not competition_str or '(' not in competition_str:
            return 0
        try:
            return int(competition_str.split('(')[1].split(')')[0])
        except (ValueError, IndexError):
            return 0
    
    def invalidate_cache(self, target_call: str = None):
        """
        Invalidate cached predictions.
        
        Args:
            target_call: If provided, only invalidate for this target.
                        If None, invalidate all.
        """
        if target_call:
            self.cache.invalidate(target_call)
        else:
            self.cache.invalidate()


class HeuristicPredictor:
    """
    Fallback predictor using heuristics only (no ML model).
    
    Use this when:
    - No trained model available
    - User wants "purist mode" without ML
    - Quick predictions without model loading overhead
    """
    
    def __init__(self, session_tracker: SessionTracker):
        """
        Initialize heuristic predictor.
        
        Args:
            session_tracker: Real-time session tracker
        """
        self.session_tracker = session_tracker
    
    def predict_success(self,
                        target_call: str,
                        features: Dict,
                        path_status: PathStatus = PathStatus.UNKNOWN) -> Prediction:
        """
        Predict success using heuristics only.
        
        Args:
            target_call: Target station callsign
            features: Dict with feature values including 'target_snr'
            path_status: Your path status
            
        Returns:
            Prediction based on heuristics
        """
        # Extract SNR from features
        try:
            target_snr = int(features.get('target_snr', -15))
        except (TypeError, ValueError):
            target_snr = -15
        
        # Base probability from SNR
        if target_snr >= 0:
            base = 0.40
        elif target_snr >= -5:
            base = 0.35
        elif target_snr >= -10:
            base = 0.25
        elif target_snr >= -15:
            base = 0.15
        else:
            base = 0.05
        
        factors = {}
        
        # Pileup factor
        pileup_info = self.session_tracker.get_pileup_info()
        if pileup_info:
            size = pileup_info.get('size', 0)
            if size == 0:
                factors['pileup'] = 1.5
            elif size <= 5:
                factors['pileup'] = 1.0
            elif size <= 10:
                factors['pileup'] = 0.7
            else:
                factors['pileup'] = 0.4
        
        # Path factor
        if path_status == PathStatus.CONNECTED:
            factors['path'] = 2.0
        elif path_status == PathStatus.PATH_OPEN:
            factors['path'] = 1.3
        elif path_status == PathStatus.NO_PATH:
            factors['path'] = 0.2
        
        # Apply factors
        probability = base
        for factor in factors.values():
            probability *= factor
        
        probability = max(0.01, min(0.99, probability))
        
        explanation = f"Heuristic: SNR {target_snr} dB"
        if path_status != PathStatus.UNKNOWN:
            explanation += f" | Path: {path_status.value}"
        explanation += f" → {probability:.0%}"
        
        return Prediction(
            probability=probability,
            model_contribution=base,
            live_factors=factors,
            explanation=explanation,
            confidence="low"  # Heuristic = lower confidence
        )
    
    def get_strategy(self, target_call: str, path_status: PathStatus = PathStatus.UNKNOWN,
                     target_competition: str = "") -> StrategyRecommendation:
        """
        Get strategy recommendation using heuristics.
        
        Args:
            target_call: Target callsign
            path_status: Current path status
            target_competition: v2.2.0 - Target-side competition from PSK Reporter
            
        Returns:
            Strategy recommendation
        """
        # Get pileup info
        pileup_info = self.session_tracker.get_pileup_info()
        your_status = self.session_tracker.get_your_status()
        
        reasons = []
        action = 'call_now'  # Default
        
        # Check path status first - most important factor
        if path_status == PathStatus.NO_PATH:
            action = 'try_later'
            reasons.append("No path to target")
        elif path_status == PathStatus.CONNECTED:
            action = 'call_now'
            reasons.append("Target hears you!")
        elif path_status == PathStatus.PATH_OPEN:
            action = 'call_now'
            reasons.append("Path is open")
        
        # v2.2.0: Effective competition = max of local and target-side
        local_size = pileup_info.get('size', 0) if pileup_info else 0
        target_count = 0
        if target_competition and '(' in target_competition:
            try:
                target_count = int(target_competition.split('(')[1].split(')')[0])
            except (ValueError, IndexError):
                pass
        effective_size = max(local_size, target_count)
        
        if action != 'try_later':  # Don't override no-path
            if effective_size == 0:
                reasons.append("No competition")
            elif effective_size <= 3:
                if target_count > local_size:
                    reasons.append(f"Competition at target ({target_count})")
                else:
                    reasons.append(f"Light pileup ({effective_size} callers)")
            elif effective_size <= 8:
                if target_count > local_size:
                    reasons.append(f"Hidden pileup at target ({target_count} stations)")
                else:
                    reasons.append(f"Moderate pileup ({effective_size} callers)")
            else:
                if action != 'call_now' or path_status == PathStatus.UNKNOWN:
                    action = 'wait'
                if target_count > local_size:
                    reasons.append(f"Heavy hidden pileup ({target_count} at target)")
                else:
                    reasons.append(f"Heavy pileup ({effective_size} callers)")
        
        # Check your rank
        if your_status.get('in_pileup'):
            rank = your_status.get('rank', 99)
            if rank == '?':
                reasons.append("You're calling")
            elif rank == 1:
                reasons.append("You're loudest - good position")
            elif isinstance(rank, int) and rank <= 3:
                reasons.append(f"Rank #{rank} - decent position")
        
        return StrategyRecommendation(
            target_call=target_call,
            recommended_action=action,
            recommended_frequency=None,
            reasons=reasons
        )
