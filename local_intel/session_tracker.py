"""
Session Tracker for QSO Predictor v2.0

Tracks real-time pileup activity and target station behavior
from the live UDP decode stream.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from collections import defaultdict

from .models import (
    Decode, TargetSession, PileupMember, AnsweredCall,
    PickingPattern, PickingStyle, AnalysisConfig
)
from .log_parser import MessageParser, ParsedMessage

logger = logging.getLogger(__name__)


class SessionTracker:
    """
    Track real-time pileup activity and target behavior.
    
    Maintains state for:
    - Current target session (who you're trying to work)
    - Active pileup members (who's calling the target)
    - Target's answering patterns
    - Your position in the pileup
    """
    
    def __init__(self, 
                 my_callsign: str,
                 config: AnalysisConfig = None):
        """
        Initialize tracker.
        
        Args:
            my_callsign: Your callsign
            config: Analysis configuration
        """
        self.my_callsign = my_callsign.upper()
        self.config = config or AnalysisConfig()
        
        # TX status (from JTDX/WSJT-X status updates)
        self._tx_enabled = False
        
        # Current tracking state
        self.target_session: Optional[TargetSession] = None
        self.active_sessions: Dict[str, TargetSession] = {}  # All targets we're tracking
        
        # Cycle tracking
        self.current_cycle = 0
        self.last_cycle_time: Optional[datetime] = None
        
        # Event callbacks
        self._on_pileup_update: Optional[Callable] = None
        self._on_answer_detected: Optional[Callable] = None
        self._on_pattern_detected: Optional[Callable] = None
    
    def set_target(self, callsign: str, grid: str = None, frequency: int = None):
        """
        Set the primary target station.
        
        Args:
            callsign: Target's callsign
            grid: Target's grid square (if known)
            frequency: Target's TX frequency offset
        """
        callsign = callsign.upper()
        
        if callsign in self.active_sessions:
            self.target_session = self.active_sessions[callsign]
        else:
            self.target_session = TargetSession(
                callsign=callsign,
                grid=grid,
                started=datetime.now(),
                frequency=frequency or 0
            )
            self.active_sessions[callsign] = self.target_session
        
        logger.info(f"Target set: {callsign}")
    
    def set_tx_status(self, enabled: bool):
        """
        Set TX status from JTDX/WSJT-X.
        
        Args:
            enabled: True if TX is enabled/transmitting
        """
        self._tx_enabled = enabled
    
    def process_decode(self, decode: Decode):
        """
        Process a new decode from the UDP stream.
        
        This updates pileup state, detects answers, and
        tracks target behavior.
        
        Args:
            decode: Incoming decode
        """
        if not decode.callsign:
            return
        
        # Update cycle tracking
        self._update_cycle(decode.timestamp)
        
        # Parse message for richer info
        parsed = MessageParser.parse(decode.message)
        
        # Handle CQ from target
        if parsed.is_cq and self._is_target(parsed.caller):
            self._handle_target_cq(decode, parsed)
            return
        
        # Handle reply to target (someone calling them)
        if self._is_calling_target(parsed):
            self._handle_pileup_call(decode, parsed)
            return
        
        # Handle target answering someone
        if self._is_target_answering(parsed):
            self._handle_target_answer(decode, parsed)
            return
        
        # Handle reply from target to us specifically
        if self._is_target_calling_me(parsed):
            self._handle_target_calling_me(decode, parsed)
            return
    
    def _is_target(self, callsign: str) -> bool:
        """Check if callsign is our current target."""
        if not self.target_session or not callsign:
            return False
        return callsign.upper() == self.target_session.callsign
    
    def _is_calling_target(self, parsed: ParsedMessage) -> bool:
        """Check if message is calling our target."""
        if not self.target_session:
            return False
        return parsed.callee == self.target_session.callsign
    
    def _is_target_answering(self, parsed: ParsedMessage) -> bool:
        """Check if target is answering someone (not us)."""
        if not self.target_session:
            return False
        if parsed.caller != self.target_session.callsign:
            return False
        if parsed.callee == self.my_callsign:
            return False
        return parsed.is_reply and parsed.callee is not None
    
    def _is_target_calling_me(self, parsed: ParsedMessage) -> bool:
        """Check if target is calling us."""
        if not self.target_session:
            return False
        return (parsed.caller == self.target_session.callsign and 
                parsed.callee == self.my_callsign)
    
    def _handle_target_cq(self, decode: Decode, parsed: ParsedMessage):
        """Handle CQ from target station."""
        if not self.target_session:
            return
        
        self.target_session.cq_count += 1
        self.target_session.last_activity = decode.timestamp
        
        if parsed.grid and not self.target_session.grid:
            self.target_session.grid = parsed.grid
        
        if decode.frequency:
            self.target_session.frequency = decode.frequency
        
        logger.debug(f"Target CQ #{self.target_session.cq_count}")
    
    def _handle_pileup_call(self, decode: Decode, parsed: ParsedMessage):
        """Handle a station calling our target."""
        if not self.target_session:
            return
        
        caller = parsed.caller
        if not caller:
            return
        
        self.target_session.add_caller(
            call=caller,
            freq=decode.frequency,
            snr=decode.snr,
            grid=parsed.grid
        )
        
        # Notify listeners
        if self._on_pileup_update:
            self._on_pileup_update(self.target_session)
        
        logger.debug(f"Pileup: {caller} @ {decode.frequency} Hz ({decode.snr} dB) - "
                    f"Total: {self.target_session.pileup_size}")
    
    def _handle_target_answer(self, decode: Decode, parsed: ParsedMessage):
        """Handle target answering someone in the pileup."""
        if not self.target_session:
            return
        
        answered_call = parsed.callee
        if not answered_call:
            return
        
        # Record the answer
        self.target_session.record_answer(answered_call, self.current_cycle)
        self.target_session.last_activity = decode.timestamp
        
        logger.info(f"Target answered: {answered_call}")
        
        # Notify listeners
        if self._on_answer_detected:
            if self.target_session.answered_calls:
                self._on_answer_detected(self.target_session.answered_calls[-1])
        
        # Check if we have enough data to detect pattern
        if len(self.target_session.answered_calls) >= 5:
            pattern = self._analyze_pattern()
            if pattern and self._on_pattern_detected:
                self._on_pattern_detected(pattern)
    
    def _handle_target_calling_me(self, decode: Decode, parsed: ParsedMessage):
        """Handle target calling us back."""
        logger.info(f"TARGET IS CALLING US: {decode.message}")
        
        # This is a significant event - we got through!
        # Could trigger UI notification, etc.
    
    def _update_cycle(self, timestamp: datetime):
        """Update FT8 cycle tracking."""
        if self.last_cycle_time is None:
            self.last_cycle_time = timestamp
            self.current_cycle = 0
            return
        
        # FT8 cycles are 15 seconds
        elapsed = (timestamp - self.last_cycle_time).total_seconds()
        if elapsed >= 15:
            cycles_passed = int(elapsed / 15)
            self.current_cycle += cycles_passed
            self.last_cycle_time = timestamp
            
            # Prune stale callers on cycle boundary
            if self.target_session:
                self.target_session.prune_stale_callers(
                    self.config.pileup_stale_seconds
                )
    
    def _analyze_pattern(self) -> Optional[PickingPattern]:
        """Analyze target's picking pattern from recent answers."""
        if not self.target_session:
            return None
        
        answers = self.target_session.answered_calls[-10:]  # Last 10
        if len(answers) < 5:
            return None
        
        # Calculate metrics
        loudest_picks = sum(1 for a in answers if a.was_loudest)
        loudest_ratio = loudest_picks / len(answers)
        
        # Check frequency correlation (low-to-high or high-to-low)
        if len(answers) >= 3:
            freq_correlation = self._calculate_freq_correlation(answers)
        else:
            freq_correlation = 0.0
        
        # Determine pattern
        if loudest_ratio >= 0.6:
            style = PickingStyle.LOUDEST_FIRST
            confidence = loudest_ratio
            advice = "Target picks loudest signals. Strong signal advantage."
        elif freq_correlation > 0.5:
            style = PickingStyle.METHODICAL_LOW_HIGH
            confidence = freq_correlation
            advice = "Target working low-to-high. Position at lower frequencies."
        elif freq_correlation < -0.5:
            style = PickingStyle.METHODICAL_HIGH_LOW
            confidence = abs(freq_correlation)
            advice = "Target working high-to-low. Position at higher frequencies."
        else:
            style = PickingStyle.RANDOM
            confidence = 1.0 - loudest_ratio  # More random = higher confidence in random
            advice = "No clear pattern. Persistence matters."
        
        return PickingPattern(
            style=style,
            confidence=confidence,
            sample_size=len(answers),
            advice=advice,
            loudest_pick_ratio=loudest_ratio,
            frequency_correlation=freq_correlation
        )
    
    def _calculate_freq_correlation(self, answers: List[AnsweredCall]) -> float:
        """
        Calculate Spearman correlation between answer order and frequency.
        
        Returns:
            -1 to 1: positive = low-to-high, negative = high-to-low
        """
        try:
            from scipy.stats import spearmanr
            import numpy as np
            
            order = list(range(len(answers)))
            freqs = [a.frequency for a in answers]
            
            correlation, _ = spearmanr(order, freqs)
            return correlation if not np.isnan(correlation) else 0.0
            
        except ImportError:
            # Fallback: simple correlation estimate
            return 0.0
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    def get_pileup_info(self) -> Optional[Dict]:
        """
        Get current pileup information.
        
        Returns:
            Dict with pileup stats, or None if no target
        """
        if not self.target_session:
            return None
        
        session = self.target_session
        callers = list(session.callers.values())
        
        if not callers:
            return {
                'size': 0,
                'callers': [],
                'your_rank': None,
                'loudest': None,
            }
        
        # Sort by SNR
        sorted_callers = sorted(callers, key=lambda c: c.snr, reverse=True)
        
        # Find our position
        your_rank = None
        for i, caller in enumerate(sorted_callers):
            if caller.callsign == self.my_callsign:
                your_rank = i + 1
                break
        
        return {
            'size': len(callers),
            'callers': sorted_callers,
            'your_rank': your_rank,
            'loudest': sorted_callers[0] if sorted_callers else None,
            'frequency_range': (
                min(c.frequency for c in callers),
                max(c.frequency for c in callers)
            ) if callers else None,
        }
    
    def get_target_behavior(self) -> Optional[Dict]:
        """
        Get target's observed behavior.
        
        Returns:
            Dict with behavior analysis, or None if no target
        """
        if not self.target_session:
            return None
        
        session = self.target_session
        
        pattern = self._analyze_pattern()
        
        return {
            'callsign': session.callsign,
            'qso_count': session.qso_count,
            'qso_rate': session.qso_rate_per_minute,
            'cq_count': session.cq_count,
            'answers': session.answered_calls[-10:],  # Last 10
            'pattern': pattern,
        }
    
    def get_your_status(self) -> Dict:
        """
        Get your current status in the pileup.
        
        Returns:
            Dict with your position and chances
        """
        if not self.target_session:
            return {
                'in_pileup': False,
                'rank': None,
                'total': 0,
            }
        
        session = self.target_session
        
        # Check if we're calling (TX enabled)
        if self._tx_enabled:
            # We're calling - estimate our rank based on pileup
            # Since we can't see our own signal, rank is unknown
            return {
                'in_pileup': True,
                'rank': '?',  # Unknown - we can't hear ourselves
                'total': session.pileup_size,
                'calls_made': 1,  # At least one
            }
        
        # Not transmitting
        return {
            'in_pileup': False,
            'rank': None,
            'total': session.pileup_size,
        }
    
    def on_pileup_update(self, callback: Callable):
        """Register callback for pileup updates."""
        self._on_pileup_update = callback
    
    def on_answer_detected(self, callback: Callable):
        """Register callback when target answers someone."""
        self._on_answer_detected = callback
    
    def on_pattern_detected(self, callback: Callable):
        """Register callback when picking pattern is detected."""
        self._on_pattern_detected = callback
    
    def clear_session(self):
        """Clear current session (e.g., when changing targets)."""
        self.target_session = None
    
    def clear_all(self):
        """Clear all tracking data."""
        self.target_session = None
        self.active_sessions.clear()
        self.current_cycle = 0
        self.last_cycle_time = None


class MultiTargetTracker:
    """
    Track multiple target stations simultaneously.
    
    Useful for monitoring several DX stations and their pileup conditions
    to choose the best one to call.
    """
    
    def __init__(self, my_callsign: str, config: AnalysisConfig = None):
        """
        Initialize multi-target tracker.
        
        Args:
            my_callsign: Your callsign
            config: Analysis configuration
        """
        self.my_callsign = my_callsign.upper()
        self.config = config or AnalysisConfig()
        self.trackers: Dict[str, SessionTracker] = {}
    
    def add_target(self, callsign: str, grid: str = None):
        """Add a target station to track."""
        callsign = callsign.upper()
        if callsign not in self.trackers:
            tracker = SessionTracker(self.my_callsign, self.config)
            tracker.set_target(callsign, grid)
            self.trackers[callsign] = tracker
    
    def remove_target(self, callsign: str):
        """Remove a target station from tracking."""
        callsign = callsign.upper()
        if callsign in self.trackers:
            del self.trackers[callsign]
    
    def process_decode(self, decode: Decode):
        """Process decode for all tracked targets."""
        for tracker in self.trackers.values():
            tracker.process_decode(decode)
    
    def get_best_target(self) -> Optional[str]:
        """
        Get the target with best conditions for you.
        
        Considers:
        - Pileup size (smaller = better)
        - Your SNR rank (higher = better)
        - Target's picking pattern (loudest_first + you're loud = good)
        
        Returns:
            Callsign of best target, or None
        """
        if not self.trackers:
            return None
        
        scores = {}
        
        for callsign, tracker in self.trackers.items():
            pileup = tracker.get_pileup_info()
            if not pileup:
                continue
            
            score = 0.0
            
            # Smaller pileup = better (max 50 points)
            size = pileup['size']
            if size == 0:
                score += 50  # No competition!
            else:
                score += max(0, 50 - size * 5)
            
            # Your rank matters (max 30 points)
            if pileup['your_rank']:
                rank_score = 30 - (pileup['your_rank'] - 1) * 10
                score += max(0, rank_score)
            
            # Pattern compatibility (max 20 points)
            behavior = tracker.get_target_behavior()
            if behavior and behavior['pattern']:
                pattern = behavior['pattern']
                status = tracker.get_your_status()
                
                if pattern.style == PickingStyle.LOUDEST_FIRST:
                    if status.get('rank') == 1:
                        score += 20  # We're loudest!
                    elif status.get('rank', 99) <= 3:
                        score += 10
            
            scores[callsign] = score
        
        if not scores:
            return None
        
        return max(scores, key=scores.get)
