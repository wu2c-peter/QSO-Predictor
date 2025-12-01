# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal
from psk_client import PskReporterClient

class QSOAnalyzer(QObject):
    cache_updated = pyqtSignal()
    status_message = pyqtSignal(str) 

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.psk = PskReporterClient()
        self.my_call = config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
        self.current_dial_freq = 0
        self.band_cache = {}
        self.update_trigger = threading.Event()
        self.running = True
        self.first_fetch_complete = False
        
        self.worker_thread = threading.Thread(target=self._bulk_update_loop, daemon=True)
        self.worker_thread.start()

    def set_dial_freq(self, freq):
        if self.current_dial_freq != freq:
            self.current_dial_freq = freq
            self.band_cache.clear()
            self.first_fetch_complete = False 
            self.update_trigger.set()

    def analyze_decode(self, decode_data, update_callback=None):
        if 'competition' not in decode_data: 
            decode_data['competition'] = ""
            
        if 'prob' not in decode_data or '%' not in decode_data['prob']:
            snr = decode_data.get('snr', -20)
            if snr >= 10: prob = 85
            elif snr >= 0: prob = 75
            elif snr >= -10: prob = 60
            elif snr >= -15: prob = 45
            else: prob = 25
            decode_data['prob'] = f"{prob}%"
        
        if 'rec_offset' not in decode_data: 
            decode_data['rec_offset'] = decode_data.get('freq', 1500)

        if decode_data.get('call'):
            decode_data = self._calculate_stats(decode_data)
        
        return decode_data

    def get_analysis_immediate(self, decode_data):
        return self._calculate_stats(decode_data)

    def _bulk_update_loop(self):
        time.sleep(1)
        while self.running:
            wait_time = 120 # Default wait (Success)

            if self.current_dial_freq > 0:
                self.status_message.emit("Status: Fetching Spots...")
                print(f"DEBUG: Bulk Query for {self.current_dial_freq}...")
                
                start_f = self.current_dial_freq
                end_f = self.current_dial_freq + 4000
                reports = self.psk.get_band_reports(start_f, end_f)
                
                if reports is not None:
                    new_cache = {}
                    for rep in reports:
                        sender = rep['sender'] 
                        if sender not in new_cache: new_cache[sender] = []
                        new_cache[sender].append(rep)
                    
                    self.band_cache = new_cache
                    self.first_fetch_complete = True 
                    
                    print(f"DEBUG: Cache Updated. {len(new_cache)} stations.")
                    self.cache_updated.emit()
                    self.status_message.emit("Status: Monitoring")
                    wait_time = 120 # Success: Wait 2 mins
                else:
                    self.status_message.emit("Status: Fetch Failed (Retrying...)")
                    wait_time = 15 # Fail: Retry quickly
            else:
                self.status_message.emit("Status: Waiting for Dial Freq...")
                wait_time = 5 # Wait for user to launch WSJT-X
            
            # Wait for the calculated time OR a trigger (band change)
            self.update_trigger.wait(wait_time)
            self.update_trigger.clear()

    def _calculate_stats(self, decode_data):
        if not self.first_fetch_complete:
            decode_data['competition'] = "Loading..."
            return decode_data

        target_call = decode_data['call']
        heard_reports = []
        
        if target_call in self.band_cache:
            heard_reports = self.band_cache[target_call]
        elif '/' in target_call:
            base_call = max(target_call.split('/'), key=len)
            if base_call in self.band_cache:
                heard_reports = self.band_cache[base_call]
        
        remote_qrm_data = []
        current_time = time.time()
        if self.current_dial_freq > 0:
            for rep in heard_reports:
                try:
                    rep_freq = float(rep['freq']) 
                    offset = rep_freq - self.current_dial_freq
                    if 0 < offset < 3000:
                        rep_time = rep.get('time', current_time)
                        age = max(0, current_time - rep_time)
                        remote_qrm_data.append({
                            'offset': int(offset), 'snr': rep['snr'], 'age': int(age)
                        })
                except: pass
        decode_data['remote_qrm'] = remote_qrm_data

        count = len(heard_reports)
        try:
            current_prob = int(decode_data['prob'].replace('%',''))
        except: current_prob = 25

        pileup_penalty = 0
        comp_str = "..."
        
        if count > 40: pileup_penalty = -30; comp_str = "Pileup (>40)"
        elif count > 20: pileup_penalty = -20; comp_str = "High (>20)"
        elif count > 10: pileup_penalty = -10; comp_str = "Med (>10)"
        elif count > 0: comp_str = "Low"
        else: comp_str = "No Spots"

        geo_bonus = 0
        direct_hit = False
        
        for rep in heard_reports:
            if 'call' in rep and self.my_call in rep['call']:
                geo_bonus = 100; direct_hit = True; comp_str = "CONNECTED"
                break
        
        if not direct_hit:
            if count > 0:
                geo_bonus += 10
                if decode_data.get('snr', -20) > -10: geo_bonus += 10
            else:
                snr = decode_data.get('snr', -20)
                if snr > -5: geo_bonus += 10 
                elif snr > -12: geo_bonus += 0  
                else: geo_bonus -= 15 

        final_prob = max(5, min(99, current_prob + geo_bonus + pileup_penalty))
        decode_data['prob'] = f"{final_prob}%"
        decode_data['competition'] = comp_str
        
        return decode_data