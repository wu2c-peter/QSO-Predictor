# QSO Predictor v2.1.4
# Copyright (C) 2025 Peter Hirst (WU2C)
#
# v2.1.4 Changes:
# - Fixed: JTDX detection in auto-paste scripts (title bar contains "WSJT-X")
# - Fixed: Band map frequency scale too dim on Windows (brightened labels and ticks)
# - Added: Auto-paste scripts click Enable TX after pasting callsign
# - Added: Separate JTDX/WSJT-X coordinates in auto-paste scripts
#
# v2.1.3 Changes:
# - Added: Click-to-copy target callsign (click target in either panel)
# - Added: Local decode evidence for path detection (works without PSK Reporter)
# - Changed: Path status labels clarified (Heard by Target, Reported in Region, etc.)
# - Changed: "Sync to JTDX" renamed to "Fetch Target" (clearer direction)
# - Changed: Combined AutoHotkey/Hammerspoon scripts support frequency + callsign
# - Fixed: AP decode codes (a1-a7) stripped from Call column
#
# v2.1.1 Changes:
# - Added: Band map hover tooltips showing callsign, SNR, tier, grid (Brian's request)
# - Added: Frequency scale with Hz labels on band map (Brian's request)
# - Added: Resilient data source monitoring - status bar warns if UDP/MQTT data stops
# - Added: Diagnostic logging in analyzer for debugging empty Target Perspective
# - Fixed: Silent exception handler in analyzer.handle_live_spot now logs errors
#
# v2.1.0 Changes:
# - Added: Target View as undockable panel (Dashboard + Band Map)
# - Added: Insights as undockable panel (right side, full height)
# - Added: View menu with panel toggles and Reset Layout option
# - Added: Hunt Mode - track stations/prefixes/countries, alert when active (suggested by Warren KC0GU)
#   - Hunt List dialog (Tools → Hunt List, Ctrl+H)
#   - Right-click context menu to add/remove from hunt list
#   - Gold highlighting for hunted stations in decode table
#   - System tray alerts when hunted station active
#   - "Heard nearby" alerts when hunted station's signal reaches your region
#   - Country/DXCC support with autocomplete (type "Japan" to hunt all JA stations)
# - Added: Click-to-clipboard - click band map or Rec frequency to copy to clipboard
# - Added: Auto-clear on QSY - clear target when changing bands (Brian's request)
# - Fixed: Right dock (Local Intel) no longer pushes down band map (setCorner fix)
# - Changed: Decode table uses less vertical space by default
#
# v2.0.8 Changes:
# - Added: Background scanner for incremental log file processing
# - Added: Behavior distribution display (L/M/R bar) in Insights panel
# - Added: get_behavior_distribution() method for historical data
# - Added: Bayesian update_observations() for incremental count updates
# - Fixed: Bootstrap timeout with large log files (background processing)
# - Fixed: JTDX dated file trailing markers (^ * . d)
#
# v2.0.7 Changes:
# - Fixed: UI freeze when clicking stations with large ALL.TXT files
#   (removed blocking log scan, now cache-only lookup)
# - Fixed: Rapid table refresh from UDP status flooding (throttled to 2Hz)
# - Fixed: Yellow TX line flickering on band map
# - Fixed: Table re-sorting jitter during decode updates
#   (reported by Doug McDonald)
#
# v2.0.9 Changes:
# - Added: Startup health check dialog when no UDP data detected
#   (based on user feedback from Doug McDonald)
#
# v2.0.6 Changes:
# - Fixed: Severe CPU usage on macOS (band map optimization)
# - Fixed: Splitter position persistence (suggested by KC0GU)
# - Fixed: VERSION file not bundled in macOS build
# - Added: Sync to WSJT-X/JTDX button and Ctrl+Y shortcut (suggested by KC0GU)
#          (renamed to "Fetch Target" in v2.1.3 for clarity)
# - Added: Dock widget (Insights panel) position persistence
#
# v2.0.4 Changes:
# - Fixed: Cache cleanup thread death (analyzer.py)
# - Fixed: MQTT auto-reconnect (mqtt_client.py)
# - Fixed: Status bar shows unique stations instead of total spots
# - Added: Solar data refresh timer (every 15 minutes)
#
# v2.0.3 Changes:
# - Added: Column width persistence (suggested by KC0GU)
# - Added: Clear Target button and Ctrl+R shortcut (suggested by KC0GU)
# - Added: QSO Logged message handling for auto-clear (suggested by KC0GU)
# - Added: Auto-clear on QSO logged setting
# - Fixed: Ctrl+R shortcut (was documented but not implemented)

import ctypes
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from collections import deque

# Initialize logging FIRST before other imports
from logging_config import setup_logging, set_debug_mode, get_log_file_path, open_log_folder
setup_logging(console=True, file=True)

logger = logging.getLogger(__name__)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QTableView, QLabel, QHeaderView, QDockWidget,
                             QMessageBox, QProgressBar, QAbstractItemView, QFrame, QSizePolicy, 
                             QSystemTrayIcon, QMenu, QToolBar, QPushButton, QCheckBox,
                             QStyledItemDelegate, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QAbstractTableModel, QModelIndex, QByteArray
from PyQt6.QtGui import QColor, QAction, QKeySequence, QFont, QIcon, QCursor, QBrush

# v2.1.0: Hunt Mode imports
try:
    from hunt_manager import HuntManager
    from hunt_dialog import HuntListDialog
    HUNT_MODE_AVAILABLE = True
except ImportError as e:
    HUNT_MODE_AVAILABLE = False
    logger.warning(f"Hunt Mode not available: {e}")


def get_version():
    """Get version from git tag or VERSION file."""
    # Determine base path (handles PyInstaller frozen exe)
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        base_path = Path(sys._MEIPASS)
    else:
        # Running as script
        base_path = Path(__file__).parent
    
    # Try git first (works for developers running from repo)
    if not getattr(sys, 'frozen', False):
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                capture_output=True, text=True, cwd=base_path
            )
            if result.returncode == 0:
                return result.stdout.strip().lstrip('v')
        except:
            pass
    
    # Fall back to VERSION file (works for zip downloads and frozen exe)
    try:
        return (base_path / "VERSION").read_text().strip()
    except:
        return "dev"


def compare_versions(current, latest):
    """Compare version strings. Returns True if latest > current."""
    try:
        # Handle versions like "1.2.3" or "1.2.3-5-gabcdef"
        def parse(v):
            # Take only the numeric part before any dash
            v = v.split('-')[0]
            return [int(x) for x in v.split('.')]
        
        curr_parts = parse(current)
        latest_parts = parse(latest)
        
        # Pad shorter list with zeros
        max_len = max(len(curr_parts), len(latest_parts))
        curr_parts += [0] * (max_len - len(curr_parts))
        latest_parts += [0] * (max_len - len(latest_parts))
        
        return latest_parts > curr_parts
    except:
        # If parsing fails, do simple string comparison
        return latest != current and latest > current


try:
    from config_manager import ConfigManager
    from udp_handler import UDPHandler
    from analyzer import QSOAnalyzer
    from band_map_widget import BandMapWidget
    from settings_dialog import SettingsDialog
except ImportError as e:
    app = QApplication(sys.argv)
    QMessageBox.critical(None, "Missing Files", f"Error: {e}")
    sys.exit(1)

# v2.0.9: Import startup health dialog
try:
    from startup_health_dialog import StartupHealthDialog
    STARTUP_HEALTH_AVAILABLE = True
except ImportError:
    STARTUP_HEALTH_AVAILABLE = False

try:
    from solar_client import SolarClient
    SOLAR_AVAILABLE = True
except ImportError:
    SOLAR_AVAILABLE = False

# --- LOCAL INTELLIGENCE v2.0 ---
try:
    from local_intel_integration import LocalIntelligence
    from local_intel import PathStatus
    LOCAL_INTEL_AVAILABLE = True
except ImportError as e:
    LOCAL_INTEL_AVAILABLE = False
    logger.warning(f"Local Intelligence not available: {e}")


# --- WIDGET: TARGET DASHBOARD ---
class TargetDashboard(QFrame):
    # v2.0.6: Signal when user wants to sync target to JTDX
    sync_requested = pyqtSignal()
    # v2.1.0: Signal for status bar messages (e.g., clipboard feedback)
    status_message = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._activity_state = 'unknown'    # v2.3.5: Track for competition override
        self._raw_competition = ''           # v2.3.5: Real competition before override
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(120) 
        self.setStyleSheet("""
            QFrame { 
                background-color: #003333; 
                border-top: 2px solid #00AAAA; 
                border-bottom: 1px solid #000;
            }
            QLabel { color: #DDD; font-size: 11pt; border: none; padding: 0 5px; }
            QLabel#header { color: #888; font-size: 8pt; font-weight: bold; }
            QLabel#data { font-weight: bold; color: #FFF; }
            QLabel#target { color: #FF00FF; font-size: 16pt; font-weight: bold; padding-right: 5px; }
            QPushButton#target {
                color: #FF00FF;
                font-size: 16pt;
                font-weight: bold;
                padding-right: 5px;
                background: transparent;
                border: none;
                text-align: left;
            }
            QPushButton#target:hover {
                color: #FF66FF;
            }
            QLabel#rec { 
                font-family: Consolas, monospace; 
                font-weight: bold; 
                border: 1px solid #444; 
                border-radius: 4px; 
                padding: 4px; 
                background-color: #001100; 
            }
            QPushButton#sync {
                background-color: #444;
                color: #DDD;
                border: 1px solid #555;
                border-radius: 3px;
                font-size: 14px;
                font-weight: bold;
                padding: 2px;
            }
            QPushButton#sync:hover {
                background-color: #555;
            }
            QPushButton#sync:pressed {
                background-color: #333;
            }
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(10)
        
        # v2.1.3: Target label is clickable — copies callsign to clipboard
        self.lbl_target = QPushButton("NO TARGET")
        self.lbl_target.setObjectName("target")
        self.lbl_target.setFlat(True)
        self.lbl_target.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_target.setToolTip("Click to copy callsign to clipboard.\nWith auto-paste script: sends to DX Call field in WSJT-X/JTDX")
        self.lbl_target.clicked.connect(self._copy_target_to_clipboard)
        layout.addWidget(self.lbl_target)
        
        # v2.0.6: Fetch button — pulls target from WSJT-X/JTDX
        self.btn_sync = QPushButton("⟳")
        self.btn_sync.setObjectName("sync")
        self.btn_sync.setToolTip("Fetch target from WSJT-X/JTDX (Ctrl+Y)")
        self.btn_sync.setFixedSize(28, 28)
        self.btn_sync.clicked.connect(self.sync_requested.emit)
        layout.addWidget(self.btn_sync)
        
        def add_field(label_text, width=None, stretch=False, tooltip=None):
            container = QWidget()
            vbox = QVBoxLayout(container)
            vbox.setContentsMargins(0,0,0,0)
            vbox.setSpacing(0)
            lbl_title = QLabel(label_text)
            lbl_title.setObjectName("header")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if tooltip:
                lbl_title.setToolTip(tooltip)
            lbl_val = QLabel("--")
            lbl_val.setObjectName("data")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(lbl_title)
            vbox.addWidget(lbl_val)
            if width: container.setFixedWidth(width)
            layout.addWidget(container)
            if stretch: layout.setStretchFactor(container, 1)
            return lbl_val

        self.val_utc = add_field("UTC", 50, tooltip="Last decode time of target at your receiver")
        self.val_snr = add_field("dB", 40, tooltip="How strong target's signal is at YOUR receiver")
        self.val_dt = add_field("DT", 40, tooltip="Target's time offset (seconds)")
        self.val_freq = add_field("Freq", 50, tooltip="Target's transmit audio frequency offset (Hz)")
        self.val_msg = add_field("Last Msg", stretch=True, tooltip="Last decoded message from/to this target.\nMay be several cycles old — check UTC timestamp.") 
        self.val_msg.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.val_grid = add_field("Grid", 60, tooltip="Target's Maidenhead grid locator")
        self.val_prob = add_field("Score", 70, tooltip="Opportunity score for this target.\nCombines signal strength + path status - competition.\nHigher = better prospect. Not a statistical probability.")
        
        # Stacked Path / Competition field
        path_comp_container = QWidget()
        path_comp_vbox = QVBoxLayout(path_comp_container)
        path_comp_vbox.setContentsMargins(0,0,0,0)
        path_comp_vbox.setSpacing(2)
        
        # Path row
        path_row = QWidget()
        path_hbox = QHBoxLayout(path_row)
        path_hbox.setContentsMargins(0,0,0,0)
        path_hbox.setSpacing(4)
        lbl_path_title = QLabel("Path")
        lbl_path_title.setObjectName("header")
        lbl_path_title.setFixedWidth(70)
        lbl_path_title.setToolTip("Has your signal been detected near this station?\nSources: PSK Reporter spots + local decode analysis")
        self.val_path = QLabel("--")
        self.val_path.setObjectName("data")
        path_hbox.addWidget(lbl_path_title)
        path_hbox.addWidget(self.val_path)
        path_comp_vbox.addWidget(path_row)
        
        # Competition row
        comp_row = QWidget()
        comp_hbox = QHBoxLayout(comp_row)
        comp_hbox.setContentsMargins(0,0,0,0)
        comp_hbox.setSpacing(4)
        lbl_comp_title = QLabel("Competition")
        lbl_comp_title.setObjectName("header")
        lbl_comp_title.setFixedWidth(75)
        lbl_comp_title.setToolTip("Signal density near target FROM THEIR PERSPECTIVE.\nSource: PSK Reporter. You may not hear these stations.")
        self.val_comp = QLabel("--")
        self.val_comp.setObjectName("data")
        comp_hbox.addWidget(lbl_comp_title)
        comp_hbox.addWidget(self.val_comp)
        path_comp_vbox.addWidget(comp_row)
        
        # v2.3.0: Target Activity Status row
        status_row = QWidget()
        status_hbox = QHBoxLayout(status_row)
        status_hbox.setContentsMargins(0,0,0,0)
        status_hbox.setSpacing(4)
        lbl_status_title = QLabel("Status")
        lbl_status_title.setObjectName("header")
        lbl_status_title.setFixedWidth(75)
        lbl_status_title.setToolTip("What the target station is doing right now.\nSource: Local decodes (real-time)")
        self.val_activity = QLabel("--")
        self.val_activity.setObjectName("data")
        status_hbox.addWidget(lbl_status_title)
        status_hbox.addWidget(self.val_activity)
        path_comp_vbox.addWidget(status_row)
        
        path_comp_container.setFixedWidth(270)  # v2.2.0: wider to fit "Not Reported in Region"
        layout.addWidget(path_comp_container)

        layout.addSpacing(10)
        # v2.1.0: Use ClickableCopyLabel so user can click to copy frequency
        self.lbl_rec = ClickableCopyLabel()
        self.lbl_rec.setObjectName("rec")
        self.lbl_rec.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_rec.setToolTip("Recommended TX frequency based on target perspective analysis.\nClick to copy. Rec = recommended, Cur = your current TX frequency.\nWith auto-paste script: sends to TX frequency field in WSJT-X/JTDX")
        self.lbl_rec.copied.connect(self.status_message.emit)  # Bubble up to main window
        self.update_rec("----", "----") 
        layout.addWidget(self.lbl_rec)

    def _copy_target_to_clipboard(self):
        """Copy current target callsign to clipboard."""
        text = self.lbl_target.text()
        if text and text != "NO TARGET":
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            # Brief visual feedback
            original_text = text
            self.lbl_target.setText(f"✓ Copied!")
            self.status_message.emit(f"Copied to clipboard: {text}")
            # Restore after 1 second
            QTimer.singleShot(1000, lambda: self.lbl_target.setText(original_text))

    def update_data(self, data):
        if not data:
            self.lbl_target.setText("NO TARGET")
            self.val_utc.setText("--")
            self.val_snr.setText("--")
            self.val_dt.setText("--")
            self.val_freq.setText("--")
            self.val_msg.setText("")
            self.val_grid.setText("--")
            self.val_prob.setText("--")
            self.val_path.setText("--")
            self.val_path.setStyleSheet("")
            self.val_comp.setText("--")
            self.val_comp.setStyleSheet("")
            self.val_activity.setText("--")
            self.val_activity.setStyleSheet("")
            self._raw_competition = ''       # v2.3.5: Reset cached state
            self._activity_state = 'unknown'
            return

        self.lbl_target.setText(data.get('call', '???'))
        self.val_utc.setText(str(data.get('time', '')))
        
        snr = str(data.get('snr', '--'))
        self.val_snr.setText(snr)
        try:
            val = int(snr)
            col = "#00FF00" if val >= 0 else ("#FFFF00" if val >= -10 else "#FF5555")
            self.val_snr.setStyleSheet(f"color: {col}; font-weight: bold;")
        except: self.val_snr.setStyleSheet("")

        self.val_dt.setText(str(data.get('dt', '')))
        self.val_freq.setText(str(data.get('freq', '')))
        self.val_msg.setText(str(data.get('message', '')))
        self.val_grid.setText(str(data.get('grid', '')))
        
        prob = str(data.get('prob', '--'))
        self.val_prob.setText(prob)
        try:
            val = int(prob)
            col = "#00FF00" if val > 75 else ("#FF5555" if val < 30 else "#DDDDDD")
            self.val_prob.setStyleSheet(f"color: {col}; font-weight: bold;")
        except: self.val_prob.setStyleSheet("")
        
        # Path status
        path = str(data.get('path', '--'))
        my_snr = data.get('my_snr_at_target', None)
        # v2.3.0: Append SNR to path display when available
        path_display = path
        if my_snr is not None and path in ("Heard by Target", "Reported in Region"):
            snr_str = f"{my_snr:+d}" if isinstance(my_snr, int) else str(my_snr)
            # Shorten labels to fit with SNR ("Rprtd" not "Rptd" — latter implies "Repeated")
            short = "Heard by Target" if path == "Heard by Target" else "Rprtd in Region"
            path_display = f"{short} ({snr_str} dB)"
        self.val_path.setText(path_display)
        if "Heard by Target" in path:
            self.val_path.setStyleSheet("color: #00FFFF; font-weight: bold;")  # Cyan
        elif "Not Reported in Region" in path:
            # MUST check "Not Reported" BEFORE "Reported" — substring match issue
            self.val_path.setStyleSheet("color: #FFA500; font-weight: bold;")  # Orange
        elif "Reported in Region" in path:
            self.val_path.setStyleSheet("color: #00FF00; font-weight: bold;")  # Green
        elif "Not Transmitting" in path:
            self.val_path.setStyleSheet("color: #888888; font-weight: bold;")  # Gray
        elif "No Reporters" in path:
            self.val_path.setStyleSheet("color: #666666; font-weight: bold;")  # Dark gray
        else:
            self.val_path.setStyleSheet("color: #DDDDDD;")
        
        comp = str(data.get('competition', ''))
        self._raw_competition = comp  # v2.3.5: Cache real value for override logic
        self._refresh_competition_display()

    def update_rec(self, rec_freq, cur_freq):
        if str(rec_freq) == str(cur_freq) and str(rec_freq) != "----":
            cur_color = "#00FF00"  # Green
        elif str(rec_freq) == "----":
            cur_color = "#BBBBBB"  # Grey
        else:
            cur_color = "#FF5555"  # Red
            
        html_text = f"""
        <html>
        <head><style>td {{ padding-right: 12px; }}</style></head>
        <body>
            <table cellspacing="0" cellpadding="0">
                <tr><td style="color: #BBBBBB;">Rec:</td> <td style="color: #00FF00; font-weight: bold;">{rec_freq} Hz</td></tr>
                <tr><td style="color: #BBBBBB;">Cur:</td> <td style="color: {cur_color}; font-weight: bold;">{cur_freq} Hz</td></tr>
            </table>
        </body>
        </html>
        """
        self.lbl_rec.setText(html_text)
        
        # v2.1.0: Set copy value for click-to-clipboard
        if str(rec_freq) != "----":
            self.lbl_rec.set_copy_value(rec_freq)

    def update_activity(self, state, other_call=None):
        """v2.3.0: Update target activity state display.
        
        Args:
            state: Activity state string
            other_call: Callsign of station target is working (if applicable)
        """
        prev_state = self._activity_state   # v2.3.5
        self._activity_state = state         # v2.3.5: Cache for competition override
        
        if state == 'cqing':
            self.val_activity.setText("CQing")
            self.val_activity.setStyleSheet("color: #00FF00; font-weight: bold;")
        elif state == 'working_you':
            self.val_activity.setText("Working YOU")
            self.val_activity.setStyleSheet("color: #00FFFF; font-weight: bold;")
        elif state == 'completing_with_you':
            self.val_activity.setText("QSO complete!")
            self.val_activity.setStyleSheet("color: #00FFFF; font-weight: bold;")
        elif state == 'working_other':
            display_call = other_call[:8] if other_call else "?"
            self.val_activity.setText(f"Working {display_call}")
            self.val_activity.setStyleSheet("color: #FFA500; font-weight: bold;")
        elif state == 'completing_with_other':
            self.val_activity.setText("Finishing QSO")
            self.val_activity.setStyleSheet("color: #FFFF00; font-weight: bold;")
        elif state == 'being_called':
            self.val_activity.setText("Being called")
            self.val_activity.setStyleSheet("color: #DDDDDD;")
        elif state == 'idle':
            self.val_activity.setText("Idle")
            self.val_activity.setStyleSheet("color: #888888;")
        else:
            self.val_activity.setText("--")
            self.val_activity.setStyleSheet("color: #666666;")
        
        # v2.3.5: If activity state changed in a way that affects the competition
        # override, refresh competition display immediately (don't wait for 3s timer)
        in_qso_states = ('working_other', 'completing_with_other')
        if (state in in_qso_states) != (prev_state in in_qso_states):
            self._refresh_competition_display()

    def _refresh_competition_display(self):
        """v2.3.5: Render competition with activity-state override.
        
        When target is mid-QSO (working_other / completing_with_other),
        shows "In QSO" in amber instead of misleading "Clear" or stale
        pileup data. Called from both update_data() and update_activity()
        so competition display stays in sync with both data streams.
        """
        # Apply override when target is in QSO with someone else
        if self._activity_state in ('working_other', 'completing_with_other'):
            comp = 'In QSO'
        else:
            comp = self._raw_competition if self._raw_competition else '--'
        
        self.val_comp.setText(comp)
        
        # Color-code competition status
        if comp == 'In QSO':
            self.val_comp.setStyleSheet("color: #FFA500; font-weight: bold;")  # Amber — target mid-QSO
        elif "Heard by Target" in comp:
            self.val_comp.setStyleSheet("color: #00FFFF; font-weight: bold;")  # Cyan
        elif "PILEUP" in comp:
            self.val_comp.setStyleSheet("color: #FF5555; font-weight: bold;")  # Red
        elif "High" in comp:
            self.val_comp.setStyleSheet("color: #FFA500; font-weight: bold;")  # Orange
        elif "Unknown" in comp:
            self.val_comp.setStyleSheet("color: #888888; font-weight: bold;")  # Gray
        elif "Clear" in comp:
            self.val_comp.setStyleSheet("color: #00FF00; font-weight: bold;")  # Green
        else:
            self.val_comp.setStyleSheet("color: #DDDDDD;")


# --- DELEGATE: Custom painting for hunt highlighting ---
class HuntHighlightDelegate(QStyledItemDelegate):
    """Custom delegate to paint background colors from model data.
    
    Qt stylesheets override model BackgroundRole, so we need a delegate
    to respect the model's background colors for hunt highlighting.
    """
    def paint(self, painter, option, index):
        # Get background color from model
        bg_color = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg_color and isinstance(bg_color, QColor):
            painter.fillRect(option.rect, QBrush(bg_color))
        # Call default painting for text, selection, etc.
        super().paint(painter, option, index)


# --- v2.2.0: TACTICAL OBSERVATION TOASTS ---
class TacticalToast(QFrame):
    """Thin notification bar for tactical observations.
    
    Shows event-driven alerts like hidden pileups, path changes,
    and competition shifts. Auto-dismisses after 8 seconds.
    Rate-limited to 1 toast per 15 seconds to avoid spam.
    """
    
    # Style presets by priority
    STYLES = {
        'warning': "background-color: #3A2800; color: #FFA500; border: 1px solid #664400; border-radius: 3px; padding: 4px 12px; font-weight: bold;",
        'success': "background-color: #002A00; color: #00FF00; border: 1px solid #004400; border-radius: 3px; padding: 4px 12px; font-weight: bold;",
        'info':    "background-color: #001A2A; color: #00CCFF; border: 1px solid #003344; border-radius: 3px; padding: 4px 12px; font-weight: bold;",
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.hide()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(4)
        
        self._label = QLabel()
        self._label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self._label, 1)
        
        self._dismiss_btn = QLabel("✕")
        self._dismiss_btn.setStyleSheet("color: #888; font-size: 14px; font-weight: bold;")
        self._dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dismiss_btn.mousePressEvent = lambda e: self._dismiss()
        layout.addWidget(self._dismiss_btn)
        
        # Auto-dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)
        
        # Rate limiting
        self._last_show_time = 0
        self._min_interval = 15  # seconds between toasts
        self._queue = []  # [(message, style_key)]
        
        # State tracking for change detection
        self._prev_competition_count = 0
        self._prev_path_status = ""
        self._prev_reporting_near_target = 0
    
    def show_toast(self, message, style='info', duration=8000):
        """Show a toast notification, or queue it if rate-limited."""
        now = time.time()
        elapsed = now - self._last_show_time
        
        if elapsed < self._min_interval and self.isVisible():
            # Rate-limited — queue it (keep only the latest)
            self._queue = [(message, style)]
            return
        
        self._display(message, style, duration)
    
    def _display(self, message, style, duration):
        """Actually show the toast."""
        self._label.setText(message)
        self.setStyleSheet(self.STYLES.get(style, self.STYLES['info']))
        self._last_show_time = time.time()
        self._timer.start(duration)
        self.show()
    
    def _dismiss(self):
        """Hide toast and show queued toast if any."""
        self._timer.stop()
        self.hide()
        
        # Show queued toast after a brief pause
        if self._queue:
            msg, style = self._queue.pop(0)
            QTimer.singleShot(500, lambda: self._display(msg, style, 8000))
    
    def check_competition_change(self, competition_str, local_callers):
        """Detect and toast competition changes.
        
        Args:
            competition_str: e.g. "High (4)", "PILEUP (8)", "Low (1)", "High (6) local"
            local_callers: int count from local pileup tracking
        """
        # Extract count from competition string
        count = 0
        if competition_str and '(' in competition_str:
            try:
                count = int(competition_str.split('(')[1].split(')')[0])
            except (ValueError, IndexError):
                pass
        
        # v2.2.1: Local decode data is never "hidden" — you can see it
        is_local_source = 'local' in str(competition_str).lower()
        
        prev = self._prev_competition_count
        self._prev_competition_count = count
        
        # Skip if no previous data (first update)
        if prev == 0 and count == 0:
            return
        
        # Hidden pileup detection — only for PSK Reporter data, not local decodes
        if count >= 3 and local_callers <= 1 and prev < 3 and not is_local_source:
            self.show_toast(
                f"⚠️ Hidden pileup: {local_callers} caller{'s' if local_callers != 1 else ''} locally, "
                f"{count} at target's end — you can't hear your competition",
                'warning'
            )
        # Significant pileup growth
        elif count >= prev + 3 and prev > 0:
            self.show_toast(
                f"📈 Competition increasing at target: was {prev}, now {count}",
                'warning'
            )
        # Pileup thinning
        elif count <= prev - 3 and count > 0 and prev > 3:
            self.show_toast(
                f"📉 Competition dropping at target: was {prev}, now {count}",
                'success'
            )
    
    def check_path_change(self, new_path_status, target_call):
        """Detect and toast path status changes."""
        prev = self._prev_path_status
        self._prev_path_status = new_path_status
        
        if not prev or not target_call:
            return
        
        # Path opened (wasn't connected/open, now is)
        if new_path_status in ('Heard by Target', 'Reported in Region') and \
           prev not in ('Heard by Target', 'Reported in Region'):
            if new_path_status == 'Heard by Target':
                self.show_toast(
                    f"🎯 {target_call} has decoded YOU — call now!",
                    'success'
                )
            else:
                self.show_toast(
                    f"🟢 Path to {target_call}'s region confirmed!",
                    'success'
                )
        # Path lost
        elif new_path_status in ('Not Reported in Region', 'No Path') and \
             prev in ('Heard by Target', 'Reported in Region'):
            self.show_toast(
                f"🔴 Path to {target_call}'s region no longer confirmed",
                'warning'
            )
    
    def check_near_target_spotted(self, near_target_count, target_call):
        """Toast when first spotted near target."""
        prev = self._prev_reporting_near_target
        self._prev_reporting_near_target = near_target_count
        
        if prev == 0 and near_target_count > 0 and target_call:
            self.show_toast(
                f"📡 You've been spotted near {target_call}! Keep calling",
                'success'
            )
    
    def reset_state(self):
        """Reset state tracking (called on target clear/change)."""
        self._prev_competition_count = 0
        self._prev_path_status = ""
        self._prev_reporting_near_target = 0
        self._queue.clear()
        self._dismiss()


# --- MODEL: DECODE TABLE ---
class DecodeTableModel(QAbstractTableModel):
    def __init__(self, headers, config):
        super().__init__()
        self._headers = headers
        self._data = []
        self.config = config
        self.target_call = None
        self.hunt_manager = None  # v2.1.0: Set by MainWindow after init

    def set_target_call(self, callsign):
        self.target_call = callsign
        self.layoutChanged.emit()
    
    def clear(self):
        """Clear all decode data from the table."""
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        row_item = self._data[index.row()]
        col_name = self._headers[index.column()]

        key_map = {
            "UTC": "time", "Call": "call", "Grid": "grid", "dB": "snr",
            "DT": "dt", "Freq": "freq", "Message": "message",
            "Score": "prob", "Competition": "competition", "Global Activity": "competition",
            "Path": "path"
        }
        key = key_map.get(col_name, col_name.lower())
        
        if role == Qt.ItemDataRole.DisplayRole:
            return str(row_item.get(key, ""))
            
        # --- FIX: ALIGNMENT LOGIC ---
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            # Left align specified columns
            if key in ['call', 'message']:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            # Center align everything else (UTC, dB, DT, Freq, Grid, Prob, Path)
            return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter

        elif role == Qt.ItemDataRole.ForegroundRole:
            if key == "snr":
                try:
                    val = int(row_item.get('snr', -99))
                    if val >= 0: return QColor("#00FF00")       
                    elif val >= -10: return QColor("#FFFF00")   
                    return QColor("#FF5555")                    
                except: pass
            if key == "prob":
                try:
                    val = int(row_item.get('prob', '0'))
                    if val > 75: return QColor("#00FF00")
                    elif val < 30: return QColor("#FF5555")
                except: pass
            if key == "path":
                path = str(row_item.get('path', ''))
                if "Heard by Target" in path:
                    return QColor("#00FFFF")  # Cyan - target hears you!
                elif "Not Reported in Region" in path:
                    # MUST check "Not Reported" BEFORE "Reported" — substring match issue
                    return QColor("#FFA500")  # Orange - reporters exist but haven't spotted you
                elif "Reported in Region" in path:
                    return QColor("#00FF00")  # Green - path to region confirmed
                elif "Not Transmitting" in path:
                    return QColor("#888888")  # Gray - not transmitting recently
                elif "No Reporters" in path:
                    return QColor("#666666")  # Dark gray - no data available

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Highlight rows based on path status and hunt mode
            path = str(row_item.get('path', ''))
            
            # Heard by Target = highest priority (target hears you!)
            if "Heard by Target" in path:
                return QColor("#004040")  # Teal background
            
            # Reported in Region = propagation confirmed to region
            # Exclude "Not Reported" — substring match issue
            if "Reported in Region" in path and "Not Reported" not in path:
                return QColor("#002800")  # Dark green background
            
            # v2.1.0: Hunt Mode - highlight hunted stations with gold background
            call = row_item.get('call', '')
            
            # Debug: Log hunt_manager status once
            if not hasattr(self, '_hunt_debug_done'):
                self._hunt_debug_done = True
                logger.info(f"Hunt highlight debug: hunt_manager={self.hunt_manager is not None}")
                if self.hunt_manager:
                    logger.info(f"Hunt list contents: {self.hunt_manager.get_list()}")
            
            if self.hunt_manager and call:
                is_hunted = self.hunt_manager.is_hunted(call)
                if is_hunted:
                    return QColor("#7A5500")  # Visible gold/amber background for hunted
            
            if self.target_call and row_item.get('call') == self.target_call:
                return QColor("#004444")  # Teal for selected target
            
            # Default alternating row colors (visible contrast)
            if index.row() % 2 == 0:
                return QColor("#141414")  # Dark for even rows
            else:
                return QColor("#1c1c1c")  # Lighter for odd rows

        return None

    def headerData(self, section, orientation, role):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return self._headers[section]
            # --- FIX: FORCE CENTER ALIGNMENT FOR HEADERS ---
            elif role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignCenter
            # v2.2.0: Column header tooltips for data provenance
            elif role == Qt.ItemDataRole.ToolTipRole:
                tooltips = {
                    "UTC": "Time of decode (UTC)",
                    "dB": "Signal-to-noise ratio at your receiver",
                    "DT": "Time offset from expected (seconds)",
                    "Freq": "Audio frequency offset (Hz)",
                    "Call": "Station callsign",
                    "Grid": "Maidenhead grid locator",
                    "Message": "Decoded FT8/FT4 message",
                    "Score": "Opportunity score (higher = better prospect).\nCombines signal strength + path status - competition.\nNot a statistical probability.",
                    "Path": "Propagation status to this station.\nSources: PSK Reporter spots + local decode analysis.",
                }
                col_name = self._headers[section]
                return tooltips.get(col_name)
        return None

    def sort(self, column, order):
        col_name = self._headers[column]
        key_map = {
            "UTC": "time", "Call": "call", "Grid": "grid", "dB": "snr",
            "DT": "dt", "Freq": "freq", "Message": "message", 
            "Score": "prob", "Competition": "competition", "Path": "path"
        }
        key = key_map.get(col_name, col_name.lower())
        reverse = (order == Qt.SortOrder.DescendingOrder)
        
        def sort_key(row):
            val = row.get(key, "")
            if key in ['snr', 'prob', 'freq', 'dt', 'time']:
                try: 
                    return float(val)
                except: return -99999.0
            return str(val).lower()

        self.layoutAboutToBeChanged.emit()
        self._data.sort(key=sort_key, reverse=reverse)
        
        if self.target_call:
            targets = [r for r in self._data if r.get('call') == self.target_call]
            others = [r for r in self._data if r.get('call') != self.target_call]
            self._data = targets + others
            
        self.layoutChanged.emit()

    def add_batch(self, new_rows):
        if not new_rows: return
        start = len(self._data)
        self.beginInsertRows(QModelIndex(), start, start + len(new_rows) - 1)
        self._data.extend(new_rows)
        self.endInsertRows()
        
        if len(self._data) > 500:
            remove_count = len(self._data) - 500
            self.beginRemoveRows(QModelIndex(), 0, remove_count - 1)
            del self._data[:remove_count]
            self.endRemoveRows()

    def update_data_in_place(self, analyzer_func):
        if not self._data: return
        for item in self._data:
            analyzer_func(item)
        # Note: We emit dataChanged but sorting is controlled by view
        # The view should only re-sort on explicit user action, not data updates
        tl = self.index(0, 0)
        br = self.index(len(self._data)-1, len(self._headers)-1)
        self.dataChanged.emit(tl, br, [])  # Empty roles list = no sort trigger


# --- CLICKABLE LABEL FOR UPDATE NOTIFICATION ---
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_url = None
    
    def mousePressEvent(self, event):
        if self.update_url:
            webbrowser.open(self.update_url)
        self.clicked.emit()


# --- v2.1.0: CLICKABLE LABEL THAT COPIES VALUE TO CLIPBOARD ---
class ClickableCopyLabel(QLabel):
    """Label that copies a value to clipboard when clicked."""
    copied = pyqtSignal(str)  # Emits the copied value for status bar feedback
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._copy_value = ""
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    
    def set_copy_value(self, value):
        """Set the value that will be copied to clipboard on click."""
        self._copy_value = str(value)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._copy_value:
            clipboard = QApplication.clipboard()
            clipboard.setText(self._copy_value)
            self.copied.emit(f"Copied to clipboard: {self._copy_value} Hz")


# --- v2.3.0: TARGET ACTIVITY STATE PARSER ---
def parse_target_activity(message, target_call, my_call):
    """Parse an FT8/FT4 message to determine target's activity state.
    
    Analyzes decoded messages to infer what the target station is doing:
    - CQing (open for calls)
    - Working you (responding to your callsign)  
    - Working another station (competition confirmed)
    - Being called by someone
    
    Args:
        message: Raw FT8 message string (e.g., "WU2C J51A -04")
        target_call: Current target callsign (uppercase)
        my_call: Our callsign (uppercase)
    
    Returns:
        (state, other_call) tuple, or (None, None) if message doesn't involve target.
        state values: 'cqing', 'working_you', 'completing_with_you',
                      'working_other', 'completing_with_other', 'being_called'
    """
    if not message or not target_call:
        return None, None
    
    parts = message.split()
    if len(parts) < 2:
        return None, None
    
    target_upper = target_call.upper()
    my_upper = my_call.upper() if my_call else ""
    
    # Target is CQing: "CQ J51A GF25" or "CQ DX J51A GF25"
    if parts[0] == 'CQ':
        if target_upper in parts:
            return 'cqing', None
        return None, None
    
    # Target in Position 2 — they are transmitting TO the station in Position 1
    # Pattern: "OTHERCALL TARGET payload"
    if len(parts) >= 3 and parts[1] == target_upper:
        other_call = parts[0]
        payload = ' '.join(parts[2:])
        
        if my_upper and other_call == my_upper:
            # Target is working US
            if 'RR73' in payload or payload.strip() == '73':
                return 'completing_with_you', my_upper
            return 'working_you', my_upper
        else:
            # Target is working someone else
            if 'RR73' in payload or payload.strip() == '73':
                return 'completing_with_other', other_call
            return 'working_other', other_call
    
    # Target in Position 1 — someone is calling/responding TO target
    # Pattern: "TARGET CALLER payload"
    if len(parts) >= 2 and parts[0] == target_upper:
        caller = parts[1] if len(parts) >= 2 else None
        # Don't count if caller looks like a grid or report
        if caller and len(caller) >= 3 and any(c.isdigit() for c in caller) and any(c.isalpha() for c in caller):
            return 'being_called', caller
    
    return None, None


# --- MAIN APPLICATION WINDOW ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = ConfigManager()
        self.setWindowTitle(f"QSO Predictor v{get_version()} by WU2C")
        self.resize(1100, 800)
        
        # --- v2.0.3: Restore window geometry ---
        geo = self.config.get('WINDOW', 'geometry')
        if geo:
            self.restoreGeometry(QByteArray.fromHex(geo.encode()))
            
            # v2.1.0: Ensure window fits on screen (fix for Windows off-screen issue)
            screen = QApplication.primaryScreen()
            if screen:
                available = screen.availableGeometry()
                frame = self.frameGeometry()
                
                # If window extends beyond screen, resize to fit
                if frame.bottom() > available.bottom():
                    new_height = available.height() - 50  # Leave some margin
                    if new_height < 600:
                        new_height = 600  # Minimum usable height
                    self.resize(self.width(), new_height)
                    self.move(frame.x(), available.y() + 10)
                
                if frame.right() > available.right():
                    self.move(available.x() + 10, self.y())

        self.analyzer = QSOAnalyzer(self.config)
        self.udp = UDPHandler(self.config)
        
        # --- TARGET TRACKING STATE ---
        self.current_target_call = ""
        self.current_target_grid = ""
        self.jtdx_last_dx_call = ""  # Track what JTDX last sent (separate from our selection)
        
        # v2.3.0: Target Activity State tracking
        self._target_activity_state = 'unknown'
        self._target_activity_other = None  # Who target is working
        self._target_activity_time = 0  # Last activity timestamp
        self._inferred_competitors = {}  # {callsign: timestamp} — competitors inferred from target responses
        self._activity_idle_timeout = 120  # Seconds before state goes to 'idle'
        
        # v2.3.0: Fox/Hound mode state
        self._fh_active = False           # Master F/H state (from any trigger)
        self._fh_source = None            # What triggered F/H: 'manual', 'udp', 'inferred'
        self._fh_type = None              # 'fh' (old-style) or 'superfh' — controls clamping behavior
        self._fh_fox_qso = False          # Fox is controlling our TX frequency
        self._fh_dialog_shown = False     # Prevent repeated dialogs in same session
        
        # --- UPDATE CHECK STATE ---
        self.update_available = None  # Will hold version string if update available
        self._normal_status = ""     # v2.1.1: Last non-warning status message
        
        # --- UDP STATUS TRACKING ---
        self._decode_count = 0
        self._decode_start_time = None
        
        # --- v2.1.0: Shutdown flag for clean notification handling ---
        self._closing = False
        
        if SOLAR_AVAILABLE:
            self.solar = SolarClient()
            self.solar_update_signal.connect(self.update_solar_ui)
        
        # --- LOCAL INTELLIGENCE v2.0 ---
        self.local_intel = None
        if LOCAL_INTEL_AVAILABLE:
            self._init_local_intelligence()
        
        # --- v2.1.0: HUNT MODE ---
        self.hunt_manager = None
        if HUNT_MODE_AVAILABLE:
            self._init_hunt_mode()
            
        self.init_ui()
        self.setup_connections()
        
        self.buffer = []
        self.buffer_timer = QTimer()
        self.buffer_timer.timeout.connect(self.process_buffer)
        self.buffer_timer.start(500) 
        
        # --- PERSPECTIVE REFRESH TIMER ---
        self.perspective_timer = QTimer()
        self.perspective_timer.timeout.connect(self.refresh_target_perspective)
        self.perspective_timer.start(3000)  # Refresh every 3 seconds
        
        self.udp.start()
        
        # --- v2.0.6: Solar data fetch with periodic refresh ---
        if SOLAR_AVAILABLE:
            self.fetch_solar_data()
            # Refresh solar data every 15 minutes
            self.solar_timer = QTimer()
            self.solar_timer.timeout.connect(self.fetch_solar_data)
            self.solar_timer.start(15 * 60 * 1000)  # 15 minutes
        
        # Check for updates on startup (non-blocking, silent)
        self.check_for_updates(manual=False)
        
        # v2.1.1: Periodic data health check (detects UDP/MQTT data loss)
        self._data_health_timer = QTimer()
        self._data_health_timer.timeout.connect(self._check_data_health)
        self._data_health_timer.start(10000)  # Check every 10 seconds
        self._last_health_warning = ""  # Track to avoid redundant status updates
        
        # Check for unconfigured callsign/grid on startup
        QTimer.singleShot(500, self._check_first_run_config)
        
        # v2.0.9: Start health check timer (checks for UDP data after 20 seconds)
        #self._start_health_check_timer()
    
    def _check_first_run_config(self):
        """Warn user if callsign/grid haven't been configured."""
        my_call = self.config.get('ANALYSIS', 'my_callsign', fallback='N0CALL')
        my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='FN00aa')
        
        if my_call == 'N0CALL' or my_grid == 'FN00aa':
            QMessageBox.information(
                self,
                "Welcome to QSO Predictor!",
                "Please configure your callsign and grid square "
                "for accurate predictions.\n\n"
                "Go to Edit → Settings to set them up."
            )

    def _init_local_intelligence(self):
        """Initialize Local Intelligence v2.0 features."""
        try:
            my_callsign = self.config.get('ANALYSIS', 'my_callsign', fallback='')
            if not my_callsign:
                logger.info("Local Intelligence: No callsign configured, some features disabled")
                my_callsign = 'N0CALL'
            
            self.local_intel = LocalIntelligence(my_callsign=my_callsign)
            logger.info("Local Intelligence initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Local Intelligence: {e}")
            self.local_intel = None
    
    def _init_hunt_mode(self):
        """Initialize Hunt Mode v2.1.0 features."""
        try:
            self.hunt_manager = HuntManager(config_manager=self.config)
            
            # Set user's grid for "working nearby" detection
            my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='')
            self.hunt_manager.set_my_grid(my_grid)
            
            # Connect hunt alerts to notification handler
            self.hunt_manager.hunt_alert.connect(self._on_hunt_alert)
            
            logger.info(f"Hunt Mode initialized with {len(self.hunt_manager.get_list())} items")
        except Exception as e:
            logger.error(f"Failed to initialize Hunt Mode: {e}")
            self.hunt_manager = None

    solar_update_signal = pyqtSignal(dict)
    update_check_signal = pyqtSignal(str, bool)  # (version_or_status, was_manual)

    def init_ui(self):
        # --- v2.1.0: DOCK LAYOUT ---
        # Central widget: Decode Table (with info bar and toolbar)
        # Bottom dock: Target View (Dashboard + Band Map) - can undock
        # Right dock: Insights panel - can undock, spans full height
        #
        # setCorner: Right dock owns the corners, so it spans full height
        # and the bottom dock (Target View) only spans left of it.
        # This prevents Local Intel from pushing down the band map.
        
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # v2.1.0: Size policy - allow central widget to shrink so bottom dock gets space
        # This is critical on Windows where Qt is more aggressive about central widget expansion
        main_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)
        
        # 1. Info Bar (clickable for updates)
        self.info_bar = ClickableLabel("Waiting for WSJT-X...")
        self.info_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_bar.setFixedHeight(25) 
        self.info_bar.setStyleSheet("background-color: #2A2A2A; color: #AAA; padding: 4px;")
        main_layout.addWidget(self.info_bar)
        
        # Connect update check signal
        self.update_check_signal.connect(self.on_update_check_result)
        
        # --- v2.0.3: TOOLBAR WITH CLEAR TARGET ---
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("main_toolbar")  # Required for saveState
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar { 
                background-color: #2A2A2A; 
                border: none; 
                padding: 2px;
                spacing: 5px;
            }
            QPushButton {
                background-color: #444;
                color: #DDD;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 12px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #333;
            }
            QCheckBox {
                color: #AAA;
                font-size: 9pt;
                padding-left: 10px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
        """)
        
        # Clear Target button
        self.btn_clear_target = QPushButton("Clear Target")
        self.btn_clear_target.setToolTip("Clear current target selection (Ctrl+R)")
        self.btn_clear_target.clicked.connect(self.clear_target)
        toolbar.addWidget(self.btn_clear_target)
        
        # v2.0.6: Fetch target from JTDX (pulls THEIR selection into QSOP)
        self.btn_sync_jtdx = QPushButton("← Fetch Target")
        self.btn_sync_jtdx.setToolTip("Set QSOP target to match WSJT-X/JTDX selection (Ctrl+Y)")
        self.btn_sync_jtdx.clicked.connect(self.sync_to_jtdx)
        toolbar.addWidget(self.btn_sync_jtdx)
        
        # Auto-clear checkbox
        self.chk_auto_clear = QCheckBox("Auto-clear on QSO")
        self.chk_auto_clear.setToolTip("Automatically clear target after logging a QSO")
        auto_clear_enabled = self.config.get('BEHAVIOR', 'auto_clear_on_log', fallback='false') == 'true'
        self.chk_auto_clear.setChecked(auto_clear_enabled)
        self.chk_auto_clear.stateChanged.connect(self._on_auto_clear_changed)
        toolbar.addWidget(self.chk_auto_clear)
        
        # v2.1.0: Auto-clear on band change checkbox (Brian's request)
        self.chk_auto_clear_band = QCheckBox("Auto-clear on QSY")
        self.chk_auto_clear_band.setToolTip("Automatically clear target when you change bands")
        auto_clear_band = self.config.get('BEHAVIOR', 'auto_clear_on_band', fallback='false') == 'true'
        self.chk_auto_clear_band.setChecked(auto_clear_band)
        self.chk_auto_clear_band.stateChanged.connect(self._on_auto_clear_band_changed)
        toolbar.addWidget(self.chk_auto_clear_band)
        
        toolbar.addSeparator()
        
        # v2.3.0: Fox/Hound mode selector (Off / F/H / SuperF/H)
        self.cmb_fh_mode = QComboBox()
        self.cmb_fh_mode.addItems(["F/H Off", "F/H", "SuperF/H"])
        self.cmb_fh_mode.setToolTip(
            "Fox/Hound mode:\n"
            "  F/H — Old-style: clamps TX to 1000+ Hz\n"
            "  SuperF/H — SuperFox: full band, no clamping\n"
            "Auto-detected from WSJT-X or decode patterns when possible."
        )
        self.cmb_fh_mode.setCurrentIndex(0)
        self.cmb_fh_mode.currentIndexChanged.connect(self._on_fh_combo_changed)
        self.cmb_fh_mode.setStyleSheet("""
            QComboBox {
                color: #CCCCCC;
                background: #2A2A2A;
                border: 1px solid #555;
                padding: 2px 6px;
                min-width: 80px;
            }
            QComboBox:hover { border-color: #00FFFF; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                color: #CCCCCC;
                background: #2A2A2A;
                selection-background-color: #444;
            }
        """)
        toolbar.addWidget(self.cmb_fh_mode)
        
        # Spacer to push items to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        
        self.addToolBar(toolbar)
        
        # --- DECODE TABLE (Central Widget) ---
        cols = ["UTC", "dB", "DT", "Freq", "Call", "Grid", "Message", "Score", "Path"]
        self.model = DecodeTableModel(cols, self.config)
        
        # v2.1.0: Give model access to hunt manager for highlighting
        if self.hunt_manager:
            self.model.hunt_manager = self.hunt_manager
            logger.info(f"Hunt Mode: Assigned hunt_manager to model (list={self.hunt_manager.get_list()})")
            # Refresh table when hunt list changes (e.g., via dialog)
            def refresh_hunt_highlighting():
                """Force full table repaint when hunt list changes."""
                if self.model.rowCount() > 0:
                    self.model.dataChanged.emit(
                        self.model.index(0, 0),
                        self.model.index(self.model.rowCount() - 1, self.model.columnCount() - 1),
                        [Qt.ItemDataRole.BackgroundRole]
                    )
            self.hunt_manager.hunt_list_changed.connect(refresh_hunt_highlighting)
        else:
            logger.warning("Hunt Mode: hunt_manager is None, highlighting disabled")
        
        self.table_view = QTableView()
        self.table_view.setModel(self.model)
        
        # v2.1.0: Size policy - allow table to shrink to make room for dock widgets
        self.table_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table_view.setMinimumHeight(100)  # Ensure table never disappears completely
        
        # v2.1.0: Custom delegate for hunt highlighting (bypasses stylesheet override)
        self.table_view.setItemDelegate(HuntHighlightDelegate(self.table_view))
        
        # v2.1.0: Enable context menu for hunt mode
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_table_context_menu)
        
        self.table_view.setAlternatingRowColors(False)  # Let model control backgrounds
        self.table_view.setStyleSheet("""
            QTableView { 
                background-color: #121212; 
                gridline-color: #333; 
                color: #EEE;
                outline: 0; 
                border: none;
            }
            QTableView::item {
                border: none;
                padding: 2px;
            }
            QTableView::item:selected { 
                background-color: #1a3a5c; 
                color: #FFFFFF; 
            }
            QHeaderView::section { 
                background-color: #222; 
                color: #DDD; 
                padding: 4px; 
                border: 1px solid #444; 
            }
        """)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSortIndicatorShown(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.clicked.connect(self.on_row_click)
        
        # --- v2.0.3: Restore column widths ---
        self._restore_column_widths()
        
        # v2.2.0: Tactical observation toast bar (between info bar and table)
        self.tactical_toast = TacticalToast()
        main_layout.addWidget(self.tactical_toast)
        
        # Table is the central content
        main_layout.addWidget(self.table_view)
        
        # --- TARGET VIEW DOCK (Dashboard + Band Map) ---
        self.target_dock = QDockWidget("Target View", self)
        self.target_dock.setObjectName("target_dock")
        
        # Container for Dashboard + Band Map
        target_container = QWidget()
        target_container.setMinimumHeight(380)  # Ensure band map shows all sections including local decodes
        # Note: No maximum height - setCorner() fix handles layout, user can resize freely
        target_layout = QVBoxLayout(target_container)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(0)
        
        # Dashboard
        self.dashboard = TargetDashboard()
        self.dashboard.sync_requested.connect(self.sync_to_jtdx)  # v2.0.6
        self.dashboard.status_message.connect(self.update_status_msg)  # v2.1.0: clipboard feedback
        target_layout.addWidget(self.dashboard)
        
        # Band Map
        self.band_map = BandMapWidget()
        self.band_map.recommendation_changed.connect(self.on_recommendation)
        self.band_map.status_message.connect(self.update_status_msg)  # v2.1.0: clipboard feedback
        target_layout.addWidget(self.band_map)
        
        self.target_dock.setWidget(target_container)
        self.target_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.target_dock)
        
        # Menu
        # v2.2.2: Force menu bar inside app window on Linux (prevents GNOME/Ubuntu
        # global menu integration from swallowing Edit/View/Tools menus).
        # Not needed on macOS (native menu bar works correctly) or Windows (no global menu bar).
        if sys.platform.startswith('linux'):
            self.menuBar().setNativeMenuBar(False)
        menu = self.menuBar()
        
        # --- FILE MENU ---
        file_menu = menu.addMenu("File")
        refresh_action = QAction("Force Refresh Spots", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(self.analyzer.force_refresh)
        file_menu.addAction(refresh_action)
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # --- EDIT MENU (NEW for v2.0.3) ---
        edit_menu = menu.addMenu("Edit")
        
        # v2.0.3: Clear Target action with Ctrl+R shortcut
        clear_target_action = QAction("Clear Target", self)
        clear_target_action.setShortcut(QKeySequence("Ctrl+R"))
        clear_target_action.triggered.connect(self.clear_target)
        edit_menu.addAction(clear_target_action)
        
        # v2.0.6: Fetch target from logging app with Ctrl+Y shortcut
        sync_jtdx_action = QAction("Fetch Target from WSJT-X/JTDX", self)
        sync_jtdx_action.setShortcut(QKeySequence("Ctrl+Y"))
        sync_jtdx_action.triggered.connect(self.sync_to_jtdx)
        edit_menu.addAction(sync_jtdx_action)
        
        # --- v2.1.0: VIEW MENU ---
        view_menu = menu.addMenu("View")
        
        # Panel visibility toggles - both docks work the same way
        view_menu.addAction(self.target_dock.toggleViewAction())
        # Insights dock toggle will be added after Insights panel setup
        self._view_menu = view_menu  # Store reference for adding insights toggle later
        
        view_menu.addSeparator()
        
        # Reset Layout action
        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.setToolTip("Restore default window layout")
        reset_layout_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout_action)
        
        # --- TOOLS MENU ---
        tools_menu = menu.addMenu("Tools")
        
        # v2.1.0: Hunt Mode
        if self.hunt_manager:
            hunt_list_action = QAction("Hunt List...", self)
            hunt_list_action.setShortcut(QKeySequence("Ctrl+H"))
            hunt_list_action.setToolTip("Manage stations you're hunting")
            hunt_list_action.triggered.connect(self._show_hunt_list_dialog)
            tools_menu.addAction(hunt_list_action)
            tools_menu.addSeparator()
        
        # Add Insights menu items if available
        if self.local_intel:
            self.local_intel.add_menu_items(tools_menu)
        else:
            disabled_action = QAction("Insights (not available)", self)
            disabled_action.setEnabled(False)
            tools_menu.addAction(disabled_action)
        
        # Help Menu
        help_menu = menu.addMenu("Help")
        guide_action = QAction("User Guide", self)
        guide_action.setShortcut(QKeySequence("F1"))
        guide_action.triggered.connect(self.open_user_guide)
        help_menu.addAction(guide_action)
        
        # v2.0.9: Connection Help menu item
        connection_help_action = QAction("Connection Help...", self)
        connection_help_action.triggered.connect(self._show_connection_help)
        help_menu.addAction(connection_help_action)
        
        help_menu.addSeparator()
        
        # v2.0.9: Debug Logging toggle
        self.debug_logging_action = QAction("Enable Debug Logging", self)
        self.debug_logging_action.setCheckable(True)
        self.debug_logging_action.setChecked(False)
        self.debug_logging_action.setToolTip("Enable verbose logging for troubleshooting")
        self.debug_logging_action.triggered.connect(self._toggle_debug_logging)
        help_menu.addAction(self.debug_logging_action)
        
        # v2.0.9: Open Log Folder
        open_log_action = QAction("Open Log Folder...", self)
        open_log_action.setToolTip("Open the folder containing log files")
        open_log_action.triggered.connect(self._open_log_folder)
        help_menu.addAction(open_log_action)
        
        help_menu.addSeparator()
        
        check_update_action = QAction("Check for Updates", self)
        check_update_action.triggered.connect(lambda: self.check_for_updates(manual=True))
        help_menu.addAction(check_update_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        # --- ICON SETUP ---
        app_icon = QIcon("icon.ico")
        self.setWindowIcon(app_icon) # Top-left of window & Taskbar

        # --- SYSTEM TRAY ---
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(app_icon) 
        
        # Tray Menu
        tray_menu = QMenu()
        show_action = QAction("Show Dashboard", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # --- LOCAL INTELLIGENCE PANEL SETUP ---
        if self.local_intel:
            try:
                self.local_intel.setup(self)
                
                # v2.1.0: Connect Phase 2 Path Intelligence analysis request
                if self.local_intel.insights_panel:
                    self.local_intel.insights_panel.path_analyze_requested.connect(
                        self._on_path_analyze_requested
                    )
                
                # v2.1.0: Add insights panel toggle to View menu
                if self.local_intel.insights_dock and hasattr(self, '_view_menu'):
                    # Insert before the separator (position 2, after decode and target toggles)
                    actions = self._view_menu.actions()
                    if len(actions) >= 2:
                        self._view_menu.insertAction(actions[2], self.local_intel.insights_dock.toggleViewAction())
                
                # --- v2.1.0: Restore dock widget positions (must be after all docks are created) ---
                dock_state = self.config.get('WINDOW', 'dock_state')
                if dock_state:
                    self.restoreState(QByteArray.fromHex(dock_state.encode()))
                    
                    # v2.1.0: Re-apply corner ownership AFTER restoreState
                    # On Windows, restoreState can override setCorner, causing bottom dock 
                    # to span full width instead of right dock spanning full height
                    self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
                    self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
            except Exception as e:
                logger.error(f"Failed to setup Local Intelligence panel: {e}")
    
    # --- v2.0.3: Column width persistence ---
    def _restore_column_widths(self):
        """Restore saved column widths from config."""
        widths_str = self.config.get('WINDOW', 'column_widths', fallback='')
        if widths_str:
            try:
                widths = [int(w) for w in widths_str.split(',')]
                for i, width in enumerate(widths):
                    if i < self.model.columnCount() and width > 0:
                        self.table_view.setColumnWidth(i, width)
            except (ValueError, IndexError) as e:
                logger.debug(f"Could not restore column widths: {e}")
    
    def _save_column_widths(self):
        """Save current column widths to config."""
        widths = []
        for i in range(self.model.columnCount()):
            widths.append(str(self.table_view.columnWidth(i)))
        self.config.save_setting('WINDOW', 'column_widths', ','.join(widths))
    
    # --- v2.1.0: Reset Layout functionality ---
    def _reset_layout(self):
        """Reset dock widgets to their default positions.
        
        Shows all panels, un-floats them, and restores default positions.
        Also ensures window fits on screen.
        """
        # v2.1.0: CRITICAL - Re-apply corner ownership BEFORE re-docking
        # This makes right dock span full height, bottom dock only spans left of it
        # Without this, Windows reverts to bottom dock spanning full width
        self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
        
        # Remove docks first to reset their state completely
        self.removeDockWidget(self.target_dock)
        if self.local_intel and self.local_intel.insights_dock:
            self.removeDockWidget(self.local_intel.insights_dock)
        
        # Re-add docks in correct order: RIGHT dock first (so it claims corners), then BOTTOM
        if self.local_intel and self.local_intel.insights_dock:
            self.local_intel.insights_dock.show()
            self.local_intel.insights_dock.setFloating(False)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.local_intel.insights_dock)
        
        self.target_dock.show()
        self.target_dock.setFloating(False)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.target_dock)
        
        # Ensure window fits on screen
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            # Reset to reasonable size that fits on screen
            new_width = min(1200, available.width() - 100)
            new_height = min(850, available.height() - 100)
            self.resize(new_width, new_height)
            # Center on screen
            self.move(
                available.x() + (available.width() - new_width) // 2,
                available.y() + (available.height() - new_height) // 2
            )
        
        # Clear saved dock state so next restart also uses defaults
        self.config.save_setting('WINDOW', 'dock_state', '')
        self.config.save_setting('WINDOW', 'geometry', '')  # Also clear saved geometry
        
        logger.info("Layout reset to defaults")
    
    # --- v2.0.3: Auto-clear setting handler ---
    def _on_auto_clear_changed(self, state):
        """Handle auto-clear checkbox state change."""
        enabled = 'true' if state == Qt.CheckState.Checked.value else 'false'
        self.config.save_setting('BEHAVIOR', 'auto_clear_on_log', enabled)
    
    # --- v2.1.0: Auto-clear on band change handler (Brian's request) ---
    def _on_auto_clear_band_changed(self, state):
        """Handle auto-clear on band change checkbox state change."""
        enabled = 'true' if state == Qt.CheckState.Checked.value else 'false'
        self.config.save_setting('BEHAVIOR', 'auto_clear_on_band', enabled)
    
    def _freq_to_band(self, freq):
        """Convert frequency in Hz to band string."""
        f = freq / 1_000_000
        if 1.8 <= f <= 2.0: return "160m"
        if 3.5 <= f <= 4.0: return "80m"
        if 5.3 <= f <= 5.4: return "60m"
        if 7.0 <= f <= 7.3: return "40m"
        if 10.1 <= f <= 10.15: return "30m"
        if 14.0 <= f <= 14.35: return "20m"
        if 18.068 <= f <= 18.168: return "17m"
        if 21.0 <= f <= 21.45: return "15m"
        if 24.89 <= f <= 24.99: return "12m"
        if 28.0 <= f <= 29.7: return "10m"
        if 50.0 <= f <= 54.0: return "6m"
        return "?"

    def setup_connections(self):
        self.udp.new_decode.connect(self.handle_decode)
        self.udp.status_update.connect(self.handle_status_update)
        # v2.0.3: Connect QSO Logged signal
        self.udp.qso_logged.connect(self.on_qso_logged)
        # Note: Removed cache_updated -> refresh_analysis connection
        # With target perspective, re-analyzing all 500 rows every 2 seconds is too expensive.
        # Reconnect cache_updated to lightweight path refresh (not full analysis)
        self.analyzer.cache_updated.connect(self.refresh_paths)
        self.analyzer.status_message.connect(self.update_status_msg)
        
        # v2.1.0: Hunt Mode - check MQTT spots against hunt list
        if self.hunt_manager:
            self.analyzer.spot_received.connect(self._check_hunt_spot)
    
    # --- v2.3.3: Unified target-change handler ---
    def _set_new_target(self, call, grid="", freq=0, row_data=None):
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
        is_clearing = not call
        
        # --- Find row data if not provided ---
        if call and not row_data:
            for row in self.model._data:
                if row.get('call') == call:
                    row_data = row
                    if not grid:
                        grid = row.get('grid', '')
                    if not freq:
                        freq = row.get('freq', 0)
                    break
        
        prev_target = self.current_target_call
        logger.info(f"Target: '{prev_target}' → '{call or '(cleared)'}'")
        
        # --- 1. Core state ---
        self.current_target_call = call
        self.current_target_grid = grid
        self.analyzer.current_target_grid = grid
        
        # --- 2. Reset per-target tracking ---
        self._target_activity_state = 'unknown'
        self._target_activity_other = None
        self._target_activity_time = 0
        self._inferred_competitors.clear()
        self.dashboard.update_activity('unknown')  # v2.3.5: Reset dashboard cached state too
        
        # --- 3. F/H per-target state (keep manual/UDP mode setting) ---
        self._fh_fox_qso = False
        self._fh_dialog_shown = False
        self.band_map.set_fox_qso(False)
        if self._fh_source == 'inferred':
            self._set_fox_hound_active(False, None, None)
        
        # --- 4. Table highlighting ---
        self.model.set_target_call(call if call else None)
        
        # --- 5. Dashboard ---
        if is_clearing:
            self.dashboard.update_data(None)
        elif row_data:
            # Re-analyze with full perspective before displaying
            self.analyzer.analyze_decode(row_data, use_perspective=True)
            self.dashboard.update_data(row_data)
        else:
            # Have call but no row data yet — show call, clear other fields
            self.dashboard.lbl_target.setText(call)
        
        # --- 6. Band map ---
        self.band_map.set_target_freq(freq)
        self.band_map.set_target_call(call)
        self.band_map.set_target_grid(grid)
        if is_clearing:
            self.band_map.update_perspective({
                'tier1': [], 'tier2': [], 'tier3': [], 'global': []
            })
        
        # --- 7. Local Intelligence ---
        if self.local_intel:
            try:
                self.local_intel.set_target(call if call else "", grid)
                if row_data and not is_clearing:
                    self._update_local_intel_path_status(row_data)
                    comp_str = str(row_data.get('competition', ''))
                    if hasattr(self.local_intel, 'insights_panel'):
                        self.local_intel.insights_panel.set_target_competition(comp_str)
            except Exception as e:
                logger.debug(f"Error updating local intel target: {e}")
        
        # --- 8. Tactical toast ---
        self.tactical_toast.reset_state()
        
        # --- 9. Perspective update (fetches PSK Reporter data for new target) ---
        if not is_clearing:
            self._update_perspective_display()
    
    # --- v2.0.3: Clear Target functionality (suggested by KC0GU) ---
    def clear_target(self):
        """Clear the current target selection.
        
        Resets all target-related state and UI to "NO TARGET" mode.
        Can be triggered via Ctrl+R shortcut or Clear Target button.
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        self._set_new_target("", "", 0, None)
    
    # --- v2.0.3: QSO Logged handler (suggested by KC0GU) ---
    def on_qso_logged(self, data):
        """Handle QSO Logged notification from WSJT-X/JTDX.
        
        When a QSO is logged, optionally clear the target if:
        1. Auto-clear is enabled
        2. The logged callsign matches our current target
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        logged_call = data.get('dx_call', '').upper()
        
        # Check if auto-clear is enabled
        if self.chk_auto_clear.isChecked():
            # Only clear if we logged the station we were targeting
            current_upper = self.current_target_call.upper() if self.current_target_call else ''
            if logged_call and logged_call == current_upper:
                logger.info(f"Auto-clear: Target cleared after logging {logged_call}")
                self.clear_target()

    # --- v2.0.6: Fetch target from JTDX (suggested by KC0GU) ---
    def sync_to_jtdx(self):
        """Fetch target from WSJT-X/JTDX into QSO Predictor.
        
        When user has selected a different station in QSO Predictor,
        double-clicking in JTDX won't re-send the UDP message (JTDX
        thinks it's already on that station). This button forces
        QSO Predictor to match JTDX's selection.
        
        Feature suggested by: Warren KC0GU (Dec 2025)
        """
        if not self.jtdx_last_dx_call:
            return
        if self.jtdx_last_dx_call == self.current_target_call:
            return
        
        logger.info(f"Sync: Syncing to JTDX target: {self.jtdx_last_dx_call}")
        self._set_new_target(self.jtdx_last_dx_call)

    def handle_decode(self, data):
        self.buffer.append(data)
        # Track decode rate
        if self._decode_start_time is None:
            from datetime import datetime
            self._decode_start_time = datetime.now()
        self._decode_count += 1

    def process_buffer(self):
        if not self.buffer: return
        
        # Check if we're at the bottom before adding rows
        scrollbar = self.table_view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 20
        
        chunk = self.buffer[:50]
        del self.buffer[:50]
        for item in chunk:
            self.analyzer.analyze_decode(item)
            
            # --- LOCAL INTELLIGENCE: Process decode ---
            if self.local_intel:
                self.local_intel.process_decode({
                    'callsign': item.get('call'),
                    'snr': item.get('snr'),
                    'frequency': item.get('freq'),
                    'message': item.get('message'),
                    'dt': item.get('dt', 0.0),
                    'mode': 'FT8',
                })
            
            # --- v2.3.0: TARGET ACTIVITY STATE ---
            if self.current_target_call:
                my_call = self.config.get('ANALYSIS', 'my_callsign', fallback='')
                state, other = parse_target_activity(
                    item.get('message', ''),
                    self.current_target_call.upper(),
                    my_call.upper()
                )
                if state:
                    self._update_target_activity(state, other)
            
            # v2.3.0: SuperFox auto-detection from decode content
            self._check_superfox_from_decodes(item.get('message', ''))
        
        # Disable sorting during batch add to prevent jitter
        self.table_view.setSortingEnabled(False)
        self.model.add_batch(chunk)
        self.table_view.setSortingEnabled(True)
        
        self.band_map.update_signals(chunk)
        
        # Auto-scroll to bottom if user was already there
        if at_bottom:
            self.table_view.scrollToBottom()

    def refresh_paths(self):
        """Lightweight refresh - just update path status for all rows."""
        # Throttle: only refresh every 2 seconds max
        now = time.time()
        if hasattr(self, '_last_path_refresh') and (now - self._last_path_refresh) < 2.0:
            return
        self._last_path_refresh = now
        
        # Disable sorting during update to prevent jitter
        self.table_view.setSortingEnabled(False)
        self.model.update_data_in_place(self.analyzer.update_path_only)
        self.table_view.setSortingEnabled(True)

    def refresh_analysis(self):
        self.model.update_data_in_place(self.analyzer.analyze_decode)

    def handle_status_update(self, status):
        now = time.time()
        
        # --- TARGET HANDLING (before throttle) ---
        # dx_call changes must be processed immediately — double-clicking a station
        # in WSJT-X/JTDX should update QSOP's target without waiting for the next
        # un-throttled status message. This is just a string comparison, no perf cost.
        dx_call = status.get('dx_call', '')
        if dx_call != self.jtdx_last_dx_call:
            self.jtdx_last_dx_call = dx_call
            if dx_call and dx_call != self.current_target_call:
                self._set_new_target(dx_call)
            # Note: If JTDX clears dx_call, we don't clear our target
            # (user may have manually selected something in the table)
        
        # Throttle remaining UI updates: JTDX sends status many times per second
        if hasattr(self, '_last_status_time') and (now - self._last_status_time) < 0.5:
            return
        self._last_status_time = now
        
        dial = status.get('dial_freq', 0)
        if dial > 0:
            # v2.1.0: Check for band change before updating (Brian's request)
            try:
                old_band = getattr(self, '_current_band', None)
                new_band = self._freq_to_band(dial)
                
                if old_band and new_band != old_band:
                    # Band changed!
                    logger.info(f"Band change detected: {old_band} -> {new_band}")
                    chk_enabled = hasattr(self, 'chk_auto_clear_band') and self.chk_auto_clear_band.isChecked()
                    logger.info(f"Auto-clear QSY: checkbox={chk_enabled}, target={self.current_target_call}")
                    if chk_enabled:
                        logger.info(f"Auto-clearing decode table, band map, and target due to band change")
                        self.model.clear()  # Clear decode table
                        self.band_map.clear()  # Clear band map signals
                        self.clear_target()  # Clear target selection
                
                self._current_band = new_band
            except Exception as e:
                logger.error(f"Error in band change detection: {e}")
            
            self.analyzer.set_dial_freq(dial)
        
        # Update Band Map (Yellow Line)
        cur_tx = status.get('tx_df', 0)
        self.band_map.set_current_tx_freq(cur_tx)
        
        # v2.3.0: Fox/Hound mode detection from UDP Special Operation Mode
        special_mode = status.get('special_mode', 0)
        # Hound mode: value 6 (older WSJT-X) or 7 (newer with WW DIGI)
        # Note: WSJT-X sends 7 for BOTH Hound and SuperHound — can't distinguish
        is_hound = special_mode in (6, 7)
        if is_hound and not self._fh_active:
            logger.info(f"Fox/Hound: UDP special_mode={special_mode} — showing disambiguation dialog")
            self._show_fh_disambiguation_dialog('udp')
        elif not is_hound and self._fh_source == 'udp':
            logger.info(f"Fox/Hound: UDP special_mode={special_mode} — deactivating (was udp-triggered)")
            self._set_fox_hound_active(False, None, None)
        
        # --- LOCAL INTELLIGENCE: Update TX status ---
        if self.local_intel:
            # Check for TX enabled (transmitting or tx_enabled field)
            tx_enabled = status.get('transmitting', False) or status.get('tx_enabled', False)
            dx_call = status.get('dx_call', '')
            # Pass who we're calling so pileup status knows if we're calling THIS target
            self.local_intel.set_tx_status(tx_enabled, calling=dx_call)
        
        # Update Dashboard Text Immediately
        rec = self.band_map.best_offset
        self.dashboard.update_rec(rec, cur_tx)

 
    def on_row_click(self, index):
        logger.debug(f"on_row_click: row {index.row()}")
        row = index.row()
        if row < len(self.model._data):
            data = self.model._data[row]
            target_call = data.get('call', '')
            
            # Skip if clicking same target (avoid redundant processing)
            if target_call == self.current_target_call:
                logger.debug(f"Same target {target_call}, skipping")
                return
            
            self._set_new_target(
                target_call,
                data.get('grid', ''),
                data.get('freq', 0),
                data
            )

    def _update_target_activity(self, state, other_call):
        """v2.3.0: Update target activity state from decoded message.
        
        Called when a local decode reveals what the target is doing.
        
        Args:
            state: Activity state from parse_target_activity()
            other_call: Callsign of station target is interacting with
        """
        import time as _time
        now = _time.time()
        prev_state = self._target_activity_state
        
        self._target_activity_state = state
        self._target_activity_other = other_call
        self._target_activity_time = now
        
        # Track inferred competitors (stations we know are competing because 
        # the target responded to them, even if we never saw them call)
        if state in ('working_other', 'completing_with_other') and other_call:
            self._inferred_competitors[other_call] = now
        
        # Clean up old inferred competitors (>2 minutes)
        cutoff = now - 120
        self._inferred_competitors = {
            c: t for c, t in self._inferred_competitors.items() if t > cutoff
        }
        
        # Update dashboard display
        self.dashboard.update_activity(state, other_call)
        
        # Toast triggers for significant state transitions
        target = self.current_target_call
        if state == 'cqing' and prev_state in ('working_other', 'completing_with_other', 'idle', 'unknown'):
            self.tactical_toast.show_toast(
                f"🎯 {target} is now CQing — call now!", 'success'
            )
        elif state == 'working_you' and prev_state != 'working_you':
            self.tactical_toast.show_toast(
                f"📡 {target} is responding to YOU!", 'success'
            )
        elif state == 'working_other' and prev_state == 'cqing':
            self.tactical_toast.show_toast(
                f"📡 {target} working {other_call} — competition confirmed", 'info'
            )
        
        # v2.3.0: Fox QSO detection — when F/H active and Fox responds to us
        if self._fh_active:
            if state in ('working_you', 'completing_with_you'):
                self._set_fox_qso_active(True)
            elif self._fh_fox_qso and state not in ('working_you', 'completing_with_you'):
                # Fox stopped responding to us — restore click-to-set
                self._set_fox_qso_active(False)
    
    def _check_target_activity_idle(self):
        """v2.3.0: Check if target activity should transition to idle.
        Called from refresh_target_perspective timer."""
        import time as _time
        if (self._target_activity_state not in ('idle', 'unknown') and 
            self._target_activity_time > 0 and
            _time.time() - self._target_activity_time > self._activity_idle_timeout):
            self._target_activity_state = 'idle'
            self._target_activity_other = None
            self.dashboard.update_activity('idle')

    # =========================================================================
    # v2.3.0: FOX/HOUND MODE MANAGEMENT
    # =========================================================================
    
    def _on_fh_combo_changed(self, index):
        """Handle F/H combo box selection: 0=Off, 1=F/H, 2=SuperF/H."""
        labels = ['Off', 'F/H', 'SuperF/H']
        logger.info(f"Fox/Hound: Combo box changed to {labels[index]} (index={index})")
        if index == 0:
            self._set_fox_hound_active(False, None, None)
        elif index == 1:
            self._set_fox_hound_active(True, 'manual', 'fh')
        elif index == 2:
            self._set_fox_hound_active(True, 'manual', 'superfh')
    
    def _show_fh_disambiguation_dialog(self, source):
        """Show dialog asking user to choose between old F/H and SuperF/H.
        
        Called when UDP detects Hound mode but can't tell which type.
        Only shown once per session (reset on target change or manual override).
        
        Args:
            source: 'udp' — what triggered the detection
        """
        if self._fh_dialog_shown:
            return
        self._fh_dialog_shown = True
        
        logger.info(f"Fox/Hound: Disambiguation dialog triggered (source={source})")
        
        title = "Hound Mode Detected"
        text = "WSJT-X reports Hound mode is active."
        
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(f"{text}\n\nWhich type of operation?")
        msg.setInformativeText(
            "Fox/Hound — TX clamped to 1000+ Hz, Fox controls your TX during QSO\n\n"
            "SuperFox/Hound — Full band (200-2800 Hz), you keep your calling frequency"
        )
        msg.setIcon(QMessageBox.Icon.Question)
        
        btn_fh = msg.addButton("Fox/Hound", QMessageBox.ButtonRole.AcceptRole)
        btn_sfh = msg.addButton("SuperFox/Hound", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = msg.addButton("Ignore", QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        
        clicked = msg.clickedButton()
        if clicked == btn_fh:
            logger.info("Fox/Hound: User selected Fox/Hound (old-style)")
            self._set_fox_hound_active(True, source, 'fh')
        elif clicked == btn_sfh:
            logger.info("Fox/Hound: User selected SuperFox/Hound")
            self._set_fox_hound_active(True, source, 'superfh')
        else:
            logger.info("Fox/Hound: User clicked Ignore")
    
    def _set_fox_hound_active(self, active, source, fh_type):
        """Master F/H state setter — called by all triggers.
        
        Args:
            active: True to enable F/H mode
            source: 'manual', 'udp', or 'inferred'
            fh_type: 'fh' (old-style, clamp 1000+) or 'superfh' (full band)
        """
        if active == self._fh_active and source == self._fh_source and fh_type == self._fh_type:
            return  # No change
        
        prev_active = self._fh_active
        prev_type = self._fh_type
        self._fh_active = active
        self._fh_source = source if active else None
        self._fh_type = fh_type if active else None
        
        # Only clamp to 1000+ Hz for old-style F/H, not SuperFox
        use_clamping = active and fh_type == 'fh'
        self.band_map.set_hound_mode(use_clamping)
        
        # Update combo box (without re-triggering signal)
        self.cmb_fh_mode.blockSignals(True)
        if not active:
            self.cmb_fh_mode.setCurrentIndex(0)  # Off
        elif fh_type == 'fh':
            self.cmb_fh_mode.setCurrentIndex(1)  # F/H
        elif fh_type == 'superfh':
            self.cmb_fh_mode.setCurrentIndex(2)  # SuperF/H
        self.cmb_fh_mode.blockSignals(False)
        
        # Toast on state change
        if active and not prev_active:
            if fh_type == 'fh':
                self.tactical_toast.show_toast(
                    "🦊 F/H mode — recommendations clamped to 1000+ Hz", 'info'
                )
            elif fh_type == 'superfh':
                self.tactical_toast.show_toast(
                    "🦊 SuperFox mode — full band available, finding best frequency", 'info'
                )
            logger.info(f"Fox/Hound: ACTIVATED (source={source}, type={fh_type})")
        elif active and prev_active and fh_type != prev_type:
            # Type changed while active
            logger.info(f"Fox/Hound: Type changed to {fh_type}")
        elif not active and prev_active:
            self.tactical_toast.show_toast(
                "F/H mode disabled — full frequency range restored", 'info'
            )
            # Reset Fox QSO state
            self._fh_fox_qso = False
            self.band_map.set_fox_qso(False)
            self._fh_dialog_shown = False
            logger.info("Fox/Hound: DEACTIVATED")
    
    def _check_superfox_from_decodes(self, message):
        """v2.3.0: Detect SuperFox from decode content.
        
        Looks for "verified" or "$VERIFY$" tokens in decoded messages,
        which are definitive SuperFox indicators. Only works with WSJT-X
        (JTDX cannot decode SuperFox).
        
        Note: Layer 2 F/H inference (frequency counting) was removed in v2.3.2.
        On standard frequencies nobody runs Fox, and on non-standard frequencies
        the frequency itself is sufficient — the counting logic was either
        wrong (false positive on standard freq) or redundant (non-standard freq).
        F/H detection now relies on manual combo box and UDP field 18 only.
        
        Args:
            message: Raw decoded message string
        """
        if not self.current_target_call or not message:
            return
        
        msg_lower = message.lower()
        if (('verified' in msg_lower or '$verify$' in msg_lower) and 
            self.current_target_call.upper() in message.upper() and
            self._fh_type != 'superfh'):
            logger.info(f"Fox/Hound: SuperFox detected — 'verified' in decode for {self.current_target_call}")
            self._set_fox_hound_active(True, 'inferred', 'superfh')
            self.tactical_toast.show_toast(
                f"🦊 {self.current_target_call} is verified SuperFox — full band available", 'info'
            )
    
    def _set_fox_qso_active(self, active):
        """v2.3.0: Set Fox QSO state — Fox is controlling our TX frequency.
        
        When active, click-to-set is disabled and recommendation line hidden.
        Called when activity state detects Fox responding to us.
        """
        if active == self._fh_fox_qso:
            return
        
        self._fh_fox_qso = active
        self.band_map.set_fox_qso(active)
        
        if active:
            if self._fh_type == 'superfh':
                self.tactical_toast.show_toast(
                    "🎯 Fox is calling you — stay on your frequency!", 'success'
                )
            else:
                self.tactical_toast.show_toast(
                    "🎯 Fox is calling you — TX frequency under Fox control!", 'success'
                )
            logger.info("Fox/Hound: Fox QSO active — click-to-set disabled")
        else:
            logger.info("Fox/Hound: Fox QSO ended — click-to-set restored")

    def _update_local_intel_path_status(self, row_data):
        """Update Local Intelligence with current path status."""
        if not self.local_intel:
            return
        
        path = str(row_data.get('path', ''))
        my_snr = row_data.get('my_snr_at_target', None)
        my_snr_reporter = row_data.get('my_snr_reporter', None)
        
        if "Heard by Target" in path:
            self.local_intel.set_path_status(PathStatus.CONNECTED, my_snr=my_snr, reporter=my_snr_reporter)
        elif "Not Reported in Region" in path:
            # MUST check "Not Reported" BEFORE "Reported" — 
            # "Not Reported in Region" contains "Reported in Region"
            self.local_intel.set_path_status(PathStatus.NO_PATH)
        elif "Reported in Region" in path:
            self.local_intel.set_path_status(PathStatus.PATH_OPEN, my_snr=my_snr, reporter=my_snr_reporter)
        else:
            self.local_intel.set_path_status(PathStatus.UNKNOWN)

    def refresh_target_perspective(self):
        """Called periodically by timer to keep target perspective current."""
        if self.current_target_call:
            # v2.3.0: Check if target activity should transition to idle
            self._check_target_activity_idle()
            
            # Find and re-analyze the selected target with full perspective
            for row in self.model._data:
                if row.get('call') == self.current_target_call:
                    self.analyzer.analyze_decode(row, use_perspective=True)
                    
                    # v2.3.0: Augment competition with inferred competitors
                    # (stations we know about from target responses, not visible callers)
                    if self._inferred_competitors:
                        comp = row.get('competition', '')
                        inferred_count = len(self._inferred_competitors)
                        if comp in ('Clear', 'Unknown'):
                            # Replace with inferred data
                            if inferred_count == 1:
                                row['competition'] = f"Low ({inferred_count}) inferred"
                            else:
                                row['competition'] = f"Moderate ({inferred_count}) inferred"
                    
                    self.dashboard.update_data(row)
                    
                    # --- LOCAL INTELLIGENCE: Update path status ---
                    if self.local_intel:
                        self._update_local_intel_path_status(row)
                    
                    # --- v2.2.0: TACTICAL TOAST TRIGGERS ---
                    # Check competition changes
                    competition_str = str(row.get('competition', ''))
                    local_callers = 0
                    if self.local_intel and hasattr(self.local_intel, 'insights_panel'):
                        pw = self.local_intel.insights_panel.pileup_widget
                        if hasattr(pw, '_last_caller_count'):
                            local_callers = pw._last_caller_count
                    self.tactical_toast.check_competition_change(competition_str, local_callers)
                    
                    # v2.2.0: Forward target-side competition to Insights panel
                    # This bridges PSK Reporter intelligence → Insights for:
                    # - Pileup contrast alert (local vs target competition)
                    # - Strategy recommendation (accounts for hidden pileup)
                    # - Success prediction (effective competition = max of local, target)
                    if self.local_intel and hasattr(self.local_intel, 'insights_panel'):
                        self.local_intel.insights_panel.set_target_competition(competition_str)
                    
                    # Check path changes
                    path_str = str(row.get('path', ''))
                    self.tactical_toast.check_path_change(path_str, self.current_target_call)
                    
                    break
            
            # Update band map perspective
            self._update_perspective_display()

    def _update_perspective_display(self):
        """Fetch and display target perspective data on band map."""
        if self.analyzer.current_dial_freq > 0 and self.current_target_call:
            dial = self.analyzer.current_dial_freq
            
            # Get tiered perspective data
            perspective = self.analyzer.get_target_perspective(
                self.current_target_call, 
                self.current_target_grid
            )
            
            # Convert RF frequencies to audio offsets for each tier
            converted = {}
            for tier_name in ['tier1', 'tier2', 'tier3', 'global']:
                tier_spots = perspective.get(tier_name, [])
                converted[tier_name] = []
                for spot in tier_spots:
                    rf_freq = int(spot.get('freq', 0))
                    offset = rf_freq - dial
                    if 0 <= offset <= 3000:
                        converted[tier_name].append({
                            'freq': offset,
                            'snr': int(spot.get('snr', -10)),
                            'receiver': spot.get('receiver', ''),
                            'sender': spot.get('sender', ''),          # v2.1.1: for tooltip
                            'sender_grid': spot.get('sender_grid', ''),  # v2.1.1: for tooltip
                            'tier': spot.get('tier', 4)
                        })
            
            # Update band map with tiered perspective
            self.band_map.update_perspective(converted)
            
            # Diagnostic: log what we're sending to band map
            total_converted = sum(len(v) for v in converted.values())
            if total_converted == 0 and not hasattr(self, '_empty_perspective_logged'):
                logger.warning(
                    f"Perspective display EMPTY for target={self.current_target_call}, "
                    f"grid='{self.current_target_grid}', dial={dial}"
                )
                self._empty_perspective_logged = True
            elif total_converted > 0:
                self._empty_perspective_logged = False  # Reset so we log if it goes empty again
            
            # v2.1.0: Path Intelligence - find stations near me getting through
            my_grid = self.config.get('ANALYSIS', 'my_grid', fallback='')
            my_call = self.config.get('ANALYSIS', 'my_callsign', fallback='')
            if my_grid and self.local_intel:
                near_me_data = self.analyzer.find_near_me_stations(
                    self.current_target_call,
                    self.current_target_grid,
                    my_grid,
                    my_call  # Exclude my own callsign from the list
                )
                self.local_intel.update_near_me(near_me_data)
            
        else:
            # No dial freq or no target - clear perspective
            self.band_map.update_perspective({
                'tier1': [], 'tier2': [], 'tier3': [], 'global': []
            })
            # v2.1.0: Clear near-me display
            if self.local_intel:
                self.local_intel.update_near_me(None)



    def on_recommendation(self, freq):
        cur = self.band_map.current_tx_freq
        self.dashboard.update_rec(freq, cur)

    def update_status_msg(self, msg):
        # v2.1.1: Save non-warning messages so we can restore after health warnings clear
        if msg and not msg.startswith("⚠"):
            self._normal_status = msg
        self.str_status = msg
        self.update_header()

    def update_header(self):
        s_update = ""
        if self.update_available:
            s_update = f"⬆ v{self.update_available} available — click to download   |   "
            self.info_bar.update_url = "https://github.com/wu2c-peter/qso-predictor/releases"
            self.info_bar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.info_bar.update_url = None
            self.info_bar.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        
        s_solar = getattr(self, 'str_solar', "")
        s_status = getattr(self, 'str_status', "")
        self.info_bar.setText(f"{s_update}{s_solar}   |   {s_status}")
        
        # Update styling based on state
        if self.update_available:
            # Gold/amber for update available
            self.info_bar.setStyleSheet(
                "background-color: #3D3D00; color: #FFD700; padding: 4px; font-weight: bold;"
            )
        elif hasattr(self, 'str_solar') and self.str_solar:
            # Solar-based coloring
            bg_color = "#2A2A2A"
            # Check K index from stored data
            if hasattr(self, '_solar_data'):
                k = self._solar_data.get('k', 0)
                sfi = self._solar_data.get('sfi', 0)
                if k >= 5: bg_color = "#880000"
                elif k >= 4: bg_color = "#884400"
                elif sfi >= 100: bg_color = "#004400"
            self.info_bar.setStyleSheet(
                f"background-color: {bg_color}; color: #FFF; padding: 4px; font-weight: bold;"
            )
        else:
            self.info_bar.setStyleSheet(
                "background-color: #2A2A2A; color: #AAA; padding: 4px;"
            )

    def update_solar_ui(self, data):
        self._solar_data = data  # Store for header styling
        self.str_solar = f"Solar: SFI {data['sfi']} | K {data['k']} ({data['condx']})"
        self.update_header()

    def check_for_updates(self, manual=False):
        """Check GitHub for newer release (runs in background thread)."""
        t = threading.Thread(target=self._update_check_worker, args=(manual,), daemon=True)
        t.start()
    
    def _update_check_worker(self, manual):
        """Worker thread for update check."""
        try:
            import requests  # Lazy import - app works without it
        except ImportError:
            if manual:
                self.update_check_signal.emit("NO_REQUESTS", manual)
            return
        
        try:
            r = requests.get(
                "https://api.github.com/repos/wu2c-peter/qso-predictor/releases/latest",
                timeout=10
            )
            if r.status_code == 200:
                latest = r.json().get('tag_name', '').lstrip('v')
                current = get_version()
                if latest and compare_versions(current, latest):
                    # Update available
                    self.update_check_signal.emit(latest, manual)
                elif manual:
                    # No update, but user asked - tell them they're up to date
                    self.update_check_signal.emit("UP_TO_DATE", manual)
            elif manual:
                # API error
                self.update_check_signal.emit("ERROR", manual)
        except Exception as e:
            if manual:
                self.update_check_signal.emit("ERROR", manual)
            # Fail silently for automatic checks
    
    def on_update_check_result(self, result, was_manual):
        """Handle update check result."""
        if result == "UP_TO_DATE":
            QMessageBox.information(
                self, 
                "Up to Date", 
                f"You're running the latest version (v{get_version()})."
            )
        elif result == "ERROR":
            QMessageBox.warning(
                self, 
                "Update Check Failed",
                "Couldn't reach GitHub to check for updates.\nPlease check your internet connection."
            )
        elif result == "NO_REQUESTS":
            QMessageBox.warning(
                self,
                "Update Check Unavailable",
                "The 'requests' module is not installed.\n\n"
                "To enable update checking, run:\n"
                "  pip install requests"
            )
        else:
            # It's a version number - update available
            self.update_available = result
            self.update_header()
            
            if was_manual:
                # User manually checked - show dialog with option to download
                reply = QMessageBox.information(
                    self,
                    "Update Available",
                    f"A new version is available: v{result}\n\n"
                    f"You're currently running v{get_version()}.\n\n"
                    f"Would you like to open the download page?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    webbrowser.open("https://github.com/wu2c-peter/qso-predictor/releases")

    # --- v2.1.1: Periodic Data Health Check ---
    def _check_data_health(self):
        """Check if UDP and MQTT data sources are flowing.
        
        Called every 10 seconds. Shows/clears status bar warnings when data
        sources go silent, without blocking the main thread.
        """
        warnings = []
        
        # Check UDP health
        if hasattr(self, 'udp') and self.udp:
            udp_ok, udp_msg = self.udp.check_data_health()
            if not udp_ok and udp_msg:
                warnings.append(udp_msg)
        
        # Check MQTT health
        if hasattr(self, 'mqtt') and self.mqtt:
            mqtt_ok, mqtt_msg = self.mqtt.check_data_health()
            if not mqtt_ok and mqtt_msg:
                warnings.append(mqtt_msg)
        
        # Update status bar if warning state changed
        warning_text = "   |   ".join(warnings) if warnings else ""
        if warning_text != self._last_health_warning:
            self._last_health_warning = warning_text
            if warning_text:
                self.update_status_msg(warning_text)
            else:
                # Clear warning - restore normal status
                self.update_status_msg(getattr(self, '_normal_status', ''))
    
    # --- v2.0.9: Startup Health Check ---
    def _start_health_check_timer(self):
        """Start a timer to check if data is being received after startup.
        
        Shows a help dialog if no UDP data detected after 20 seconds.
        Feature added based on user feedback from Doug McDonald.
        """
        # Check after 20 seconds - enough time for:
        # - MQTT to connect
        # - At least one FT8 cycle (15 sec) to complete
        # - Some buffer for slow startup
        QTimer.singleShot(20000, self._check_startup_health)
    
    def _check_startup_health(self):
        """Check if we're receiving data. Show help dialog if not."""
        # Check if user has disabled this popup
        skip_check = self.config.get('UI', 'skip_startup_health_check', fallback='false') == 'true'
        if skip_check:
            return
        
        # Check UDP status using the message counter on udp handler
        has_udp = False
        if hasattr(self, 'udp') and self.udp:
            has_udp = getattr(self.udp, 'messages_received', 0) > 0
        
        # Alternative check using decode count (should match)
        if not has_udp:
            has_udp = self._decode_count > 0
        
        # Check MQTT status - look for indication in status message
        has_mqtt = False
        if hasattr(self, 'str_status'):
            # If status contains "tracking X stations", MQTT is working
            has_mqtt = 'tracking' in self.str_status.lower() or 'stations' in self.str_status.lower()
        
        # If UDP is working, we're good - don't show popup
        if has_udp:
            return
        
        # Show the help dialog
        self._show_startup_health_dialog(has_udp, has_mqtt)
    
    def _show_startup_health_dialog(self, udp_ok, mqtt_ok):
        """Display the startup health check dialog."""
        if not STARTUP_HEALTH_AVAILABLE:
            # Fallback if dialog module not available
            configured_port = self.config.get('NETWORK', 'udp_port', fallback='2237')
            QMessageBox.warning(
                self,
                "No Data Detected",
                f"QSO Predictor isn't receiving data from WSJT-X or JTDX.\n\n"
                f"Please check:\n"
                f"• WSJT-X/JTDX Settings → Reporting → UDP Server\n"
                f"• Port in WSJT-X/JTDX matches QSO Predictor ({configured_port})\n"
                f"• 'Accept UDP Requests' is checked\n\n"
                f"See Help → Documentation for more details."
            )
            return
        
        # Get the configured port to show in dialog
        configured_port = int(self.config.get('NETWORK', 'udp_port', fallback='2237'))
        
        dialog = StartupHealthDialog(
            parent=self,
            udp_ok=udp_ok,
            mqtt_ok=mqtt_ok,
            configured_port=configured_port
        )
        
        result = dialog.exec()
        
        # Handle "don't show again"
        if dialog.dont_show_again:
            self.config.save_setting('UI', 'skip_startup_health_check', 'true')
        
        # Handle "Open Settings" button (custom return code 2)
        if result == 2:
            self.open_settings()
    
    def _show_connection_help(self):
        """Manually show the connection help dialog (from Help menu)."""
        # Get current status
        has_udp = False
        if hasattr(self, 'udp') and self.udp:
            has_udp = getattr(self.udp, 'messages_received', 0) > 0
        if not has_udp:
            has_udp = self._decode_count > 0
        
        has_mqtt = False
        if hasattr(self, 'str_status'):
            has_mqtt = 'tracking' in self.str_status.lower() or 'stations' in self.str_status.lower()
        
        self._show_startup_health_dialog(has_udp, has_mqtt)

    def open_settings(self):
        # Calculate UDP status for settings dialog
        udp_status = self._get_udp_status()
        dlg = SettingsDialog(self.config, self, udp_status=udp_status)
        if dlg.exec():
            self.udp.stop()
            self.udp = UDPHandler(self.config)
            self.udp.start()
            self.setup_connections()
            # Reset decode tracking after settings change
            self._decode_count = 0
            self._decode_start_time = None
    
    def _get_udp_status(self):
        """Get current UDP connection status."""
        from datetime import datetime
        
        if self._decode_start_time is None or self._decode_count == 0:
            return {'receiving': False, 'rate': 0}
        
        elapsed = (datetime.now() - self._decode_start_time).total_seconds()
        if elapsed < 1:
            elapsed = 1  # Avoid division by zero
        
        rate = (self._decode_count / elapsed) * 60  # decodes per minute
        
        return {
            'receiving': self._decode_count > 0,
            'rate': rate
        }

    def open_user_guide(self):
        """Open the User Guide on GitHub (renders markdown nicely)."""
        webbrowser.open("https://github.com/wu2c-peter/qso-predictor/blob/main/docs/USER_GUIDE.md")
    
    # v2.0.9: Debug logging menu handlers
    def _toggle_debug_logging(self, checked):
        """Toggle debug logging on/off.
        
        When enabled, verbose DEBUG level messages are written to log.
        When disabled, only INFO and above are logged.
        """
        set_debug_mode(checked)
        if checked:
            logger.info("Debug logging enabled by user")
            # Show confirmation with log file location
            QMessageBox.information(
                self,
                "Debug Logging Enabled",
                f"Verbose logging is now enabled.\n\n"
                f"Log file location:\n{get_log_file_path()}\n\n"
                f"Note: Debug logging will be disabled on next restart."
            )
        else:
            logger.info("Debug logging disabled by user")
    
    def _open_log_folder(self):
        """Open the log folder in system file browser."""
        open_log_folder()
        logger.info(f"Opened log folder: {get_log_file_path().parent}")
    
    def show_about(self):
        """Show about dialog."""
        version = get_version()
        local_intel_status = "Enabled" if self.local_intel else "Not available"
        log_path = str(get_log_file_path())
        QMessageBox.about(self, "About QSO Predictor",
            f"<h2>QSO Predictor v{version}</h2>"
            f"<p>Real-Time Tactical Assistant for FT8 & FT4</p>"
            f"<p>Copyright © 2025 Peter Hirst (WU2C)</p>"
            f"<p>Licensed under GNU GPL v3</p>"
            f"<p>Insights Engine: {local_intel_status}</p>"
            f"<p>Log file: <small>{log_path}</small></p>"
            f"<p><a href='https://github.com/wu2c-peter/qso-predictor'>GitHub Repository</a></p>"
        )

    def fetch_solar_data(self):
        if not SOLAR_AVAILABLE: return
        t = threading.Thread(target=self._solar_worker, daemon=True)
        t.start()
        
    def _solar_worker(self):
        if self.solar:
            data = self.solar.get_solar_data()
            self.solar_update_signal.emit(data)
    
    # --- v2.1.0: HUNT MODE METHODS ---
    
    def _show_hunt_list_dialog(self):
        """Show the Hunt List management dialog."""
        if not self.hunt_manager:
            return
        dialog = HuntListDialog(self.hunt_manager, self)
        dialog.exec()
        # Refresh table to update highlighting
        self.model.layoutChanged.emit()
    
    def _show_table_context_menu(self, pos):
        """Show context menu for decode table with Hunt Mode options."""
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return
        
        # Get the callsign from the clicked row
        row_data = self.model._data[index.row()]
        callsign = row_data.get('call', '')
        
        if not callsign:
            return
        
        menu = QMenu(self)
        
        # Hunt Mode actions
        if self.hunt_manager:
            if self.hunt_manager.is_hunted(callsign):
                remove_action = menu.addAction(f"Remove {callsign} from Hunt List")
                remove_action.triggered.connect(lambda: self._remove_from_hunt(callsign))
            else:
                add_action = menu.addAction(f"Add {callsign} to Hunt List")
                add_action.triggered.connect(lambda: self._add_to_hunt(callsign))
            
            menu.addSeparator()
        
        # Set as Target action
        target_action = menu.addAction(f"Set {callsign} as Target")
        target_action.triggered.connect(lambda: self.on_row_click(index))
        
        menu.exec(self.table_view.viewport().mapToGlobal(pos))
    
    def _add_to_hunt(self, callsign):
        """Add callsign to hunt list from context menu."""
        if self.hunt_manager and self.hunt_manager.add(callsign):
            self.model.layoutChanged.emit()  # Refresh highlighting
            self.tray_icon.showMessage(
                "Hunt Mode",
                f"Added {callsign} to hunt list",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
    
    def _remove_from_hunt(self, callsign):
        """Remove callsign from hunt list from context menu."""
        if self.hunt_manager and self.hunt_manager.remove(callsign):
            self.model.layoutChanged.emit()  # Refresh highlighting
    
    def _check_hunt_spot(self, spot):
        """Check incoming MQTT spot against hunt list."""
        if not self.hunt_manager or self.hunt_manager.is_empty():
            return
        
        # Check spot against hunt list (handles cooldown internally)
        self.hunt_manager.check_spot(spot, time.time())
    
    def _on_path_analyze_requested(self, stations: list):
        """
        Handle Phase 2 Path Intelligence analysis request.
        
        v2.1.0: Called when user clicks "Analyze" button in Path Intelligence panel.
        Performs reverse PSK Reporter lookups and directional analysis.
        
        Args:
            stations: List of near-me station dicts to analyze
        """
        if not stations:
            return
        
        # Get current target grid
        target_call = self.current_target_call if hasattr(self, 'current_target_call') else ''
        target_grid = self.current_target_grid if hasattr(self, 'current_target_grid') else ''
        
        logger.info(f"Path Intelligence Phase 2: Analyzing {len(stations)} station(s)")
        
        # Perform analysis for each station
        results = []
        for station in stations[:3]:  # Limit to 3 to avoid too many API calls
            try:
                result = self.analyzer.analyze_near_me_station(
                    station=station,
                    all_near_me=stations,
                    target_grid=target_grid
                )
                results.append(result)
                logger.debug(f"Analyzed {station.get('call', '?')}: {result.get('insights', [])}")
            except Exception as e:
                logger.error(f"Phase 2 analysis error for {station.get('call', '?')}: {e}")
                results.append({
                    'call': station.get('call', '?'),
                    'error': str(e),
                    'insights': [f"⚠️ Analysis failed: {e}"]
                })
        
        # Send results back to insights panel
        if self.local_intel and self.local_intel.insights_panel:
            self.local_intel.insights_panel.update_path_analysis_results(results)
    
    def _on_hunt_alert(self, call, band, alert_type, details):
        """Handle hunt alert - show notification to user."""
        # Don't show notifications if we're closing
        if getattr(self, '_closing', False):
            return
        
        if alert_type == 'working_nearby':
            # High priority - propagation path to your region confirmed!
            title = f"🎯 {call} Heard Nearby!"
            message = f"{call} on {band}: {details}"
            icon = QSystemTrayIcon.MessageIcon.Warning
            duration = 5000
        else:
            # Normal - they're just active
            title = f"📡 {call} Active"
            message = f"{call} spotted on {band}"
            icon = QSystemTrayIcon.MessageIcon.Information
            duration = 3000
        
        # System tray notification
        self.tray_icon.showMessage(title, message, icon, duration)
        
        # Also update status bar briefly
        self.update_status_msg(f"Hunt: {call} {alert_type} on {band}")

    def closeEvent(self, event):
        # --- v2.1.0: Flag to prevent notifications during shutdown ---
        self._closing = True
        
        # --- LOCAL INTELLIGENCE: Clean shutdown ---
        if self.local_intel:
            try:
                self.local_intel.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down Local Intelligence: {e}")
        
        self.analyzer.stop()
        self.udp.stop()
        
        # --- v2.1.0: Hide and cleanup tray icon to stop notifications ---
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.setVisible(False)
        
        # --- v2.0.3: Save window geometry ---
        geo = self.saveGeometry().toHex().data().decode()
        self.config.save_setting('WINDOW', 'geometry', geo)
        
        # --- v2.1.0: Save dock widget positions ---
        dock_state = self.saveState().toHex().data().decode()
        self.config.save_setting('WINDOW', 'dock_state', dock_state)
        
        # --- v2.0.3: Save column widths ---
        self._save_column_widths()
        
        event.accept()

if __name__ == "__main__":
    # Set Windows taskbar app ID (Windows only)
    if sys.platform == 'win32':
        try:
            myappid = 'wu2c.qsopredictor.v2.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # v2.1.1: Explicit QToolTip styling — prevents black-on-black on dark widgets (Windows)
    app.setStyleSheet("""
        QToolTip {
            background-color: #2A2A2A;
            color: #00FFFF;
            border: 1px solid #555;
            padding: 4px;
            font-family: Consolas, monospace;
            font-size: 9pt;
        }
    """)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
