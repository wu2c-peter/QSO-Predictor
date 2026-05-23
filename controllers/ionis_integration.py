"""IONIS propagation engine integration controller.

Owns the IonisEngine instance and the bridge from prediction results to
the InsightsPanel's PropagationWidget. Compares ML predictions against
PSK Reporter observations to produce the vs-reality classification.

Engine state (`_ionis_engine`, `_ionis_shown`) and dependencies on
`current_target_call`, `current_target_grid`, `analyzer`, `_solar_data`,
`local_intel`, and `_current_band` are read from MainWindow directly —
this controller is a "methods home" pulling the IONIS workflow out of
MainWindow without rearranging unrelated state.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging

from PyQt6.QtCore import QObject

try:
    from ionis import IonisEngine
    IONIS_AVAILABLE = True
except ImportError:
    IONIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class IonisIntegration(QObject):
    """Drive the IONIS propagation engine and update its insights widget."""

    MARGINAL_THRESHOLD = -25.0

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        if IONIS_AVAILABLE:
            self._init_engine()

    def _init_engine(self):
        """Initialize IONIS propagation engine v2.4.0."""
        mw = self.main_window
        try:
            ionis_enabled = mw.config.get('IONIS', 'enabled', fallback='true') == 'true'
            if not ionis_enabled:
                logger.info("IONIS propagation engine disabled in settings")
                return

            mw._ionis_engine = IonisEngine()
            if mw._ionis_engine.is_available():
                logger.info("IONIS propagation engine initialized")
            else:
                logger.warning("IONIS engine created but model not available")
                mw._ionis_engine = None
        except Exception as e:
            logger.error(f"Failed to initialize IONIS engine: {e}")
            mw._ionis_engine = None

    def update_prediction(self):
        """Recompute IONIS propagation prediction for current target.

        Called on: target change, band change, solar data refresh.
        Pushes results to PropagationWidget in Insights Panel.
        """
        mw = self.main_window
        if not mw._ionis_engine or not mw._ionis_engine.is_available():
            return

        # Need target grid and current band
        if not mw.current_target_grid:
            self._show_waiting("Awaiting target grid…")
            return
        band = getattr(mw, '_current_band', None)
        # v2.4.4: Derive band from MQTT dial frequency if UDP not connected
        if not band and mw.analyzer.current_dial_freq > 0:
            band = mw._freq_to_band(mw.analyzer.current_dial_freq)
        if not band:
            self._show_waiting("Awaiting band info…")
            return

        # Need our own grid
        my_grid = mw.config.get('ANALYSIS', 'my_grid', fallback='')
        if not my_grid or my_grid == 'FN00aa':
            return

        # Get solar conditions (default to safe values if not yet fetched)
        sfi = 100
        kp = 2
        if hasattr(mw, '_solar_data') and mw._solar_data:
            sfi = mw._solar_data.get('sfi', 100)
            kp = mw._solar_data.get('k', 2)

        try:
            # Single prediction for current conditions
            prediction = mw._ionis_engine.predict(
                my_grid, mw.current_target_grid, band, sfi, kp
            )

            if prediction:
                prediction['tx_grid'] = my_grid[:4].upper()
                prediction['rx_grid'] = mw.current_target_grid[:4].upper()

            # 12-hour forecast
            forecast = mw._ionis_engine.predict_range(
                my_grid, mw.current_target_grid, band, sfi, kp, hours=12
            )

            # vs-reality comparison
            vs_reality = self._compute_vs_reality(prediction)

            # Push to widget
            if (mw.local_intel and
                    hasattr(mw.local_intel, 'insights_panel') and
                    mw.local_intel.insights_panel):
                panel = mw.local_intel.insights_panel
                panel.propagation_widget.show()
                panel.propagation_widget.update_display(
                    prediction, forecast, vs_reality)
                panel.propagation_widget.set_conditions(sfi, kp)
                mw._ionis_shown = True

        except Exception as e:
            logger.debug(f"IONIS prediction error: {e}")

    def _compute_vs_reality(self, prediction: dict) -> str:
        """Compare IONIS prediction against PSK Reporter observations.

        Checks whether there are recent spots from our field arriving
        at the target's area — not just any activity at the target.
        This confirms the specific path IONIS is predicting.

        Args:
            prediction: dict from IonisEngine.predict()

        Returns:
            One of: confirmed, unconfirmed, better_than_expected,
                    closed, unexpected_opening, unknown
        """
        mw = self.main_window
        if not prediction:
            return 'unknown'

        ionis_open = prediction.get('ft8_open', False)
        ionis_snr = prediction.get('snr_db', -40)

        # Check PSK Reporter data: are there spots FROM OUR AREA
        # arriving at the target's area? Filter tier 1-3 spots by
        # sender grid matching our field (first 2 chars).
        psk_has_path_spots = False
        try:
            my_grid = mw.config.get('ANALYSIS', 'my_grid', fallback='')
            my_field = my_grid[:2].upper() if len(my_grid) >= 2 else ''

            if my_field and hasattr(mw, 'analyzer') and mw.analyzer:
                perspective = mw.analyzer.get_target_perspective(
                    mw.current_target_call, mw.current_target_grid
                )
                if perspective:
                    # Count spots where sender is from our field
                    for tier_key in ('tier1', 'tier2', 'tier3'):
                        for spot in perspective.get(tier_key, []):
                            sender_grid = spot.get('sender_grid', '')
                            if (len(sender_grid) >= 2 and
                                    sender_grid[:2].upper() == my_field):
                                psk_has_path_spots = True
                                break
                        if psk_has_path_spots:
                            break
        except Exception:
            pass

        if ionis_open and psk_has_path_spots:
            return 'confirmed'
        elif ionis_open and not psk_has_path_spots:
            return 'unconfirmed'
        elif not ionis_open and ionis_snr >= self.MARGINAL_THRESHOLD and psk_has_path_spots:
            return 'better_than_expected'
        elif not ionis_open and not psk_has_path_spots:
            return 'closed'
        elif not ionis_open and psk_has_path_spots:
            return 'unexpected_opening'
        return 'unknown'

    def clear_prediction(self):
        """Clear and hide the IONIS propagation display."""
        mw = self.main_window
        if (mw.local_intel and
                hasattr(mw.local_intel, 'insights_panel') and
                mw.local_intel.insights_panel):
            panel = mw.local_intel.insights_panel
            panel.propagation_widget.clear()
            panel.propagation_widget.hide()

    def _show_waiting(self, message: str):
        """Show a waiting message in the IONIS widget."""
        mw = self.main_window
        if (mw.local_intel and
                hasattr(mw.local_intel, 'insights_panel') and
                mw.local_intel.insights_panel):
            panel = mw.local_intel.insights_panel
            panel.propagation_widget.show()
            panel.propagation_widget.prediction_label.setText(message)
            panel.propagation_widget.prediction_label.setStyleSheet("color: #888888;")
