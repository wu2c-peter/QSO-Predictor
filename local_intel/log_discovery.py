"""
Log File Discovery for QSO Predictor v2.0

Automatically discovers all.txt files from WSJT-X and JTDX installations.
Handles platform differences and JTDX monthly file naming.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict

from .models import LogFileSource

logger = logging.getLogger(__name__)


class LogFileDiscovery:
    """
    Discover and manage all.txt log files from WSJT-X and JTDX.
    
    Handles:
    - Platform-specific default locations (Windows, Linux, macOS)
    - WSJT-X single ALL.TXT file
    - JTDX monthly files (all_jtdx_YYYYMM.txt)
    - Custom user-specified locations
    """
    
    # Default search paths by platform
    SEARCH_PATHS: Dict[str, List[Path]] = {
        'win32': [
            Path(os.environ.get('LOCALAPPDATA', '')) / 'WSJT-X',
            Path(os.environ.get('LOCALAPPDATA', '')) / 'JTDX',
            Path.home() / 'AppData' / 'Local' / 'WSJT-X',
            Path.home() / 'AppData' / 'Local' / 'JTDX',
            Path.home() / 'Documents' / 'WSJT-X',
            Path.home() / 'Documents' / 'JTDX',
        ],
        'linux': [
            Path.home() / '.local' / 'share' / 'WSJT-X',
            Path.home() / '.local' / 'share' / 'JTDX',
            Path.home() / 'WSJT-X',
            Path.home() / 'JTDX',
        ],
        'darwin': [
            Path.home() / 'Library' / 'Application Support' / 'WSJT-X',
            Path.home() / 'Library' / 'Application Support' / 'JTDX',
        ],
    }
    
    # File patterns to search for
    WSJT_PATTERNS = ['ALL.TXT', 'all.txt']
    JTDX_PATTERNS = ['ALL.TXT', 'all.txt']
    JTDX_MONTHLY_PATTERN = 'all_jtdx_*.txt'
    JTDX_DATED_PATTERN = '*_ALL.TXT'  # YYYYMM_ALL.TXT pattern
    
    def __init__(self, custom_paths: List[Path] = None):
        """
        Initialize discovery.
        
        Args:
            custom_paths: Additional paths to search (user-configured)
        """
        self.custom_paths = custom_paths or []
        self._cache: Dict[Path, LogFileSource] = {}
    
    def get_platform_paths(self) -> List[Path]:
        """Get search paths for current platform."""
        platform = sys.platform
        if platform.startswith('linux'):
            platform = 'linux'
        
        paths = self.SEARCH_PATHS.get(platform, [])
        
        # Filter to existing directories
        existing = [p for p in paths if p.exists() and p.is_dir()]
        
        # Add custom paths
        for custom in self.custom_paths:
            if custom.exists() and custom.is_dir() and custom not in existing:
                existing.append(custom)
        
        return existing
    
    def discover_all_files(self, refresh: bool = False) -> List[LogFileSource]:
        """
        Find all log files across both programs.
        
        Args:
            refresh: Force re-scan even if cached
            
        Returns:
            List of discovered log file sources
        """
        if not refresh and self._cache:
            return list(self._cache.values())
        
        sources = []
        seen_paths = set()  # Track resolved paths to detect symlink duplicates
        
        for search_path in self.get_platform_paths():
            logger.debug(f"Searching: {search_path}")
            
            # Determine program from path
            path_str = str(search_path).lower()
            if 'jtdx' in path_str:
                program = 'JTDX'
            elif 'wsjt' in path_str:
                program = 'WSJT-X'
            else:
                program = 'Unknown'
            
            # Check for standard ALL.TXT
            for pattern in self.WSJT_PATTERNS:
                file_path = search_path / pattern
                if file_path.exists():
                    # Resolve symlinks to detect duplicates
                    resolved = file_path.resolve()
                    if resolved not in seen_paths:
                        source = self._analyze_file(file_path, program)
                        if source:
                            sources.append(source)
                            seen_paths.add(resolved)
            
            # Check for JTDX monthly files (all_jtdx_YYYYMM.txt)
            if program == 'JTDX' or 'jtdx' in path_str:
                for file_path in search_path.glob(self.JTDX_MONTHLY_PATTERN):
                    resolved = file_path.resolve()
                    if resolved not in seen_paths:
                        source = self._analyze_file(file_path, 'JTDX')
                        if source:
                            sources.append(source)
                            seen_paths.add(resolved)
            
            # Check for JTDX dated files (YYYYMM_ALL.TXT)
            for file_path in search_path.glob(self.JTDX_DATED_PATTERN):
                # Verify it matches YYYYMM_ALL.TXT format
                name = file_path.name.upper()
                if len(name) >= 12 and name[:6].isdigit() and name.endswith('_ALL.TXT'):
                    resolved = file_path.resolve()
                    if resolved not in seen_paths:
                        source = self._analyze_file(file_path, program)
                        if source:
                            sources.append(source)
                            seen_paths.add(resolved)
        
        # Sort by modification time (newest first)
        sources.sort(key=lambda s: s.modified, reverse=True)
        
        # Update cache
        self._cache = {s.path: s for s in sources}
        
        logger.info(f"Discovered {len(sources)} log files")
        return sources
    
    def _analyze_file(self, path: Path, program: str) -> Optional[LogFileSource]:
        """
        Analyze a single log file.
        
        Args:
            path: Path to the log file
            program: "WSJT-X" or "JTDX"
            
        Returns:
            LogFileSource with file metadata, or None if invalid
        """
        try:
            stat = path.stat()
            
            source = LogFileSource(
                path=path,
                program=program,
                modified=datetime.fromtimestamp(stat.st_mtime),
                size_bytes=stat.st_size,
            )
            
            # Quick line count (approximate for large files)
            if stat.st_size < 10_000_000:  # < 10MB: count exactly
                source.line_count = self._count_lines(path)
            else:
                # Estimate from sample
                source.line_count = self._estimate_line_count(path)
            
            # Try to get date range from first/last lines
            source.date_range = self._get_date_range(path)
            
            logger.debug(f"Analyzed: {path} ({source.line_count} lines)")
            return source
            
        except Exception as e:
            logger.warning(f"Failed to analyze {path}: {e}")
            return None
    
    def _count_lines(self, path: Path) -> int:
        """Count lines in a file."""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
    
    def _estimate_line_count(self, path: Path) -> int:
        """Estimate line count from file size and sample."""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read first 1000 lines to get average line length
                sample_lines = []
                for i, line in enumerate(f):
                    if i >= 1000:
                        break
                    sample_lines.append(len(line))
                
                if not sample_lines:
                    return 0
                
                avg_line_length = sum(sample_lines) / len(sample_lines)
                estimated = int(path.stat().st_size / avg_line_length)
                return estimated
                
        except Exception:
            return 0
    
    def _get_date_range(self, path: Path) -> Optional[tuple]:
        """
        Get date range from first and last entries in file.
        
        Returns:
            Tuple of (start_date, end_date) or None
        """
        try:
            first_date = None
            last_date = None
            
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                # Get first date
                for line in f:
                    date = self._parse_date_from_line(line)
                    if date:
                        first_date = date
                        break
                
                # Seek to end and read backwards for last date
                # (simplified: just read last 100 lines)
                f.seek(0, 2)  # End
                file_size = f.tell()
                
                # Read last ~10KB
                read_size = min(10240, file_size)
                f.seek(max(0, file_size - read_size))
                
                for line in f:
                    date = self._parse_date_from_line(line)
                    if date:
                        last_date = date
            
            if first_date and last_date:
                return (first_date, last_date)
            
        except Exception as e:
            logger.debug(f"Could not get date range from {path}: {e}")
        
        return None
    
    def _parse_date_from_line(self, line: str) -> Optional[datetime]:
        """
        Parse date from an all.txt line.
        
        Format: YYMMDD_HHMMSS or YYYY-MM-DD HH:MM:SS
        Example: 241204_143022 or 2024-12-04 14:30:22
        """
        try:
            # Try WSJT-X format: YYMMDD_HHMMSS
            parts = line.split()
            if len(parts) >= 1:
                date_str = parts[0]
                if '_' in date_str and len(date_str) == 13:
                    return datetime.strptime(date_str, '%y%m%d_%H%M%S')
                
                # Try JTDX format: YYYY-MM-DD HH:MM:SS
                if '-' in date_str and len(parts) >= 2:
                    full_date = f"{parts[0]} {parts[1]}"
                    return datetime.strptime(full_date[:19], '%Y-%m-%d %H:%M:%S')
        except (ValueError, IndexError):
            pass
        
        return None
    
    def add_custom_path(self, path: Path) -> bool:
        """
        Add a custom search path.
        
        Args:
            path: Directory or file path to add
            
        Returns:
            True if path was added successfully
        """
        if path.is_file():
            # Direct file reference
            program = 'JTDX' if 'jtdx' in path.name.lower() else 'WSJT-X'
            source = self._analyze_file(path, program)
            if source:
                self._cache[path] = source
                return True
        elif path.is_dir():
            # Directory to search
            if path not in self.custom_paths:
                self.custom_paths.append(path)
                # Re-discover
                self.discover_all_files(refresh=True)
                return True
        
        return False
    
    def get_total_stats(self) -> Dict:
        """Get summary statistics across all discovered files."""
        sources = self.discover_all_files()
        
        total_lines = sum(s.line_count for s in sources)
        total_size = sum(s.size_bytes for s in sources)
        
        # Get overall date range
        all_ranges = [s.date_range for s in sources if s.date_range]
        if all_ranges:
            earliest = min(r[0] for r in all_ranges)
            latest = max(r[1] for r in all_ranges)
            date_range = (earliest, latest)
        else:
            date_range = None
        
        return {
            'file_count': len(sources),
            'total_lines': total_lines,
            'total_size_mb': total_size / (1024 * 1024),
            'date_range': date_range,
            'programs': list(set(s.program for s in sources)),
        }


def discover_log_files(custom_paths: List[Path] = None) -> List[LogFileSource]:
    """
    Convenience function to discover log files.
    
    Args:
        custom_paths: Additional paths to search
        
    Returns:
        List of discovered log file sources
    """
    discovery = LogFileDiscovery(custom_paths)
    return discovery.discover_all_files()
