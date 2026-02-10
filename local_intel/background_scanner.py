"""
Background Scanner for QSO Predictor v2.0.8

Incrementally scans log files in a background thread, updating
behavior history without blocking the UI. Uses file position
tracking to only process new data.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Set, List, Callable
from dataclasses import dataclass, field

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker

logger = logging.getLogger(__name__)


@dataclass
class FilePosition:
    """Tracks scanning position in a log file."""
    path: str
    byte_offset: int = 0
    last_timestamp: Optional[str] = None
    last_scanned: Optional[str] = None


@dataclass 
class ScanProgress:
    """Progress info for UI updates."""
    files_total: int = 0
    files_done: int = 0
    decodes_processed: int = 0
    stations_updated: int = 0
    is_initial_scan: bool = False


class BackgroundScanner(QThread):
    """
    Background thread for incremental log file scanning.
    
    Features:
    - Tracks file positions to only scan new data
    - No timeout - runs at leisure in background
    - Periodic saves to prevent data loss
    - Priority queue for visible callsigns
    - Signals for UI updates
    
    Usage:
        scanner = BackgroundScanner(behavior_predictor)
        scanner.progress_updated.connect(on_progress)
        scanner.scan_complete.connect(on_complete)
        scanner.start()
        
        # When user clicks a station not in cache:
        scanner.prioritize_callsign("JA1ABC")
        
        # On app shutdown:
        scanner.stop()
        scanner.wait()
    """
    
    # Signals
    progress_updated = pyqtSignal(object)  # ScanProgress
    scan_complete = pyqtSignal(int)  # stations_updated count
    station_updated = pyqtSignal(str)  # callsign when a specific station is updated
    
    # Scan interval (seconds between incremental scans)
    SCAN_INTERVAL = 30
    
    # Save interval (seconds between history saves)
    SAVE_INTERVAL = 60
    
    # Session gap for behavior analysis
    SESSION_GAP_SECONDS = 300  # 5 minutes
    
    def __init__(self, behavior_predictor, parent=None):
        """
        Initialize background scanner.
        
        Args:
            behavior_predictor: BehaviorPredictor instance to update
            parent: Parent QObject
        """
        super().__init__(parent)
        
        self._predictor = behavior_predictor
        self._running = False
        self._stop_requested = False
        self._mutex = QMutex()
        
        # File position tracking
        self._positions: Dict[str, FilePosition] = {}
        self._positions_file = self._get_positions_file()
        
        # Priority queue for callsigns user is interested in
        self._priority_callsigns: Set[str] = set()
        
        # Track if this is first run (full scan needed)
        self._is_initial_scan = False
        
        # Stats
        self._last_save_time = 0
        self._decodes_since_save = 0
        
        # Load saved positions
        self._load_positions()
    
    def _get_positions_file(self) -> Path:
        """Get path to file positions JSON."""
        data_dir = Path.home() / '.qso-predictor'
        data_dir.mkdir(exist_ok=True)
        return data_dir / 'file_positions.json'
    
    def _load_positions(self):
        """Load file positions from disk."""
        try:
            if self._positions_file.exists():
                with open(self._positions_file, 'r') as f:
                    data = json.load(f)
                    for path, pos_data in data.get('positions', {}).items():
                        self._positions[path] = FilePosition(
                            path=path,
                            byte_offset=pos_data.get('byte_offset', 0),
                            last_timestamp=pos_data.get('last_timestamp'),
                            last_scanned=pos_data.get('last_scanned')
                        )
                logger.info(f"Loaded positions for {len(self._positions)} files")
        except Exception as e:
            logger.warning(f"Could not load file positions: {e}")
            self._positions = {}
    
    def _save_positions(self):
        """Save file positions to disk."""
        try:
            data = {
                'version': '1.0',
                'updated': datetime.now().isoformat(),
                'positions': {
                    path: {
                        'byte_offset': pos.byte_offset,
                        'last_timestamp': pos.last_timestamp,
                        'last_scanned': pos.last_scanned
                    }
                    for path, pos in self._positions.items()
                }
            }
            with open(self._positions_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save file positions: {e}")
    
    def prioritize_callsign(self, callsign: str):
        """Add a callsign to priority queue for immediate processing."""
        with QMutexLocker(self._mutex):
            self._priority_callsigns.add(callsign.upper())
    
    def stop(self):
        """Request scanner to stop."""
        self._stop_requested = True
    
    def run(self):
        """Main scanner loop."""
        from local_intel.log_discovery import LogFileDiscovery
        from local_intel.log_parser import LogParser
        
        self._running = True
        self._stop_requested = False
        logger.info("Background scanner started")
        
        discovery = LogFileDiscovery()
        parser = LogParser()
        
        # Check if this is initial scan (no positions saved)
        self._is_initial_scan = len(self._positions) == 0
        
        while not self._stop_requested:
            try:
                # Discover current log files
                sources = discovery.discover_all_files()
                
                if not sources:
                    self._sleep_interruptible(self.SCAN_INTERVAL)
                    continue
                
                progress = ScanProgress(
                    files_total=len(sources),
                    is_initial_scan=self._is_initial_scan
                )
                
                stations_updated = 0
                
                for source in sources:
                    if self._stop_requested:
                        break
                    
                    path_str = str(source.path)
                    
                    # Get or create position tracker
                    if path_str not in self._positions:
                        self._positions[path_str] = FilePosition(path=path_str)
                    
                    pos = self._positions[path_str]
                    
                    # Check if file has new data
                    try:
                        file_size = source.path.stat().st_size
                    except OSError:
                        continue
                    
                    if file_size <= pos.byte_offset:
                        # No new data
                        progress.files_done += 1
                        continue
                    
                    # Process new data from this file
                    new_decodes = self._scan_file_incremental(
                        source, parser, pos, progress
                    )
                    
                    if new_decodes:
                        # Process decodes for behavior analysis
                        updated = self._process_decodes(new_decodes)
                        stations_updated += updated
                        progress.stations_updated = stations_updated
                    
                    progress.files_done += 1
                    self.progress_updated.emit(progress)
                    
                    # Check for priority callsigns
                    self._process_priority_callsigns()
                    
                    # Periodic save
                    if time.time() - self._last_save_time > self.SAVE_INTERVAL:
                        self._save_all()
                
                # Emit completion signal
                if stations_updated > 0:
                    self.scan_complete.emit(stations_updated)
                
                # No longer initial scan after first pass
                self._is_initial_scan = False
                
                # Wait before next scan cycle
                self._sleep_interruptible(self.SCAN_INTERVAL)
                
            except Exception as e:
                logger.error(f"Background scanner error: {e}")
                self._sleep_interruptible(self.SCAN_INTERVAL)
        
        # Final save on shutdown
        self._save_all()
        self._running = False
        logger.info("Background scanner stopped")
    
    def _sleep_interruptible(self, seconds: float):
        """Sleep that can be interrupted by stop request."""
        end_time = time.time() + seconds
        while time.time() < end_time and not self._stop_requested:
            time.sleep(0.5)
    
    def _scan_file_incremental(self, source, parser, pos: FilePosition, 
                                progress: ScanProgress) -> List:
        """
        Scan a file from last known position.
        
        Returns list of new Decode objects.
        """
        from local_intel.log_parser import LogParser
        
        new_decodes = []
        
        try:
            with open(source.path, 'r', encoding='utf-8', errors='replace') as f:
                # Seek to last position
                if pos.byte_offset > 0:
                    f.seek(pos.byte_offset)
                
                # Read and parse new lines
                for line in f:
                    if self._stop_requested:
                        break
                    
                    decode = parser.parse_line(line)
                    if decode:
                        new_decodes.append(decode)
                        progress.decodes_processed += 1
                
                # Update position
                pos.byte_offset = f.tell()
                pos.last_scanned = datetime.now().isoformat()
                if new_decodes:
                    last_ts = new_decodes[-1].timestamp
                    if last_ts:
                        pos.last_timestamp = last_ts.isoformat()
                        
        except Exception as e:
            logger.error(f"Error scanning {source.path}: {e}")
        
        return new_decodes
    
    def _process_decodes(self, decodes: List) -> int:
        """
        Process decodes for behavior analysis.
        
        Uses Bayesian approach: just increment counts based on observations.
        
        Returns number of stations updated.
        """
        if not decodes:
            return 0
        
        # Sort by timestamp
        decodes.sort(key=lambda d: d.timestamp or datetime.min)
        
        # Track DX activity in this batch
        # dx_data[call] = {
        #   'callers': {caller: snr},  # Current pileup
        #   'answers': [],  # (was_loudest, caller)
        # }
        dx_data: Dict[str, dict] = {}
        
        # Find stations who CQ in this batch
        for d in decodes:
            if d.is_cq and d.callsign:
                call = d.callsign.upper()
                if call not in dx_data:
                    dx_data[call] = {'callers': {}, 'answers': []}
        
        if not dx_data:
            return 0
        
        # Process activity
        for d in decodes:
            # Track callers to DX
            if d.replying_to:
                dx_call = d.replying_to.upper()
                caller = d.callsign.upper() if d.callsign else None
                
                if dx_call in dx_data and caller:
                    dx_data[dx_call]['callers'][caller] = d.snr or -20
                
                # Check if sender is DX answering someone
                if d.callsign:
                    sender = d.callsign.upper()
                    if sender in dx_data:
                        answered = d.replying_to.upper()
                        data = dx_data[sender]
                        callers = data['callers']
                        
                        if callers:
                            answered_snr = callers.get(answered, -20)
                            max_snr = max(callers.values()) if callers else answered_snr
                            was_loudest = answered_snr >= max_snr - 1
                            data['answers'].append((was_loudest, answered))
            
            # Reset pileup on CQ
            if d.is_cq and d.callsign:
                call = d.callsign.upper()
                if call in dx_data:
                    dx_data[call]['callers'].clear()
        
        # Update behavior predictor with observations
        stations_updated = 0
        
        for dx_call, data in dx_data.items():
            answers = data['answers']
            if not answers:
                continue
            
            # Increment counts in behavior predictor
            try:
                updated = self._predictor.update_observations(
                    dx_call, 
                    answers
                )
                if updated:
                    stations_updated += 1
                    self.station_updated.emit(dx_call)
            except Exception as e:
                logger.error(f"Error updating {dx_call}: {e}")
        
        self._decodes_since_save += len(decodes)
        
        return stations_updated
    
    def _process_priority_callsigns(self):
        """Process any priority callsigns immediately."""
        with QMutexLocker(self._mutex):
            callsigns = list(self._priority_callsigns)
            self._priority_callsigns.clear()
        
        # For now, just mark them as processed
        # Full lookup would require re-scanning which defeats the purpose
        # Priority callsigns get live tracking instead
        for call in callsigns:
            logger.debug(f"Priority callsign {call} - will track live")
    
    def _save_all(self):
        """Save positions and behavior history."""
        self._save_positions()
        self._predictor._save_history()
        self._last_save_time = time.time()
        self._decodes_since_save = 0
        logger.debug("Background scanner: saved positions and history")
