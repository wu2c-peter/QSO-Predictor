# QSO Predictor
# Copyright (C) 2025 Peter Hirst (WU2C)

import logging
import threading
import time
from typing import List, Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

class QSOAnalyzer(QObject):
    cache_updated = pyqtSignal()
    status_message = pyqtSignal(str)
    spot_received = pyqtSignal(dict)  # v2.1.0: Passthrough for hunt mode

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.my_call = config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
        self.my_grid = config.get('ANALYSIS', 'my_grid', fallback='')
        
        # --- THREAD SAFETY LOCK ---
        self.lock = threading.Lock() 
        
        # Diagnostic: track spot processing health
        self._spot_error_logged = False
        self._spots_processed = 0
        
        self.mqtt = MQTTClient()
        self.mqtt.spot_received.connect(self.handle_live_spot)
        self.mqtt.status_message.connect(self.relay_status)
        
        logger.info(f"Analyzer initialized: my_call={self.my_call}, my_grid={self.my_grid}")
        
        self.current_dial_freq = 0
        self.current_target_grid = ""  # v2.2.0: Set by main when target changes
        self.band_cache = {}      
        self.my_reception_cache = [] 
        
        # --- NEW: Target Perspective Caches ---
        # Keyed by receiver callsign -> list of spots (spots reported by each receiver)
        self.receiver_cache = {}
        # Keyed by grid[:4] (subsquare) -> list of spots (spots reported from that grid)
        self.grid_cache = {}
        # v2.1.0: Keyed by sender callsign -> list of spots (who reports that station)
        # Used for Phase 2 Path Intelligence reverse lookups
        self.sender_cache = {}
        
        # --- Local Decode Path Evidence (v2.1.3) ---
        # When we decode "WU2C DH2YBG JO43", FT8 format is TO FROM payload.
        # DH2YBG transmitted this addressed to WU2C → proof DH2YBG decoded WU2C.
        # This provides path evidence WITHOUT PSK Reporter.
        self.decode_evidence = {}   # {call: {'responded_to': set(), 'last_seen': float}}
        self.call_grid_map = {}     # {call: grid} from decoded stations
        self.responded_to_me = {}   # {call: last_seen} stations that addressed my_call
        
        self.running = True
        self.mqtt.start()
        
        # Subscribe to 20m default to catch startup traffic
        self.mqtt.update_subscriptions(self.my_call, 14074000)
        
        self.worker_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self.worker_thread.start()

    def set_dial_freq(self, freq):
        if self.current_dial_freq != freq:
            # LOCK: Modifying cache
            with self.lock:
                self.current_dial_freq = freq
                self.band_cache.clear()
                self.my_reception_cache.clear()
                self.receiver_cache.clear()
                self.grid_cache.clear()
                self.sender_cache.clear()  # v2.1.0: Phase 2 reverse lookup cache
                self.decode_evidence.clear()   # v2.1.3: Local decode path evidence
                self.call_grid_map.clear()
                self.responded_to_me.clear()
            
            self.mqtt.update_subscriptions(self.my_call, freq)
            self.cache_updated.emit()

    def force_refresh(self):
        # Read freq safely
        f = self.current_dial_freq if self.current_dial_freq > 0 else 14074000
        self.mqtt.update_subscriptions(self.my_call, f)

    def relay_status(self, msg):
        pass 

    def handle_live_spot(self, spot):
        try:
            # SANITIZE
            if spot.get('snr') is None: spot['snr'] = -99
            else: spot['snr'] = int(spot['snr'])

            spot_freq = int(spot['freq'])
            receiver_call = spot.get('receiver', '').upper()
            receiver_grid = spot.get('grid', '').upper()
            
            # LOCK: Writing to cache
            with self.lock:
                if self.current_dial_freq == 0:
                    self.current_dial_freq = int(spot_freq / 1000) * 1000 
                
                if spot['sender'] == self.my_call:
                    self.my_reception_cache.append(spot)
                
                # Original band_cache (keyed by frequency)
                if abs(spot_freq - self.current_dial_freq) < 5000:
                    if spot_freq not in self.band_cache:
                        self.band_cache[spot_freq] = []
                    self.band_cache[spot_freq].append(spot)
                    
                    # --- NEW: Populate receiver_cache ---
                    if receiver_call:
                        if receiver_call not in self.receiver_cache:
                            self.receiver_cache[receiver_call] = []
                        self.receiver_cache[receiver_call].append(spot)
                    
                    # --- NEW: Populate grid_cache ---
                    if len(receiver_grid) >= 4:
                        grid_key = receiver_grid[:4]
                        if grid_key not in self.grid_cache:
                            self.grid_cache[grid_key] = []
                        self.grid_cache[grid_key].append(spot)
                    
                    # v2.1.0: Populate sender_cache for Phase 2 reverse lookups
                    sender_call = spot.get('sender', '').upper()
                    if sender_call:
                        if sender_call not in self.sender_cache:
                            self.sender_cache[sender_call] = []
                        self.sender_cache[sender_call].append(spot)
            
            # v2.1.0: Emit for hunt mode checking (outside lock)
            self.spot_received.emit(spot)
            
            self._spots_processed += 1
                        
        except Exception as e:
            if not self._spot_error_logged:
                logger.error(f"handle_live_spot FAILED: {e}", exc_info=True)
                logger.error(f"Failing spot data: {spot}")
                self._spot_error_logged = True

    def get_target_perspective(self, target_call, target_grid):
        """
        Returns spots representing what the target station (and nearby stations) hear.
        
        Returns dict with tiered results:
        {
            'tier1': [...],  # Direct: spots reported BY the target station
            'tier2': [...],  # Same grid square (4-char match)
            'tier3': [...],  # Same field (2-char match)
            'global': [...]  # Everything else (background)
        }
        
        Each spot includes 'tier' field for rendering priority.
        """
        target_call = (target_call or '').upper().strip()
        target_grid = (target_grid or '').upper().strip()
        
        recent_limit = time.time() - 60  # 60 seconds for target perspective
        
        tier1 = []  # Direct from target
        tier2 = []  # Same 4-char grid
        tier3 = []  # Same 2-char field
        global_spots = []  # Everything else
        
        # Track what we've already categorized to avoid duplicates
        seen_spots = set()  # (sender, freq) tuples
        
        with self.lock:
            dial = self.current_dial_freq
            if dial <= 0:
                return {'tier1': [], 'tier2': [], 'tier3': [], 'global': []}
            
            # --- TIER 1: Direct reports from target ---
            if target_call and target_call in self.receiver_cache:
                for spot in self.receiver_cache[target_call]:
                    if spot['time'] > recent_limit:
                        spot_key = (spot['sender'], spot['freq'])
                        if spot_key not in seen_spots:
                            spot_copy = spot.copy()
                            spot_copy['tier'] = 1
                            tier1.append(spot_copy)
                            seen_spots.add(spot_key)
            
            # --- TIER 2: Same 4-char grid square ---
            if len(target_grid) >= 4:
                grid4 = target_grid[:4]
                if grid4 in self.grid_cache:
                    for spot in self.grid_cache[grid4]:
                        if spot['time'] > recent_limit:
                            spot_key = (spot['sender'], spot['freq'])
                            if spot_key not in seen_spots:
                                # Exclude if receiver IS the target (already in tier1)
                                if spot.get('receiver', '').upper() != target_call:
                                    spot_copy = spot.copy()
                                    spot_copy['tier'] = 2
                                    tier2.append(spot_copy)
                                    seen_spots.add(spot_key)
            
            # --- TIER 3: Same 2-char field ---
            if len(target_grid) >= 2:
                field = target_grid[:2]
                for grid_key, spots in self.grid_cache.items():
                    if grid_key[:2] == field and grid_key != target_grid[:4]:
                        for spot in spots:
                            if spot['time'] > recent_limit:
                                spot_key = (spot['sender'], spot['freq'])
                                if spot_key not in seen_spots:
                                    spot_copy = spot.copy()
                                    spot_copy['tier'] = 3
                                    tier3.append(spot_copy)
                                    seen_spots.add(spot_key)
            
            # --- GLOBAL: Everything else in the passband ---
            for freq, spots in self.band_cache.items():
                if dial <= freq <= dial + 3000:
                    for spot in spots:
                        if spot['time'] > recent_limit:
                            spot_key = (spot['sender'], spot['freq'])
                            if spot_key not in seen_spots:
                                spot_copy = spot.copy()
                                spot_copy['tier'] = 4
                                global_spots.append(spot_copy)
                                seen_spots.add(spot_key)
        
        result = {
            'tier1': tier1,
            'tier2': tier2,
            'tier3': tier3,
            'global': global_spots
        }
        
        # Diagnostic: log perspective results when a target is selected
        total = len(tier1) + len(tier2) + len(tier3) + len(global_spots)
        if total == 0:
            logger.debug(
                f"get_target_perspective({target_call}, grid='{target_grid}'): "
                f"EMPTY - dial={self.current_dial_freq}, "
                f"receiver_cache has {len(self.receiver_cache)} calls, "
                f"target_in_cache={target_call in self.receiver_cache}"
            )
        
        return result

    def find_near_me_stations(self, target_call: str, target_grid: str, my_grid: str, my_call: str = '') -> dict:
        """
        Find stations near MY location that are being heard by the target region.
        
        Phase 1 of Path Intelligence: Answer "Is anyone from my area getting through?"
        
        Uses MQTT data we already have (Tier 1/2/3 spots) - no API calls needed.
        
        Args:
            target_call: Target station callsign
            target_grid: Target station grid (4-6 chars)
            my_grid: My grid locator (4-6 chars)
            my_call: My callsign (to exclude from list - already shown in Path column)
        
        Returns:
            {
                'stations': [
                    {
                        'call': 'W2XYZ',
                        'grid': 'FN31ab',
                        'snr': -12,
                        'freq': 1847,  # Audio offset Hz
                        'distance': 'grid',  # 'grid' (same 4-char) or 'field' (same 2-char)
                        'heard_by': 'target' | 'proxy',  # Direct target or nearby proxy
                        'heard_by_call': 'EA8ABC'
                    },
                    ...
                ],
                'target_uploading': bool,  # Is target directly reporting to PSK Reporter?
                'proxy_count': int,  # Number of proxy stations used (if target not uploading)
                'my_grid': str  # Echo back for UI
            }
        """
        target_call = (target_call or '').upper().strip()
        target_grid = (target_grid or '').upper().strip()
        my_grid = (my_grid or '').upper().strip()
        my_call = (my_call or '').upper().strip()
        
        if not my_grid or len(my_grid) < 2:
            return {'stations': [], 'target_uploading': False, 'proxy_count': 0, 'my_grid': ''}
        
        my_field = my_grid[:2]
        my_grid4 = my_grid[:4] if len(my_grid) >= 4 else None
        
        recent_limit = time.time() - 60  # 60 seconds
        
        near_me_stations = []
        seen_calls = set()  # Avoid duplicates
        target_uploading = False
        proxy_reporters = set()
        
        with self.lock:
            dial = self.current_dial_freq  # For converting RF to audio offset
            
            # First check if target is directly uploading (has Tier 1 spots)
            if target_call and target_call in self.receiver_cache:
                target_spots = [s for s in self.receiver_cache[target_call] 
                               if s['time'] > recent_limit]
                if target_spots:
                    target_uploading = True
                    
                    # Check each spot - is the SENDER near me?
                    for spot in target_spots:
                        sender_call = spot.get('sender', '')
                        sender_grid = spot.get('sender_grid', '')
                        
                        if not sender_grid or len(sender_grid) < 2:
                            continue
                        
                        # Skip my own callsign (already shown in Path column as "Heard by Target")
                        if my_call and sender_call == my_call:
                            continue
                        
                        if sender_call in seen_calls:
                            continue
                        
                        # Check if sender is near my grid
                        distance = None
                        if my_grid4 and len(sender_grid) >= 4 and sender_grid[:4] == my_grid4:
                            distance = 'grid'  # Same 4-char grid (~100km)
                        elif sender_grid[:2] == my_field:
                            distance = 'field'  # Same 2-char field (~1000km)
                        
                        if distance:
                            # Convert RF frequency to audio offset
                            rf_freq = spot.get('freq', 0)
                            audio_freq = rf_freq - dial if dial > 0 else rf_freq
                            
                            near_me_stations.append({
                                'call': sender_call,
                                'grid': sender_grid,
                                'snr': spot.get('snr', -99),
                                'freq': audio_freq,
                                'distance': distance,
                                'heard_by': 'target',
                                'heard_by_call': target_call
                            })
                            seen_calls.add(sender_call)
            
            # If target not uploading (or has few spots), check proxy stations in their grid/field
            if not target_uploading or len(near_me_stations) < 2:
                # Get all spots from target's grid area (Tier 2/3)
                if len(target_grid) >= 4:
                    target_grid4 = target_grid[:4]
                    if target_grid4 in self.grid_cache:
                        for spot in self.grid_cache[target_grid4]:
                            if spot['time'] > recent_limit:
                                sender_call = spot.get('sender', '')
                                sender_grid = spot.get('sender_grid', '')
                                receiver_call = spot.get('receiver', '')
                                
                                if not sender_grid or len(sender_grid) < 2:
                                    continue
                                
                                # Skip my own callsign
                                if my_call and sender_call == my_call:
                                    continue
                                
                                if sender_call in seen_calls:
                                    continue
                                
                                # Check if sender is near my grid
                                distance = None
                                if my_grid4 and len(sender_grid) >= 4 and sender_grid[:4] == my_grid4:
                                    distance = 'grid'
                                elif sender_grid[:2] == my_field:
                                    distance = 'field'
                                
                                if distance:
                                    # Convert RF frequency to audio offset
                                    rf_freq = spot.get('freq', 0)
                                    audio_freq = rf_freq - dial if dial > 0 else rf_freq
                                    
                                    near_me_stations.append({
                                        'call': sender_call,
                                        'grid': sender_grid,
                                        'snr': spot.get('snr', -99),
                                        'freq': audio_freq,
                                        'distance': distance,
                                        'heard_by': 'proxy',
                                        'heard_by_call': receiver_call
                                    })
                                    seen_calls.add(sender_call)
                                    proxy_reporters.add(receiver_call)
                
                # Also check same field (Tier 3) if still need more data
                if len(target_grid) >= 2 and len(near_me_stations) < 3:
                    target_field = target_grid[:2]
                    for grid_key, spots in self.grid_cache.items():
                        if grid_key[:2] == target_field:
                            for spot in spots:
                                if spot['time'] > recent_limit:
                                    sender_call = spot.get('sender', '')
                                    sender_grid = spot.get('sender_grid', '')
                                    receiver_call = spot.get('receiver', '')
                                    
                                    if not sender_grid or len(sender_grid) < 2:
                                        continue
                                    
                                    # Skip my own callsign
                                    if my_call and sender_call == my_call:
                                        continue
                                    
                                    if sender_call in seen_calls:
                                        continue
                                    
                                    # Check if sender is near my grid
                                    distance = None
                                    if my_grid4 and len(sender_grid) >= 4 and sender_grid[:4] == my_grid4:
                                        distance = 'grid'
                                    elif sender_grid[:2] == my_field:
                                        distance = 'field'
                                    
                                    if distance:
                                        # Convert RF frequency to audio offset
                                        rf_freq = spot.get('freq', 0)
                                        audio_freq = rf_freq - dial if dial > 0 else rf_freq
                                        
                                        near_me_stations.append({
                                            'call': sender_call,
                                            'grid': sender_grid,
                                            'snr': spot.get('snr', -99),
                                            'freq': audio_freq,
                                            'distance': distance,
                                            'heard_by': 'proxy',
                                            'heard_by_call': receiver_call
                                        })
                                        seen_calls.add(sender_call)
                                        proxy_reporters.add(receiver_call)
        
        # Sort by distance (grid first) then by SNR (strongest first)
        near_me_stations.sort(key=lambda x: (0 if x['distance'] == 'grid' else 1, -x['snr']))
        
        return {
            'stations': near_me_stations,
            'target_uploading': target_uploading,
            'proxy_count': len(proxy_reporters),
            'my_grid': my_grid
        }

    def analyze_near_me_station(self, station: dict, all_near_me: List[dict], target_grid: str) -> dict:
        """
        Phase 2 Path Intelligence: Analyze WHY a near-me station is getting through.
        
        Uses MQTT data we already have (sender_cache) instead of HTTP API.
        
        BEAMING DETECTION uses differential analysis:
        - Compare this station's directional pattern to peer stations
        - If they're MORE concentrated in one direction than peers → beaming
        - This controls for propagation paths and reporter density
        
        Args:
            station: Single station dict from find_near_me_stations()
            all_near_me: All near-me stations (for peer comparison)
            target_grid: Target station's grid (for bearing calculation)
            
        Returns:
            dict with analysis results and insights
        """
        from psk_reporter_api import calculate_bearing, classify_beam_pattern
        
        call = station.get('call', '').upper()
        grid = station.get('grid', '')
        snr = station.get('snr', -99)
        freq = station.get('freq', 0)
        
        result = {
            'call': call,
            'grid': grid,
            'snr': snr,
            'freq': freq,
            'is_beaming': False,
            'beam_direction': '',
            'beam_confidence': 0,
            'snr_vs_peers': 0,
            'has_power_advantage': False,
            'freq_density': 0,
            'freq_clear': False,
            'insights': [],
            'analysis_done': False,
            'error': None
        }
        
        try:
            recent_limit = time.time() - 300  # Last 5 minutes
            
            # 1. Get spots for THIS station
            with self.lock:
                my_spots = []
                if call in self.sender_cache:
                    my_spots = [s for s in self.sender_cache[call] if s.get('time', 0) > recent_limit]
            
            logger.info(f"Phase 2: {call} has {len(my_spots)} recent spots in cache")
            
            # 2. Get spots for ALL peer stations (for baseline comparison)
            peer_spots_by_call = {}
            with self.lock:
                for peer in all_near_me:
                    peer_call = peer.get('call', '').upper()
                    if peer_call and peer_call != call and peer_call in self.sender_cache:
                        peer_spots = [s for s in self.sender_cache[peer_call] if s.get('time', 0) > recent_limit]
                        if len(peer_spots) >= 3:
                            peer_spots_by_call[peer_call] = peer_spots
            
            logger.info(f"Phase 2: Found {len(peer_spots_by_call)} peer station(s) with 3+ spots for comparison")
            
            if len(my_spots) < 3:
                result['insights'].append(f"ℹ️ Only {len(my_spots)} recent spot(s) — need 3+ for beaming analysis")
            else:
                # 3. Calculate THIS station's sector distribution
                my_sectors = self._calculate_sector_distribution(my_spots, grid)
                my_concentration = self._get_max_concentration(my_sectors)
                
                # Log this station's pattern
                sector_names = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
                my_sector_str = ', '.join([f"{sector_names[i]}:{my_sectors[i]}" for i in range(8) if my_sectors[i] > 0])
                logger.info(f"Phase 2 {call} sectors: {my_sector_str} (max 3-sector concentration: {my_concentration}%)")
                
                # 4. Calculate PEER baseline (what's the "normal" pattern from this area?)
                if peer_spots_by_call:
                    peer_concentrations = []
                    for peer_call, peer_spots in peer_spots_by_call.items():
                        peer_grid = next((p.get('grid', '') for p in all_near_me if p.get('call', '').upper() == peer_call), '')
                        if peer_grid:
                            peer_sectors = self._calculate_sector_distribution(peer_spots, peer_grid)
                            peer_conc = self._get_max_concentration(peer_sectors)
                            peer_concentrations.append(peer_conc)
                            
                            peer_sector_str = ', '.join([f"{sector_names[i]}:{peer_sectors[i]}" for i in range(8) if peer_sectors[i] > 0])
                            logger.info(f"Phase 2 {peer_call} sectors: {peer_sector_str} (concentration: {peer_conc}%)")
                    
                    if peer_concentrations:
                        avg_peer_concentration = sum(peer_concentrations) / len(peer_concentrations)
                        concentration_diff = my_concentration - avg_peer_concentration
                        
                        logger.info(f"Phase 2 DIFFERENTIAL: {call}={my_concentration}% vs peers avg={avg_peer_concentration:.0f}% → diff={concentration_diff:+.0f}% (n={len(peer_concentrations)} peers)")
                        
                        peer_count = len(peer_concentrations)
                        confidence_note = ""
                        if peer_count == 1:
                            confidence_note = " (low confidence: only 1 peer)"
                        elif peer_count >= 4:
                            confidence_note = f" (good confidence: {peer_count} peers)"
                        
                        # If this station is 20%+ MORE concentrated than peers → likely beaming
                        # Lower threshold with more peers (more significant)
                        beam_threshold = 20 if peer_count <= 2 else 15
                        
                        if concentration_diff >= beam_threshold and my_concentration >= 70:
                            result['is_beaming'] = True
                            # Find dominant direction
                            max_sector = my_sectors.index(max(my_sectors))
                            result['beam_direction'] = self._bearing_to_region_simple(max_sector * 45 + 22.5)
                            result['beam_confidence'] = my_concentration
                            result['insights'].append(
                                f"📡 Likely beaming — {my_concentration}% concentrated vs {avg_peer_concentration:.0f}% peer avg{confidence_note}"
                            )
                        elif concentration_diff <= -15:
                            # This station is LESS concentrated than peers — omnidirectional
                            result['insights'].append(
                                f"📻 More omnidirectional than peers ({my_concentration}% vs {avg_peer_concentration:.0f}%){confidence_note}"
                            )
                        elif my_concentration >= 85 and avg_peer_concentration >= 85:
                            # BOTH are highly concentrated in same direction — ambiguous!
                            max_sector = my_sectors.index(max(my_sectors))
                            direction = self._bearing_to_region_simple(max_sector * 45 + 22.5)
                            if peer_count >= 3:
                                # With 3+ peers all showing same pattern, more likely propagation
                                result['insights'].append(
                                    f"📡 All {peer_count + 1} stations ~{my_concentration}% toward {direction} — likely propagation"
                                )
                            else:
                                result['insights'].append(
                                    f"🤷 Both stations ~{my_concentration}% toward {direction} — could be propagation OR both beaming"
                                )
                        else:
                            result['insights'].append(
                                f"Similar pattern to nearby stations ({my_concentration}% vs {avg_peer_concentration:.0f}%){confidence_note}"
                            )
                    else:
                        # No valid peer data, fall back to absolute threshold
                        if my_concentration >= 80:
                            result['insights'].append(f"⚠️ {my_concentration}% concentrated (no peers to compare)")
                        else:
                            result['insights'].append(f"Pattern looks normal ({my_concentration}% concentration)")
                else:
                    # No peers to compare - just report the raw numbers
                    if my_concentration >= 80:
                        result['insights'].append(f"⚠️ {my_concentration}% concentrated in one direction (no peers to compare)")
                    else:
                        result['insights'].append(f"Spread across directions ({my_concentration}% max concentration)")
            
            # 5. SNR comparison to peers (unchanged)
            if len(all_near_me) >= 2:
                peer_snrs = [s.get('snr', -99) for s in all_near_me if s.get('call', '').upper() != call]
                if peer_snrs:
                    peer_avg = sum(peer_snrs) / len(peer_snrs)
                    snr_diff = snr - peer_avg
                    result['snr_vs_peers'] = int(snr_diff)
                    
                    if snr_diff >= 6:
                        result['has_power_advantage'] = True
                        result['insights'].append(f"⚡ +{int(snr_diff)}dB above others nearby — likely power/antenna advantage")
            
            # 6. Frequency density check
            freq_density = self._get_freq_density(freq)
            result['freq_density'] = freq_density
            result['freq_clear'] = freq_density <= 3
            
            # 7. Final actionable insight
            if not result['is_beaming'] and not result['has_power_advantage'] and len(my_spots) >= 3:
                if result['freq_clear']:
                    result['insights'].append(f"💡 Their freq has light traffic — try {freq} Hz?")
            
            result['analysis_done'] = True
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Phase 2 analysis error: {e}", exc_info=True)
        
        return result
    
    def _calculate_sector_distribution(self, spots: list, from_grid: str) -> List[int]:
        """Calculate how spots are distributed across 8 compass sectors."""
        from psk_reporter_api import calculate_bearing
        
        sectors = [0] * 8  # N, NE, E, SE, S, SW, W, NW
        
        for spot in spots:
            receiver_grid = spot.get('grid', '')
            if receiver_grid and len(receiver_grid) >= 4 and from_grid and len(from_grid) >= 4:
                bearing = calculate_bearing(from_grid, receiver_grid)
                if bearing is not None:
                    sector = int(bearing / 45) % 8
                    sectors[sector] += 1
        
        return sectors
    
    def _get_max_concentration(self, sectors: List[int]) -> int:
        """Get the max concentration in any 3 adjacent sectors (135° arc)."""
        total = sum(sectors)
        if total == 0:
            return 0
        
        max_conc = 0
        for i in range(8):
            # 3 adjacent sectors
            left = (i - 1) % 8
            right = (i + 1) % 8
            concentrated = sectors[left] + sectors[i] + sectors[right]
            conc_pct = int(100 * concentrated / total)
            if conc_pct > max_conc:
                max_conc = conc_pct
        
        return max_conc
    
    def _bearing_to_region_simple(self, bearing: float) -> str:
        """Simple bearing to region conversion."""
        bearing = bearing % 360
        if 20 <= bearing < 70:
            return "EU"
        elif 70 <= bearing < 120:
            return "AF/ME"
        elif 120 <= bearing < 180:
            return "AS"
        elif 180 <= bearing < 240:
            return "OC"
        elif 240 <= bearing < 300:
            return "SA"
        elif 300 <= bearing < 340:
            return "CA"
        else:
            return "NA"
    
    def _get_freq_density(self, audio_freq: int) -> int:
        """Get signal density at a frequency from cached data."""
        with self.lock:
            if self.current_dial_freq > 0:
                rf_freq = self.current_dial_freq + audio_freq
            else:
                rf_freq = audio_freq
            
            count = 0
            recent_limit = time.time() - 45
            
            for cached_freq, reports in self.band_cache.items():
                if abs(cached_freq - rf_freq) < 60:  # 60Hz window
                    for r in reports:
                        if r.get('time', 0) > recent_limit:
                            count += 1
            
            return count

    def get_qrm_for_freq(self, target_freq_in):
        """Returns RECENT spots overlapping the target."""
        target_rf = int(target_freq_in)
        
        # LOCK: Reading cache
        with self.lock:
            if target_rf < 10000 and self.current_dial_freq > 0:
                target_rf += self.current_dial_freq
                
            overlapping_spots = []
            seen_senders = set()
            
            # TIME FILTER: Only count signals heard in the last 45 seconds
            recent_limit = time.time() - 45
            
            for cached_freq, reports in self.band_cache.items():
                # 60Hz Match Window
                if abs(cached_freq - target_rf) < 60:
                    for r in reports:
                        if r['time'] > recent_limit:
                            if r['sender'] not in seen_senders:
                                overlapping_spots.append(r)
                                seen_senders.add(r['sender'])
        
        return overlapping_spots

    def get_band_spots(self):
        """Returns ALL spots currently in the 3kHz passband."""
        spots = []
        # LOCK: Reading cache
        with self.lock:
            if self.current_dial_freq > 0:
                # We only want spots that fall into the audio window (Dial to Dial+3000)
                recent_limit = time.time() - 45
                
                for f, reports in self.band_cache.items():
                    # Check if freq is in our 3kHz window
                    if self.current_dial_freq <= f <= self.current_dial_freq + 3000:
                        for r in reports:
                            if r['time'] > recent_limit:
                                spots.append(r)
        return spots

    # =========================================================================
    # Local Decode Path Evidence (v2.1.3)
    # =========================================================================
    # FT8 messages decoded by our radio contain path evidence:
    #   "WU2C DH2YBG JO43" → DH2YBG (FROM) transmitted to WU2C (TO)
    #   Proves DH2YBG decoded WU2C — no PSK Reporter needed.
    # =========================================================================
    
    @staticmethod
    def _is_callsign(s):
        """Check if string looks like an amateur radio callsign."""
        if not s or len(s) < 3 or len(s) > 10:
            return False
        s = s.strip('<>')
        return any(c.isdigit() for c in s) and all(c.isalnum() or c == '/' for c in s)

    def _record_decode_evidence(self, decode_data):
        """
        Extract QSO evidence from an FT8 decoded message.
        
        FT8 QSO messages have format: TO FROM payload
        When FROM responds to TO, it proves FROM decoded TO.
        
        Also maintains call_grid_map for grid lookups.
        """
        message = decode_data.get('message', '')
        if not message:
            return
        
        # Update call → grid mapping from this decode
        call = decode_data.get('call', '').upper()
        grid = decode_data.get('grid', '').upper()
        if call and grid and len(grid) >= 4:
            self.call_grid_map[call] = grid
        
        # Parse message for QSO evidence
        parts = message.strip().split()
        if len(parts) < 2:
            return
        
        # Skip CQ messages — they don't prove anyone was heard
        if parts[0].upper() == 'CQ':
            return
        
        to_call = parts[0].strip('<>').upper()
        from_call = parts[1].strip('<>').upper()
        
        if not self._is_callsign(to_call) or not self._is_callsign(from_call):
            return
        
        # Record: FROM responded to TO (FROM decoded TO)
        now = time.time()
        with self.lock:
            if from_call not in self.decode_evidence:
                self.decode_evidence[from_call] = {'responded_to': set(), 'last_seen': now}
            is_new = to_call not in self.decode_evidence[from_call]['responded_to']
            self.decode_evidence[from_call]['responded_to'].add(to_call)
            self.decode_evidence[from_call]['last_seen'] = now
            
            # Reverse index: if TO is my callsign, FROM heard me
            if to_call == self.my_call.upper():
                was_new = from_call not in self.responded_to_me
                self.responded_to_me[from_call] = now
                if was_new:
                    logger.info(f"Decode evidence: {from_call} responded to ME ({to_call}) — Heard by Target proof")
            elif is_new:
                logger.debug(f"Decode evidence: {from_call} responded to {to_call}")

    def _check_decode_path(self, target_call, target_grid):
        """
        Check local decode evidence for path status to target.
        
        Returns:
            ('Heard by Target', geo_bonus) if target responded to my call
            ('Reported in Region', geo_bonus) if regional evidence found
            (None, 0) if no evidence
        """
        if not target_call:
            return None, 0
        
        target_upper = target_call.upper()
        my_call_upper = self.my_call.upper()
        my_field = self.my_grid[:2].upper() if len(self.my_grid) >= 2 else ''
        target_field = target_grid[:2].upper() if target_grid and len(target_grid) >= 2 else ''
        
        with self.lock:
            # Case 1: Target responded to my call → Heard by Target
            evidence = self.decode_evidence.get(target_upper, {})
            if my_call_upper in evidence.get('responded_to', set()):
                logger.debug(f"Decode path: {target_upper} → Heard by Target (responded to {my_call_upper})")
                return 'Heard by Target', 100
            
            # Case 2: Target responded to someone near me → Reported in Region
            if my_field and evidence.get('responded_to'):
                for heard_call in evidence['responded_to']:
                    heard_grid = self.call_grid_map.get(heard_call, '')
                    if heard_grid and len(heard_grid) >= 2 and heard_grid[:2] == my_field:
                        logger.debug(f"Decode path: {target_upper} → Reported in Region (responded to {heard_call} in {heard_grid})")
                        return 'Reported in Region', 15
            
            # Case 3: Someone near target responded to my call → Reported in Region
            if target_field:
                for responder_call, _ in self.responded_to_me.items():
                    responder_grid = self.call_grid_map.get(responder_call, '')
                    if responder_grid and len(responder_grid) >= 2 and responder_grid[:2] == target_field:
                        logger.debug(f"Decode path: {target_upper} → Reported in Region ({responder_call} in {responder_grid} heard me)")
                        return 'Reported in Region', 15
        
        return None, 0

    def analyze_decode(self, decode_data, update_callback=None, use_perspective=False):
        """
        Analyze a decode and calculate probability, path status, and competition.
        
        Args:
            decode_data: The decode dict to analyze (modified in place)
            update_callback: Optional callback after analysis
            use_perspective: If True, also compute full competition from target's perspective.
                           This is expensive - only use for selected target (dashboard).
        
        Sets:
            'path': Path status for table column (Heard by Target, Reported in Region, etc.)
            'prob': Success probability percentage
            'competition': Full competition analysis (only when use_perspective=True)
        """
        snr = decode_data.get('snr', -20)
        base_prob = 0
        if snr > 0: base_prob = 80
        elif snr > -10: base_prob = 60
        elif snr > -15: base_prob = 40
        elif snr > -20: base_prob = 20
        else: base_prob = 5
        
        # v2.1.3: Record any QSO evidence from this decode's message
        self._record_decode_evidence(decode_data)
        
        target_call = decode_data.get('call', '')
        target_grid = decode_data.get('grid', '')
        target_freq = decode_data.get('freq', 0)
        
        # --- PATH STATUS (cheap, always computed) ---
        # Check if target or nearby stations have heard us
        path_str = ""
        geo_bonus = 0
        direct_hit = False
        
        with self.lock:
            my_reception_snapshot = list(self.my_reception_cache)
            
            # Check if there are any reporters near target
            has_nearby_reporters = False
            if target_grid and len(target_grid) >= 2:
                target_major = target_grid[:2]
                target_minor = target_grid[:4] if len(target_grid) >= 4 else ""
                
                # Check grid_cache for reporters in same grid or field
                for grid_key in self.grid_cache:
                    if target_minor and grid_key == target_minor:
                        has_nearby_reporters = True
                        break
                    elif grid_key[:2] == target_major:
                        has_nearby_reporters = True
                        break
                
                # Also check receiver_cache for the target itself
                if target_call in self.receiver_cache:
                    has_nearby_reporters = True

        # Check for direct connection (target heard us)
        for my_rep in my_reception_snapshot:
            if my_rep['receiver'] == target_call:
                geo_bonus = 100
                direct_hit = True
                path_str = "Heard by Target"
                break
        
        # Check for path open (nearby station heard us)
        if not direct_hit and target_grid and len(target_grid) >= 2:
            target_major = target_grid[:2] 
            target_minor = target_grid[:4] if len(target_grid) >= 4 else ""
            
            for my_rep in my_reception_snapshot:
                r_grid = my_rep.get('grid', "")
                if len(r_grid) >= 4:
                    if target_minor and r_grid[:4] == target_minor:
                        geo_bonus = 25 
                        path_str = "Reported in Region"
                        break
                    elif r_grid[:2] == target_major:
                        geo_bonus = 15
                        path_str = "Reported in Region"
        
        # v2.1.3: Check local decode evidence (works without PSK Reporter)
        if not path_str:
            decode_path, decode_bonus = self._check_decode_path(target_call, target_grid)
            if decode_path:
                path_str = decode_path
                geo_bonus = decode_bonus
                if decode_path == "Heard by Target":
                    direct_hit = True
        
        # If no path found, distinguish between "no reporters" vs "not heard" vs "not TXing"
        if not path_str:
            have_any_spots = len(my_reception_snapshot) > 0
            
            if has_nearby_reporters:
                if have_any_spots:
                    path_str = "Not Reported in Region"  # We're TXing (spotted elsewhere), just not reaching target
                else:
                    path_str = "Not Transmitting"  # No spots anywhere — likely not TXing
            else:
                path_str = "No Reporters in Region"
        
        # SNR-based probability adjustment (when no path data)
        if not direct_hit and geo_bonus == 0:
            if snr > -5: geo_bonus = 10 
            elif snr > -12: geo_bonus = 0  
            else: geo_bonus = -15 
        
        decode_data['path'] = path_str
        
        # --- COMPETITION (expensive, only for selected target) ---
        if use_perspective:
            # Convert target_freq to RF if it's an audio offset
            if target_freq < 10000 and self.current_dial_freq > 0:
                target_rf = target_freq + self.current_dial_freq
            else:
                target_rf = target_freq
            
            perspective = self.get_target_perspective(target_call, target_grid)
            seen_senders = set()
            competition_count = 0
            strong_qrm = False
            
            # Count Tier 1 and Tier 2 at full weight
            for tier_name in ['tier1', 'tier2']:
                for spot in perspective.get(tier_name, []):
                    spot_freq = spot.get('freq', 0)
                    sender = spot.get('sender', '')
                    if abs(spot_freq - target_rf) < 60:
                        if sender and sender not in seen_senders:
                            competition_count += 1
                            seen_senders.add(sender)
                            if spot.get('snr', -99) > 0:
                                strong_qrm = True
            
            # Count Tier 3 at 50% weight
            tier3_count = 0
            for spot in perspective.get('tier3', []):
                spot_freq = spot.get('freq', 0)
                sender = spot.get('sender', '')
                if abs(spot_freq - target_rf) < 60:
                    if sender and sender not in seen_senders:
                        tier3_count += 1
                        seen_senders.add(sender)
            competition_count += tier3_count // 2
            
            total_perspective = (len(perspective.get('tier1', [])) + 
                                len(perspective.get('tier2', [])) + 
                                len(perspective.get('tier3', [])))
            
            # Build competition string
            comp_str = "Clear"
            qrm_penalty = 0

            if competition_count > 0:
                if competition_count <= 1:
                    intensity = "Low"
                    qrm_penalty = 5
                elif competition_count <= 3:
                    intensity = "Medium"
                    qrm_penalty = 15
                elif competition_count <= 6:
                    intensity = "High"
                    qrm_penalty = 30
                else:
                    intensity = "PILEUP"
                    qrm_penalty = 50
                    
                comp_str = f"{intensity} ({competition_count})"
                if strong_qrm:
                    comp_str += " + QRM"
                    qrm_penalty += 20
            
            # No perspective data available
            if total_perspective == 0 and competition_count == 0:
                comp_str = "Unknown"
            
            # Override with path status if connected
            if direct_hit:
                comp_str = "Heard by Target"
            
            decode_data['competition'] = comp_str
            geo_bonus -= qrm_penalty  # Factor competition into probability
        else:
            # For bulk analysis, just use path status as competition placeholder
            decode_data['competition'] = path_str if path_str else ""

        final_prob = max(5, min(99, base_prob + geo_bonus))
        decode_data['prob'] = f"{final_prob}%"
        
        if update_callback:
            update_callback(decode_data)

    def update_path_only(self, decode_data):
        """
        Lightweight path-only update. Much faster than full analyze_decode.
        Use this for bulk updates when my_reception_cache changes.
        
        Path values:
            Heard by Target - target heard me
            Reported in Region - station in same grid/field reported me
            Not Reported in Region - reporters near target exist, I'm spotted elsewhere, but not there
            Not Transmitting - reporters near target exist, but I have no spots anywhere
            No Reporters in Region - no reporters in target's region
        """
        target_call = decode_data.get('call', '')
        target_grid = decode_data.get('grid', '')
        
        path_str = ""
        
        with self.lock:
            my_reception_snapshot = list(self.my_reception_cache)
            
            # Check if there are any reporters near target
            has_nearby_reporters = False
            if target_grid and len(target_grid) >= 2:
                target_major = target_grid[:2]
                target_minor = target_grid[:4] if len(target_grid) >= 4 else ""
                
                # Check grid_cache for reporters in same grid or field
                for grid_key in self.grid_cache:
                    if target_minor and grid_key == target_minor:
                        has_nearby_reporters = True
                        break
                    elif grid_key[:2] == target_major:
                        has_nearby_reporters = True
                        break
                
                # Also check receiver_cache for the target itself
                if target_call in self.receiver_cache:
                    has_nearby_reporters = True

        # Check for direct connection (target heard us)
        for my_rep in my_reception_snapshot:
            if my_rep['receiver'] == target_call:
                path_str = "Heard by Target"
                break
        
        # Check for path open (nearby station heard us)
        if not path_str and target_grid and len(target_grid) >= 2:
            target_major = target_grid[:2] 
            target_minor = target_grid[:4] if len(target_grid) >= 4 else ""
            
            for my_rep in my_reception_snapshot:
                r_grid = my_rep.get('grid', "")
                if len(r_grid) >= 4:
                    if target_minor and r_grid[:4] == target_minor:
                        path_str = "Reported in Region"
                        break
                    elif r_grid[:2] == target_major:
                        path_str = "Reported in Region"
        
        # v2.1.3: Check local decode evidence (works without PSK Reporter)
        if not path_str:
            decode_path, _ = self._check_decode_path(target_call, target_grid)
            if decode_path:
                path_str = decode_path
        
        # If no path found, distinguish between "no reporters" vs "not heard" vs "not TXing"
        if not path_str:
            have_any_spots = len(my_reception_snapshot) > 0
            
            if has_nearby_reporters:
                if have_any_spots:
                    path_str = "Not Reported in Region"  # We're TXing (spotted elsewhere), just not reaching target
                else:
                    path_str = "Not Transmitting"  # No spots anywhere — likely not TXing
            else:
                path_str = "No Reporters in Region"
        
        decode_data['path'] = path_str

    def stop(self):
        self.running = False
        self.mqtt.stop()

    def _maintenance_loop(self):
        """
        Background thread that cleans up expired spots from caches.
        FIX v2.0.4: Wrapped in try/except to prevent thread death from bad data.
        """
        while self.running:
            time.sleep(2) 
            
            try:
                now = time.time()
                cutoff = now - (15 * 60)  # Keep 15 mins for BAND MAP history
                cutoff_recent = now - (3 * 60)  # Keep 3 mins for "who reports me" (tactical relevance)
                
                # LOCK: Modifying cache
                with self.lock:
                    # --- Original band_cache cleanup ---
                    keys_to_remove = []
                    unique_senders = set()  # FIX v2.0.4: Count unique callsigns, not total spots
                    for f in self.band_cache:
                        # FIX v2.0.4: Safe comparison - skip spots with invalid time
                        self.band_cache[f] = [
                            r for r in self.band_cache[f] 
                            if isinstance(r.get('time'), (int, float)) and r['time'] > cutoff
                        ]
                        if not self.band_cache[f]:
                            keys_to_remove.append(f)
                        else:
                            # Count unique senders (more meaningful than total reports)
                            for r in self.band_cache[f]:
                                unique_senders.add(r.get('sender', ''))
                    
                    for k in keys_to_remove:
                        del self.band_cache[k]
                    
                    # Use shorter window for "who reports me" - recent propagation matters
                    # FIX v2.0.4: Safe comparison
                    self.my_reception_cache = [
                        r for r in self.my_reception_cache 
                        if isinstance(r.get('time'), (int, float)) and r['time'] > cutoff_recent
                    ]
                    reporting_me_count = len(self.my_reception_cache)
                    
                    # v2.2.0: Count how many reporters are near current target
                    near_target_count = 0
                    if self.current_target_grid and len(self.current_target_grid) >= 2:
                        target_field = self.current_target_grid[:2]
                        for rep in self.my_reception_cache:
                            rep_grid = rep.get('grid', '')
                            if rep_grid and len(rep_grid) >= 2 and rep_grid[:2] == target_field:
                                near_target_count += 1
                    
                    # --- NEW: Cleanup receiver_cache ---
                    receiver_keys_to_remove = []
                    for call in self.receiver_cache:
                        # FIX v2.0.4: Safe comparison
                        self.receiver_cache[call] = [
                            r for r in self.receiver_cache[call] 
                            if isinstance(r.get('time'), (int, float)) and r['time'] > cutoff
                        ]
                        if not self.receiver_cache[call]:
                            receiver_keys_to_remove.append(call)
                    for k in receiver_keys_to_remove:
                        del self.receiver_cache[k]
                    
                    # --- NEW: Cleanup grid_cache ---
                    grid_keys_to_remove = []
                    for grid in self.grid_cache:
                        # FIX v2.0.4: Safe comparison
                        self.grid_cache[grid] = [
                            r for r in self.grid_cache[grid] 
                            if isinstance(r.get('time'), (int, float)) and r['time'] > cutoff
                        ]
                        if not self.grid_cache[grid]:
                            grid_keys_to_remove.append(grid)
                    for k in grid_keys_to_remove:
                        del self.grid_cache[k]
                    
                    # --- v2.1.3: Cleanup decode evidence caches ---
                    evidence_to_remove = []
                    for call, ev in self.decode_evidence.items():
                        if ev.get('last_seen', 0) < cutoff:
                            evidence_to_remove.append(call)
                    for k in evidence_to_remove:
                        del self.decode_evidence[k]
                    
                    resp_to_remove = [c for c, t in self.responded_to_me.items() if t < cutoff]
                    for k in resp_to_remove:
                        del self.responded_to_me[k]
                    
                    # Cap call_grid_map size (grids don't expire but shouldn't grow unbounded)
                    if len(self.call_grid_map) > 5000:
                        self.call_grid_map.clear()
                    
                    # Stats for status
                    receiver_count = len(self.receiver_cache)
                    grid_count = len(self.grid_cache)
                    
                    # Format dial frequency for display
                    dial_display = ""
                    if self.current_dial_freq > 0:
                        freq_mhz = self.current_dial_freq / 1_000_000
                        band = self._freq_to_band(self.current_dial_freq)
                        dial_display = f"{band} ({freq_mhz:.3f} MHz) | "
                
                # v2.2.0: "reporting" not "hear"; add near-target count
                reporting_str = f"{reporting_me_count} reporting {self.my_call}"
                if self.current_target_grid and len(self.current_target_grid) >= 2:
                    reporting_str += f" ({near_target_count} near target)"
                
                self.cache_updated.emit()
                self.status_message.emit(
                    f"{dial_display}Tracking {len(unique_senders)} stations | {reporting_str}"
                )
                
                # Diagnostic: log cache health every ~30 seconds (every 15th cycle)
                if not hasattr(self, '_maint_cycle'):
                    self._maint_cycle = 0
                self._maint_cycle += 1
                if self._maint_cycle % 15 == 1:
                    logger.info(
                        f"Analyzer cache health: spots_processed={self._spots_processed}, "
                        f"band_cache_freqs={len(self.band_cache)}, "
                        f"receiver_cache_calls={len(self.receiver_cache)}, "
                        f"grid_cache_grids={len(self.grid_cache)}, "
                        f"decode_evidence={len(self.decode_evidence)}, "
                        f"responded_to_me={len(self.responded_to_me)}, "
                        f"unique_senders={len(unique_senders)}, "
                        f"dial_freq={self.current_dial_freq}, "
                        f"spot_errors={'YES' if self._spot_error_logged else 'none'}"
                    )
                
            except Exception as e:
                # FIX v2.0.4: Log error but don't die - keep cleaning
                logger.warning(f"Maintenance: Error during cleanup: {e}")
                # Continue running - next iteration may succeed
    
    def _freq_to_band(self, freq):
        """Convert frequency in Hz to band name."""
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
        return "??m"
