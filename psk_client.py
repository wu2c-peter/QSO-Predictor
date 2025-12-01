# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import requests
import xml.etree.ElementTree as ET
import time

class PskReporterClient:
    def __init__(self):
        self.url = "https://retrieve.pskreporter.info/query"

    def get_band_reports(self, start_freq, end_freq):
        # Fetch stations hearing OTHERS (The Band Map data)
        params = {
            'flowStartSeconds': f"-{10 * 60}", # Last 10 mins
            'frange': f"{start_freq}-{end_freq}",
            'rronly': 1, 
            'mode': 'FT8'
        }
        return self._perform_query(params)

    def get_reports_for_call(self, callsign):
        # Fetch stations hearing ME (The "Open Path" data)
        if not callsign or callsign == 'N0CALL': return []
        
        params = {
            'flowStartSeconds': f"-{15 * 60}", # Last 15 mins
            'senderCallsign': callsign,
            'rronly': 1, # Receiver reports only
            'mode': 'FT8'
        }
        return self._perform_query(params)

    def _perform_query(self, params):
        try:
            response = requests.get(self.url, params=params, timeout=5)
            if response.status_code != 200: return None
            
            root = ET.fromstring(response.content)
            reports = []
            
            for reception in root.findall(".//receptionReport"):
                # "receiverCallsign" is who HEARD the signal
                # "senderCallsign" is who TRANSMITTED
                rx_call = reception.get("receiverCallsign")
                sender_call = reception.get("senderCallsign")
                freq = reception.get("frequency")
                snr = reception.get("sbr")
                ts = reception.get("flowStartSeconds")
                grid = reception.get("receiverLocator") # Grid of the RECEIVER
                
                if rx_call and freq and ts:
                    reports.append({
                        'receiver': rx_call,
                        'sender': sender_call,
                        'freq': freq,
                        'snr': int(snr) if snr else -20,
                        'time': int(ts),
                        'grid': grid[:4] if grid else "" # Store 4-char grid
                    })
            return reports
        except:
            return None