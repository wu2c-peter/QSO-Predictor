# QSO Predictor - Hunt Mode
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# Hunt Mode allows users to track specific stations, prefixes, grids, or DXCC entities.
# Alerts when hunted stations become active, especially when working stations nearby.
#
# v2.1.0: Initial implementation (suggested by Warren KC0GU)

import logging
import re
from typing import Set, Optional, List, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

# DXCC Entity to prefix mapping (curated list of common entities)
# Users can type either the country name or the prefix
DXCC_ENTITIES = {
    # North America
    "UNITED STATES": ["K", "W", "N", "AA", "AB", "AC", "AD", "AE", "AF", "AG", "AI", "AJ", "AK"],
    "CANADA": ["VE", "VA", "VO", "VY"],
    "MEXICO": ["XE", "XF"],
    "ALASKA": ["KL", "AL", "NL", "WL"],
    "HAWAII": ["KH6", "AH6", "NH6", "WH6"],
    "PUERTO RICO": ["KP4", "NP4", "WP4"],
    "US VIRGIN ISLANDS": ["KP2", "NP2", "WP2"],
    
    # Europe
    "ENGLAND": ["G", "M", "2E"],
    "SCOTLAND": ["GM", "MM", "2M"],
    "WALES": ["GW", "MW", "2W"],
    "NORTHERN IRELAND": ["GI", "MI"],
    "GERMANY": ["DL", "DA", "DB", "DC", "DD", "DE", "DF", "DG", "DH", "DI", "DJ", "DK", "DM", "DN", "DO", "DP", "DQ", "DR"],
    "FRANCE": ["F"],
    "SPAIN": ["EA", "EB", "EC", "ED", "EE", "EF", "EG", "EH"],
    "ITALY": ["I", "IK", "IZ", "IU", "IW"],
    "NETHERLANDS": ["PA", "PB", "PC", "PD", "PE", "PF", "PG", "PH", "PI"],
    "BELGIUM": ["ON", "OO", "OQ", "OR", "OS", "OT"],
    "SWITZERLAND": ["HB9", "HB0"],
    "AUSTRIA": ["OE"],
    "POLAND": ["SP", "SQ", "SO", "SN", "3Z"],
    "CZECH REPUBLIC": ["OK", "OL"],
    "SWEDEN": ["SM", "SA", "SB", "SC", "SD", "SE", "SF", "SG", "SH", "SI", "SJ", "SK", "SL", "7S", "8S"],
    "NORWAY": ["LA", "LB", "LC", "LD", "LE", "LF", "LG", "LH", "LI", "LJ", "LK", "LL", "LM", "LN"],
    "FINLAND": ["OH", "OG", "OI"],
    "DENMARK": ["OZ", "OU", "OV", "OW", "5P", "5Q"],
    "PORTUGAL": ["CT", "CQ", "CR", "CS"],
    "GREECE": ["SV", "SW", "SX", "SY", "SZ", "J4"],
    "RUSSIA": ["UA", "RA", "R", "RK", "RN", "RU", "RV", "RW", "RX", "RY", "RZ", "U"],
    "UKRAINE": ["UR", "US", "UT", "UU", "UV", "UW", "UX", "UY", "UZ"],
    "CROATIA": ["9A"],
    "SLOVENIA": ["S5"],
    "SERBIA": ["YU", "YT"],
    "HUNGARY": ["HA", "HG"],
    "ROMANIA": ["YO", "YP", "YQ", "YR"],
    "BULGARIA": ["LZ"],
    "IRELAND": ["EI", "EJ"],
    
    # Asia
    "JAPAN": ["JA", "JE", "JF", "JG", "JH", "JI", "JJ", "JK", "JL", "JM", "JN", "JO", "JP", "JQ", "JR", "JS", "7J", "7K", "7L", "7M", "7N", "8J", "8K", "8L", "8M", "8N"],
    "CHINA": ["BY", "BA", "BD", "BG", "BH", "BI", "BJ", "BL", "BM", "BO", "BP", "BQ", "BR", "BS", "BT", "BU", "BV", "BW", "BX", "BZ"],
    "SOUTH KOREA": ["HL", "DS", "DT", "6K", "6L", "6M", "6N"],
    "TAIWAN": ["BV", "BW", "BX"],
    "HONG KONG": ["VR"],
    "INDIA": ["VU", "AT", "AU", "AV", "AW", "AX"],
    "THAILAND": ["HS", "E2"],
    "PHILIPPINES": ["DU", "DV", "DW", "DX", "DY", "DZ", "4D", "4E", "4F", "4G", "4H", "4I"],
    "INDONESIA": ["YB", "YC", "YD", "YE", "YF", "YG", "YH"],
    "MALAYSIA": ["9M", "9W"],
    "SINGAPORE": ["9V"],
    "VIETNAM": ["XV", "3W"],
    
    # Oceania
    "AUSTRALIA": ["VK"],
    "NEW ZEALAND": ["ZL", "ZM"],
    "FIJI": ["3D2"],
    "PAPUA NEW GUINEA": ["P2"],
    "GUAM": ["KH2", "AH2", "NH2", "WH2"],
    
    # South America
    "BRAZIL": ["PY", "PP", "PQ", "PR", "PS", "PT", "PU", "PV", "PW", "PX", "ZV", "ZW", "ZX", "ZY", "ZZ"],
    "ARGENTINA": ["LU", "LO", "LP", "LQ", "LR", "LS", "LT", "LV", "LW", "AY", "AZ", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"],
    "CHILE": ["CE", "CA", "CB", "CC", "CD", "XQ", "XR", "3G"],
    "COLOMBIA": ["HK", "HJ", "5J", "5K"],
    "VENEZUELA": ["YV", "YW", "YX", "YY", "4M"],
    "PERU": ["OA", "OB", "OC", "4T"],
    "ECUADOR": ["HC", "HD"],
    "URUGUAY": ["CX", "CV", "CW"],
    "PARAGUAY": ["ZP"],
    "BOLIVIA": ["CP"],
    
    # Africa
    "SOUTH AFRICA": ["ZS", "ZR", "ZT", "ZU", "V9"],
    "NIGERIA": ["5N", "5O"],
    "KENYA": ["5Y", "5Z"],
    "EGYPT": ["SU"],
    "MOROCCO": ["CN"],
    "TUNISIA": ["3V", "TS"],
    "ALGERIA": ["7X"],
    "SENEGAL": ["6W"],
    "GHANA": ["9G"],
    "NAMIBIA": ["V5"],
    "BOTSWANA": ["A2"],
    "ZIMBABWE": ["Z2"],
    "ZAMBIA": ["9J"],
    "MOZAMBIQUE": ["C9"],
    "MADAGASCAR": ["5R", "5S"],
    "MAURITIUS": ["3B8"],
    "REUNION": ["FR"],
    
    # Caribbean
    "CUBA": ["CM", "CL", "CO", "T4"],
    "DOMINICAN REPUBLIC": ["HI"],
    "HAITI": ["HH"],
    "JAMAICA": ["6Y"],
    "BAHAMAS": ["C6"],
    "BARBADOS": ["8P"],
    "TRINIDAD": ["9Y", "9Z"],
    "ARUBA": ["P4"],
    "CURACAO": ["PJ2"],
    "BONAIRE": ["PJ4"],
    "CAYMAN ISLANDS": ["ZF"],
    "BERMUDA": ["VP9"],
    "TURKS AND CAICOS": ["VP5"],
    
    # Rare/DXpedition targets
    "BOUVET": ["3Y0"],
    "HEARD ISLAND": ["VK0H"],
    "PETER I": ["3Y0P"],
    "NORTH KOREA": ["P5"],
    "NAVASSA": ["KP1"],
    "DESECHEO": ["KP5"],
    "BAKER HOWLAND": ["KH1"],
    "MIDWAY": ["KH4"],
    "PALMYRA JARVIS": ["KH5"],
    "WAKE": ["KH9"],
    "AMSTERDAM ST PAUL": ["FT5Z"],
    "CROZET": ["FT5W"],
    "KERGUELEN": ["FT5X"],
    "SVALBARD": ["JW"],
    "FRANZ JOSEF LAND": ["R1FJ"],
    "MARKET REEF": ["OJ0"],
    "MOUNT ATHOS": ["SV/A"],
    "SOVEREIGN MILITARY ORDER OF MALTA": ["1A"],
}


class HuntManager(QObject):
    """Manages the hunt list and alerts for Hunt Mode.
    
    Hunt list can contain:
    - Full callsigns: "K5D", "3Y0J"
    - Prefixes: "VU4" (matches VU4A, VU4B, etc.)
    - Grids: "FN31" (matches stations in that grid)
    - DXCC prefixes: "ZL" (matches all New Zealand)
    
    Signals:
        hunt_alert: Emitted when a hunted station is spotted
            - call: The callsign spotted
            - band: Band they're on
            - alert_type: 'active' or 'working_nearby'
            - details: Additional info (e.g., "working FN grids")
        
        hunt_list_changed: Emitted when hunt list is modified
    """
    
    hunt_alert = pyqtSignal(str, str, str, str)  # call, band, alert_type, details
    hunt_list_changed = pyqtSignal()
    
    def __init__(self, config_manager=None):
        super().__init__()
        self._hunt_list: Set[str] = set()
        self._config = config_manager
        self._my_grid = ""
        
        # Track recent alerts to avoid spam (call -> last_alert_time)
        self._recent_alerts: Dict[str, float] = {}
        self._alert_cooldown = 60  # seconds between alerts for same call
        
        # Load saved hunt list
        if self._config:
            self._load_from_config()
    
    def set_my_grid(self, grid: str):
        """Set user's grid for 'working nearby' detection."""
        self._my_grid = grid.upper()[:4] if grid else ""
    
    def _load_from_config(self):
        """Load hunt list from config file."""
        try:
            hunt_str = self._config.get('HUNT', 'list', fallback='')
            if hunt_str:
                items = [item.strip().upper() for item in hunt_str.split(',') if item.strip()]
                self._hunt_list = set(items)
                logger.info(f"Hunt Mode: Loaded {len(self._hunt_list)} items from config")
        except Exception as e:
            logger.warning(f"Hunt Mode: Could not load config - {e}")
    
    def _save_to_config(self):
        """Save hunt list to config file."""
        if self._config:
            hunt_str = ','.join(sorted(self._hunt_list))
            self._config.save_setting('HUNT', 'list', hunt_str)
    
    def add(self, item: str) -> bool:
        """Add item to hunt list. Returns True if added (not duplicate).
        
        Accepts:
        - Callsigns: "K5D", "3Y0J"
        - Prefixes: "VU4", "ZL"
        - Grids: "FN31"
        - Country names: "Japan", "New Zealand" (case insensitive)
        """
        item = item.strip().upper()
        if not item:
            return False
        
        # Check if this is a country name
        if item in DXCC_ENTITIES:
            # Store the country name itself (we'll expand to prefixes when matching)
            pass  # item is already the country name
        
        if item in self._hunt_list:
            logger.debug(f"Hunt Mode: '{item}' already in list")
            return False
        
        self._hunt_list.add(item)
        self._save_to_config()
        self.hunt_list_changed.emit()
        logger.info(f"Hunt Mode: Added '{item}' to hunt list")
        return True
    
    def remove(self, item: str) -> bool:
        """Remove item from hunt list. Returns True if removed."""
        item = item.strip().upper()
        if item not in self._hunt_list:
            return False
        
        self._hunt_list.discard(item)
        self._save_to_config()
        self.hunt_list_changed.emit()
        logger.info(f"Hunt Mode: Removed '{item}' from hunt list")
        return True
    
    def clear(self):
        """Clear all items from hunt list."""
        self._hunt_list.clear()
        self._save_to_config()
        self.hunt_list_changed.emit()
        logger.info("Hunt Mode: Cleared hunt list")
    
    def get_list(self) -> List[str]:
        """Get sorted copy of hunt list."""
        return sorted(self._hunt_list)
    
    def is_empty(self) -> bool:
        """Check if hunt list is empty."""
        return len(self._hunt_list) == 0
    
    def is_hunted(self, callsign: str) -> bool:
        """Check if callsign matches any item in hunt list.
        
        Matches:
        - Exact callsign match
        - Prefix match (hunt "VU4" matches "VU4A")
        - DXCC entity match (hunt "JAPAN" matches "JA1ABC")
        """
        if not callsign or not self._hunt_list:
            return False
        
        call = callsign.strip().upper()
        
        for hunt_item in self._hunt_list:
            # Check if hunt_item is a DXCC entity (country name)
            if hunt_item in DXCC_ENTITIES:
                prefixes = DXCC_ENTITIES[hunt_item]
                for prefix in prefixes:
                    if call.startswith(prefix):
                        return True
                continue
            
            # Exact match
            if call == hunt_item:
                return True
            
            # Prefix match - hunt item is prefix of callsign
            if call.startswith(hunt_item):
                return True
        
        return False
    
    def is_grid_hunted(self, grid: str) -> bool:
        """Check if grid matches any item in hunt list."""
        if not grid or not self._hunt_list:
            return False
        
        grid = grid.strip().upper()
        
        for hunt_item in self._hunt_list:
            # Grid match (2 or 4 char)
            if len(hunt_item) in [2, 4, 6] and grid.startswith(hunt_item):
                return True
        
        return False
    
    @staticmethod
    def get_available_countries() -> List[str]:
        """Get list of available DXCC entity names for autocomplete."""
        return sorted(DXCC_ENTITIES.keys())
    
    @staticmethod
    def is_country_name(item: str) -> bool:
        """Check if item is a known DXCC country name."""
        return item.upper() in DXCC_ENTITIES
    
    @staticmethod
    def get_country_prefixes(country: str) -> List[str]:
        """Get prefixes for a country name."""
        return DXCC_ENTITIES.get(country.upper(), [])
    
    def check_spot(self, spot: Dict[str, Any], current_time: float) -> Optional[Dict[str, Any]]:
        """Check an MQTT spot against hunt list. Returns alert dict if match.
        
        Args:
            spot: Dict with 'sender', 'receiver', 'freq', 'snr', 'grid'
            current_time: Current timestamp for cooldown checking
        
        Returns:
            Alert dict or None
        """
        sender = spot.get('sender', '')
        receiver_grid = spot.get('grid', '')
        
        if not self.is_hunted(sender):
            return None
        
        # Check cooldown
        last_alert = self._recent_alerts.get(sender, 0)
        if current_time - last_alert < self._alert_cooldown:
            return None
        
        # Determine alert type
        alert_type = 'active'
        details = f"Active on {self._freq_to_band(spot.get('freq', 0))}"
        
        # Check if working nearby (receiver is in similar grid to user)
        if self._my_grid and receiver_grid:
            if receiver_grid[:2] == self._my_grid[:2]:  # Same field
                alert_type = 'working_nearby'
                details = f"Working {receiver_grid[:4]} stations!"
        
        # Update cooldown
        self._recent_alerts[sender] = current_time
        
        # Clean old entries from cooldown cache
        self._clean_cooldown_cache(current_time)
        
        alert = {
            'call': sender,
            'band': self._freq_to_band(spot.get('freq', 0)),
            'alert_type': alert_type,
            'details': details,
            'snr': spot.get('snr', -99),
            'receiver_grid': receiver_grid
        }
        
        logger.info(f"Hunt Mode: Alert - {sender} {alert_type}: {details}")
        
        # Emit signal
        self.hunt_alert.emit(sender, alert['band'], alert_type, details)
        
        return alert
    
    def _clean_cooldown_cache(self, current_time: float):
        """Remove old entries from cooldown cache."""
        cutoff = current_time - (self._alert_cooldown * 2)
        self._recent_alerts = {
            k: v for k, v in self._recent_alerts.items() 
            if v > cutoff
        }
    
    def _freq_to_band(self, freq: int) -> str:
        """Convert frequency in Hz to band string."""
        f = freq / 1_000_000
        if 1.8 <= f <= 2.0: return "160m"
        if 3.5 <= f <= 4.0: return "80m"
        if 5.3 <= f <= 5.4: return "60m"
        if 7.0 <= f <= 7.3: return "40m"
        if 10.1 <= f <= 10.15: return "30m"
        if 14.0 <= f <= 14.35: return "20m"
        if 18.068 <= f <= 18.168: return "17m"
        if 21.0 <= f <= 21.45: return "15m"
        if 24.89 <= f <= 24.99: return "12m"
        if 28.0 <= f <= 29.7: return "10m"
        if 50.0 <= f <= 54.0: return "6m"
        return "?"
