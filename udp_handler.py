# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import socket
import struct
import threading
from PyQt6.QtCore import QObject, pyqtSignal

class UDPHandler(QObject):
    new_decode = pyqtSignal(dict)
    status_update = pyqtSignal(dict)

    def __init__(self, config):
        super().__init__()
        self.port = int(config.get('NETWORK', 'udp_port'))
        # Support multicast address configuration
        self.ip = config.get('NETWORK', 'udp_ip', fallback='0.0.0.0')
        self.forward_ports = config.get_forward_ports()
        self.running = False
        self.is_multicast = self._is_multicast_address(self.ip)

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            if self.is_multicast:
                # Multicast setup
                # Bind to INADDR_ANY on the port
                self.sock.bind(('', self.port))
                # Join the multicast group
                mreq = struct.pack("4sl", socket.inet_aton(self.ip), socket.INADDR_ANY)
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                print(f"UDP Multicast joined {self.ip}:{self.port}")
            else:
                # Standard unicast
                self.sock.bind(('0.0.0.0', self.port))
                print(f"UDP Bound to {self.port}")
        except Exception as e:
            print(f"UDP Bind Error: {e}")
    
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
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            if self.is_multicast:
                # Leave multicast group
                mreq = struct.pack("4sl", socket.inet_aton(self.ip), socket.INADDR_ANY)
                self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, mreq)
        except:
            pass
        try: 
            self.sock.close()
        except: 
            pass

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                self._forward_packet(data)
                self._parse_packet(data)
            except OSError: break
            except Exception: pass

    def _forward_packet(self, data):
        for port in self.forward_ports:
            try: self.sock.sendto(data, ('127.0.0.1', port))
            except: pass

    def _parse_packet(self, data):
        if len(data) < 12: return

        # Check Magic Number
        magic = struct.unpack('>I', data[0:4])[0]
        if magic != 2914763738 and magic != 2914831322: return

        try:
            # Message Type
            msg_type = struct.unpack('>I', data[8:12])[0]

            if msg_type == 1: # Status
                self._process_status(data)
            elif msg_type == 2: # Decode
                self._process_decode(data)
        except Exception as e:
            print(f"Header Error: {e}")

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
            # 1. ID (String)
            _, idx = self._read_utf8(data, idx)

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

                # Emit the update!
                self.status_update.emit({
                    'dial_freq': dial_freq,
                    'dx_call': dx_call,
                    'tx_df': tx_df,
                    'tx_enabled': tx_enabled,
                    'transmitting': transmitting,
                })
        except Exception:
            # Silently fail on bad packet, but don't crash thread
            pass

    def _process_decode(self, data):
        idx = 12
        try:
            # 1. ID
            _, idx = self._read_utf8(data, idx)
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

            # --- Parsing Logic ---
            parts = message.strip().split()
            grid = ""
            call = ""

            def is_suffix(s):
                s = s.upper()
                if s in ['73', 'RR73', 'RRR']: return True
                if s.startswith(('+', '-', 'R+', 'R-')) and len(s) > 1: return True
                return False

            def is_grid(s):
                if len(s) != 4: return False
                return s[0].isalpha() and s[1].isalpha() and s[2].isdigit() and s[3].isdigit()

            if len(parts) >= 3:
                last = parts[-1]
                if is_grid(last):
                    grid = last
                    call = parts[-2]
                elif is_suffix(last):
                    call = parts[-2]
                else:
                    call = last

            elif len(parts) == 2:
                call = parts[1]

            call = call.strip('<>')
            # ---------------------

            self.new_decode.emit({
                'time': time_str, 'snr': snr, 'dt': round(dt, 1),
                'freq': freq, 'mode': mode, 'message': message,
                'call': call, 'grid': grid
            })
        except Exception as e:
            print(f"Decode Error: {e}")
