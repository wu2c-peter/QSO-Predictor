# PSK Reporter API Client
# v2.1.0 - Phase 2 Path Intelligence
#
# Provides reverse lookups: "Who hears station X?"
# Used for beaming detection and directional analysis.

import time
import math
import logging
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SpotRecord:
    """A single spot from PSK Reporter."""
    receiver_call: str
    receiver_grid: str
    snr: int
    freq: int
    timestamp: float


class PSKReporterAPI:
    """
    Client for PSK Reporter reverse lookups.
    
    Rate limited and cached to avoid hammering the API.
    """
    
    BASE_URL = "https://retrieve.pskreporter.info/query"
    
    # Cache settings
    CACHE_TTL = 300  # 5 minutes
    MIN_REFRESH_INTERVAL = 60  # 1 minute between refreshes for same station
    
    # Rate limiting
    MAX_REQUESTS_PER_MINUTE = 10
    
    def __init__(self):
        self._cache: Dict[str, dict] = {}  # call -> {data, timestamp}
        self._last_request_time = 0
        self._request_count = 0
        self._minute_start = time.time()
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = time.time()
        
        # Reset counter every minute
        if now - self._minute_start > 60:
            self._minute_start = now
            self._request_count = 0
        
        if self._request_count >= self.MAX_REQUESTS_PER_MINUTE:
            logger.warning("PSK Reporter rate limit reached")
            return False
        
        return True
    
    def _get_cached(self, call: str) -> Optional[List[SpotRecord]]:
        """Get cached data if still valid."""
        if call in self._cache:
            entry = self._cache[call]
            age = time.time() - entry['timestamp']
            if age < self.CACHE_TTL:
                logger.debug(f"Cache hit for {call} (age: {age:.0f}s)")
                return entry['data']
        return None
    
    def _can_refresh(self, call: str) -> bool:
        """Check if enough time has passed to refresh this station."""
        if call not in self._cache:
            return True
        age = time.time() - self._cache[call]['timestamp']
        return age >= self.MIN_REFRESH_INTERVAL
    
    def reverse_lookup(self, call: str, force: bool = False) -> Optional[List[SpotRecord]]:
        """
        Find all stations that have heard the given callsign recently.
        
        Args:
            call: Callsign to look up
            force: Force refresh even if cached
            
        Returns:
            List of SpotRecord, or None if request failed
        """
        call = call.upper().strip()
        
        # Check cache first
        if not force:
            cached = self._get_cached(call)
            if cached is not None:
                return cached
        
        # Check if we can refresh
        if not force and not self._can_refresh(call):
            logger.debug(f"Too soon to refresh {call}, returning stale cache")
            return self._get_cached(call)
        
        # Check rate limit
        if not self._check_rate_limit():
            return self._get_cached(call)
        
        # Make the request
        try:
            params = {
                'senderCallsign': call,
                'flowStartSeconds': -3600,  # Last 1 hour (was 15 min)
                'rronly': 1,  # Reception reports only
                'noactive': 1,  # Don't need active reporters
                'format': 'json'
            }
            
            # Headers required by PSK Reporter
            headers = {
                'User-Agent': 'QSO-Predictor/2.1.0 (Amateur Radio Tool; +https://github.com/wu2c-peter/qso-predictor)',
                'Accept': 'application/json'
            }
            
            logger.info(f"PSK Reporter lookup: {call}")
            
            response = requests.get(
                self.BASE_URL,
                params=params,
                headers=headers,
                timeout=10
            )
            
            self._request_count += 1
            self._last_request_time = time.time()
            
            if response.status_code != 200:
                logger.error(f"PSK Reporter API error: {response.status_code}")
                return None
            
            data = response.json()
            
            # DEBUG: Log the raw response structure
            logger.info(f"PSK Reporter raw keys: {list(data.keys())}")
            if 'receptionReport' in data:
                reports = data['receptionReport']
                logger.info(f"receptionReport type: {type(reports)}, count: {len(reports) if isinstance(reports, list) else 'not a list'}")
            else:
                # Try other common wrapper structures
                logger.info(f"No 'receptionReport' key. Full response (truncated): {str(data)[:500]}")
            
            # Parse the response
            spots = self._parse_response(data)
            
            # Cache it
            self._cache[call] = {
                'data': spots,
                'timestamp': time.time()
            }
            
            logger.info(f"PSK Reporter: {call} heard by {len(spots)} stations")
            return spots
            
        except requests.RequestException as e:
            logger.error(f"PSK Reporter request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"PSK Reporter parse error: {e}")
            return None
    
    def _parse_response(self, data: dict) -> List[SpotRecord]:
        """Parse PSK Reporter JSON response into SpotRecords."""
        spots = []
        
        # Handle various PSK Reporter response formats
        # Try direct 'receptionReport' first
        reception_reports = data.get('receptionReport', [])
        
        # Try nested under 'initialDataReception'
        if not reception_reports and 'initialDataReception' in data:
            inner = data['initialDataReception']
            if isinstance(inner, dict):
                reception_reports = inner.get('receptionReport', [])
        
        # Try nested under 'receptionReports' (plural)
        if not reception_reports:
            reception_reports = data.get('receptionReports', [])
        
        # Ensure it's a list
        if not isinstance(reception_reports, list):
            if reception_reports:
                reception_reports = [reception_reports]
            else:
                reception_reports = []
        
        logger.debug(f"Parsing {len(reception_reports)} reception reports")
        
        for report in reception_reports:
            try:
                receiver_call = report.get('receiverCallsign', '')
                receiver_grid = report.get('receiverLocator', '')
                snr = int(report.get('sNR', -99))
                freq = int(report.get('frequency', 0))
                timestamp = float(report.get('flowStartSeconds', 0))
                
                if receiver_call and receiver_grid:
                    spots.append(SpotRecord(
                        receiver_call=receiver_call,
                        receiver_grid=receiver_grid,
                        snr=snr,
                        freq=freq,
                        timestamp=timestamp
                    ))
            except (ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed spot: {e}")
                continue
        
        return spots
    
    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()


def calculate_bearing(from_grid: str, to_grid: str) -> Optional[float]:
    """
    Calculate bearing from one grid to another.
    
    Args:
        from_grid: Starting grid (4-6 chars)
        to_grid: Destination grid (4-6 chars)
    
    Returns:
        Bearing in degrees (0-360), or None if grids invalid
    """
    try:
        lat1, lon1 = grid_to_latlon(from_grid)
        lat2, lon2 = grid_to_latlon(to_grid)
        
        if lat1 is None or lat2 is None:
            return None
        
        # Convert to radians
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlon_r = math.radians(lon2 - lon1)
        
        x = math.sin(dlon_r) * math.cos(lat2_r)
        y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon_r)
        
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360
        
    except Exception as e:
        logger.debug(f"Bearing calculation error: {e}")
        return None


def grid_to_latlon(grid: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Convert Maidenhead grid to lat/lon (center of grid square).
    
    Args:
        grid: Maidenhead locator (2-6 chars)
        
    Returns:
        (latitude, longitude) or (None, None) if invalid
    """
    grid = grid.upper().strip()
    
    if len(grid) < 2:
        return None, None
    
    try:
        # Field (2 chars)
        lon = (ord(grid[0]) - ord('A')) * 20 - 180
        lat = (ord(grid[1]) - ord('A')) * 10 - 90
        
        if len(grid) >= 4:
            # Square (2 more chars)
            lon += int(grid[2]) * 2
            lat += int(grid[3]) * 1
        
        if len(grid) >= 6:
            # Subsquare (2 more chars)
            lon += (ord(grid[4]) - ord('A')) * (2/24)
            lat += (ord(grid[5]) - ord('A')) * (1/24)
        
        # Return center of grid
        if len(grid) == 2:
            lon += 10
            lat += 5
        elif len(grid) == 4:
            lon += 1
            lat += 0.5
        elif len(grid) >= 6:
            lon += 1/24
            lat += 0.5/24
        
        return lat, lon
        
    except (ValueError, IndexError):
        return None, None


def bearing_to_region(bearing: float) -> str:
    """
    Convert bearing to general region name.
    
    This is a rough approximation based on typical amateur radio
    path directions from North America.
    """
    # Normalize to 0-360
    bearing = bearing % 360
    
    # Rough regions (from eastern North America perspective)
    if 20 <= bearing < 70:
        return "EU"  # Europe
    elif 70 <= bearing < 120:
        return "AF/ME"  # Africa/Middle East
    elif 120 <= bearing < 180:
        return "AS"  # Asia (southern route)
    elif 180 <= bearing < 240:
        return "OC"  # Oceania
    elif 240 <= bearing < 300:
        return "SA"  # South America
    elif 300 <= bearing < 340:
        return "CA"  # Caribbean/Central America
    else:
        return "NA"  # North America (NE or NW)


def classify_beam_pattern(bearings: List[float]) -> Tuple[bool, str, int]:
    """
    Determine if a station appears to be beaming directionally.
    
    Args:
        bearings: List of bearings to all stations that heard them
        
    Returns:
        (is_beaming, primary_direction, confidence_percent)
    """
    if len(bearings) < 3:
        return False, "", 0
    
    # Group into 45-degree sectors (8 sectors)
    sectors = [0] * 8
    for b in bearings:
        sector = int(b / 45) % 8
        sectors[sector] = sectors[sector] + 1
    
    total = len(bearings)
    
    # Find the dominant sector and its neighbors
    max_sector = sectors.index(max(sectors))
    
    # Count spots in dominant sector + adjacent sectors (3 sectors = 135 degrees)
    left = (max_sector - 1) % 8
    right = (max_sector + 1) % 8
    concentrated = sectors[left] + sectors[max_sector] + sectors[right]
    
    concentration_pct = int(100 * concentrated / total)
    
    # If >70% of spots are in a 135-degree arc, likely beaming
    is_beaming = concentration_pct >= 70
    
    # Determine primary direction
    center_bearing = max_sector * 45 + 22.5
    direction = bearing_to_region(center_bearing)
    
    return is_beaming, direction, concentration_pct


# Singleton instance
_api_instance = None

def get_api() -> PSKReporterAPI:
    """Get the singleton API instance."""
    global _api_instance
    if _api_instance is None:
        _api_instance = PSKReporterAPI()
    return _api_instance
