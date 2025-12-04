"""
Feature Builders for QSO Predictor v2.0

Convert raw decode/QSO data into feature matrices for ML training.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

# Import from local_intel (parent directory when running as subprocess)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from local_intel.models import Decode, QSO, TargetSession, AnsweredCall

logger = logging.getLogger(__name__)


# =============================================================================
# Encoding Helpers
# =============================================================================

BAND_ENCODING = {
    '160m': 0, '80m': 1, '60m': 2, '40m': 3, '30m': 4,
    '20m': 5, '17m': 6, '15m': 7, '12m': 8, '10m': 9,
    '6m': 10, '2m': 11, 'unknown': 12
}

CONTINENT_ENCODING = {
    'NA': 0, 'SA': 1, 'EU': 2, 'AF': 3, 'AS': 4, 'OC': 5, 'AN': 6, 'unknown': 7
}

def encode_band(band: str) -> int:
    """Encode band name to integer."""
    return BAND_ENCODING.get(band, 12)

def encode_continent(continent: str) -> int:
    """Encode continent to integer."""
    return CONTINENT_ENCODING.get(continent, 7)

def grid_to_continent(grid: str) -> str:
    """Rough continent estimation from grid square."""
    if not grid or len(grid) < 2:
        return 'unknown'
    
    field = grid[:2].upper()
    
    # Very rough mapping of grid fields to continents
    na_fields = {'CN', 'CO', 'CM', 'DN', 'DO', 'DM', 'DL', 'EN', 'EM', 'EL', 
                 'FN', 'FM', 'FL', 'FK'}
    eu_fields = {'IO', 'IN', 'IM', 'JO', 'JN', 'JM', 'KO', 'KN', 'KM'}
    as_fields = {'PM', 'PN', 'PO', 'OM', 'ON', 'OO', 'NM', 'NN', 'NO', 'MM', 'MN'}
    oc_fields = {'QF', 'QG', 'QH', 'PF', 'PG', 'PH', 'OF', 'OG', 'OH', 'RF', 'RG'}
    sa_fields = {'FG', 'FH', 'FI', 'GG', 'GH', 'GI', 'HG', 'HH', 'HI'}
    af_fields = {'IJ', 'IK', 'IL', 'JJ', 'JK', 'JL', 'KJ', 'KK', 'KL'}
    
    if field in na_fields:
        return 'NA'
    elif field in eu_fields:
        return 'EU'
    elif field in as_fields:
        return 'AS'
    elif field in oc_fields:
        return 'OC'
    elif field in sa_fields:
        return 'SA'
    elif field in af_fields:
        return 'AF'
    else:
        return 'unknown'


# =============================================================================
# QSO Attempt Reconstruction
# =============================================================================

@dataclass
class ReconstructedAttempt:
    """A reconstructed QSO attempt from decode history."""
    target_call: str
    target_grid: Optional[str]
    started: datetime
    ended: datetime
    
    # Your parameters
    your_snr: Optional[int]  # Target's SNR at your QTH
    target_snr: Optional[int]  # Your SNR at target (from their report)
    your_frequency: Optional[int]
    band: str
    
    # Outcome
    succeeded: bool
    calls_made: int
    
    # Context
    hour_utc: int
    pileup_estimate: int  # Estimated competition


class AttemptReconstructor:
    """
    Reconstruct QSO attempts from decode history.
    
    An "attempt" is a sequence of calls you made to a specific target,
    ending either in success (QSO) or abandonment.
    """
    
    def __init__(self, my_callsign: str):
        self.my_callsign = my_callsign.upper()
    
    def reconstruct(self, 
                    decodes: List[Decode], 
                    qsos: List[QSO]) -> List[ReconstructedAttempt]:
        """
        Reconstruct attempts from decode history.
        
        Args:
            decodes: All decodes from logs
            qsos: Completed QSOs
            
        Returns:
            List of reconstructed attempts
        """
        # Build QSO lookup for success detection
        qso_lookup = {}
        for qso in qsos:
            key = (qso.callsign.upper(), qso.timestamp.date())
            qso_lookup[key] = qso
        
        # Group decodes by target
        by_target = defaultdict(list)
        for decode in decodes:
            if decode.replying_to and decode.callsign == self.my_callsign:
                # This is us calling someone
                by_target[decode.replying_to].append(decode)
            elif decode.is_cq and decode.callsign:
                # CQ from a station - track for context
                by_target[decode.callsign].append(decode)
        
        attempts = []
        
        for target_call, target_decodes in by_target.items():
            target_attempts = self._reconstruct_target_attempts(
                target_call, target_decodes, qso_lookup
            )
            attempts.extend(target_attempts)
        
        return attempts
    
    def _reconstruct_target_attempts(self,
                                     target_call: str,
                                     decodes: List[Decode],
                                     qso_lookup: Dict) -> List[ReconstructedAttempt]:
        """Reconstruct attempts for a single target."""
        # Sort by time
        decodes = sorted(decodes, key=lambda d: d.timestamp)
        
        attempts = []
        current_attempt = None
        last_time = None
        
        for decode in decodes:
            # Check if this starts a new attempt (gap > 5 minutes)
            if last_time and (decode.timestamp - last_time) > timedelta(minutes=5):
                if current_attempt:
                    attempts.append(current_attempt)
                current_attempt = None
            
            # Start new attempt if needed
            if current_attempt is None:
                current_attempt = {
                    'target_call': target_call,
                    'started': decode.timestamp,
                    'ended': decode.timestamp,
                    'decodes': [],
                    'my_calls': 0,
                    'target_snr': None,
                    'your_frequency': None,
                    'band': decode.band or 'unknown',
                }
            
            # Update attempt
            current_attempt['ended'] = decode.timestamp
            current_attempt['decodes'].append(decode)
            
            if decode.callsign == self.my_callsign:
                current_attempt['my_calls'] += 1
                current_attempt['your_frequency'] = decode.frequency
            elif decode.callsign == target_call:
                current_attempt['target_snr'] = decode.snr
            
            last_time = decode.timestamp
        
        # Don't forget last attempt
        if current_attempt:
            attempts.append(current_attempt)
        
        # Convert to ReconstructedAttempt objects
        result = []
        for att in attempts:
            if att['my_calls'] == 0:
                continue  # Not actually an attempt
            
            # Check for success
            key = (target_call.upper(), att['started'].date())
            succeeded = key in qso_lookup
            
            # Estimate pileup (other stations calling same target)
            pileup = self._estimate_pileup(att['decodes'], target_call)
            
            result.append(ReconstructedAttempt(
                target_call=target_call,
                target_grid=None,  # Would need to extract from decodes
                started=att['started'],
                ended=att['ended'],
                your_snr=att['target_snr'],
                target_snr=None,  # Would need R-xx message parsing
                your_frequency=att['your_frequency'],
                band=att['band'],
                succeeded=succeeded,
                calls_made=att['my_calls'],
                hour_utc=att['started'].hour,
                pileup_estimate=pileup
            ))
        
        return result
    
    def _estimate_pileup(self, decodes: List[Decode], target_call: str) -> int:
        """Estimate pileup size from decodes."""
        callers = set()
        for d in decodes:
            if d.replying_to == target_call and d.callsign != self.my_callsign:
                callers.add(d.callsign)
        return len(callers)


# =============================================================================
# Feature Builders
# =============================================================================

class SuccessFeatureBuilder:
    """
    Build features for the success prediction model.
    
    Target: P(QSO success | features)
    
    Features:
    - target_snr: Target's signal at your QTH
    - your_snr: Your signal at target (if known)
    - band_encoded: Operating band (0-12)
    - hour_utc: Hour of day (0-23)
    - competition: Estimated pileup size
    - region_encoded: Target's continent (0-7)
    - calls_made: How many times you called
    """
    
    FEATURE_NAMES = [
        'target_snr', 'your_snr', 'band_encoded', 'hour_utc',
        'competition', 'region_encoded', 'calls_made'
    ]
    
    def __init__(self, my_callsign: str):
        self.my_callsign = my_callsign.upper()
        self.reconstructor = AttemptReconstructor(my_callsign)
    
    def build(self, 
              decodes: List[Decode], 
              qsos: List[QSO]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Build feature matrix and labels.
        
        Args:
            decodes: All decodes
            qsos: Completed QSOs
            
        Returns:
            (X, y) where X is feature matrix, y is labels (0/1)
        """
        # Reconstruct attempts
        attempts = self.reconstructor.reconstruct(decodes, qsos)
        
        if not attempts:
            return np.array([]), np.array([])
        
        # Build feature matrix
        X = []
        y = []
        
        for att in attempts:
            features = self._extract_features(att)
            X.append(features)
            y.append(1 if att.succeeded else 0)
        
        return np.array(X), np.array(y)
    
    def _extract_features(self, attempt: ReconstructedAttempt) -> List[float]:
        """Extract feature vector from an attempt."""
        # Get continent from grid (if available)
        continent = grid_to_continent(attempt.target_grid) if attempt.target_grid else 'unknown'
        
        return [
            attempt.your_snr if attempt.your_snr is not None else -15,  # Default SNR
            attempt.target_snr if attempt.target_snr is not None else -15,
            encode_band(attempt.band),
            attempt.hour_utc,
            attempt.pileup_estimate,
            encode_continent(continent),
            attempt.calls_made,
        ]
    
    @property
    def feature_names(self) -> List[str]:
        return self.FEATURE_NAMES


class BehaviorFeatureBuilder:
    """
    Build features for target behavior classification.
    
    Target: Classify picking style (loudest_first, methodical, random)
    
    Features per target session:
    - snr_correlation: Correlation between answer order and SNR
    - freq_correlation: Correlation between answer order and frequency
    - region_entropy: How spread out are answered regions
    - timing_variance: Consistency of QSO rate
    - sample_size: Number of QSOs in session
    """
    
    FEATURE_NAMES = [
        'snr_correlation', 'freq_correlation', 'region_entropy',
        'timing_variance', 'sample_size'
    ]
    
    LABELS = ['loudest_first', 'methodical', 'random']
    
    def build_from_sessions(self, 
                            sessions: List[TargetSession]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Build features from observed target sessions.
        
        Args:
            sessions: List of TargetSession with answered_calls populated
            
        Returns:
            (X, y) where X is feature matrix, y is label indices
        """
        X = []
        y = []
        
        for session in sessions:
            if len(session.answered_calls) < 5:
                continue  # Need enough data
            
            features, label = self._analyze_session(session)
            X.append(features)
            y.append(self.LABELS.index(label))
        
        return np.array(X), np.array(y)
    
    def _analyze_session(self, session: TargetSession) -> Tuple[List[float], str]:
        """Analyze a session to extract features and determine label."""
        answers = session.answered_calls
        
        # Calculate correlations
        snr_corr = self._calc_snr_correlation(answers)
        freq_corr = self._calc_freq_correlation(answers)
        
        # Region entropy (how spread out are answers geographically)
        region_entropy = 0.5  # Placeholder - would need grid data
        
        # Timing variance
        timing_var = self._calc_timing_variance(answers)
        
        features = [
            snr_corr,
            freq_corr,
            region_entropy,
            timing_var,
            len(answers)
        ]
        
        # Determine label
        if snr_corr > 0.5:
            label = 'loudest_first'
        elif abs(freq_corr) > 0.5:
            label = 'methodical'
        else:
            label = 'random'
        
        return features, label
    
    def _calc_snr_correlation(self, answers: List[AnsweredCall]) -> float:
        """Correlation between SNR rank and answer order."""
        if len(answers) < 3:
            return 0.0
        
        # Higher SNR answered earlier = positive correlation
        snr_ranks = [a.snr_rank for a in answers]
        order = list(range(len(answers)))
        
        try:
            from scipy.stats import spearmanr
            corr, _ = spearmanr(order, snr_ranks)
            return -corr if not np.isnan(corr) else 0.0  # Negate: rank 1 = loudest
        except ImportError:
            return 0.0
    
    def _calc_freq_correlation(self, answers: List[AnsweredCall]) -> float:
        """Correlation between frequency and answer order."""
        if len(answers) < 3:
            return 0.0
        
        freqs = [a.frequency for a in answers]
        order = list(range(len(answers)))
        
        try:
            from scipy.stats import spearmanr
            corr, _ = spearmanr(order, freqs)
            return corr if not np.isnan(corr) else 0.0
        except ImportError:
            return 0.0
    
    def _calc_timing_variance(self, answers: List[AnsweredCall]) -> float:
        """Variance in time between answers (normalized)."""
        if len(answers) < 3:
            return 0.5
        
        gaps = []
        for i in range(1, len(answers)):
            gap = (answers[i].answered_at - answers[i-1].answered_at).total_seconds()
            gaps.append(gap)
        
        if not gaps:
            return 0.5
        
        mean_gap = np.mean(gaps)
        if mean_gap == 0:
            return 0.5
        
        # Coefficient of variation (normalized variance)
        cv = np.std(gaps) / mean_gap
        return min(1.0, cv)  # Cap at 1.0
    
    @property
    def feature_names(self) -> List[str]:
        return self.FEATURE_NAMES


class FrequencyFeatureBuilder:
    """
    Build features for frequency recommendation model.
    
    Target: Recommend optimal TX frequency offset
    
    Features:
    - band_encoded: Current band
    - hour_utc: Time of day
    - pileup_size: Current competition
    - avg_pileup_freq: Average frequency of pileup
    - your_historical_freq: Your typical successful frequency
    """
    
    FEATURE_NAMES = [
        'band_encoded', 'hour_utc', 'pileup_size',
        'avg_pileup_freq', 'your_historical_freq'
    ]
    
    def __init__(self, my_callsign: str):
        self.my_callsign = my_callsign.upper()
    
    def build_from_history(self,
                           successful_qsos: List[QSO],
                           attempts: List[ReconstructedAttempt]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Build features from historical data.
        
        Args:
            successful_qsos: QSOs that succeeded
            attempts: All attempts (for context)
            
        Returns:
            (X, y) where X is features, y is the frequency that worked
        """
        X = []
        y = []
        
        for qso in successful_qsos:
            # Find matching attempt
            matching = [a for a in attempts 
                       if a.target_call.upper() == qso.callsign.upper()
                       and a.succeeded
                       and abs((a.started - qso.timestamp).total_seconds()) < 300]
            
            if not matching:
                continue
            
            att = matching[0]
            if not att.your_frequency:
                continue
            
            features = [
                encode_band(qso.band),
                qso.timestamp.hour,
                att.pileup_estimate,
                1500,  # Default avg freq - would need actual pileup data
                att.your_frequency
            ]
            
            X.append(features)
            y.append(att.your_frequency)
        
        return np.array(X), np.array(y)
    
    def calculate_your_typical_freq(self, 
                                    successful_attempts: List[ReconstructedAttempt],
                                    band: str = None) -> float:
        """Calculate your typical successful TX frequency."""
        freqs = []
        for att in successful_attempts:
            if att.succeeded and att.your_frequency:
                if band is None or att.band == band:
                    freqs.append(att.your_frequency)
        
        if not freqs:
            return 1500  # Default middle of passband
        
        return np.median(freqs)
    
    @property
    def feature_names(self) -> List[str]:
        return self.FEATURE_NAMES


# =============================================================================
# Statistics Calculator
# =============================================================================

class StatsCalculator:
    """Calculate summary statistics from QSO/attempt data."""
    
    def __init__(self, my_callsign: str):
        self.my_callsign = my_callsign.upper()
    
    def success_rate_by_snr(self, 
                            attempts: List[ReconstructedAttempt]) -> Dict[str, Dict]:
        """Calculate success rate bucketed by SNR."""
        buckets = {
            '< -20': {'success': 0, 'total': 0},
            '-20 to -15': {'success': 0, 'total': 0},
            '-15 to -10': {'success': 0, 'total': 0},
            '-10 to -5': {'success': 0, 'total': 0},
            '-5 to 0': {'success': 0, 'total': 0},
            '> 0': {'success': 0, 'total': 0},
        }
        
        for att in attempts:
            snr = att.your_snr if att.your_snr is not None else -15
            
            if snr < -20:
                bucket = '< -20'
            elif snr < -15:
                bucket = '-20 to -15'
            elif snr < -10:
                bucket = '-15 to -10'
            elif snr < -5:
                bucket = '-10 to -5'
            elif snr <= 0:
                bucket = '-5 to 0'
            else:
                bucket = '> 0'
            
            buckets[bucket]['total'] += 1
            if att.succeeded:
                buckets[bucket]['success'] += 1
        
        # Calculate rates
        for bucket in buckets:
            total = buckets[bucket]['total']
            if total > 0:
                buckets[bucket]['rate'] = buckets[bucket]['success'] / total
            else:
                buckets[bucket]['rate'] = 0.0
        
        return buckets
    
    def success_rate_by_band(self, 
                             attempts: List[ReconstructedAttempt]) -> Dict[str, Dict]:
        """Calculate success rate by band."""
        buckets = defaultdict(lambda: {'success': 0, 'total': 0})
        
        for att in attempts:
            band = att.band or 'unknown'
            buckets[band]['total'] += 1
            if att.succeeded:
                buckets[band]['success'] += 1
        
        # Calculate rates
        result = {}
        for band, data in buckets.items():
            if data['total'] > 0:
                data['rate'] = data['success'] / data['total']
            else:
                data['rate'] = 0.0
            result[band] = dict(data)
        
        return result
    
    def success_rate_by_hour(self, 
                             attempts: List[ReconstructedAttempt]) -> Dict[int, Dict]:
        """Calculate success rate by hour of day."""
        buckets = {h: {'success': 0, 'total': 0} for h in range(24)}
        
        for att in attempts:
            hour = att.hour_utc
            buckets[hour]['total'] += 1
            if att.succeeded:
                buckets[hour]['success'] += 1
        
        # Calculate rates
        for hour in buckets:
            total = buckets[hour]['total']
            if total > 0:
                buckets[hour]['rate'] = buckets[hour]['success'] / total
            else:
                buckets[hour]['rate'] = 0.0
        
        return buckets
    
    def avg_calls_to_success(self, 
                             attempts: List[ReconstructedAttempt]) -> float:
        """Calculate average number of calls before success."""
        successful = [a for a in attempts if a.succeeded]
        if not successful:
            return 0.0
        
        return np.mean([a.calls_made for a in successful])
