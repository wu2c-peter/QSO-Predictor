# QSO Predictor
# Copyright (C) 2025 Peter Hirst (WU2C)
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

import logging
import requests

logger = logging.getLogger(__name__)

class SolarClient:
    # NOAA SWPC Data Feeds
    URL_FLUX = "https://services.swpc.noaa.gov/products/summary/10cm-flux.json"
    URL_PLANETARY_K = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"

    def get_solar_data(self):
        """
        Returns a dict with SFI, K-Index, and a simple Condition text.
        
        v2.3.3 hotfix: NOAA changed JSON formats on March 31, 2026 (SCN 26-21).
        - 10cm-flux.json: now array of objects, key "flux" (was "Flux"), numeric values
        - noaa-planetary-k-index.json: now array of objects with "Kp" key (was positional)
        """
        data = {'sfi': 0, 'k': 0, 'condx': 'Unknown'}
        
        try:
            # 1. Get Solar Flux (SFI) - Higher is better
            r = requests.get(self.URL_FLUX, timeout=5)
            if r.status_code == 200:
                json_data = r.json()
                # New format (March 2026): [{"flux": 130, "time_tag": "..."}]
                # Old format: {"Flux": "130", "TimeStamp": "..."}
                if isinstance(json_data, list) and len(json_data) > 0:
                    data['sfi'] = int(json_data[0].get('flux', 0))
                elif isinstance(json_data, dict):
                    data['sfi'] = int(json_data.get('Flux', json_data.get('flux', 0)))

            # 2. Get K-Index - Lower is better
            r = requests.get(self.URL_PLANETARY_K, timeout=5)
            if r.status_code == 200:
                json_data = r.json()
                if len(json_data) > 1:
                    last_entry = json_data[-1]
                    # New format (March 2026): {"Kp": 3.33, "time_tag": "..."}
                    # Old format: ["2026-02-19 00:00:00", "3.33", ...]
                    if isinstance(last_entry, dict):
                        data['k'] = int(float(last_entry.get('Kp', 0)))
                    elif isinstance(last_entry, list):
                        data['k'] = int(float(last_entry[1]))
            
            # 3. Determine Conditions
            data['condx'] = self._calc_condition(data['sfi'], data['k'])
            
        except Exception as e:
            logger.warning(f"Solar fetch error: {e}")
        
        return data

    def _calc_condition(self, sfi, k):
        if k >= 5: return "STORM (High Noise)"
        if k >= 4: return "Unstable"
        
        if sfi > 150: return "Excellent"
        if sfi > 100: return "Good"
        if sfi > 70: return "Fair"
        return "Poor"


