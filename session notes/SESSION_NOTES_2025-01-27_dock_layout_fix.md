# QSO Predictor Session Notes
**Date:** January 27, 2025  
**Version:** 2.1.0  
**Session:** Windows Dock Layout Fix (CRITICAL - DO NOT BREAK)

---

## The Problem

On Windows, the Local Intelligence panel (right dock) was pushing the Target View (band map) off the bottom of the screen. The decode table was too tall and couldn't be resized vertically.

**Symptoms:**
- Decode window took too much vertical space
- Band map pushed off bottom of screen
- Vertical divider between decode and band map wouldn't move
- Horizontal divider (decode ↔ local intel) worked fine
- Worked correctly on Mac, broken on Windows

**Key Observation from Peter:**
> "On mac the local intel takes the whole right side... On windows the band map is full width"

This revealed the `setCorner()` was being applied opposite on the two platforms.

---

## Root Cause

**Qt's `restoreState()` overrides `setCorner()` on Windows.**

The saved dock state from previous sessions was restoring the corner ownership, undoing our `setCorner()` calls that were made earlier in `init_ui()`.

Additionally, the order of adding docks matters - the right dock must be added FIRST to claim the corners.

---

## The Solution (DO NOT CHANGE)

### 1. setCorner() in init_ui() (line ~789)
```python
self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
```
This makes the right dock span full height, bottom dock only spans left of it.

### 2. Re-apply setCorner() AFTER restoreState() (line ~1132)
```python
dock_state = self.config.get('WINDOW', 'dock_state')
if dock_state:
    self.restoreState(QByteArray.fromHex(dock_state.encode()))
    
    # CRITICAL: Re-apply corner ownership AFTER restoreState
    # On Windows, restoreState can override setCorner
    self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
    self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
```

### 3. Reset Layout must also re-apply (in _reset_layout())
```python
# Re-apply corner ownership BEFORE re-docking
self.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)
self.setCorner(Qt.Corner.TopRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

# Remove docks first
self.removeDockWidget(self.target_dock)
if self.local_intel and self.local_intel.insights_dock:
    self.removeDockWidget(self.local_intel.insights_dock)

# Re-add RIGHT dock FIRST (so it claims corners), then BOTTOM
if self.local_intel and self.local_intel.insights_dock:
    self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, ...)
    
self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.target_dock)
```

### 4. Minimum height for Target View (line ~965)
```python
target_container.setMinimumHeight(380)  # Shows all band map sections including local decodes
```

---

## Correct Layout

```
┌─────────────────────────────┬──────────────────┐
│   Decode Table              │                  │
│   (can resize vertically)   │  Local Intel     │
├─────────────────────────────┤  (full height)   │
│   Target View               │                  │
│   (Dashboard + Band Map)    │                  │
└─────────────────────────────┴──────────────────┘
```

- Right dock (Local Intel) spans FULL HEIGHT
- Bottom dock (Target View) only spans LEFT of right dock
- Vertical divider between decode and band map IS MOVABLE
- Horizontal divider between decode and local intel IS MOVABLE

---

## What NOT To Do

❌ **NEVER suggest replacing docks with QSplitter** - we spent hours on this and docks work correctly now

❌ **NEVER remove the setCorner() calls** - they are critical for correct layout

❌ **NEVER remove the post-restoreState setCorner()** - Windows needs this

❌ **NEVER change the dock addition order** - right dock must be added FIRST

---

## Other Fixes in This Session

1. **QSizePolicy import error** - Removed redundant local import inside `init_ui()` that was shadowing the top-level import

2. **Central widget size policy** - Set to `QSizePolicy.Policy.Ignored` vertically so it yields space to bottom dock

---

## Files Modified

| File | Changes |
|------|---------|
| `main_v2.py` | setCorner() placement, restoreState fix, _reset_layout fix, min height 380px |

---

## Testing Checklist

- [ ] Windows: Layout correct on fresh start (no config)
- [ ] Windows: Layout correct after View → Reset Layout
- [ ] Windows: Vertical divider between decode/band map movable
- [ ] Windows: Local Intel spans full height
- [ ] Windows: Band map shows all sections (including local decode bars at bottom)
- [ ] Mac: Still works correctly (regression test)

---

## Session Statistics

- **Duration:** ~2 hours
- **Iterations:** Many (too many)
- **Root cause:** Qt restoreState() overrides setCorner() on Windows
- **Key insight:** Peter noticed Mac vs Windows had opposite dock corner ownership

---

**REMEMBER: The dock layout works. Don't break it. Don't suggest splitters.**

**73 de WU2C & Claude**
