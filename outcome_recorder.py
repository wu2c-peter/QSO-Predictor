# QSO Predictor — OutcomeRecorder
# Copyright (C) 2025-2026 Peter Hirst (WU2C)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# Phase 1: Silent data collector for QSO attempt outcomes.
# Records QSOP's ephemeral scoring context at the moment of each
# outcome event. No UI, no runtime analysis. Fires only on terminal
# events (target cleared, QSO logged, app closed) — never on individual
# decodes or MQTT spots.
#
# See OUTCOME_RECORDER_SPEC.md for full design rationale.

import json
import logging
import math
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# File size safety limit (~15 years of heavy use)
MAX_FILE_SIZE_MB = 50

# Schema version — increment when event format changes
SCHEMA_VERSION = 1


def _haversine_km(grid1: str, grid2: str) -> int:
    """Compute great-circle distance between two Maidenhead grid squares.
    
    Accepts 4-char or 6-char grids. Returns integer km, or -1 if
    either grid is invalid/missing.
    """
    try:
        if not grid1 or not grid2 or len(grid1) < 4 or len(grid2) < 4:
            return -1
        
        lat1, lon1 = _grid_to_latlon(grid1)
        lat2, lon2 = _grid_to_latlon(grid2)
        
        # Haversine formula
        R = 6371  # Earth radius km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return int(R * c)
    except Exception:
        return -1


def _grid_to_latlon(grid: str) -> tuple:
    """Convert Maidenhead grid to (latitude, longitude) center point."""
    grid = grid.upper()
    lon = (ord(grid[0]) - ord('A')) * 20 - 180
    lat = (ord(grid[1]) - ord('A')) * 10 - 90
    lon += int(grid[2]) * 2
    lat += int(grid[3]) * 1
    if len(grid) >= 6:
        lon += (ord(grid[4]) - ord('A')) * (2 / 24) + (1 / 24)
        lat += (ord(grid[5]) - ord('A')) * (1 / 24) + (1 / 48)
    else:
        lon += 1    # center of 2-degree square
        lat += 0.5  # center of 1-degree square
    return lat, lon


def _grid_to_continent(grid: str) -> str:
    """Approximate continent from Maidenhead field (first 2 chars).
    
    This is a rough mapping — sufficient for filtering, not for
    official DXCC purposes.
    """
    if not grid or len(grid) < 2:
        return ""
    
    field = grid[:2].upper()
    lon_field = ord(field[0]) - ord('A')  # 0-17
    lat_field = ord(field[1]) - ord('A')  # 0-17
    
    # Rough continent buckets based on field position
    # lon_field: 0=180W, 9=0 (Greenwich), 17=180E
    # lat_field: 0=90S, 9=0 (Equator), 17=90N
    
    if lat_field <= 3:
        # Southern hemisphere
        if lon_field <= 4:
            return "SA"  # South America / Pacific
        elif lon_field <= 9:
            return "AF"  # Africa
        elif lon_field <= 14:
            return "OC"  # Oceania / Indian Ocean
        else:
            return "OC"
    elif lat_field <= 8:
        # Tropical / subtropical
        if lon_field <= 2:
            return "OC"  # Pacific
        elif lon_field <= 5:
            return "SA"  # South / Central America
        elif lon_field <= 9:
            return "AF"  # Africa
        elif lon_field <= 14:
            return "AS"  # Asia
        else:
            return "OC"  # Pacific / Oceania
    elif lat_field <= 12:
        # Temperate
        if lon_field <= 1:
            return "OC"  # Pacific
        elif lon_field <= 5:
            return "NA"  # North America
        elif lon_field <= 9:
            return "EU"  # Europe
        elif lon_field <= 14:
            return "AS"  # Asia
        else:
            return "AS"  # Far East Asia
    else:
        # Arctic / subarctic
        if lon_field <= 5:
            return "NA"
        elif lon_field <= 9:
            return "EU"
        else:
            return "AS"


class OutcomeRecorder:
    """Records QSO attempt outcomes for future performance analysis.
    
    Silent data collector — no UI, no runtime analysis.
    Fires only on outcome events (target cleared, QSO logged, etc.)
    
    Usage (Option B — snapshot dict pattern):
        The caller builds a snapshot dict of QSOP's ephemeral state
        and passes it to record_outcome(). The recorder never reaches
        into the UI or other subsystems.
    
    See OUTCOME_RECORDER_SPEC.md for full specification.
    """

    def __init__(self, my_callsign: str, my_grid: str, enabled: bool = True):
        """Initialize the OutcomeRecorder.
        
        Args:
            my_callsign: Operator's callsign (for RESPONDED detection)
            my_grid: Operator's grid square (for distance calculation)
            enabled: Whether recording is active (from settings)
        """
        data_dir = Path.home() / '.qso-predictor'
        data_dir.mkdir(exist_ok=True)
        self.filepath = str(data_dir / 'outcome_history.jsonl')
        
        self._my_call = my_callsign.upper()
        self._my_grid = my_grid.upper() if my_grid else ""
        self._enabled = enabled
        
        # Per-target state (reset on each target selection)
        self._current_target = None
        self._current_target_grid = ""
        self._target_selected_at = None
        self._first_tx_at = None
        self._tx_cycle_count = 0
        self._target_responded = False
        self._was_transmitting = False  # Edge detection for TX cycles
        
        # Session tracking — sessions are tied to target activity, not app lifetime.
        # A session starts when the first target is selected and ends when no
        # target has been active for SESSION_GAP_SECONDS, or on app close.
        # Passive monitoring (no target selected) generates zero records.
        # Session start is deferred to the first TX cycle — browsing without
        # transmitting creates no session.
        self._session_active = False
        self._session_start_time = None
        self._session_outcome_count = 0
        self._last_activity_time = None  # Timestamp of last outcome or target selection
        self._pending_session = None     # Buffered session params, written on first TX
        
        logger.info(f"OutcomeRecorder: initialized (enabled={enabled}), "
                     f"file={self.filepath}")

    # Session gap: if no target activity for this long, close the session.
    # Next target selection opens a new session.
    SESSION_GAP_SECONDS = 600  # 10 minutes

    # --- Public API: Event hooks ---

    def on_target_selected(self, call: str, grid: str,
                           band: str = "", sfi: int = 0, k: int = 0):
        """Called when user selects a new target.
        
        If no session is active (or the gap since last activity exceeds
        SESSION_GAP_SECONDS), starts a new session automatically.
        
        If a previous target was active, its outcome is NOT recorded
        here — the caller must call record_outcome() with a snapshot
        BEFORE calling this method. This ensures the snapshot captures
        state before _set_new_target() resets it.
        
        Args:
            call: New target callsign
            grid: New target grid square
            band: Current operating band (for session_start marker)
            sfi: Solar flux index (for session_start marker)
            k: K-index (for session_start marker)
        """
        if not self._enabled:
            return
        
        now = datetime.utcnow()
        
        # Session management: check if existing session has expired
        if self._session_active and self._last_activity_time:
            gap = (now - self._last_activity_time).total_seconds()
            if gap > self.SESSION_GAP_SECONDS:
                # Been idle too long — close old session
                self._end_session()
        
        # Buffer session params — actual session_start is deferred to first
        # TX cycle. If user just browses targets without transmitting, no
        # session is created and no data is written.
        self._pending_session = {
            'band': band, 'sfi': sfi, 'k': k
        }
        
        self._current_target = call.upper() if call else None
        self._current_target_grid = grid.upper() if grid else ""
        self._target_selected_at = now
        self._first_tx_at = None
        self._tx_cycle_count = 0
        self._target_responded = False
        self._was_transmitting = False

    def on_status_update(self, transmitting: bool):
        """Called on each UDP status update — detects TX cycle edges.
        
        Counts rising edges of 'transmitting' flag. This fires once
        per TX period, not continuously while transmitting.
        
        Also triggers deferred session_start on first TX — ensures
        sessions only exist when the user actually transmits.
        
        Args:
            transmitting: Current TX state from UDP Type 1
        """
        if not self._enabled or not self._current_target:
            return
        
        # Rising edge detection: was not transmitting, now is
        if transmitting and not self._was_transmitting:
            self._tx_cycle_count += 1
            if self._first_tx_at is None:
                self._first_tx_at = datetime.utcnow()
                
                # Deferred session start — first TX cycle confirms
                # the user is actually operating, not just browsing
                if not self._session_active and self._pending_session:
                    ps = self._pending_session
                    self._start_session(
                        self._target_selected_at or datetime.utcnow(),
                        ps['band'], ps['sfi'], ps['k']
                    )
                    self._pending_session = None
        
        self._was_transmitting = transmitting

    def on_decode(self, from_call: str, message: str):
        """Called on each decoded message — checks for target response.
        
        Lightweight: one string comparison per decode, only when
        we have an active target. Does not store the decode.
        
        Args:
            from_call: Callsign of the station that sent this message
            message: Full decoded message text
        """
        if not self._enabled or not self._current_target:
            return
        
        if not from_call or not message:
            return
        
        # Check if this decode is FROM our target and contains our callsign
        if (from_call.upper() == self._current_target and
                self._my_call and
                self._my_call in message.upper()):
            if not self._target_responded:
                self._target_responded = True
                logger.debug(f"OutcomeRecorder: target {self._current_target} "
                             f"responded (detected in decode)")

    def record_outcome(self, trigger: str, snapshot: dict):
        """Record an outcome event with QSOP's ephemeral state snapshot.
        
        CRITICAL: The caller must build the snapshot dict BEFORE any
        state-clearing code runs (e.g., before _set_new_target("")).
        
        Args:
            trigger: What caused the outcome: 'QSO_LOGGED', 'CLEARED',
                     'TARGET_CHANGED', 'BAND_CHANGED', 'APP_CLOSED'
            snapshot: Dict of QSOP's current state. Expected keys:
                - rec_freq (int): Recommended frequency (green line)
                - rec_score (float): Score at recommended freq
                - tx_freq (int): Actual TX frequency from UDP
                - tx_score (float): Score at actual TX freq
                - score_reason (int): Top score reason code at TX freq
                - path (str): Path status string
                - competition (int): Competition count
                - reporters (int): Active reporter count
                - ionis (str): IONIS status string
                - fh_mode (str): F/H mode string
                - band (str): Current band
                - sfi (int): Solar flux index
                - k (int): K-index
        """
        if not self._enabled or not self._current_target:
            return
        
        if not self._target_selected_at:
            return
        
        # Skip non-attempts: if user never transmitted, this was just
        # browsing (clicked a station, looked at it, moved on).
        # Not useful data for scoring analysis. QSO_LOGGED always records
        # as a safety net (shouldn't happen with 0 cycles, but just in case).
        if self._tx_cycle_count == 0 and trigger != 'QSO_LOGGED':
            logger.debug(f"OutcomeRecorder: skipping {self._current_target} "
                         f"— no TX cycles (browsing, not an attempt)")
            # Reset per-target state without recording
            self._current_target = None
            self._current_target_grid = ""
            self._target_selected_at = None
            self._target_responded = False
            self._tx_cycle_count = 0
            self._first_tx_at = None
            self._was_transmitting = False
            return
        
        now = datetime.utcnow()
        
        # Determine outcome tier
        if trigger == 'QSO_LOGGED':
            outcome = 'QSO_LOGGED'
        elif self._target_responded:
            outcome = 'RESPONDED'
        else:
            outcome = 'NO_RESPONSE'
        
        # Extract snapshot values with safe defaults
        rec_freq = snapshot.get('rec_freq', 0)
        tx_freq = snapshot.get('tx_freq', 0)
        
        # Calculate distance
        distance_km = _haversine_km(self._my_grid, self._current_target_grid)
        
        # Build event
        event = {
            "v": SCHEMA_VERSION,
            "type": "outcome",
            "ts": now.isoformat() + 'Z',
            "band": snapshot.get('band', ''),
            "outcome": outcome,
            
            # QSOP scoring context (unique to us — lost if not captured)
            "rec_freq": rec_freq,
            "rec_score": round(snapshot.get('rec_score', 0), 1),
            "tx_freq": tx_freq,
            "tx_score": round(snapshot.get('tx_score', 0), 1),
            "followed": abs(tx_freq - rec_freq) < 30 if (tx_freq and rec_freq) else None,
            "score_reason": snapshot.get('score_reason', 0),
            
            # Ephemeral context
            "path": snapshot.get('path', ''),
            "competition": snapshot.get('competition', 0),
            "reporters": snapshot.get('reporters', 0),
            "ionis": snapshot.get('ionis', ''),
            "fh_mode": snapshot.get('fh_mode', 'normal'),
            
            # Solar conditions
            "sfi": snapshot.get('sfi', 0),
            "k": snapshot.get('k', 0),
            "a": snapshot.get('a', None),  # Not yet implemented in QSOP
            
            # Session counters
            "tx_cycles": self._tx_cycle_count,
            "elapsed_s": int((now - self._target_selected_at).total_seconds()),
            
            # Filter-enabling fields
            "hour_utc": now.hour,
            "dow": now.weekday(),  # 0=Monday, 6=Sunday
            "distance_km": distance_km if distance_km >= 0 else None,
            "target_continent": _grid_to_continent(self._current_target_grid),
        }
        
        self._write_event(event)
        self._session_outcome_count += 1
        self._last_activity_time = now  # Track for session gap detection
        
        logger.info(f"OutcomeRecorder: {outcome} for {self._current_target} "
                     f"(trigger={trigger}, tx_cycles={self._tx_cycle_count}, "
                     f"score={snapshot.get('tx_score', '?')})")
        
        # Reset per-target state
        self._current_target = None
        self._current_target_grid = ""
        self._target_selected_at = None
        self._target_responded = False
        self._tx_cycle_count = 0
        self._first_tx_at = None
        self._was_transmitting = False

    def on_app_close(self):
        """Clean shutdown — flush pending outcome and close session.
        
        Call from closeEvent. The caller should call
        _record_outcome_for_current_target('APP_CLOSED') before this.
        """
        if not self._enabled:
            return
        if self._session_active:
            self._end_session()

    # --- State queries ---

    @property
    def has_active_target(self) -> bool:
        """Whether we're currently tracking a target attempt."""
        return self._current_target is not None

    @property
    def active_target(self) -> str:
        """Current target callsign, or empty string."""
        return self._current_target or ""

    @property
    def target_responded(self) -> bool:
        """Whether the current target has responded to us."""
        return self._target_responded

    # --- Internal ---

    def _start_session(self, now: datetime, band: str, sfi: int, k: int):
        """Write session_start marker and reset session counters."""
        self._session_active = True
        self._session_start_time = now
        self._session_outcome_count = 0
        self._write_event({
            "v": SCHEMA_VERSION,
            "type": "session_start",
            "ts": now.isoformat() + 'Z',
            "band": band or "",
            "sfi": sfi,
            "k": k,
        })
        logger.info("OutcomeRecorder: session started")

    def _end_session(self):
        """Write session_end marker and deactivate session."""
        now = datetime.utcnow()
        
        # If last activity was long ago (e.g., app left running overnight),
        # use the last activity time as the effective session end, not now.
        effective_end = now
        if self._last_activity_time:
            gap = (now - self._last_activity_time).total_seconds()
            if gap > self.SESSION_GAP_SECONDS:
                effective_end = self._last_activity_time
        
        elapsed = 0
        if self._session_start_time:
            elapsed = int((effective_end - self._session_start_time).total_seconds())
        
        self._write_event({
            "v": SCHEMA_VERSION,
            "type": "session_end",
            "ts": effective_end.isoformat() + 'Z',
            "outcomes": self._session_outcome_count,
            "elapsed_s": elapsed,
        })
        
        outcomes = self._session_outcome_count
        self._session_active = False
        self._session_start_time = None
        self._session_outcome_count = 0
        logger.info(f"OutcomeRecorder: session ended ({outcomes} outcomes, {elapsed}s)")

    def _write_event(self, event: dict):
        """Append one JSON line to the outcome file.
        
        Never raises — recording failures must not crash the app.
        """
        try:
            # Safety check: rotate if file is absurdly large
            if os.path.exists(self.filepath):
                size_mb = os.path.getsize(self.filepath) / (1024 * 1024)
                if size_mb > MAX_FILE_SIZE_MB:
                    self._rotate()
            
            with open(self.filepath, 'a') as f:
                f.write(json.dumps(event, separators=(',', ':')) + '\n')
        except Exception as e:
            # Log once, don't spam
            logger.warning(f"OutcomeRecorder: write failed: {e}")

    def _rotate(self):
        """Rename current file to .bak, start fresh."""
        try:
            bak = self.filepath + '.bak'
            if os.path.exists(bak):
                os.remove(bak)
            os.rename(self.filepath, bak)
            logger.info(f"OutcomeRecorder: rotated {self.filepath} → .bak")
        except Exception as e:
            logger.warning(f"OutcomeRecorder: rotation failed: {e}")
