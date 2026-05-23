"""Header dashboard for the current target station.

Renders callsign, last decode summary (UTC/SNR/DT/Freq/Message/Grid),
score, path status, competition, and target activity state. Also hosts
the WSJT-X sync button, manual-target entry, and the recommended-frequency
display (click-to-copy).

Copyright (C) 2025 Peter Hirst (WU2C)
"""

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from local_intel.models import PathStatus

from .clickable_labels import ClickableCopyLabel


class TargetDashboard(QFrame):
    # v2.0.6: Signal when user wants to sync target to JTDX
    sync_requested = pyqtSignal()
    # v2.1.0: Signal for status bar messages (e.g., clipboard feedback)
    status_message = pyqtSignal(str)
    # v2.4.4: Signal when user manually enters a target callsign
    manual_target_requested = pyqtSignal(str)

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

        # v2.4.4: Manual target entry button and field
        self.btn_manual = QPushButton("+")
        self.btn_manual.setObjectName("sync")  # Reuse sync styling
        self.btn_manual.setToolTip("Manually enter a target callsign")
        self.btn_manual.setFixedSize(28, 28)
        self.btn_manual.clicked.connect(self._toggle_manual_entry)
        layout.addWidget(self.btn_manual)

        self.manual_entry = QLineEdit()
        self.manual_entry.setPlaceholderText("Enter callsign...")
        self.manual_entry.setFixedWidth(140)
        self.manual_entry.setStyleSheet("""
            QLineEdit {
                background-color: #1a1a2e;
                color: #FF00FF;
                border: 1px solid #00AAAA;
                border-radius: 3px;
                padding: 2px 4px;
                font-size: 14pt;
                font-weight: bold;
                font-family: Consolas, monospace;
            }
        """)
        self.manual_entry.returnPressed.connect(self._submit_manual_entry)
        # Escape cancels manual entry
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.manual_entry)
        esc_shortcut.activated.connect(self._toggle_manual_entry)
        self.manual_entry.hide()
        layout.addWidget(self.manual_entry)

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
        # v2.4.4: Strip manual target indicator before copying
        clean_text = text.replace("⚠ ", "").strip()
        if clean_text and clean_text != "NO TARGET":
            clipboard = QApplication.clipboard()
            clipboard.setText(clean_text)
            # Brief visual feedback
            original_text = text
            self.lbl_target.setText(f"✓ Copied!")
            self.status_message.emit(f"Copied to clipboard: {clean_text}")
            # Restore after 1 second
            QTimer.singleShot(1000, lambda: self.lbl_target.setText(original_text))

    def _toggle_manual_entry(self):
        """v2.4.4: Toggle manual target entry field visibility."""
        if self.manual_entry.isVisible():
            self.manual_entry.hide()
            self.manual_entry.clear()
            self.lbl_target.show()
        else:
            self.manual_entry.show()
            self.manual_entry.clear()
            self.manual_entry.setFocus()
            self.lbl_target.hide()

    def _submit_manual_entry(self):
        """v2.4.4: Submit manually entered callsign."""
        call = self.manual_entry.text().strip().upper()
        self.manual_entry.hide()
        self.manual_entry.clear()
        self.lbl_target.show()
        if call:
            self.manual_target_requested.emit(call)

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

        # v2.4.4: Show "⚠" prefix for manual targets not yet decoded locally
        call_display = data.get('call', '???')
        if data.get('manual_target'):
            call_display = f"⚠ {call_display}"
        self.lbl_target.setText(call_display)
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
        status = PathStatus.from_display(path)
        my_snr = data.get('my_snr_at_target', None)
        path_age = data.get('path_heard_age', None)  # v2.5.1: seconds since heard
        path_stale = data.get('path_stale', False)    # v2.5.1: target uploaded without us

        # v2.5.1: Build path display with freshness and staleness
        path_display = path
        if status in (PathStatus.HEARD_BY_TARGET, PathStatus.REPORTED_IN_REGION):
            short = status.short_label

            snr_part = ""
            if my_snr is not None:
                snr_str = f"{my_snr:+d}" if isinstance(my_snr, int) else str(my_snr)
                snr_part = f" ({snr_str} dB)"

            age_part = ""
            if path_age is not None:
                if path_age < 60:
                    age_part = f" {path_age}s"
                else:
                    age_part = f" {path_age // 60}m ago"

            if path_stale and status == PathStatus.HEARD_BY_TARGET:
                # Target's decoder was active after hearing us but didn't
                # hear us in latest batch — signal may have faded
                age_str = f"{path_age // 60}m" if path_age and path_age >= 60 else f"{path_age}s"
                path_display = f"Was Heard ({age_str} ago)"
            else:
                path_display = f"{short}{snr_part}{age_part}"

        self.val_path.setText(path_display)

        # Color coding — stale-heard gets a distinct amber warning; otherwise
        # let the enum drive color and tooltip.
        if path_stale and status == PathStatus.HEARD_BY_TARGET:
            self.val_path.setStyleSheet("color: #FFAA00; font-weight: bold;")
            self.val_path.setToolTip("Target uploaded newer spots without you — signal may have faded")
        else:
            weight = "" if status == PathStatus.UNKNOWN else " font-weight: bold;"
            self.val_path.setStyleSheet(f"color: {status.color};{weight}")
            self.val_path.setToolTip(status.tooltip)

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
