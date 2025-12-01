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


import requests
import xml.etree.ElementTree as ET
import time
import re

class PskReporterClient:
    BASE_URL = "https://retrieve.pskreporter.info/query"
    HEADERS = {
        'User-Agent': 'QSO-Predictor-App/1.0 (Amateur Radio Tool)',
        'Accept': 'application/xml'
    }

    def __init__(self):
        self.cache = {}

    def get_band_reports(self, start_freq, end_freq):
        """
        Fetches reports for a frequency range (Hz).
        """
        frange = f"{int(start_freq)}-{int(end_freq)}"
        
        # Optimized: 10 minutes (-600) is the tactical standard.
        # 15 mins was too large and slow to parse.
        params = {
            'frange': frange,
            'flowStartSeconds': '-600', 
            'rronly': '1'
        }
        
        try:
            response = requests.get(self.BASE_URL, params=params, headers=self.HEADERS, timeout=10)
            if response.status_code == 200:
                return self._parse_bulk_xml(response.content)
            return None
        except Exception as e:
            print(f"PSK Network Error: {e}")
            return None

    def _parse_bulk_xml(self, xml_content):
        results = []
        try:
            # Using standard ET parsing. 
            # (Future optimization could use iterparse if this remains slow)
            root = ET.fromstring(xml_content)
            for child in root:
                if child.tag == 'receptionReport':
                    sender = child.attrib.get('senderCallsign')
                    receiver = child.attrib.get('receiverCallsign')
                    snr = child.attrib.get('sNR')
                    freq = child.attrib.get('frequency')
                    flow_start = child.attrib.get('flowStartSeconds')
                    
                    if sender and receiver:
                        results.append({
                            'sender': self._clean_callsign(sender),
                            'call': receiver,
                            'snr': int(snr) if snr else -99,
                            'freq': freq,
                            'time': int(flow_start) if flow_start else int(time.time())
                        })
        except: pass
        return results

    def _clean_callsign(self, call):
        if not call: return None
        match = re.search(r"([A-Z0-9/]+)", call)
        if match:
            c = match.group(1)
            if '/' in c: c = max(c.split('/'), key=len)
            return c
        return None
