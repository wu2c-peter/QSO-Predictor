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
        
        self.mqtt = MQTTClient()
        self.mqtt.spot_received.connect(self.handle_live_spot)
        self.mqtt.status_message.connect(self.relay_status)
        
        self.current_dial_freq = 0
        self.band_cache = {}      
        self.my_reception_cache = [] 
        
        self.running = True
        self.mqtt.start()
        
        # Subscribe to 20m default to catch startup traffic
        self.mqtt.update_subscriptions(self.my_call, 14074000)
        
        self.worker_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self.worker_thread.start()

    def set_dial_freq(self, freq):
        if self.current_dial_freq != freq:
            self.current_dial_freq = freq
            self.band_cache.clear()
            self.my_reception_cache.clear()
            self.mqtt.update_subscriptions(self.my_call, freq)
            self.cache_updated.emit()

    def force_refresh(self):
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
            if self.current_dial_freq == 0:
                self.current_dial_freq = int(spot_freq / 1000) * 1000 
            
            if spot['sender'] == self.my_call:
                self.my_reception_cache.append(spot)
            
            if abs(spot_freq - self.current_dial_freq) < 5000:
                if spot_freq not in self.band_cache:
                    self.band_cache[spot_freq] = []
                self.band_cache[spot_freq].append(spot)
        except Exception: pass

    def get_qrm_for_freq(self, target_freq_in):
        """Returns RECENT spots overlapping the target."""
        target_rf = int(target_freq_in)
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
                    # CHECK TIMESTAMP
                    if r['time'] > recent_limit:
                        if r['sender'] not in seen_senders:
                            overlapping_spots.append(r)
                            seen_senders.add(r['sender'])
        
        return overlapping_spots

    def analyze_decode(self, decode_data, update_callback=None):
        if 'competition' not in decode_data:
            decode_data['competition'] = "Analyzing..."
            
        snr = decode_data.get('snr', -20)
        base_prob = 0
        if snr > 0: base_prob = 80
        elif snr > -10: base_prob = 60
        elif snr > -15: base_prob = 40
        elif snr > -20: base_prob = 20
        else: base_prob = 5
        
        # --- FIXED COMPETITION LOGIC (Time-Aware) ---
        raw_freq = decode_data.get('freq', 0)
        
        # Only gets spots from last 45s
        qrm_spots = self.get_qrm_for_freq(raw_freq)
        
        count = len(qrm_spots)
        strong_qrm = False
        for r in qrm_spots:
            if r.get('snr', -99) > 0:
                strong_qrm = True
                break
        
        comp_str = "Clear"
        qrm_penalty = 0

        if count > 0:
            if count <= 1:
                intensity = "Low"
                qrm_penalty = 5
            elif count <= 3:
                intensity = "Medium"
                qrm_penalty = 15
            elif count <= 6:
                intensity = "High"
                qrm_penalty = 30
            else:
                intensity = "PILEUP"
                qrm_penalty = 50
                
            comp_str = f"{intensity} ({count})"
            if strong_qrm:
                comp_str += " + QRM"
                qrm_penalty += 20

        geo_bonus = 0
        target_grid = decode_data.get('grid', "")
        
        direct_hit = False
        target_call = decode_data.get('call', '')
        
        for my_rep in self.my_reception_cache:
            if my_rep['receiver'] == target_call:
                 geo_bonus = 100; direct_hit = True; comp_str = "CONNECTED"
                 break
        
        if not direct_hit:
            path_bonus = 0
            if target_grid and len(target_grid) >= 2:
                target_major = target_grid[:2] 
                target_minor = target_grid[:4] 
                
                for my_rep in self.my_reception_cache:
                    r_grid = my_rep.get('grid', "")
                    if len(r_grid) >= 4:
                        if r_grid == target_minor:
                            path_bonus = 25 
                            break
                        elif r_grid[:2] == target_major:
                            path_bonus = 15 
            
            if path_bonus > 0:
                geo_bonus += path_bonus
                if "Path" not in comp_str: comp_str += " (Path Open)"

            if count > 0:
                geo_bonus += 10
                if decode_data.get('snr', -20) > -10: geo_bonus += 10
            else:
                snr = decode_data.get('snr', -20)
                if snr > -5: geo_bonus += 10 
                elif snr > -12: geo_bonus += 0  
                else: geo_bonus -= 15 

        final_prob = max(5, min(99, base_prob - qrm_penalty + geo_bonus))
        
        decode_data['prob'] = f"{final_prob}%"
        decode_data['competition'] = comp_str
        
        if update_callback:
            update_callback(decode_data)

    def stop(self):
        self.running = False
        self.mqtt.stop()

    def _maintenance_loop(self):
        while self.running:
            time.sleep(2) 
            now = time.time()
            cutoff = now - (15 * 60) # Keep 15 mins for BAND MAP history
            
            keys_to_remove = []
            total_signals = 0
            for f in self.band_cache:
                self.band_cache[f] = [r for r in self.band_cache[f] if r['time'] > cutoff]
                if not self.band_cache[f]:
                    keys_to_remove.append(f)
                else:
                    total_signals += len(self.band_cache[f])
            
            for k in keys_to_remove:
                del self.band_cache[k]
                
            self.my_reception_cache = [r for r in self.my_reception_cache if r['time'] > cutoff]
            hearing_me_count = len(self.my_reception_cache)
            
            self.cache_updated.emit()
            self.status_message.emit(
                f"Tracking {total_signals} signals | {hearing_me_count} stations hear {self.my_call}"
            )