# QSO Predictor
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.1.3 Changes:
# - Fixed: AP (a priori) decoding indicators (a1-a7) showing as callsigns
#   in target list instead of actual call (reported by Brian KB1OPD)
#
# v2.1.1 Changes:
# - Added: check_data_health() method for resilient data source monitoring
# - Added: Timeout detection (30s threshold) with automatic warning/recovery
#
# v2.0.9 Changes:
# - Added: Proper logging throughout (replacing print statements)
# - Added: Periodic stats logging instead of per-packet logging
# - Added: messages_received counter for startup health check
# - Fixed: Windows 10054 error when forwarding to closed port (SIO_UDP_CONNRESET)
#
# v2.0.3 Changes:
# - Added: QSO Logged message handling (Type 5) for auto-clear feature
#   (suggested by KC0GU)

import logging
import platform
import re
import socket
import struct
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal

from config_manager import is_local_host
from utils import wsjtx_protocol

logger = logging.getLogger(__name__)


def parse_decode_message(message):
    """Extract (call, grid) of the transmitting station from an FT8/FT4 message.

    Shared by UDPHandler and FT8WebHandler so both sources classify decodes
    identically. Returns ("", "") when no callsign can be extracted.
    """
    # v2.1.3: Strip WSJT-X/JTDX AP (a priori) decoding indicators
    # These appear as trailing " a1" through " a7" and confuse callsign extraction
    # (Reported by Brian KB1OPD)
    message_clean = re.sub(r'\s+a[1-7]$', '', message.strip())
    parts = message_clean.split()
    grid = ""
    call = ""

    def is_suffix(s):
        s = s.upper()
        if s in ['73', 'RR73', 'RRR']: return True
        if s.startswith(('+', '-', 'R+', 'R-')) and len(s) > 1: return True
        return False

    def is_grid(s):
        # v2.1.2: Validate Maidenhead grid [A-R][A-R][0-9][0-9]
        # Previous check was too loose - accepted RR73 (FT8 ack) as grid
        if len(s) != 4: return False
        return (s[0].upper() in 'ABCDEFGHIJKLMNOPQR' and
                s[1].upper() in 'ABCDEFGHIJKLMNOPQR' and
                s[2].isdigit() and s[3].isdigit())

    if len(parts) >= 3:
        last = parts[-1]
        # v2.1.2: Check is_suffix FIRST to prevent FT8 tokens (RR73)
        # from being misidentified as grid squares
        if is_suffix(last):
            call = parts[-2]
        elif is_grid(last):
            grid = last
            call = parts[-2]
        else:
            call = last

    elif len(parts) == 2:
        call = parts[1]

    call = call.strip('<>')
    return call, grid


def strip_local_self_forwards(targets, listen_port):
    """Drop LOCAL forward targets that match our own listen port — that
    is a packet loop (and FT8web would re-ingest its own rebroadcast).
    A REMOTE host reusing the same port number is a legitimate
    cross-machine chain and is kept."""
    kept = []
    for host, port in targets:
        if port == listen_port and is_local_host(host):
            logger.warning(f"UDP: Removed self-forward to {host}:{port} "
                           f"(same as listen port)")
        else:
            kept.append((host, port))
    return kept


def multicast_join_addrs():
    """Local IPv4 addresses to join a multicast group on, loopback first.

    Joining only with INADDR_ANY attaches the membership to whichever
    interface holds the lowest-metric multicast route. That interface can
    be an idle VPN adapter (observed live: NordVPN's NordLynx at metric
    261 beat Ethernet's 281 with the VPN disconnected), leaving the socket
    deaf while other apps on the same group receive normally. Joining on
    loopback and every local address makes reception independent of the
    sender's egress interface and of adapter metric games.
    """
    addrs = ['127.0.0.1']
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET,
                                       socket.SOCK_DGRAM):
            ip = info[4][0]
            if ip not in addrs:
                addrs.append(ip)
    except OSError:
        # Hostname doesn't resolve locally — loopback join still happens
        pass
    return addrs


def multicast_membership_requests(group_ip, addrs):
    """(label, packed ip_mreq) for INADDR_ANY plus each local address."""
    group = socket.inet_aton(group_ip)
    requests = [('default', struct.pack('4sl', group, socket.INADDR_ANY))]
    for addr in addrs:
        requests.append((addr, struct.pack('4s4s', group,
                                           socket.inet_aton(addr))))
    return requests


class UDPHandler(QObject):
    new_decode = pyqtSignal(dict)
    status_update = pyqtSignal(dict)
    qso_logged = pyqtSignal(dict)  # v2.0.3: New signal for QSO Logged messages

    def __init__(self, config):
        super().__init__()
        self.port = int(config.get('NETWORK', 'udp_port'))
        # Support multicast address configuration
        self.ip = config.get('NETWORK', 'udp_ip', fallback='0.0.0.0')
        # (host, port) tuples; bare ports in config mean 127.0.0.1
        self.forward_targets = strip_local_self_forwards(
            config.get_forward_targets(), self.port)
        
        self.running = False
        self.is_multicast = self._is_multicast_address(self.ip)
        
        # v2.0.9: Track statistics for logging and diagnostics
        self.messages_received = 0
        self._decodes_received = 0
        self._status_received = 0
        self._first_decode_logged = False
        self._first_status_logged = False
        self._last_stats_log_time = None
        self._stats_log_interval = 60  # Log stats every 60 seconds
        
        # Track last received time for diagnostics
        self._last_packet_time = None
        # Click-to-call request routing state
        self._last_source_addr = None
        self._last_client_id = "WSJT-X"
        # Last data-bearing packet (status/decode/qso_logged, not heartbeat)
        # — used for dual-source detection when FT8web is also active
        self._last_data_time = None
        
        # v2.1.2: Rate-limit ICMP connection reset logging
        self._icmp_reset_count = 0
        
        # v2.1.1: Timeout detection state
        self._timeout_warned = False
        self._timeout_threshold = 30  # seconds with no data before warning
        
        # Track forward errors to avoid log spam
        self._forward_errors_logged = set()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # v2.5.5.1: SO_REUSEPORT enables multicast co-binding on macOS/BSD (suggested by W6IX).
        # No-op on Windows (constant doesn't exist); additive on Linux.
        if hasattr(socket, 'SO_REUSEPORT'):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        
        # v2.0.10: On Windows, disable ICMP "port unreachable" errors from killing the socket
        # This is critical for UDP forwarding to work reliably
        # See: https://stackoverflow.com/questions/34242622/windows-udp-sockets-recvfrom-fails-with-error-10054
        if platform.system() == 'Windows':
            try:
                # SIO_UDP_CONNRESET - Windows IOCTL to disable connection reset errors
                # Must use struct.pack for the value parameter
                SIO_UDP_CONNRESET = struct.unpack('i', struct.pack('I', 0x9800000C))[0]
                self.sock.ioctl(SIO_UDP_CONNRESET, struct.pack('I', 0))
                logger.debug("UDP: Disabled Windows ICMP connection reset errors")
            except (AttributeError, OSError, ValueError) as e:
                logger.debug(f"UDP: Could not disable ICMP errors (non-critical): {e}")
        
        # v2.3.2: Separate bind and multicast join so failures are survivable.
        # Previously, multicast join failure (e.g. WinError 10065) crashed the app
        # at startup, leaving users unable to fix their settings via the UI.
        self._bind_ok = False
        # Memberships that actually succeeded, so stop() drops exactly these
        self._joined_memberships = []

        try:
            if self.is_multicast:
                # Multicast setup: bind first, then join the group on every
                # interface. A single INADDR_ANY join lands on the lowest-
                # metric multicast route, which can be an idle VPN adapter —
                # see multicast_join_addrs().
                self.sock.bind(('', self.port))
                joined = []
                for label, mreq in multicast_membership_requests(
                        self.ip, multicast_join_addrs()):
                    try:
                        self.sock.setsockopt(socket.IPPROTO_IP,
                                             socket.IP_ADD_MEMBERSHIP, mreq)
                        self._joined_memberships.append(mreq)
                        joined.append(label)
                    except OSError as e:
                        # Duplicate membership (INADDR_ANY resolved to this
                        # interface already) or interface can't join — fine
                        # as long as at least one join sticks
                        logger.debug(f"UDP: Multicast join on {label} failed - {e}")
                if joined:
                    logger.info(f"UDP: Multicast joined {self.ip}:{self.port} "
                                f"on: {', '.join(joined)}")
                    self._bind_ok = True
                else:
                    # No membership at all (e.g. no route, adapter issue)
                    # Socket is bound but won't receive multicast — user can fix in Settings
                    logger.error(
                        f"UDP: Multicast join failed for {self.ip} on all interfaces. "
                        f"No UDP data will be received. "
                        f"Go to Settings → Network and switch to 'Standard (localhost)' "
                        f"if you don't need multicast."
                    )
            else:
                # Standard unicast
                self.sock.bind(('0.0.0.0', self.port))
                logger.info(f"UDP: Bound to port {self.port}")
                self._bind_ok = True
                
        except OSError as e:
            # Bind itself failed — try unicast fallback
            logger.error(f"UDP: Bind failed on port {self.port} - {e}")
            if self.is_multicast:
                logger.warning("UDP: Attempting unicast fallback on 0.0.0.0...")
                try:
                    # Need a fresh socket — the old one may be in a bad state
                    self.sock.close()
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    # v2.5.5.1: See note above re: SO_REUSEPORT for macOS/BSD co-binding.
                    if hasattr(socket, 'SO_REUSEPORT'):
                        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    self.sock.bind(('0.0.0.0', self.port))
                    self.is_multicast = False  # Clear flag so stop() doesn't try to leave group
                    logger.warning(
                        f"UDP: Fell back to unicast on port {self.port}. "
                        f"Update Settings → Network to match your WSJT-X/JTDX configuration."
                    )
                    self._bind_ok = True
                except OSError as e2:
                    logger.error(f"UDP: Unicast fallback also failed - {e2}. No UDP data available.")
            else:
                logger.error("UDP: Cannot listen for data. Check Settings → Network.")
                
        # Log forward targets if configured
        if self.forward_targets:
            logger.info("UDP: Forwarding enabled to: " + ", ".join(
                f"{h}:{p}" for h, p in self.forward_targets))
    
    def _is_multicast_address(self, ip: str) -> bool:
        """Check if IP is in multicast range (224.0.0.0 - 239.255.255.255)"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            first_octet = int(parts[0])
            return 224 <= first_octet <= 239
        except (ValueError, AttributeError):
            return False

    def start(self):
        self.running = True
        self._start_time = time.time()
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        logger.info("UDP: Listener thread started")

    def stop(self):
        logger.info(f"UDP: Stopping listener (total: {self.messages_received} packets, {self._decodes_received} decodes, {self._status_received} status)")
        self.running = False
        for mreq in self._joined_memberships:
            try:
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
            except Exception as e:
                logger.debug(f"UDP: Error leaving multicast group: {e}")
        self._joined_memberships = []
        try: 
            self.sock.close()
        except Exception as e:
            logger.debug(f"UDP: Error closing socket: {e}")
        logger.info("UDP: Listener stopped")

    def _listen_loop(self):
        logger.debug("UDP: Listen loop started")
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                self._last_packet_time = time.time()
                # Remember the sender's socket: on a unicast link this is
                # where requests (Reply/Configure) must go back to
                self._last_source_addr = addr
                self._forward_packet(data)
                self._parse_packet(data)
                self._periodic_stats_log()
            except OSError as e:
                if self.running:
                    # Check for Windows ICMP errors that we can safely ignore
                    error_code = getattr(e, 'winerror', None) or getattr(e, 'errno', None)
                    if error_code == 10054:
                        # WSAECONNRESET - "Connection reset by remote host"
                        # This happens on Windows when forwarding to a closed port
                        # v2.1.2: Rate-limit logging (was flooding Brian's log with 1697 entries)
                        self._icmp_reset_count += 1
                        if self._icmp_reset_count == 1:
                            logger.debug("UDP: Windows ICMP connection reset (forward target may be closed) - suppressing repeats")
                        continue  # Don't break - keep listening!
                    else:
                        logger.warning(f"UDP: Socket error in listen loop: {e}")
                        break
            except Exception as e:
                logger.debug(f"UDP: Exception in listen loop: {e}")
    
    def _periodic_stats_log(self):
        """Log periodic stats summary instead of per-packet logging."""
        now = time.time()
        if self._last_stats_log_time is None:
            self._last_stats_log_time = now
        elif now - self._last_stats_log_time >= self._stats_log_interval:
            logger.debug(f"UDP: Stats - {self._decodes_received} decodes, {self._status_received} status updates total"
                         + (f", {self._icmp_reset_count} ICMP resets suppressed" if self._icmp_reset_count else ""))
            self._last_stats_log_time = now

    # ------------------------------------------------------------------ #
    # Click-to-call: outgoing requests to WSJT-X/JTDX (v2.8)
    # ------------------------------------------------------------------ #

    def request_destination(self):
        """Where requests to WSJT-X must be sent, or None if unknowable.

        WSJT-X does NOT listen on its configured UDP server port — it
        transmits from an EPHEMERAL socket and accepts requests only
        there (verified live 2026-08-02: wsjtx.exe held no 2237 socket;
        group-addressed requests landed on the other listeners and were
        ignored). So, multicast or unicast alike, requests go to the
        source address of the packets we received — the same
        reply-to-sender model JTAlert and GridTracker use. Behind a
        forwarder that source is the forwarder, which ignores requests;
        callers should surface that instead of failing silently.
        """
        return self._last_source_addr

    def send_reply(self, decode) -> bool:
        """Type 4 Reply — WSJT-X treats it as a double-click on this
        decode (CQ/QRZ only, by WSJT-X's design). Echo the decode's raw
        fields verbatim; requires 'time_ms' (UDP-sourced decodes only)."""
        dest = self.request_destination()
        if dest is None or 'time_ms' not in decode:
            return False
        packet = wsjtx_protocol.build_reply(
            self._last_client_id, decode['time_ms'], decode['snr'],
            decode.get('raw_dt', decode.get('dt', 0.0)), decode['freq'],
            decode.get('mode', '~'), decode['message'])
        return self._send_request(packet, dest, f"reply to {decode.get('call', '?')}")

    def send_configure(self, dx_call, dx_grid="") -> bool:
        """Type 15 Configure — set DX Call/Grid (any callsign) and
        generate standard messages. Leaves Enable TX to the operator."""
        dest = self.request_destination()
        if dest is None or not dx_call:
            return False
        packet = wsjtx_protocol.build_configure(
            self._last_client_id, dx_call, dx_grid)
        return self._send_request(packet, dest, f"configure DX call {dx_call}")

    def _send_request(self, packet, dest, what) -> bool:
        try:
            self.sock.sendto(packet, dest)
            logger.info(f"UDP: Sent {what} to {dest[0]}:{dest[1]} "
                        f"(id={self._last_client_id})")
            return True
        except OSError as e:
            logger.warning(f"UDP: Could not send {what}: {e}")
            return False

    def _forward_packet(self, data):
        """Forward packet to configured targets, handling errors gracefully.

        The SIO_UDP_CONNRESET ioctl set at init applies to this socket
        for ANY destination: remote hosts' ICMP port-unreachable would
        otherwise raise 10054 here exactly like local closed ports do.
        """
        for target in self.forward_targets:
            label = f"{target[0]}:{target[1]}"
            try:
                self.sock.sendto(data, target)
            except OSError as e:
                # Log each target's error only once to avoid spam
                if target not in self._forward_errors_logged:
                    error_code = getattr(e, 'winerror', None) or getattr(e, 'errno', None)
                    if error_code == 10054:
                        logger.info(f"UDP: Forward to {label} - target not listening (will retry silently)")
                    else:
                        logger.warning(f"UDP: Forward to {label} failed: {e}")
                    self._forward_errors_logged.add(target)
            except Exception as e:
                if target not in self._forward_errors_logged:
                    logger.debug(f"UDP: Forward to {label} failed: {e}")
                    self._forward_errors_logged.add(target)

    def _parse_packet(self, data):
        if len(data) < 12: 
            return
        
        # Count all valid packets for health check
        self.messages_received += 1

        # Check Magic Number
        magic = struct.unpack('>I', data[0:4])[0]
        if magic != 2914763738 and magic != 2914831322: 
            return

        try:
            # Message Type
            msg_type = struct.unpack('>I', data[8:12])[0]

            if msg_type in (1, 2, 5):
                # Data-bearing types only — heartbeats (type 0) don't count
                # as an "active source" for dual-source detection.
                self._last_data_time = time.time()

            if msg_type == 1:  # Status
                self._process_status(data)
            elif msg_type == 2:  # Decode
                self._process_decode(data)
            elif msg_type == 5:  # v2.0.3: QSO Logged
                self._process_qso_logged(data)
        except Exception as e:
            logger.warning(f"UDP: Header parse error: {e}")

    def _read_utf8(self, data, idx):
        """Reads a WSJT-X style UTF-8 string (Length + Bytes)"""
        if idx + 4 > len(data): return "", idx
        length = struct.unpack('>I', data[idx:idx+4])[0]
        idx += 4

        if length == 0xFFFFFFFF: return None, idx # Null string
        if length == 0: return "", idx # Empty string

        if idx + length > len(data): return "", idx

        val = data[idx:idx+length].decode('utf-8', errors='replace')
        return val, idx + length

    def _process_status(self, data):
        # WSJT-X Status Packet Format (Type 1)
        idx = 12
        try:
            # 1. ID (String) — see _process_decode: requests echo this
            client_id, idx = self._read_utf8(data, idx)
            if client_id:
                self._last_client_id = client_id

            # 2. Dial Freq (8 bytes - quint64)
            dial_freq = struct.unpack('>Q', data[idx:idx+8])[0]
            idx += 8

            # 3. Mode (String)
            _, idx = self._read_utf8(data, idx)

            # 4. DX Call (String)
            dx_call, idx = self._read_utf8(data, idx)

            # 5. Report (String)
            _, idx = self._read_utf8(data, idx)

            # 6. Tx Mode (String)
            _, idx = self._read_utf8(data, idx)

            # 7. Tx Enabled (1 byte bool)
            tx_enabled = bool(data[idx]) if idx < len(data) else False
            idx += 1

            # 8. Transmitting (1 byte bool)
            transmitting = bool(data[idx]) if idx < len(data) else False
            idx += 1

            # 9. Decoding (1 byte bool)
            idx += 1

            # 10. Rx DF (4 bytes - quint32)
            idx += 4

            # 11. Tx DF (4 bytes - quint32)
            if idx + 4 <= len(data):
                tx_df = struct.unpack('>I', data[idx:idx+4])[0]
                idx += 4

                self._status_received += 1
                
                # v2.3.0: Parse additional fields for Special Operation Mode
                # Fields 12-18 may not be present in older WSJT-X/JTDX versions
                de_call = ""
                de_grid = ""
                dx_grid = ""  # v2.4.4: DX grid from JTDX (was parsed but discarded)
                special_mode = 0  # 0=None, 5=WW DIGI, 6=Fox, 7=Hound
                
                # Diagnostic: log remaining bytes on first status (helps debug JTDX vs WSJT-X)
                if not self._first_status_logged:
                    remaining = len(data) - idx
                    logger.info(f"UDP: Status msg total={len(data)} bytes, idx after field 11={idx}, remaining={remaining}")
                
                try:
                    # 12. DE call (utf8)
                    de_call, idx = self._read_utf8(data, idx)
                    # 13. DE grid (utf8)
                    de_grid, idx = self._read_utf8(data, idx)
                    # 14. DX grid (utf8)
                    dx_grid, idx = self._read_utf8(data, idx)
                    # 15. Tx Watchdog (bool)
                    idx += 1
                    # 16. Sub-mode (utf8)
                    _, idx = self._read_utf8(data, idx)
                    # 17. Fast mode (bool)
                    idx += 1
                    # 18. Special Operation Mode (quint8)
                    if idx < len(data):
                        special_mode = data[idx]
                        idx += 1
                except (IndexError, struct.error) as e:
                    if not self._first_status_logged:
                        logger.info(f"UDP: Extended field parsing stopped: {e}")
                
                # Log first status with full diagnostic info
                if not self._first_status_logged:
                    logger.info(f"UDP: First status received - freq={dial_freq}, dx_call={dx_call or '(none)'}")
                    logger.info(f"UDP: Extended fields: de_call='{de_call}', de_grid='{de_grid}', special_mode={special_mode}")
                    logger.info("UDP: Status updates flowing (not logged individually)")
                    self._first_status_logged = True
                
                # Emit the update!
                self.status_update.emit({
                    'dial_freq': dial_freq,
                    'dx_call': dx_call,
                    'dx_grid': dx_grid,          # v2.4.4: DX grid (was discarded)
                    'tx_df': tx_df,
                    'tx_enabled': tx_enabled,
                    'transmitting': transmitting,
                    'de_call': de_call,          # v2.3.0: our callsign from JTDX
                    'de_grid': de_grid,          # v2.3.0: our grid from JTDX
                    'special_mode': special_mode, # v2.3.0: 0=None, 6=Fox, 7=Hound
                })
        except Exception as e:
            logger.debug(f"UDP: Status parse error: {e}")

    def _process_decode(self, data):
        idx = 12
        try:
            # 1. ID — kept: outgoing requests (Reply/Configure) must echo
            # the WSJT-X instance id or WSJT-X ignores them
            client_id, idx = self._read_utf8(data, idx)
            if client_id:
                self._last_client_id = client_id
            # 2. New
            idx += 1
            # 3. Time
            ms_midnight = struct.unpack('>I', data[idx:idx+4])[0]
            idx += 4
            hours = ms_midnight // 3600000
            mins = (ms_midnight % 3600000) // 60000
            time_str = f"{hours:02d}{mins:02d}"
            # 4. SNR
            snr = struct.unpack('>i', data[idx:idx+4])[0]
            idx += 4
            # 5. DT
            dt = struct.unpack('>d', data[idx:idx+8])[0]
            idx += 8
            # 6. Freq
            freq = struct.unpack('>I', data[idx:idx+4])[0]
            idx += 4
            # 7. Mode
            mode, idx = self._read_utf8(data, idx)
            # 8. Message
            message, idx = self._read_utf8(data, idx)

            call, grid = parse_decode_message(message)

            self._decodes_received += 1
            
            # Log first decode to confirm data is flowing
            if not self._first_decode_logged:
                logger.info(f"UDP: First decode received - {time_str} {call} {snr}dB {freq}Hz")
                logger.info("UDP: Decodes flowing (not logged individually)")
                self._first_decode_logged = True
            
            self.new_decode.emit({
                'time': time_str, 'snr': snr, 'dt': round(dt, 1),
                'freq': freq, 'mode': mode, 'message': message,
                'call': call, 'grid': grid,
                # Raw fields a Reply (click-to-call) must echo verbatim:
                # display 'time' drops seconds, but WSJT-X matches the
                # decode by exact ms-since-midnight
                'time_ms': ms_midnight, 'raw_dt': dt,
                'received_at': time.time(),
            })
        except Exception as e:
            logger.warning(f"UDP: Decode parse error: {e}")

    def _process_qso_logged(self, data):
        """Process WSJT-X QSO Logged message (Type 5).
        
        v2.0.3: New handler for QSO Logged messages.
        Emits qso_logged signal with callsign and grid of logged station.
        Feature suggested by: Warren KC0GU (Dec 2025)
        
        Note: QDateTime size varies between implementations (12-17 bytes).
        We auto-detect by trying multiple offsets and validating the callsign.
        """
        idx = 12
        try:
            # 1. ID (String)
            id_str, idx = self._read_utf8(data, idx)
            
            # 2. Date/Time Off (QDateTime) - variable size!
            # Try multiple formats, use whichever gives valid callsign
            dx_call = None
            dx_grid = None
            
            for qdatetime_size in [12, 13, 16, 17]:
                test_idx = idx + qdatetime_size
                if test_idx + 4 > len(data):
                    continue
                    
                # Read potential string length
                length = struct.unpack('>I', data[test_idx:test_idx+4])[0]
                
                # Valid callsign length: 3-15 characters
                if 3 <= length <= 15:
                    test_call, next_idx = self._read_utf8(data, test_idx)
                    # Validate it looks like a callsign (alphanumeric with optional / or -)
                    if test_call and len(test_call) >= 3:
                        clean = test_call.replace('/', '').replace('-', '')
                        if clean.isalnum() and any(c.isdigit() for c in clean):
                            # Found valid callsign!
                            dx_call = test_call
                            dx_grid, _ = self._read_utf8(data, next_idx)
                            logger.debug(f"UDP: QSO Logged parsed with QDateTime size {qdatetime_size}")
                            break
            
            # Emit the signal
            if dx_call:
                logger.info(f"UDP: QSO Logged - {dx_call} ({dx_grid})")
                self.qso_logged.emit({
                    'dx_call': dx_call.upper(),
                    'dx_grid': dx_grid or '',
                })
            else:
                logger.warning(f"UDP: QSO Logged - could not parse callsign from {len(data)} byte packet")
                
        except Exception as e:
            logger.warning(f"UDP: QSO Logged parse error: {e}")
    
    def get_diagnostics(self) -> dict:
        """Return diagnostic information about UDP status.
        
        Useful for troubleshooting connection issues.
        """
        return {
            'port': self.port,
            'ip': self.ip,
            'is_multicast': self.is_multicast,
            'running': self.running,
            'messages_received': self.messages_received,
            'decodes_received': self._decodes_received,
            'status_received': self._status_received,
            'last_packet_age': (time.time() - self._last_packet_time) if self._last_packet_time else None,
            'forward_ports': self.forward_ports,
            'forward_errors': list(self._forward_errors_logged),
        }
    
    def has_recent_data(self, window_seconds: float = 60.0) -> bool:
        """Whether a data-bearing packet (status/decode/QSO-logged) arrived
        within the window. Heartbeats don't count: an idle-but-open WSJT-X
        is harmless next to FT8web; one actively feeding decodes is not.
        """
        if self._last_data_time is None:
            return False
        return (time.time() - self._last_data_time) < window_seconds

    def check_data_health(self) -> tuple:
        """v2.1.1: Check if UDP data is flowing. Returns (is_healthy, message).
        
        Called periodically by main window to detect data source failures.
        v2.3.3: Now warns if no data ever received after grace period,
        and gives specific message if multicast bind failed.
        
        Returns:
            (True, "") if data is flowing or still in startup grace period
            (False, "warning message") if data has stopped or never arrived
        """
        if not self.running:
            return (True, "")  # Not started yet, don't warn
        
        # v2.3.3: Specific message if bind/multicast failed
        if not self._bind_ok:
            return (False, "⚠ UDP bind failed — check Settings → Network")
        
        if self._last_packet_time is None:
            # Never received any data
            start = getattr(self, '_start_time', None)
            if start and (time.time() - start) > self._timeout_threshold:
                return (False, "⚠ No UDP data received — check WSJT-X/JTDX is running and UDP settings match")
            # Still in startup grace period
            return (True, "")
        
        age = time.time() - self._last_packet_time
        if age > self._timeout_threshold:
            if not self._timeout_warned:
                self._timeout_warned = True
                logger.warning(f"UDP: No data received for {age:.0f}s")
            return (False, f"⚠ No data from WSJT-X/JTDX for {int(age)}s — is it running?")
        else:
            if self._timeout_warned:
                self._timeout_warned = False
                logger.info("UDP: Data flow resumed")
            return (True, "")
