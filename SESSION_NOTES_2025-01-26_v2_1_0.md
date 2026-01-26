# QSO Predictor Session Notes
**Date:** January 26, 2025  
**Version:** 2.1.0  
**Session:** Hunt Mode debugging and row highlighting

---

## Features Implemented in v2.1.0

### Hunt Mode (Complete Feature)
- **Hunt List Management** - Add/remove callsigns, prefixes, grids, DXCC entities
- **MQTT Alerts** - Tray notifications when hunted stations spotted
- **Table Highlighting** - Gold background for hunted stations in decode table
- **Context Menu** - Right-click to add station to hunt list
- **Hunt Dialog** - Tools → Hunt List to manage targets
- **Persistence** - Hunt list saved to config file

### Auto-Clear on QSY
- **New checkbox** "Auto-clear on QSY" in toolbar
- Detects band changes via dial frequency
- Clears decode table, band map, AND target selection
- Setting persists between sessions
- Code location: `main_v2.py` → `handle_status_update()`

### Path Status Row Highlighting
- **CONNECTED** → Teal background (#004040)
- **Path Open** → Dark green background (#002800)
- Visual scanning to quickly find workable stations

### Click-to-Clipboard (Band Map)
- Click anywhere on band map copies frequency to clipboard
- Cursor changes to pointing hand to indicate clickability
- Toast notification confirms copy

---

## Key Bug Fixes

### Hunt Highlighting Not Showing (Major Debug Session)
**Problem:** Hunt list worked for MQTT alerts but gold highlighting never appeared in decode table.

**Root Cause:** Qt stylesheet `QTableView::item` was completely overriding the model's `BackgroundRole` data. The model was returning the correct color but the view ignored it.

**Solution:** Created custom `HuntHighlightDelegate` that explicitly paints backgrounds before default rendering:

```python
class HuntHighlightDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        bg_color = index.data(Qt.ItemDataRole.BackgroundRole)
        if bg_color and isinstance(bg_color, QColor):
            painter.fillRect(option.rect, QBrush(bg_color))
        super().paint(painter, option, index)
```

**Debugging Journey:**
1. Initially thought hunt_manager wasn't assigned to model
2. Added debug logging - showed is_hunted() returning True
3. Realized model was correct, view was ignoring it
4. Tried removing stylesheet backgrounds - didn't help
5. Tried setAlternatingRowColors(False) - didn't help
6. Finally: custom delegate that paints BEFORE default render

**For Paper:** Example of Qt's layered architecture where each layer can override previous. Stylesheet > Model roles unless you use delegates.

### Selection Color Confusion
**Problem:** Clicking a row showed teal, same as CONNECTED status.

**Fix:** Changed selection color from #004444 (teal) to #1a3a5c (blue) in stylesheet.

### USA Entity Not Matching
**Problem:** Adding "USA" to hunt list didn't highlight US stations.

**Fix:** Added "USA" as alias for "UNITED STATES" in DXCC_ENTITIES dictionary.

### Tray Notifications After Close
**Problem:** System tray notifications continued appearing after closing application.

**Fix:** Added `_closing` flag, check before showing notifications, proper tray cleanup in closeEvent().

### Qt objectName Warnings
**Problem:** Console warnings about objectName not set for QDockWidget and QToolBar.

**Fix:** Added `setObjectName()` calls for toolbar and dock widgets.

---

## Technical Details

### Row Background Color Priority
```
1. CONNECTED → Teal (#004040)
2. Path Open → Dark Green (#002800)
3. Hunted → Gold (#7A5500)
4. Target selected → Teal (#004444)
5. Alternating → #141414 / #1c1c1c
```

### Hunt Mode Data Flow
```
MQTT spots arrive
    ↓
hunt_manager.check_spot() evaluates
    ↓
If hunted: emit hunt_alert signal
    ↓
_on_hunt_alert() shows tray notification
```

```
Local decodes arrive
    ↓
DecodeTableModel.data(BackgroundRole) called
    ↓
hunt_manager.is_hunted(call) checked
    ↓
If True: return QColor("#7A5500")
    ↓
HuntHighlightDelegate.paint() renders background
```

### Auto-Clear on QSY Flow
```
JTDX changes band
    ↓
UDP status update sent
    ↓
handle_status_update() receives
    ↓
_freq_to_band() converts Hz to band string
    ↓
Compares to _current_band
    ↓
If changed AND checkbox enabled:
    - model.clear()      # Clear decode table
    - band_map.clear()   # Clear band map
    - clear_target()     # Clear target selection
```

### DXCC Entity Matching
```python
# Hunt list contains "USA" or "UNITED STATES"
DXCC_ENTITIES = {
    "UNITED STATES": ["K", "W", "N", "AA", "AB", ...],
    "USA": ["K", "W", "N", "AA", "AB", ...],  # Alias
    ...
}

def is_hunted(callsign):
    for hunt_item in hunt_list:
        if hunt_item in DXCC_ENTITIES:
            for prefix in DXCC_ENTITIES[hunt_item]:
                if callsign.startswith(prefix):
                    return True
    return False
```

---

## Files Modified

| File | Changes |
|------|---------|
| `main_v2.py` | HuntHighlightDelegate, BackgroundRole colors, auto-clear on QSY, selection color, objectName |
| `hunt_manager.py` | USA alias, is_hunted() cleanup |
| `band_map_widget.py` | clear() method for band change |
| `hunt_dialog.py` | Broad target warning dialog |
| `local_intel_integration.py` | objectName for dock widget |

---

## Color Legend (For Documentation)

| Background Color | Hex Code | Meaning |
|------------------|----------|---------|
| Teal | #004040 | CONNECTED - target heard you! |
| Dark Green | #002800 | Path Open - propagation confirmed |
| Gold/Amber | #7A5500 | Hunted station from your list |
| Blue | #1a3a5c | Selected row (clicked) |
| Dark Gray | #141414 | Normal even row |
| Lighter Gray | #1c1c1c | Normal odd row |

---

## Contributors

### Brian KB1OPD
- **Request:** Auto-clear on band change ("clear on QSY")
- Implemented in this session

### Warren KC0GU
- **Hunt Mode concept** from v2.0.3 planning
- Fully implemented in v2.1.0

---

## Lessons Learned

### For AI-Assisted Development

1. **Qt styling layers:** Stylesheets override model data roles. Custom delegates are the escape hatch.

2. **Debugging visual issues:** When "the code is right but nothing shows", look at the rendering pipeline, not the data.

3. **Iterative debugging:** Added logging at each layer (model init, model data(), is_hunted()) to narrow down where the break occurred.

4. **Human observation value:** Peter spotted that alternating colors weren't showing and that some rows had unexpected colors - led to discovering the stylesheet override.

### For Future Sessions

1. When Qt model data isn't rendering, check if stylesheet is overriding
2. Custom delegates bypass stylesheet limitations
3. Selection styling applies on top of everything - use distinct colors
4. Test highlighting features with multiple match types (exact, prefix, entity)

---

## Session Statistics

- **Duration:** ~4 hours
- **Iterations on highlight fix:** 5+ 
- **Root cause discovery:** Qt stylesheet overrides model roles
- **Files modified:** 5
- **New features:** 3 (hunt highlighting, path highlighting, auto-clear QSY)
- **Bugs fixed:** 5

---

## Next Steps (v2.1.0 Release)

1. [ ] Final testing of all highlighting combinations
2. [ ] Test auto-clear on QSY with real band changes
3. [ ] Update Wiki documentation
4. [ ] Create release notes
5. [ ] Build and publish

---

**73 de WU2C**
