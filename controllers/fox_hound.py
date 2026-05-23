"""Fox/Hound mode controller.

Coordinates the F/H state machine: combo-box selection, UDP-driven
detection, SuperFox decode inference, and the "Fox is calling YOU"
transition. State attributes still live on MainWindow (`_fh_active`,
`_fh_source`, `_fh_type`, `_fh_fox_qso`, `_fh_dialog_shown`) because
several other code paths read them directly; this controller is a
"methods home" that doesn't change ownership.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QMessageBox

logger = logging.getLogger(__name__)


class FoxHoundController(QObject):
    """Drive the Fox/Hound (and SuperFox/Hound) mode state machine."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window

    def on_combo_changed(self, index):
        """Handle F/H combo box selection: 0=Off, 1=F/H, 2=SuperF/H."""
        labels = ['Off', 'F/H', 'SuperF/H']
        logger.info(f"Fox/Hound: Combo box changed to {labels[index]} (index={index})")
        if index == 0:
            self.set_active(False, None, None)
        elif index == 1:
            self.set_active(True, 'manual', 'fh')
        elif index == 2:
            self.set_active(True, 'manual', 'superfh')

    def show_disambiguation_dialog(self, source):
        """Show dialog asking user to choose between old F/H and SuperF/H.

        Called when UDP detects Hound mode but can't tell which type.
        Only shown once per session (reset on target change or manual override).

        Args:
            source: 'udp' — what triggered the detection
        """
        mw = self.main_window
        if mw._fh_dialog_shown:
            return
        mw._fh_dialog_shown = True

        logger.info(f"Fox/Hound: Disambiguation dialog triggered (source={source})")

        title = "Hound Mode Detected"
        text = "WSJT-X reports Hound mode is active."

        msg = QMessageBox(mw)
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
            self.set_active(True, source, 'fh')
        elif clicked == btn_sfh:
            logger.info("Fox/Hound: User selected SuperFox/Hound")
            self.set_active(True, source, 'superfh')
        else:
            logger.info("Fox/Hound: User clicked Ignore")

    def set_active(self, active, source, fh_type):
        """Master F/H state setter — called by all triggers.

        Args:
            active: True to enable F/H mode
            source: 'manual', 'udp', or 'inferred'
            fh_type: 'fh' (old-style, clamp 1000+) or 'superfh' (full band)
        """
        mw = self.main_window
        if active == mw._fh_active and source == mw._fh_source and fh_type == mw._fh_type:
            return  # No change

        prev_active = mw._fh_active
        prev_type = mw._fh_type
        mw._fh_active = active
        mw._fh_source = source if active else None
        mw._fh_type = fh_type if active else None

        # Only clamp to 1000+ Hz for old-style F/H, not SuperFox
        use_clamping = active and fh_type == 'fh'
        mw.band_map.set_hound_mode(use_clamping)

        # Update combo box (without re-triggering signal)
        mw.cmb_fh_mode.blockSignals(True)
        if not active:
            mw.cmb_fh_mode.setCurrentIndex(0)  # Off
        elif fh_type == 'fh':
            mw.cmb_fh_mode.setCurrentIndex(1)  # F/H
        elif fh_type == 'superfh':
            mw.cmb_fh_mode.setCurrentIndex(2)  # SuperF/H
        mw.cmb_fh_mode.blockSignals(False)

        # Toast on state change
        if active and not prev_active:
            if fh_type == 'fh':
                mw.tactical_toast.show_toast(
                    "🦊 F/H mode — recommendations clamped to 1000+ Hz", 'info'
                )
            elif fh_type == 'superfh':
                mw.tactical_toast.show_toast(
                    "🦊 SuperFox mode — full band available, finding best frequency", 'info'
                )
            logger.info(f"Fox/Hound: ACTIVATED (source={source}, type={fh_type})")
        elif active and prev_active and fh_type != prev_type:
            # Type changed while active
            logger.info(f"Fox/Hound: Type changed to {fh_type}")
        elif not active and prev_active:
            mw.tactical_toast.show_toast(
                "F/H mode disabled — full frequency range restored", 'info'
            )
            # Reset Fox QSO state
            mw._fh_fox_qso = False
            mw.band_map.set_fox_qso(False)
            mw._fh_dialog_shown = False
            logger.info("Fox/Hound: DEACTIVATED")

    def check_superfox_from_decodes(self, message):
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
        mw = self.main_window
        if not mw.current_target_call or not message:
            return

        msg_lower = message.lower()
        if (('verified' in msg_lower or '$verify$' in msg_lower) and
            mw.current_target_call.upper() in message.upper() and
            mw._fh_type != 'superfh'):
            logger.info(f"Fox/Hound: SuperFox detected — 'verified' in decode for {mw.current_target_call}")
            self.set_active(True, 'inferred', 'superfh')
            mw.tactical_toast.show_toast(
                f"🦊 {mw.current_target_call} is verified SuperFox — full band available", 'info'
            )

    def set_fox_qso_active(self, active):
        """v2.3.0: Set Fox QSO state — Fox is controlling our TX frequency.

        When active, click-to-set is disabled and recommendation line hidden.
        Called when activity state detects Fox responding to us.
        """
        mw = self.main_window
        if active == mw._fh_fox_qso:
            return

        mw._fh_fox_qso = active
        mw.band_map.set_fox_qso(active)

        if active:
            if mw._fh_type == 'superfh':
                mw.tactical_toast.show_toast(
                    "🎯 Fox is calling you — stay on your frequency!", 'success'
                )
            else:
                mw.tactical_toast.show_toast(
                    "🎯 Fox is calling you — TX frequency under Fox control!", 'success'
                )
            logger.info("Fox/Hound: Fox QSO active — click-to-set disabled")
        else:
            logger.info("Fox/Hound: Fox QSO ended — click-to-set restored")
