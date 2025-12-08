# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal
from mqtt_client import MQTTClient

class QSOAnalyzer(QObject):
    cache_updated = pyqtSignal()
    status_message = pyqtSignal(str) 

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.my_call = config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
        
        # --- THREAD SAFETY LOCK ---
        self.lock = threading.Lock() 
        
        self.mqtt = MQTTClient()
        self.mqtt.spot_received.connect(self.handle_live_spot)
        self.mqtt.status_message.connect(self.relay_status)
        
        self.current_dial_freq = 0
        self.band_cache = {}      
        self.my_reception_cache = [] 
        
        # --- NEW: Target Perspective Caches ---
        # Keyed by receiver callsign -> list of spots (what each station hears)
        self.receiver_cache = {}
        # Keyed by grid[:4] (subsquare) -> list of spots (what stations in that grid hear)
        self.grid_cache = {}
        
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
                        
        except Exception: pass

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
        
        return {
            'tier1': tier1,
            'tier2': tier2,
            'tier3': tier3,
            'global': global_spots
        }

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

    def analyze_decode(self, decode_data, update_callback=None, use_perspective=False):
        """
        Analyze a decode and calculate probability, path status, and competition.
        
        Args:
            decode_data: The decode dict to analyze (modified in place)
            update_callback: Optional callback after analysis
            use_perspective: If True, also compute full competition from target's perspective.
                           This is expensive - only use for selected target (dashboard).
        
        Sets:
            'path': Path status for table column (CONNECTED, Path Open, or blank)
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
                path_str = "CONNECTED"
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
                        path_str = "Path Open"
                        break
                    elif r_grid[:2] == target_major:
                        geo_bonus = 15
                        path_str = "Path Open"
        
        # If no path found, distinguish between "no reporters" vs "not heard" vs "not TXing"
        if not path_str:
            have_any_spots = len(my_reception_snapshot) > 0
            
            if has_nearby_reporters:
                if have_any_spots:
                    path_str = "No Path"  # We're TXing (spotted elsewhere), just not reaching target
                else:
                    path_str = "No Path or No TX"  # Could be not TXing OR no path
            else:
                path_str = "No Nearby Reporters"
        
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
                comp_str = "CONNECTED"
            
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
            CONNECTED - target heard me
            Path Open - station in same grid/field heard me
            No Path - reporters near target exist, I'm spotted elsewhere, but not there
            No Path or No TX - reporters near target exist, but I have no spots anywhere
            No Nearby Reporters - no reporters in target's region
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
                path_str = "CONNECTED"
                break
        
        # Check for path open (nearby station heard us)
        if not path_str and target_grid and len(target_grid) >= 2:
            target_major = target_grid[:2] 
            target_minor = target_grid[:4] if len(target_grid) >= 4 else ""
            
            for my_rep in my_reception_snapshot:
                r_grid = my_rep.get('grid', "")
                if len(r_grid) >= 4:
                    if target_minor and r_grid[:4] == target_minor:
                        path_str = "Path Open"
                        break
                    elif r_grid[:2] == target_major:
                        path_str = "Path Open"
        
        # If no path found, distinguish between "no reporters" vs "not heard" vs "not TXing"
        if not path_str:
            have_any_spots = len(my_reception_snapshot) > 0
            
            if has_nearby_reporters:
                if have_any_spots:
                    path_str = "No Path"  # We're TXing (spotted elsewhere), just not reaching target
                else:
                    path_str = "No Path or No TX"  # Could be not TXing OR no path
            else:
                path_str = "No Nearby Reporters"
        
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
                cutoff_recent = now - (3 * 60)  # Keep 3 mins for "who hears me" (tactical relevance)
                
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
                    
                    # Use shorter window for "who hears me" - recent propagation matters
                    # FIX v2.0.4: Safe comparison
                    self.my_reception_cache = [
                        r for r in self.my_reception_cache 
                        if isinstance(r.get('time'), (int, float)) and r['time'] > cutoff_recent
                    ]
                    hearing_me_count = len(self.my_reception_cache)
                    
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
                    
                    # Stats for status
                    receiver_count = len(self.receiver_cache)
                    grid_count = len(self.grid_cache)
                    
                    # Format dial frequency for display
                    dial_display = ""
                    if self.current_dial_freq > 0:
                        freq_mhz = self.current_dial_freq / 1_000_000
                        band = self._freq_to_band(self.current_dial_freq)
                        dial_display = f"{band} ({freq_mhz:.3f} MHz) | "
                
                self.cache_updated.emit()
                self.status_message.emit(
                    f"{dial_display}Tracking {len(unique_senders)} stations | {hearing_me_count} hear {self.my_call}"
                )
                
            except Exception as e:
                # FIX v2.0.4: Log error but don't die - keep cleaning
                print(f"[Maintenance] Error during cleanup: {e}")
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
