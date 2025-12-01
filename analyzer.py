
# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]
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


import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal
from psk_client import PskReporterClient

class QSOAnalyzer(QObject):
    cache_updated = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.psk = PskReporterClient()
        self.my_call = config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
        self.current_dial_freq = 0
        self.band_cache = {}
        self.update_trigger = threading.Event()
        self.running = True
        self.worker_thread = threading.Thread(target=self._bulk_update_loop, daemon=True)
        self.worker_thread.start()

    def set_dial_freq(self, freq):
        if self.current_dial_freq != freq:
            self.current_dial_freq = freq
            self.band_cache.clear()
            self.update_trigger.set()

    def analyze_decode(self, decode_data, update_callback=None):
        # 1. Base Prob
        if 'prob' not in decode_data or '%' not in decode_data['prob']:
            snr = decode_data.get('snr', -20)
            if snr >= -1: prob = 45
            elif snr >= -10: prob = 35
            elif snr >= -15: prob = 25
            else: prob = 15
            decode_data['prob'] = f"{prob}%"
        
        decode_data['competition'] = "..."
        if 'rec_offset' not in decode_data: decode_data['rec_offset'] = decode_data['freq']

        # 2. Threaded Lookup (For new incoming decodes)
        if decode_data['call'] and update_callback:
            threading.Thread(target=self._perform_lookup, 
                             args=(decode_data, update_callback)).start()
        
        return decode_data

    def get_analysis_immediate(self, decode_data):
        """
        Synchronous version of the lookup. 
        Returns the updated dict INSTANTLY.
        Used for refreshing the table.
        """
        return self._calculate_stats(decode_data)

    def _bulk_update_loop(self):
        time.sleep(1)
        while self.running:
            if self.current_dial_freq > 0:
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
                    print(f"DEBUG: Cache Updated. {len(new_cache)} stations.")
                    self.cache_updated.emit() 
            
            self.update_trigger.wait(120)
            self.update_trigger.clear()

    def _perform_lookup(self, decode_data, callback):
        # Thread wrapper
        result = self._calculate_stats(decode_data)
        callback(result)

    def _calculate_stats(self, decode_data):
        target_call = decode_data['call']
        heard_reports = []
        
        # 1. Cache Lookup
        if target_call in self.band_cache:
            heard_reports = self.band_cache[target_call]
        else:
            for cached_call in self.band_cache:
                if target_call == cached_call or \
                   (target_call in cached_call and '/' in cached_call) or \
                   (cached_call in target_call and '/' in target_call):
                    heard_reports = self.band_cache[cached_call]
                    break
        
        # 2. Remote QRM
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

        # 3. Competition & Geo Logic
        count = len(heard_reports)
        try:
            current_prob = int(decode_data['prob'].replace('%',''))
        except: current_prob = 15

        pileup_penalty = 0
        comp_str = "..."
        
        if count > 40: pileup_penalty = -20; comp_str = "Pileup"
        elif count > 20: pileup_penalty = -10; comp_str = "High"
        elif count > 10: comp_str = "Med"
        elif count > 0: comp_str = "Low"
        else: comp_str = "No Spots"; pileup_penalty = -5

        geo_bonus = 0
        direct_hit = False
        
        for rep in heard_reports:
            if 'call' in rep and self.my_call in rep['call']:
                geo_bonus = 100; direct_hit = True; comp_str = "CONNECTED"
                break
        
        if not direct_hit:
            if count > 0:
                geo_bonus += 10
                if decode_data.get('snr', -20) > -10: geo_bonus += 15
            else:
                geo_bonus -= 20

        final_prob = max(5, min(99, current_prob + geo_bonus + pileup_penalty))
        decode_data['prob'] = f"{final_prob}%"
        decode_data['competition'] = comp_str
        
        return decode_data
