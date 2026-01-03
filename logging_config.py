"""
Logging Configuration for QSO Predictor

Provides centralized logging setup with:
- File logging with rotation (5MB max, 3 backups)
- Console logging for development
- Menu-toggleable debug mode
- Platform-appropriate log file locations

Copyright (C) 2025 Peter Hirst (WU2C)

Usage:
    # At application startup (in main_v2.py):
    from logging_config import setup_logging, get_log_file_path, set_debug_mode
    
    setup_logging()  # Call once at startup
    
    # To toggle debug mode from menu:
    set_debug_mode(True)   # Enable verbose logging
    set_debug_mode(False)  # Back to normal
    
    # In any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("Something happened")
    logger.debug("Verbose detail")  # Only shown when debug mode enabled
"""

import logging
import logging.handlers
import sys
import platform
from pathlib import Path
from typing import Optional

# Module-level state
_debug_mode = False
_log_file_path: Optional[Path] = None
_file_handler: Optional[logging.Handler] = None
_console_handler: Optional[logging.Handler] = None

# Log format - includes timestamp, level, module name, and message
LOG_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s'
LOG_FORMAT_DEBUG = '%(asctime)s | %(levelname)-8s | %(name)-25s | %(funcName)s:%(lineno)d | %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Rotation settings
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3  # Keep 3 old log files


def get_log_directory() -> Path:
    """
    Get the platform-appropriate directory for log files.
    
    Returns:
        Path to the logs directory (created if needed)
    """
    system = platform.system()
    
    if system == 'Windows':
        # %APPDATA%\QSO Predictor\logs
        base = Path.home() / 'AppData' / 'Roaming' / 'QSO Predictor'
    elif system == 'Darwin':  # macOS
        # ~/Library/Application Support/QSO Predictor/logs
        base = Path.home() / 'Library' / 'Application Support' / 'QSO Predictor'
    else:  # Linux and others
        # ~/.config/QSO Predictor/logs
        base = Path.home() / '.config' / 'QSO Predictor'
    
    log_dir = base / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    return log_dir


def get_log_file_path() -> Path:
    """
    Get the path to the current log file.
    
    Returns:
        Path to qso_predictor.log
    """
    global _log_file_path
    if _log_file_path is None:
        _log_file_path = get_log_directory() / 'qso_predictor.log'
    return _log_file_path


def setup_logging(console: bool = True, file: bool = True) -> None:
    """
    Initialize the logging system.
    
    Call this once at application startup.
    
    Args:
        console: If True, also log to console/terminal (useful for development)
        file: If True, log to rotating file
    """
    global _file_handler, _console_handler
    
    # Get root logger for our application
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all; handlers filter
    
    # Remove any existing handlers (in case of re-init)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    debug_formatter = logging.Formatter(LOG_FORMAT_DEBUG, datefmt=DATE_FORMAT)
    
    # File handler with rotation
    if file:
        log_file = get_log_file_path()
        _file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding='utf-8'
        )
        _file_handler.setLevel(logging.INFO)  # Default to INFO level
        _file_handler.setFormatter(formatter)
        root_logger.addHandler(_file_handler)
    
    # Console handler (for terminal/development)
    if console:
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setLevel(logging.INFO)  # Default to INFO level
        _console_handler.setFormatter(formatter)
        root_logger.addHandler(_console_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger('paho.mqtt').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('PyQt6').setLevel(logging.WARNING)
    
    # Log startup
    logger = logging.getLogger('logging_config')
    logger.info("="*60)
    logger.info("QSO Predictor logging initialized")
    logger.info(f"Log file: {get_log_file_path()}")
    logger.info(f"Platform: {platform.system()} {platform.release()}")
    logger.info("="*60)


def set_debug_mode(enabled: bool) -> None:
    """
    Enable or disable debug logging level.
    
    When enabled, DEBUG level messages are written to log.
    When disabled, only INFO and above are logged.
    
    Args:
        enabled: True to enable debug mode, False to disable
    """
    global _debug_mode, _file_handler, _console_handler
    
    _debug_mode = enabled
    level = logging.DEBUG if enabled else logging.INFO
    
    # Update formatter for more detail in debug mode
    if enabled:
        formatter = logging.Formatter(LOG_FORMAT_DEBUG, datefmt=DATE_FORMAT)
    else:
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    
    if _file_handler:
        _file_handler.setLevel(level)
        _file_handler.setFormatter(formatter)
    
    if _console_handler:
        _console_handler.setLevel(level)
        _console_handler.setFormatter(formatter)
    
    logger = logging.getLogger('logging_config')
    if enabled:
        logger.info("Debug logging ENABLED - verbose output active")
    else:
        logger.info("Debug logging DISABLED - normal output")


def is_debug_mode() -> bool:
    """
    Check if debug mode is currently enabled.
    
    Returns:
        True if debug logging is enabled
    """
    return _debug_mode


def open_log_folder() -> None:
    """
    Open the log folder in the system file browser.
    
    Useful for a menu action to help users find their logs.
    """
    import subprocess
    
    log_dir = get_log_directory()
    system = platform.system()
    
    try:
        if system == 'Windows':
            subprocess.run(['explorer', str(log_dir)], check=False)
        elif system == 'Darwin':  # macOS
            subprocess.run(['open', str(log_dir)], check=False)
        else:  # Linux
            subprocess.run(['xdg-open', str(log_dir)], check=False)
    except Exception as e:
        logger = logging.getLogger('logging_config')
        logger.error(f"Failed to open log folder: {e}")
