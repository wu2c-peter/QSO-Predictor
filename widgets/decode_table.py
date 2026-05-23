"""Qt model and delegate for the live decode table.

DecodeTableModel exposes decode rows to QTableView, mapping column names
to row-dict keys and providing color/alignment hints by role.
HuntHighlightDelegate paints model-supplied BackgroundRole colors so
hunt-list highlights survive the table's stylesheet overrides.

Copyright (C) 2025 Peter Hirst (WU2C)
"""

import logging

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QStyledItemDelegate

from local_intel.models import PathStatus

logger = logging.getLogger(__name__)


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
                status = PathStatus.from_display(str(row_item.get('path', '')))
                if status != PathStatus.UNKNOWN:
                    return QColor(status.color)

        elif role == Qt.ItemDataRole.BackgroundRole:
            # Highlight rows based on path status and hunt mode
            status = PathStatus.from_display(str(row_item.get('path', '')))
            bg = status.row_background
            if bg is not None:
                return QColor(bg)

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
