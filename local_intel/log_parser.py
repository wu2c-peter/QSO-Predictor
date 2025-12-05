"""
Log Parser for QSO Predictor v2.0

Parses WSJT-X and JTDX all.txt log files into structured Decode objects.
Handles message parsing to extract callsigns, grids, and message types.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import re
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Iterator, Tuple, Dict
from dataclasses import dataclass

from .models import Decode, LogFileSource, QSO

logger = logging.getLogger(__name__)


# =============================================================================
# Message Parsing Patterns
# =============================================================================

# Callsign pattern (basic - covers most cases)
CALLSIGN_PATTERN = re.compile(
    r'^[A-Z0-9]{1,3}[0-9][A-Z0-9]{0,3}[A-Z](?:/[A-Z0-9]+)?$',
    re.IGNORECASE
)

# Grid square pattern (4 or 6 character)
GRID_PATTERN = re.compile(r'^[A-R]{2}[0-9]{2}(?:[A-X]{2})?$', re.IGNORECASE)

# Signal report pattern
REPORT_PATTERN = re.compile(r'^[+-]?\d{2}$')

# Callsign pattern - includes optional <> for hashed calls
CALL_PATTERN = r'<?[A-Z0-9/]+>?'

# Common FT8/FT4 message formats
MESSAGE_PATTERNS = {
    # CQ messages
    'cq_basic': re.compile(rf'^CQ\s+({CALL_PATTERN})\s+([A-R]{{2}}\d{{2}})', re.IGNORECASE),
    'cq_dx': re.compile(rf'^CQ\s+DX\s+({CALL_PATTERN})\s+([A-R]{{2}}\d{{2}})', re.IGNORECASE),
    'cq_region': re.compile(rf'^CQ\s+([A-Z]{{2,4}})\s+({CALL_PATTERN})\s+([A-R]{{2}}\d{{2}})', re.IGNORECASE),
    
    # Standard exchange
    'grid_reply': re.compile(rf'^({CALL_PATTERN})\s+({CALL_PATTERN})\s+([A-R]{{2}}\d{{2}})', re.IGNORECASE),
    'report_reply': re.compile(rf'^({CALL_PATTERN})\s+({CALL_PATTERN})\s+([+-]?\d{{2}})\s*$', re.IGNORECASE),
    'r_report': re.compile(rf'^({CALL_PATTERN})\s+({CALL_PATTERN})\s+R([+-]?\d{{2}})', re.IGNORECASE),
    'rr73': re.compile(rf'^({CALL_PATTERN})\s+({CALL_PATTERN})\s+RR73', re.IGNORECASE),
    'rr': re.compile(rf'^({CALL_PATTERN})\s+({CALL_PATTERN})\s+RRR', re.IGNORECASE),
    '73': re.compile(rf'^({CALL_PATTERN})\s+({CALL_PATTERN})\s+73', re.IGNORECASE),
}


@dataclass
class ParsedMessage:
    """Parsed components of an FT8/FT4 message."""
    raw: str
    message_type: str  # "cq", "grid", "report", "r_report", "rr73", "73", "unknown"
    
    # Participants
    caller: Optional[str] = None  # Station transmitting this message
    callee: Optional[str] = None  # Station being called (if applicable)
    
    # Data
    grid: Optional[str] = None
    report: Optional[int] = None
    
    # Flags
    is_cq: bool = False
    is_reply: bool = False
    is_final: bool = False  # RR73, 73, etc.


# =============================================================================
# Message Parser
# =============================================================================

def clean_callsign(call: str) -> str:
    """Remove <> brackets from hashed callsigns."""
    if call:
        return call.strip('<>').upper()
    return call


class MessageParser:
    """Parse FT8/FT4 message content."""
    
    @staticmethod
    def parse(message: str) -> ParsedMessage:
        """
        Parse an FT8/FT4 message into structured components.
        
        Args:
            message: Raw message text (e.g., "CQ W1ABC FN42")
            
        Returns:
            ParsedMessage with extracted components
        """
        message = message.strip().upper()
        result = ParsedMessage(raw=message, message_type="unknown")
        
        # Check CQ patterns
        for pattern_name in ['cq_basic', 'cq_dx', 'cq_region']:
            match = MESSAGE_PATTERNS[pattern_name].match(message)
            if match:
                groups = match.groups()
                result.message_type = "cq"
                result.is_cq = True
                if pattern_name == 'cq_basic':
                    result.caller = clean_callsign(groups[0])
                    result.grid = groups[1]
                elif pattern_name == 'cq_dx':
                    result.caller = clean_callsign(groups[0])
                    result.grid = groups[1]
                elif pattern_name == 'cq_region':
                    result.caller = clean_callsign(groups[1])
                    result.grid = groups[2]
                return result
        
        # Check final messages FIRST (before grid, since RR73 matches grid pattern)
        match = MESSAGE_PATTERNS['rr73'].match(message)
        if match:
            result.message_type = "rr73"
            result.is_reply = True
            result.is_final = True
            result.callee = clean_callsign(match.group(1))
            result.caller = clean_callsign(match.group(2))
            return result
        
        match = MESSAGE_PATTERNS['rr'].match(message)
        if match:
            result.message_type = "rrr"
            result.is_reply = True
            result.callee = clean_callsign(match.group(1))
            result.caller = clean_callsign(match.group(2))
            return result
        
        match = MESSAGE_PATTERNS['73'].match(message)
        if match:
            result.message_type = "73"
            result.is_reply = True
            result.is_final = True
            result.callee = clean_callsign(match.group(1))
            result.caller = clean_callsign(match.group(2))
            return result
        
        # Check R+report before plain report
        match = MESSAGE_PATTERNS['r_report'].match(message)
        if match:
            result.message_type = "r_report"
            result.is_reply = True
            result.callee = clean_callsign(match.group(1))
            result.caller = clean_callsign(match.group(2))
            result.report = int(match.group(3))
            return result
        
        # Check report patterns
        match = MESSAGE_PATTERNS['report_reply'].match(message)
        if match:
            result.message_type = "report"
            result.is_reply = True
            result.callee = clean_callsign(match.group(1))
            result.caller = clean_callsign(match.group(2))
            result.report = int(match.group(3))
            return result
        
        # Check grid reply (after finals and reports)
        match = MESSAGE_PATTERNS['grid_reply'].match(message)
        if match:
            result.message_type = "grid"
            result.is_reply = True
            result.callee = clean_callsign(match.group(1))
            result.caller = clean_callsign(match.group(2))
            result.grid = match.group(3)
            return result
        
        # Fallback: try to extract any callsigns from message
        parts = message.split()
        callsigns = [clean_callsign(p) for p in parts if CALLSIGN_PATTERN.match(p.strip('<>'))]
        if callsigns:
            result.caller = callsigns[-1]  # Usually last callsign is sender
            if len(callsigns) > 1:
                result.callee = callsigns[0]
        
        return result


# =============================================================================
# Log File Parser
# =============================================================================

class LogParser:
    """
    Parse WSJT-X and JTDX all.txt log files.
    
    all.txt format (WSJT-X):
    YYMMDD_HHMMSS    14.074 Rx FT8    -10  0.2 1542 CQ W1ABC FN42
    
    all.txt format (JTDX):
    2024-12-04 14:30:22  14.074 Rx FT8   -10  0.2 1542 CQ W1ABC FN42
    """
    
    # Line parsing pattern for WSJT-X format
    WSJTX_LINE = re.compile(
        r'^(\d{6}_\d{6})\s+'        # Timestamp: YYMMDD_HHMMSS
        r'(\d+\.\d+)\s+'             # Frequency: 14.074
        r'(Rx|Tx)\s+'                # Direction
        r'(FT8|FT4|JT65|JT9|FST4)\s+' # Mode
        r'([+-]?\d+)\s+'             # SNR
        r'([+-]?\d+\.\d+)\s+'        # DT
        r'(\d+)\s+'                  # Audio freq
        r'(.+)$'                     # Message
    )
    
    # Line parsing pattern for JTDX standard format
    JTDX_LINE = re.compile(
        r'^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+'  # Timestamp
        r'(\d+\.\d+)\s+'             # Frequency
        r'(Rx|Tx)\s+'                # Direction
        r'(FT8|FT4|JT65|JT9|FST4)\s+' # Mode
        r'([+-]?\d+)\s+'             # SNR
        r'([+-]?\d+\.\d+)\s+'        # DT
        r'(\d+)\s+'                  # Audio freq
        r'(.+)$'                     # Message
    )
    
    # Line parsing pattern for JTDX dated files (YYYYMM_ALL.TXT)
    # Format: 20251122_212145  -6  0.2 2521 ~ CQ WY0V EN12              *
    JTDX_DATED_LINE = re.compile(
        r'^(\d{8}_\d{6})\s+'        # Timestamp: YYYYMMDD_HHMMSS
        r'([+-]?\d+)\s+'             # SNR
        r'([+-]?\d+\.\d+)\s+'        # DT
        r'(\d+)\s+'                  # Audio freq
        r'~\s*'                      # Tilde separator
        r'(.+?)\s*[*d]?\s*$'         # Message (strip trailing * or d)
    )
    
    def __init__(self, my_callsign: str = None):
        """
        Initialize parser.
        
        Args:
            my_callsign: Your callsign for identifying your transmissions
        """
        self.my_callsign = my_callsign.upper() if my_callsign else None
        self.message_parser = MessageParser()
    
    def parse_file(self, 
                   source: LogFileSource,
                   start_date: datetime = None,
                   end_date: datetime = None,
                   rx_only: bool = True) -> Iterator[Decode]:
        """
        Parse a log file, yielding Decode objects.
        
        Args:
            source: LogFileSource to parse
            start_date: Only include decodes after this date
            end_date: Only include decodes before this date
            rx_only: Only include received decodes (not your TX)
            
        Yields:
            Decode objects
        """
        try:
            with open(source.path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        decode = self._parse_line(line, source.program)
                        if decode is None:
                            continue
                        
                        # Apply filters
                        if start_date and decode.timestamp < start_date:
                            continue
                        if end_date and decode.timestamp > end_date:
                            continue
                        if rx_only and decode.source == 'tx':
                            continue
                        
                        decode.source = source.program.lower()
                        yield decode
                        
                    except Exception as e:
                        if line_num <= 10:  # Only log first few errors
                            logger.debug(f"Failed to parse line {line_num}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to read {source.path}: {e}")
    
    def _parse_line(self, line: str, program: str) -> Optional[Decode]:
        """
        Parse a single log line.
        
        Args:
            line: Raw line from log file
            program: "WSJT-X" or "JTDX"
            
        Returns:
            Decode object or None if line doesn't match
        """
        line = line.strip()
        if not line:
            return None
        
        # Skip header/info lines
        if 'MHz' in line or 'partial loss' in line or 'JTDX v' in line:
            return None
        
        # Try WSJT-X format
        match = self.WSJTX_LINE.match(line)
        if match:
            return self._build_decode(match, 'wsjtx')
        
        # Try JTDX standard format
        match = self.JTDX_LINE.match(line)
        if match:
            return self._build_decode(match, 'jtdx')
        
        # Try JTDX dated file format (YYYYMM_ALL.TXT)
        match = self.JTDX_DATED_LINE.match(line)
        if match:
            return self._build_decode(match, 'jtdx_dated')
        
        return None
    
    def _build_decode(self, match: re.Match, format_type: str) -> Decode:
        """Build a Decode object from regex match."""
        groups = match.groups()
        
        if format_type == 'jtdx_dated':
            # JTDX dated format: YYYYMMDD_HHMMSS SNR DT FREQ ~ MESSAGE
            # Groups: timestamp, snr, dt, audio_freq, message
            timestamp = datetime.strptime(groups[0], '%Y%m%d_%H%M%S')
            snr = int(groups[1])
            dt = float(groups[2])
            audio_freq = int(groups[3])
            message = groups[4].strip()
            direction = 'rx'  # Dated files are RX only
            mode = 'FT8'  # Default, could be FT4 but no way to know
            dial_freq = 14.074  # Default, no dial freq in this format
        else:
            # Standard formats (wsjtx, jtdx)
            # Parse timestamp
            if format_type == 'wsjtx':
                timestamp = datetime.strptime(groups[0], '%y%m%d_%H%M%S')
            else:  # jtdx standard
                timestamp = datetime.strptime(groups[0], '%Y-%m-%d %H:%M:%S')
            
            # Parse other fields
            dial_freq = float(groups[1])
            direction = groups[2].lower()
            mode = groups[3]
            snr = int(groups[4])
            dt = float(groups[5])
            audio_freq = int(groups[6])
            message = groups[7].strip()
        
        # Parse message content
        parsed = self.message_parser.parse(message)
        
        # Build decode object
        decode = Decode(
            timestamp=timestamp,
            snr=snr,
            dt=dt,
            frequency=audio_freq,
            mode=mode,
            message=message,
            callsign=parsed.caller,
            grid=parsed.grid,
            is_cq=parsed.is_cq,
            is_reply=parsed.is_reply,
            replying_to=parsed.callee,
            source='tx' if direction == 'tx' else 'rx',
            dial_freq=int(dial_freq * 1_000_000),  # Convert to Hz
        )
        
        # Determine band from dial frequency
        decode.band = self._freq_to_band(dial_freq)
        
        return decode
    
    @staticmethod
    def _freq_to_band(freq_mhz: float) -> str:
        """Convert frequency in MHz to band name."""
        bands = [
            (1.8, 2.0, '160m'),
            (3.5, 4.0, '80m'),
            (5.3, 5.4, '60m'),
            (7.0, 7.3, '40m'),
            (10.1, 10.15, '30m'),
            (14.0, 14.35, '20m'),
            (18.068, 18.168, '17m'),
            (21.0, 21.45, '15m'),
            (24.89, 24.99, '12m'),
            (28.0, 29.7, '10m'),
            (50.0, 54.0, '6m'),
            (144.0, 148.0, '2m'),
        ]
        
        for low, high, name in bands:
            if low <= freq_mhz <= high:
                return name
        
        return 'unknown'
    
    def parse_files(self,
                    sources: List[LogFileSource],
                    start_date: datetime = None,
                    end_date: datetime = None,
                    progress_callback=None) -> List[Decode]:
        """
        Parse multiple log files.
        
        Args:
            sources: List of log file sources
            start_date: Only include decodes after this date
            end_date: Only include decodes before this date
            progress_callback: Called with (current, total) for progress
            
        Returns:
            List of all decoded entries, sorted by timestamp
        """
        all_decodes = []
        total_files = len(sources)
        
        for i, source in enumerate(sources):
            if progress_callback:
                progress_callback(i, total_files)
            
            decodes = list(self.parse_file(source, start_date, end_date))
            all_decodes.extend(decodes)
            
            logger.info(f"Parsed {len(decodes)} decodes from {source.path.name}")
        
        if progress_callback:
            progress_callback(total_files, total_files)
        
        # Sort by timestamp
        all_decodes.sort(key=lambda d: d.timestamp)
        
        return all_decodes


# =============================================================================
# QSO Extraction
# =============================================================================

class QSOExtractor:
    """
    Extract completed QSOs from decode stream.
    
    Tracks message exchanges to identify completed contacts.
    """
    
    def __init__(self, my_callsign: str):
        """
        Initialize extractor.
        
        Args:
            my_callsign: Your callsign
        """
        self.my_callsign = my_callsign.upper()
        self.pending_qsos: Dict[str, dict] = {}  # callsign -> QSO state
    
    def extract_qsos(self, decodes: List[Decode]) -> List[QSO]:
        """
        Extract QSOs from a list of decodes.
        
        Args:
            decodes: List of Decode objects (should be sorted by time)
            
        Returns:
            List of completed QSOs
        """
        qsos = []
        
        for decode in decodes:
            parsed = MessageParser.parse(decode.message)
            
            # Check if this involves us
            if not self._involves_me(parsed):
                continue
            
            other_call = self._get_other_callsign(parsed)
            if not other_call:
                continue
            
            # Track QSO state
            if other_call not in self.pending_qsos:
                self.pending_qsos[other_call] = {
                    'started': decode.timestamp,
                    'band': decode.band,
                    'mode': decode.mode,
                    'grid': None,
                    'sent_report': None,
                    'rcvd_report': None,
                    'last_activity': decode.timestamp,
                }
            
            state = self.pending_qsos[other_call]
            state['last_activity'] = decode.timestamp
            
            # Update state based on message type
            if parsed.grid:
                state['grid'] = parsed.grid
            
            if parsed.report is not None:
                if parsed.caller == self.my_callsign:
                    state['sent_report'] = parsed.report
                else:
                    state['rcvd_report'] = parsed.report
            
            # Check for QSO completion
            if parsed.is_final:
                qso = QSO(
                    timestamp=state['started'],
                    callsign=other_call,
                    grid=state['grid'],
                    band=state['band'],
                    mode=state['mode'],
                    sent_snr=state['sent_report'],
                    rcvd_snr=state['rcvd_report'],
                )
                qsos.append(qso)
                del self.pending_qsos[other_call]
        
        # Clean up stale pending QSOs (> 10 minutes old)
        cutoff = datetime.now() - timedelta(minutes=10)
        stale = [
            call for call, state in self.pending_qsos.items()
            if state['last_activity'] < cutoff
        ]
        for call in stale:
            del self.pending_qsos[call]
        
        return qsos
    
    def _involves_me(self, parsed: ParsedMessage) -> bool:
        """Check if message involves our callsign."""
        if parsed.caller == self.my_callsign:
            return True
        if parsed.callee == self.my_callsign:
            return True
        return False
    
    def _get_other_callsign(self, parsed: ParsedMessage) -> Optional[str]:
        """Get the other station's callsign from a message."""
        if parsed.caller == self.my_callsign:
            return parsed.callee
        elif parsed.callee == self.my_callsign:
            return parsed.caller
        return None


# =============================================================================
# Convenience Functions
# =============================================================================

def parse_log_files(sources: List[LogFileSource],
                    my_callsign: str = None,
                    start_date: datetime = None,
                    end_date: datetime = None) -> Tuple[List[Decode], List[QSO]]:
    """
    Parse log files and extract QSOs.
    
    Args:
        sources: Log files to parse
        my_callsign: Your callsign (for QSO extraction)
        start_date: Start of date range
        end_date: End of date range
        
    Returns:
        Tuple of (decodes, qsos)
    """
    parser = LogParser(my_callsign)
    decodes = parser.parse_files(sources, start_date, end_date)
    
    qsos = []
    if my_callsign:
        extractor = QSOExtractor(my_callsign)
        qsos = extractor.extract_qsos(decodes)
    
    return decodes, qsos
