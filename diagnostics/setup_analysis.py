"""
Recommendation engine: turn detection results into a QSOP setup config.

Lifted unchanged from `setup_wizard.py` (v2.2.0) in migration step 2 of
dev-docs/DIAGNOSTICS_SPEC.md.

Known impurity, kept for move fidelity: on port-conflict paths,
`analyze()` calls `PortScanner.find_free_port()`, which does live socket
binds — so this is not a pure snapshot interpreter yet. When the Network
Doctor arrives it consumes a StationSnapshot instead; untangle then, not
here.

QSO Predictor
Copyright (C) 2025 Peter Hirst (WU2C)
"""

from typing import List

from diagnostics.models import DetectedApp, PortInfo, SetupRecommendation
from diagnostics.probe_ports import PortScanner


class SetupAnalyzer:
    """
    Combines all detection results into a recommended configuration.
    """

    @staticmethod
    def analyze(apps: List[DetectedApp],
                ports_in_use: List[PortInfo],
                running_apps: List[str]) -> SetupRecommendation:
        """
        Analyze detected environment and produce a recommendation.

        Priority for callsign/grid:
          1. JTDX config (preferred for QSO Predictor)
          2. WSJT-X config

        Priority for UDP config:
          1. If multicast detected, join multicast
          2. If port free, use standard 2237
          3. If port occupied, find secondary or suggest secondary UDP
        """
        rec = SetupRecommendation()

        # --- Station info (callsign/grid) ---
        # Prefer JTDX, then WSJT-X, then first with data
        jtdx_apps = [a for a in apps if a.name == 'JTDX' and a.callsign]
        wsjtx_apps = [a for a in apps if a.name == 'WSJT-X' and a.callsign]
        any_with_call = [a for a in apps if a.callsign]

        source_app = None
        if jtdx_apps:
            source_app = jtdx_apps[0]
        elif wsjtx_apps:
            source_app = wsjtx_apps[0]
        elif any_with_call:
            source_app = any_with_call[0]

        if source_app:
            rec.callsign = source_app.callsign.upper()
            rec.grid = source_app.grid.upper() if source_app.grid else ''
            rec.source = f"from {source_app.name}" + (
                f" ({source_app.instance_name})" if source_app.instance_name else ""
            )
            rec.confidence = "high"
            rec.notes.append(
                f"Callsign and grid detected {rec.source}"
            )

        # --- UDP configuration ---
        # Check if any detected app uses multicast
        multicast_apps = [a for a in apps
                         if a.udp_ip and a.udp_ip.startswith(('224.', '225.', '226.',
                                '227.', '228.', '229.', '230.', '231.', '232.',
                                '233.', '234.', '235.', '236.', '237.', '238.', '239.'))]

        # Check if JTAlert is running (strong indicator of multicast need)
        jtalert_running = 'JTAlert' in running_apps

        if multicast_apps:
            # Use same multicast group as the detected app
            mcast_app = multicast_apps[0]
            rec.udp_ip = mcast_app.udp_ip
            rec.udp_port = mcast_app.udp_port
            rec.use_multicast = True
            rec.notes.append(
                f"Multicast detected: {mcast_app.name} uses {mcast_app.udp_ip}:{mcast_app.udp_port}"
            )

        elif jtalert_running:
            # JTAlert is running - likely needs multicast or secondary port
            rec.warnings.append(
                "JTAlert is running — you may need multicast or a secondary UDP port"
            )
            # Check if port 2237 is occupied
            port_2237_used = any(p.port == 2237 for p in ports_in_use)
            if port_2237_used:
                free_port = PortScanner.find_free_port(2238)
                rec.udp_port = free_port
                rec.udp_ip = '127.0.0.1'
                rec.notes.append(
                    f"Port 2237 in use — recommending port {free_port}"
                )
                rec.notes.append(
                    "Configure WSJT-X/JTDX secondary UDP to match this port"
                )
            else:
                rec.udp_port = 2237
                rec.udp_ip = '127.0.0.1'

        else:
            # Standard setup - use detected port or default
            if source_app and source_app.udp_port:
                target_port = source_app.udp_port
            else:
                target_port = 2237

            port_used = any(p.port == target_port for p in ports_in_use)
            if port_used:
                # Port is taken - find a free one
                free_port = PortScanner.find_free_port(target_port + 1)
                rec.udp_port = free_port
                rec.udp_ip = '127.0.0.1'

                # Find who's using the port
                occupier = next((p for p in ports_in_use if p.port == target_port), None)
                occupier_name = occupier.process_name if occupier else 'another app'

                rec.warnings.append(
                    f"Port {target_port} is in use by {occupier_name}"
                )
                rec.notes.append(
                    f"Recommending port {free_port} — configure WSJT-X/JTDX "
                    f"secondary UDP to send to 127.0.0.1:{free_port}"
                )
            else:
                rec.udp_port = target_port
                # udp_ip can be '' when the user cleared the address to
                # disable UDP — recommend the standard loopback then.
                rec.udp_ip = ((source_app.udp_ip or '127.0.0.1')
                              if source_app else '127.0.0.1')

        # --- Detect potential forward port needs ---
        other_listeners = [a for a in running_apps
                         if a not in ('WSJT-X', 'JTDX')]
        if other_listeners and not rec.use_multicast:
            rec.notes.append(
                f"Other apps detected ({', '.join(other_listeners)}) — "
                f"consider UDP forwarding if they need decode data"
            )

        # --- Confidence level ---
        if rec.callsign and rec.callsign != 'N0CALL':
            if not rec.warnings:
                rec.confidence = "high"
            else:
                rec.confidence = "medium"
        elif apps:
            rec.confidence = "medium"  # Found apps but no callsign
        else:
            rec.confidence = "low"

        return rec
