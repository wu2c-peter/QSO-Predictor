"""Target selection and activity-state coordinator.

The unified target-change handler (`set_target`) is the single entry
point through which every target transition flows — manual entry, decode
table click, WSJT-X/JTDX UDP sync, and clear. Centralizing the cascade
here keeps the ten downstream subsystems (dashboard, band map, analyzer,
local intel, F/H state, IONIS, outcome recorder, tactical toast,
perspective display) in sync.

Target state attributes (`current_target_call`, `current_target_grid`,
`jtdx_last_dx_call`, `_is_manual_target`, the `_target_activity_*`
fields, `_inferred_competitors`) still live on MainWindow because many
other code paths read them directly. This controller mutates them in
place; tightening ownership can come in a later pass.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
import time as _time

from PyQt6.QtCore import QObject

logger = logging.getLogger(__name__)


class TargetCoordinator(QObject):
    """Single entry point for target selection + activity-state transitions."""

    # Common DXCC prefix → approximate grid centroid. Used by lookup_grid as
    # the final fallback when neither local decodes nor PSK Reporter receiver
    # data have a grid for the call.
    _PREFIX_GRIDS = {
        # Japan
        'JA': 'PM95', 'JH': 'PM95', 'JR': 'PM95', 'JE': 'PM95', 'JF': 'PM95',
        'JG': 'PM95', 'JI': 'PM95', 'JJ': 'PM95', 'JK': 'PM95', 'JL': 'PM95',
        'JM': 'PM95', 'JN': 'PM95', 'JO': 'PM95', 'JP': 'PM95', 'JQ': 'PM95',
        'JS': 'PM95',
        # Central/East Asia
        'JT': 'ON48',  # Mongolia
        'HL': 'PM37', 'DS': 'PM37',  # South Korea
        'BV': 'PL05',  # Taiwan
        'BY': 'OM89', 'BA': 'OM89', 'BD': 'OM89', 'BG': 'OM89',  # China
        'VU': 'MK82', 'AT': 'MK82',  # India
        # CIS / Former Soviet
        'UA': 'KO85', 'RA': 'KO85', 'RV': 'KO85', 'RW': 'KO85', 'RX': 'KO85',
        'R': 'KO85',  # Russia (single letter prefix)
        'UN': 'MN53', 'UP': 'MN53', 'UL': 'MN53',  # Kazakhstan
        'UK': 'MM39', 'UJ': 'MM39',  # Uzbekistan
        'EX': 'MM72', 'EZ': 'MM72',  # Kyrgyzstan / Turkmenistan
        'UR': 'KN28', 'UT': 'KN28', 'UX': 'KN28', 'US': 'KN28',  # Ukraine
        'EU': 'KO33', 'EW': 'KO33',  # Belarus
        'LY': 'KO24',  # Lithuania
        'YL': 'KO26',  # Latvia
        'ES': 'KO29',  # Estonia
        'ER': 'KN47',  # Moldova
        '4L': 'LN21',  # Georgia
        '4J': 'LM49',  # Azerbaijan
        'EK': 'LN20',  # Armenia
        # Oceania
        'VK': 'QF56', 'AX': 'QF56',  # Australia
        'ZL': 'RF73',  # New Zealand
        'DU': 'PK04', 'DV': 'PK04',  # Philippines
        'YB': 'OI33', 'YC': 'OI33', 'YD': 'OI33',  # Indonesia
        '9M': 'OJ11', '9W': 'OJ11',  # Malaysia
        'HS': 'OK03', 'E2': 'OK03',  # Thailand
        'XV': 'OK30', '3W': 'OK30',  # Vietnam
        'XW': 'NK97',  # Laos
        'V8': 'OJ95',  # Brunei
        'FK': 'RG37',  # New Caledonia
        'FO': 'BH51',  # French Polynesia
        'KH6': 'BL11', 'KL7': 'BP51', 'KP4': 'FK68',
        'NH6': 'BL11', 'NL7': 'BP51', 'NP4': 'FK68',
        'WH6': 'BL11', 'WL7': 'BP51', 'WP4': 'FK68',
        'AH6': 'BL11', 'AL7': 'BP51',
        # Canada
        'VE': 'FN03', 'VA': 'FN03', 'VY': 'FN03', 'VO': 'GN37',
        # Europe
        'G': 'IO91', 'M': 'IO91', '2E': 'IO91',
        'GI': 'IO65', 'GW': 'IO71', 'GM': 'IO86', 'GD': 'IO74',
        'DL': 'JO51', 'DA': 'JO51', 'DB': 'JO51', 'DC': 'JO51', 'DD': 'JO51',
        'DF': 'JO51', 'DG': 'JO51', 'DH': 'JO51', 'DJ': 'JO51', 'DK': 'JO51',
        'DO': 'JO51',
        'F': 'JN18', 'ON': 'JO20', 'PA': 'JO22', 'PH': 'JO22',
        'I': 'JN61', 'IK': 'JN61', 'IZ': 'JN61',
        'EA': 'IN80', 'EB': 'IN80', 'EC': 'IN80',
        'CT': 'IM58', 'CS': 'IM58',
        'SM': 'JO89', 'SA': 'JO89', 'OH': 'KP20', 'OZ': 'JO55',
        'LA': 'JO59', 'LB': 'JO59',
        'SP': 'JO91', 'SQ': 'JO91', 'OK': 'JN79', 'OL': 'JN79',
        'HA': 'JN97', 'HG': 'JN97',
        'YU': 'KN04', 'YT': 'KN04',
        'OE': 'JN78',  # Austria
        'HB': 'JN47',  # Switzerland
        'OY': 'IP62',  # Faroe Islands
        'TF': 'HP94',  # Iceland
        'SV': 'KM18', 'SW': 'KM18',  # Greece
        '9A': 'JN75',  # Croatia
        'S5': 'JN76',  # Slovenia
        'Z3': 'KN01',  # North Macedonia
        'ZA': 'KN01',  # Albania
        'LZ': 'KN22',  # Bulgaria
        'YO': 'KN25',  # Romania
        'E7': 'JN84',  # Bosnia
        # Middle East
        'TA': 'KN30', 'TC': 'KN30',  # Turkey
        '5B': 'KM65',  # Cyprus
        'A4': 'LL93', 'A6': 'LL65', 'A7': 'LL55',
        'A9': 'LL46', 'HZ': 'KL41', '9K': 'LL49',
        'OD': 'KM73',  # Lebanon
        '4X': 'KM72', '4Z': 'KM72',  # Israel
        'YK': 'KM74',  # Syria
        'YI': 'LM13',  # Iraq
        'EP': 'LL48', 'EQ': 'LL48',  # Iran
        'AP': 'ML44',  # Pakistan
        # Africa
        '3B8': 'MH87', '5H': 'KI73', '5Z': 'KI88',
        '9J': 'KH25', '7Q': 'KH74', 'ZD8': 'II22',
        'CN': 'IM63',  # Morocco
        '7X': 'JM16',  # Algeria
        'SU': 'KL30',  # Egypt
        'ST': 'KK55',  # Sudan
        'ET': 'KJ19',  # Ethiopia
        '5A': 'JM73',  # Libya
        'TU': 'IJ56',  # Ivory Coast
        '6W': 'IK14',  # Senegal
        '5N': 'JJ17',  # Nigeria
        'TR': 'JI31',  # Gabon
        '9X': 'KI49',  # Rwanda
        'V5': 'JG87',  # Namibia
        'ZS': 'KG33', 'ZR': 'KG33',  # South Africa
        # Central America / Caribbean
        'TI': 'EJ89', 'HP': 'FJ09', 'HK': 'FJ34', 'YV': 'FJ66',
        'XE': 'EK09', 'XA': 'EK09',  # Mexico
        'VP9': 'FM72', 'V3': 'EK57', '8P': 'GK03',
        'HI': 'FK58',  # Dominican Republic
        'CO': 'FL11', 'CM': 'FL11',  # Cuba
        'YS': 'EK53',  # El Salvador
        'TG': 'EK44',  # Guatemala
        'HR': 'EK64',  # Honduras
        'PJ': 'FK52',  # Netherlands Antilles
        'J3': 'FK92',  # Grenada
        'J6': 'FK93',  # St Lucia
        'VP2': 'FK87',  # Anguilla/Montserrat
        'FG': 'FK96',  # Guadeloupe
        'FM': 'FK94',  # Martinique
        # South America
        'LU': 'GF05', 'LW': 'GF05',  # Argentina
        'PY': 'GG87', 'PP': 'GG87', 'PR': 'GG87', 'PS': 'GG87', 'PT': 'GG87',
        'PU': 'GG87',  # Brazil
        'CE': 'FF46', 'CA': 'FF46',  # Chile
        'HC': 'FI09',  # Ecuador
        'OA': 'FH17',  # Peru
        'CP': 'FH33',  # Bolivia
        'ZP': 'GG14',  # Paraguay
        'CX': 'GF15',  # Uruguay
    }

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window

    def set_target(self, call, grid="", freq=0, row_data=None):
        """Unified target-change handler. All target changes flow through here.

        v2.3.3: Centralized to fix inconsistent state updates across four
        separate code paths (clear_target, sync_to_jtdx, on_status,
        on_row_click). Previously, some paths missed updating analyzer grid,
        activity state, F/H state, tactical toast, or perspective display.

        Args:
            call: Target callsign (empty string to clear)
            grid: Target grid square
            freq: Target audio frequency offset
            row_data: Decode table row dict (if available; otherwise searched)
        """
        mw = self.main_window
        is_clearing = not call

        # --- Find row data if not provided ---
        if call and not row_data:
            for row in mw.model._data:
                if row.get('call') == call:
                    row_data = row
                    if not grid:
                        grid = row.get('grid', '')
                    if not freq:
                        freq = row.get('freq', 0)
                    break

        prev_target = mw.current_target_call
        logger.info(f"Target: '{prev_target}' → '{call or '(cleared)'}'")

        # --- OUTCOME RECORDER: Record outcome for previous target BEFORE state resets ---
        # Must happen here — after this point, scoring state gets cleared.
        # Safe to call if no active target (recorder checks has_active_target).
        if prev_target:
            trigger = 'CLEARED' if is_clearing else 'TARGET_CHANGED'
            mw._record_outcome_for_current_target(trigger)

        # --- 1. Core state ---
        mw.current_target_call = call
        mw.current_target_grid = grid
        mw.analyzer.current_target_grid = grid

        # --- 2. Reset per-target tracking ---
        mw._target_activity_state = 'unknown'
        mw._target_activity_other = None
        mw._target_activity_time = 0
        mw._inferred_competitors.clear()
        mw.dashboard.update_activity('unknown')  # v2.3.5: Reset dashboard cached state too

        # --- 3. F/H per-target state (keep manual/UDP mode setting) ---
        mw._fh_fox_qso = False
        mw._fh_dialog_shown = False
        mw.band_map.set_fox_qso(False)
        if mw._fh_source == 'inferred':
            mw.fox_hound.set_active(False, None, None)

        # --- 4. Table highlighting ---
        mw.model.set_target_call(call if call else None)

        # --- 5. Dashboard ---
        if is_clearing:
            mw._is_manual_target = False
            mw.dashboard.update_data(None)
        elif row_data:
            # Station is in decode table — not a manual target anymore
            if mw._is_manual_target:
                mw._is_manual_target = False
                logger.info(f"Manual target {call} found in decode table — switching to normal mode")
            # Re-analyze with full perspective before displaying
            mw.analyzer.analyze_decode(row_data, use_perspective=True)
            row_data['manual_target'] = False
            mw.dashboard.update_data(row_data)
        else:
            # Have call but no row data — may be manual target or early UDP target
            # v2.4.4: Show minimal dashboard with manual indicator
            manual_data = {
                'call': call,
                'time': '',
                'snr': '--',
                'dt': '--',
                'freq': 0,
                'message': '',
                'grid': grid or '--',
                'prob': '--',
                'path': '--',
                'competition': '--',
                'manual_target': mw._is_manual_target,
            }
            mw.dashboard.update_data(manual_data)

        # --- 6. Band map ---
        mw.band_map.set_target_freq(freq)
        mw.band_map.set_target_call(call)
        mw.band_map.set_target_grid(grid)
        if is_clearing:
            mw.band_map.update_perspective({
                'tier1': [], 'tier2': [], 'tier3': [], 'global': []
            })

        # --- 7. Local Intelligence ---
        if mw.local_intel:
            try:
                mw.local_intel.set_target(call if call else "", grid,
                                          manual=mw._is_manual_target)
                if row_data and not is_clearing:
                    mw._update_local_intel_path_status(row_data)
                    comp_str = str(row_data.get('competition', ''))
                    if hasattr(mw.local_intel, 'insights_panel'):
                        mw.local_intel.insights_panel.set_target_competition(comp_str)
            except Exception as e:
                logger.debug(f"Error updating local intel target: {e}")

        # --- 8. Tactical toast ---
        mw.tactical_toast.reset_state()

        # --- 9. Perspective update (fetches PSK Reporter data for new target) ---
        if not is_clearing:
            mw._update_perspective_display()

        # --- 10. IONIS propagation prediction (v2.4.0) ---
        mw._ionis_shown = False
        if is_clearing:
            mw.ionis.clear_prediction()
        elif mw._ionis_engine:
            mw.ionis.update_prediction()

        # --- 11. OUTCOME RECORDER: Register new target ---
        if mw.outcome_recorder and call:
            sfi = 0
            k = 0
            if hasattr(mw, '_solar_data') and mw._solar_data:
                sfi = mw._solar_data.get('sfi', 0)
                k = mw._solar_data.get('k', 0)
            # Capture path status BEFORE we start calling — this is predictive
            # (non-tautological). Path established during the QSO exchange
            # will show in the outcome snapshot's 'path' field instead.
            path_now = str(row_data.get('path', '')) if row_data else ''
            mw.outcome_recorder.on_target_selected(
                call, grid,
                band=getattr(mw, '_current_band', ''),
                sfi=sfi, k=k,
                path_at_select=path_now
            )

    def clear(self):
        """Clear the current target selection.

        Resets all target-related state and UI to "NO TARGET" mode.
        Can be triggered via Ctrl+R shortcut or Clear Target button.

        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        self.set_target("", "", 0, None)

    def lookup_grid(self, call):
        """v2.4.4: Grid lookup cascade — local sources first, then prefix fallback.

        Priority:
        1. Analyzer's call_grid_map (recent MQTT/PSK Reporter data)
        2. Decode table (currently displayed stations)
        3. DXCC prefix centroid (approximate, always available)

        Returns:
            tuple: (grid_str, source_str) e.g. ('PM95', 'PSK Reporter') or ('', 'none')
        """
        mw = self.main_window
        call = call.upper().strip()

        # 1. Analyzer's call_grid_map (populated from local decodes)
        grid = mw.analyzer.call_grid_map.get(call, '')
        if grid and len(grid) >= 2:
            logger.info(f"Manual target grid lookup: {call} → {grid} (call_grid_map)")
            return grid, 'local decode'

        # 2. Receiver cache — if station uploads to PSK Reporter, their grid
        #    is in every spot they reported (the 'grid' field = receiver's grid)
        with mw.analyzer.lock:
            if call in mw.analyzer.receiver_cache:
                spots = mw.analyzer.receiver_cache[call]
                if spots:
                    grid = spots[-1].get('grid', '')  # Most recent spot
                    if grid and len(grid) >= 2:
                        logger.info(f"Manual target grid lookup: {call} → {grid} (PSK Reporter receiver)")
                        return grid, 'PSK Reporter'

        # 3. Decode table rows
        for row in mw.model._data:
            if row.get('call') == call:
                grid = row.get('grid', '')
                if grid and len(grid) >= 2:
                    logger.info(f"Manual target grid lookup: {call} → {grid} (decode table)")
                    return grid, 'local decode'

        # 4. DXCC prefix fallback — try longest prefix match first
        # Handle special prefixes like KH6, KL7, KP4 before single-letter
        for prefix_len in (3, 2, 1):
            prefix = call[:prefix_len]
            if prefix in self._PREFIX_GRIDS:
                grid = self._PREFIX_GRIDS[prefix]
                logger.info(f"Manual target grid lookup: {call} → {grid} (DXCC prefix '{prefix}', approximate)")
                return grid, f'DXCC prefix (approx)'

        # 5. US callsign heuristic — W/K/N/AA-AL + digit gives rough area
        if len(call) >= 2 and call[0] in ('W', 'K', 'N'):
            logger.info(f"Manual target grid lookup: {call} → no grid (US call, too broad)")
            return '', 'none'

        logger.info(f"Manual target grid lookup: {call} → no grid found")
        return '', 'none'

    def on_manual_entry(self, call):
        """v2.4.4: Handle manually entered target callsign.

        Looks up grid from local caches and DXCC prefix table,
        then sets target with manual indicator.
        """
        mw = self.main_window
        call = call.upper().strip()
        if not call:
            return

        # Don't re-target if already targeting this station
        if call == mw.current_target_call:
            logger.info(f"Manual target: {call} already targeted")
            return

        # Look up grid
        grid, source = self.lookup_grid(call)

        logger.info(f"Manual target: {call}, grid={grid or '(unknown)'} via {source}")

        # Set the manual target flag BEFORE calling set_target
        mw._is_manual_target = True

        # Call unified target handler
        self.set_target(call, grid=grid)

        # Show feedback in status bar
        if grid:
            mw.update_status_msg(f"Manual target: {call} (grid {grid} via {source})")
        else:
            mw.update_status_msg(f"Manual target: {call} (grid unknown — will resolve from spots)")

    def on_row_click(self, index):
        """Decode table row click — set the clicked station as target."""
        mw = self.main_window
        logger.debug(f"on_row_click: row {index.row()}")
        row = index.row()
        if row < len(mw.model._data):
            data = mw.model._data[row]
            target_call = data.get('call', '')

            # Skip if clicking same target (avoid redundant processing)
            if target_call == mw.current_target_call:
                logger.debug(f"Same target {target_call}, skipping")
                return

            mw._is_manual_target = False  # v2.4.4: Not a manual target
            self.set_target(
                target_call,
                data.get('grid', ''),
                data.get('freq', 0),
                data
            )

    def update_activity(self, state, other_call):
        """v2.3.0: Update target activity state from decoded message.

        Called when a local decode reveals what the target is doing.

        Args:
            state: Activity state from parse_target_activity()
            other_call: Callsign of station target is interacting with
        """
        mw = self.main_window
        now = _time.time()
        prev_state = mw._target_activity_state

        mw._target_activity_state = state
        mw._target_activity_other = other_call
        mw._target_activity_time = now

        # Track inferred competitors (stations we know are competing because
        # the target responded to them, even if we never saw them call)
        if state in ('working_other', 'completing_with_other') and other_call:
            mw._inferred_competitors[other_call] = now

        # Clean up old inferred competitors (>2 minutes)
        cutoff = now - 120
        mw._inferred_competitors = {
            c: t for c, t in mw._inferred_competitors.items() if t > cutoff
        }

        # Update dashboard display
        mw.dashboard.update_activity(state, other_call)

        # Toast triggers for significant state transitions
        target = mw.current_target_call
        if state == 'cqing' and prev_state in ('working_other', 'completing_with_other', 'idle', 'unknown'):
            mw.tactical_toast.show_toast(
                f"🎯 {target} is now CQing — call now!", 'success'
            )
        elif state == 'working_you' and prev_state != 'working_you':
            mw.tactical_toast.show_toast(
                f"📡 {target} is responding to YOU!", 'success'
            )
        elif state == 'working_other' and prev_state == 'cqing':
            mw.tactical_toast.show_toast(
                f"📡 {target} working {other_call} — competition confirmed", 'info'
            )

        # v2.3.0: Fox QSO detection — when F/H active and Fox responds to us
        if mw._fh_active:
            if state in ('working_you', 'completing_with_you'):
                mw.fox_hound.set_fox_qso_active(True)
            elif mw._fh_fox_qso and state not in ('working_you', 'completing_with_you'):
                # Fox stopped responding to us — restore click-to-set
                mw.fox_hound.set_fox_qso_active(False)

    def check_activity_idle(self):
        """v2.3.0: Check if target activity should transition to idle.
        Called from refresh_target_perspective timer."""
        mw = self.main_window
        if (mw._target_activity_state not in ('idle', 'unknown') and
            mw._target_activity_time > 0 and
            _time.time() - mw._target_activity_time > mw._activity_idle_timeout):
            mw._target_activity_state = 'idle'
            mw._target_activity_other = None
            mw.dashboard.update_activity('idle')
