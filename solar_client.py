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

    # Physical plausibility bounds. Anything outside is a feed/parsing
    # problem, not space weather — never hand it to IONIS.
    SFI_RANGE = (50, 400)
    KP_RANGE = (0, 9)

    def get_solar_data(self):
        """
        Returns a dict with SFI, K-Index, a simple Condition text and a
        `valid` flag. On ANY failure (HTTP error, schema drift, network
        down) `valid` is False and sfi/k are None — a failed fetch used
        to come back as SFI 0 / K 0 "(Poor)", which looked like real
        data and was fed to the IONIS model as physically impossible
        inputs (its 100/2 fallbacks never fired because the keys were
        always present).

        v2.3.3 hotfix: NOAA changed JSON formats on March 31, 2026 (SCN 26-21).
        - 10cm-flux.json: now array of objects, key "flux" (was "Flux"), numeric values
        - noaa-planetary-k-index.json: now array of objects with "Kp" key (was positional)
        """
        sfi = self._fetch(self.URL_FLUX, self._parse_flux, 'SFI')
        k = self._fetch(self.URL_PLANETARY_K, self._parse_kp, 'Kp')

        if sfi is None or k is None:
            return {'sfi': sfi, 'k': k, 'condx': 'Unavailable', 'valid': False}
        return {'sfi': sfi, 'k': k, 'condx': self._calc_condition(sfi, k),
                'valid': True}

    def _fetch(self, url, parser, label):
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            value = parser(r.json())
        except Exception as e:
            logger.warning(f"Solar fetch error ({label}): {e}")
            return None
        if value is None:
            logger.warning(f"Solar fetch: {label} feed returned no usable value")
        return value

    def _parse_flux(self, json_data):
        # New format (March 2026): [{"flux": 130, "time_tag": "..."}]
        # Old format: {"Flux": "130", "TimeStamp": "..."}
        raw = None
        if isinstance(json_data, list) and json_data:
            raw = json_data[0].get('flux')
        elif isinstance(json_data, dict):
            raw = json_data.get('Flux', json_data.get('flux'))
        return self._in_range(raw, self.SFI_RANGE)

    def _parse_kp(self, json_data):
        # New format (March 2026): {"Kp": 3.33, "time_tag": "..."}
        # Old format: ["2026-02-19 00:00:00", "3.33", ...]
        if not isinstance(json_data, list) or len(json_data) < 2:
            return None
        last_entry = json_data[-1]
        raw = None
        if isinstance(last_entry, dict):
            raw = last_entry.get('Kp')
        elif isinstance(last_entry, list) and len(last_entry) > 1:
            raw = last_entry[1]
        return self._in_range(raw, self.KP_RANGE)

    @staticmethod
    def _in_range(raw, bounds):
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            return None
        lo, hi = bounds
        return value if lo <= value <= hi else None

    def _calc_condition(self, sfi, k):
        if k >= 5: return "STORM (High Noise)"
        if k >= 4: return "Unstable"
        
        if sfi > 150: return "Excellent"
        if sfi > 100: return "Good"
        if sfi > 70: return "Fair"
        return "Poor"


