"""
UDP port probes: which ham-range ports are occupied, and by whom.

Lifted unchanged from `setup_wizard.py` (v2.2.0) in migration step 2 of
dev-docs/DIAGNOSTICS_SPEC.md. Uses platform-native tools (netstat / lsof
/ ss) via subprocess rather than psutil to avoid a dependency; per-OS
branches run at call time, so the module imports safely everywhere.

QSO Predictor
Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging
import re
import socket
import subprocess
import sys
from typing import List

from diagnostics.models import PortInfo

logger = logging.getLogger(__name__)


class PortScanner:
    """
    Detect UDP port usage to identify conflicts.

    Uses platform-native tools (netstat/ss) rather than psutil
    to avoid adding a dependency. Falls back gracefully.
    """

    # Common ham radio UDP ports
    HAM_PORT_RANGE = range(2230, 2260)

    @staticmethod
    def scan_udp_ports() -> List[PortInfo]:
        """
        Find processes listening on UDP ports in the ham radio range.
        Returns list of PortInfo for occupied ports.
        """
        occupied = []

        try:
            if sys.platform == 'win32':
                occupied = PortScanner._scan_windows()
            elif sys.platform == 'darwin':
                occupied = PortScanner._scan_macos()
            else:
                occupied = PortScanner._scan_linux()
        except Exception as e:
            logger.debug(f"Setup: Port scan failed: {e}")

        # Also do a quick socket probe for common ports
        for port in [2237, 2238, 2239, 2240]:
            if not any(p.port == port for p in occupied):
                if PortScanner._is_port_in_use(port):
                    occupied.append(PortInfo(port=port, ip='0.0.0.0',
                                            process_name='unknown'))

        if occupied:
            logger.info(f"Setup: Ports in use: "
                       f"{', '.join(f'{p.port} ({p.process_name})' for p in occupied)}")

        return occupied

    @staticmethod
    def _scan_windows() -> List[PortInfo]:
        """Parse netstat -ano on Windows for UDP listeners."""
        result = []
        try:
            output = subprocess.check_output(
                ['netstat', '-ano', '-p', 'UDP'],
                text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            for line in output.splitlines():
                # UDP    0.0.0.0:2237    *:*    12345
                parts = line.split()
                if len(parts) >= 4 and parts[0] == 'UDP':
                    addr = parts[1]
                    if ':' in addr:
                        ip, port_str = addr.rsplit(':', 1)
                        try:
                            port = int(port_str)
                            if port in PortScanner.HAM_PORT_RANGE:
                                pid = int(parts[-1]) if parts[-1].isdigit() else 0
                                proc_name = PortScanner._get_process_name_win(pid)
                                result.append(PortInfo(
                                    port=port, ip=ip,
                                    process_name=proc_name, pid=pid
                                ))
                        except ValueError:
                            pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return result

    @staticmethod
    def _get_process_name_win(pid: int) -> str:
        """Get process name from PID on Windows."""
        if pid == 0:
            return 'unknown'
        try:
            output = subprocess.check_output(
                ['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'],
                text=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            for line in output.strip().splitlines():
                parts = line.strip('"').split('","')
                if len(parts) >= 2:
                    return parts[0]
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return f'PID {pid}'

    @staticmethod
    def _scan_macos() -> List[PortInfo]:
        """Parse lsof on macOS for UDP listeners."""
        result = []
        try:
            output = subprocess.check_output(
                ['lsof', '-iUDP', '-nP'],
                text=True, timeout=5
            )
            for line in output.splitlines()[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 9:
                    name_field = parts[8] if len(parts) > 8 else parts[-1]
                    if ':' in name_field:
                        port_str = name_field.rsplit(':', 1)[-1]
                        try:
                            port = int(port_str)
                            if port in PortScanner.HAM_PORT_RANGE:
                                result.append(PortInfo(
                                    port=port, ip='0.0.0.0',
                                    process_name=parts[0],
                                    pid=int(parts[1]) if parts[1].isdigit() else 0
                                ))
                        except ValueError:
                            pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return result

    @staticmethod
    def _scan_linux() -> List[PortInfo]:
        """Parse ss on Linux for UDP listeners."""
        result = []
        try:
            output = subprocess.check_output(
                ['ss', '-ulnp'],
                text=True, timeout=5
            )
            for line in output.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 5:
                    addr = parts[4]
                    if ':' in addr:
                        port_str = addr.rsplit(':', 1)[-1]
                        try:
                            port = int(port_str)
                            if port in PortScanner.HAM_PORT_RANGE:
                                # Extract process name from users: field
                                proc = 'unknown'
                                for p in parts:
                                    if 'users:' in p:
                                        match = re.search(r'"([^"]+)"', p)
                                        if match:
                                            proc = match.group(1)
                                result.append(PortInfo(
                                    port=port, ip=addr.rsplit(':', 1)[0],
                                    process_name=proc
                                ))
                        except ValueError:
                            pass
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return result

    @staticmethod
    def _is_port_in_use(port: int) -> bool:
        """Quick check if a UDP port is in use by trying to bind it."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            return False  # We bound it, so it was free
        except OSError:
            return True   # Already in use
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass

    @staticmethod
    def find_free_port(start: int = 2237, count: int = 20) -> int:
        """Find the first available UDP port starting from 'start'."""
        for port in range(start, start + count):
            if not PortScanner._is_port_in_use(port):
                return port
        return start  # Fallback
