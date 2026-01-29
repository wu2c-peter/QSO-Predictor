# AutoHotkey Guide: Paste TX Frequency to WSJT-X / JTDX

**For Windows users who want to quickly paste QSO Predictor's recommended frequency**

## Overview

This guide shows you how to set up **one-click frequency transfer** from QSO Predictor to WSJT-X or JTDX.

**The magic workflow:**
1. Click band map or Rec frequency in QSO Predictor
2. **That's it!** — Frequency automatically appears in WSJT-X/JTDX

No hotkeys needed — the script detects when you copy a frequency from QSO Predictor and auto-pastes it.

---

## Quick Start

### Step 1: Install AutoHotkey

1. Download AutoHotkey v2.0 from: https://www.autohotkey.com/
2. Run the installer
3. Choose "AutoHotkey v2" (recommended)

### Step 2: Find Your TX Field Coordinates

Since WSJT-X and JTDX don't expose control names, we use click coordinates instead.

1. Search for **"Window Spy"** in Start menu and open it
2. Check **"Follow Mouse"** at the top
3. Open WSJT-X or JTDX
4. Hover your mouse directly over the **TX frequency input field** (the spinbox where you type Hz)
5. Note the **Client** coordinates (e.g., `Client: 595, 485`)

**Important:** Use the **Client** coordinates, not Screen coordinates. These are relative to the window.

### Step 3: Create the Auto-Paste Script

Create a file called `QSOPredictor_AutoPaste.ahk` with this content:

```autohotkey
#Requires AutoHotkey v2.0

; =============================================================
; QSO Predictor Auto-Paste Script
; Automatically pastes frequency to WSJT-X/JTDX when you click
; the band map or Rec frequency in QSO Predictor
; =============================================================

; IMPORTANT: Update these coordinates using Window Spy!
; Hover over the TX frequency field, note the CLIENT coordinates
WSJTX_TX_X := 595    ; X coordinate for WSJT-X TX freq field
WSJTX_TX_Y := 485    ; Y coordinate for WSJT-X TX freq field

JTDX_TX_X := 595     ; X coordinate for JTDX TX freq field
JTDX_TX_Y := 485     ; Y coordinate for JTDX TX freq field

; Monitor clipboard for changes
OnClipboardChange ClipboardChanged

ClipboardChanged(dataType)
{
    ; Only process text
    if dataType != 1
        return
    
    ; Only trigger if QSO Predictor was the active window
    if !WinActive("QSO Predictor")
        return
    
    freq := A_Clipboard
    
    ; Check if it looks like an FT8 frequency (300-3000 Hz)
    if !RegExMatch(freq, "^\d{3,4}$")
        return
    if (freq < 300 || freq > 3000)
        return
    
    ; Find and paste to WSJT-X or JTDX
    if WinExist("WSJT-X")
        PasteToTxFreq("WSJT-X", WSJTX_TX_X, WSJTX_TX_Y, freq)
    else if WinExist("JTDX")
        PasteToTxFreq("JTDX", JTDX_TX_X, JTDX_TX_Y, freq)
}

PasteToTxFreq(windowTitle, clickX, clickY, freq)
{
    try {
        WinActivate windowTitle
        WinWaitActive windowTitle,, 2
        
        ; Click on the TX frequency field
        Click clickX, clickY
        Sleep 50
        
        Send "^a"      ; Select all
        Sleep 20
        Send freq      ; Type the frequency
        Send "{Enter}" ; Confirm
        
        ; Optional: Show confirmation tooltip
        ToolTip "TX Freq → " freq " Hz"
        SetTimer () => ToolTip(), -1500  ; Clear after 1.5 seconds
    } catch {
        ToolTip "Could not paste to " windowTitle
        SetTimer () => ToolTip(), -2000
    }
}
```

### Step 4: Update the Coordinates

Edit the script and replace the X/Y values with your coordinates from Window Spy:

```autohotkey
WSJTX_TX_X := 595    ; ← Replace with YOUR Client X coordinate
WSJTX_TX_Y := 485    ; ← Replace with YOUR Client Y coordinate
```

### Step 5: Run It

1. Double-click `QSOPredictor_AutoPaste.ahk`
2. You'll see a green "H" icon in your system tray
3. Now just click the band map in QSO Predictor — frequency auto-pastes!

### Step 6: Auto-Start (Optional)

To run automatically when Windows starts:
1. Press Win+R, type `shell:startup`, press Enter
2. Copy your `.ahk` file into this folder

---

## How It Works

The script monitors your clipboard. When ALL of these conditions are met:
1. QSO Predictor is the active window
2. You copy something to clipboard (clicking band map does this)
3. The clipboard contains a valid frequency (300-3000 Hz)

...it automatically activates WSJT-X/JTDX, clicks on the TX frequency field, and types the frequency.

**Safety:** It only triggers from QSO Predictor, so copying frequencies from other apps won't cause unexpected behavior.

---

## Alternative: Manual Hotkey Method

If you prefer to control when the paste happens:

```autohotkey
#Requires AutoHotkey v2.0

; Update these coordinates using Window Spy!
WSJTX_TX_X := 595
WSJTX_TX_Y := 485
JTDX_TX_X := 595
JTDX_TX_Y := 485

; Ctrl+Shift+T = Paste to WSJT-X
^+t::PasteToTxFreq("WSJT-X", WSJTX_TX_X, WSJTX_TX_Y)

; Ctrl+Shift+J = Paste to JTDX  
^+j::PasteToTxFreq("JTDX", JTDX_TX_X, JTDX_TX_Y)

PasteToTxFreq(windowTitle, clickX, clickY)
{
    freq := A_Clipboard
    
    if !RegExMatch(freq, "^\d{3,4}$")
    {
        MsgBox "Clipboard doesn't contain a valid frequency: " freq
        return
    }
    
    try {
        WinActivate windowTitle
        WinWaitActive windowTitle,, 2
        Click clickX, clickY
        Sleep 50
        Send "^a"
        Sleep 20
        Send freq
        Send "{Enter}"
    } catch {
        MsgBox "Could not find " windowTitle
    }
}
```

**Workflow with hotkeys:**
1. Click band map in QSO Predictor → copies frequency
2. Press Ctrl+Shift+T → pastes to WSJT-X (or Ctrl+Shift+J for JTDX)

---

## Troubleshooting

### Clicking the wrong spot

The coordinates are relative to the window's client area. If you resize or move the window significantly, the coordinates may need updating. Re-run Window Spy to get new coordinates.

**Tip:** Keep your WSJT-X/JTDX window the same size and position for consistent behavior.

### Frequency not being accepted

Try increasing the delays:
```autohotkey
Sleep 100  ; Increase from 50
```

### Window not activating

Make sure the window title matches. `"WSJT-X"` will match `"WSJT-X   v3.0.0   by K1JT et al."` and `"JTDX"` will match `"JTDX  by HF community"`.

---

## Summary

| Method | Workflow |
|--------|----------|
| **Auto-paste (recommended)** | Click band map → frequency appears in WSJT-X/JTDX automatically |
| **Hotkey** | Click band map → Press Ctrl+Shift+T → frequency appears |

Both methods start with QSO Predictor's click-to-clipboard feature (v2.1.0+).

---

## Mac Users: Hammerspoon (Experimental)

**This should work but hasn't been fully tested!**

[Hammerspoon](https://www.hammerspoon.org/) is a free, open-source automation tool for macOS — similar to AutoHotkey for Windows.

### Step 1: Install Hammerspoon

1. Download from https://www.hammerspoon.org/
2. Move to Applications folder
3. Launch it and grant Accessibility permissions when prompted

### Step 2: Find Your Coordinates

1. Open Hammerspoon Console (click menubar icon → Console)
2. Position your WSJT-X/JTDX window where you normally keep it
3. Hover mouse over the TX frequency field
4. In the console, type: `hs.mouse.absolutePosition()` and press Enter
5. Note the x and y values

### Step 3: Create the Script

Edit `~/.hammerspoon/init.lua` (create if it doesn't exist):

```lua
-- QSO Predictor Auto-Paste for Mac
-- EXPERIMENTAL - may need tweaking!

-- UPDATE THESE with your coordinates from Step 2
local tx_field_x = 595
local tx_field_y = 485

-- Track clipboard changes
local lastClipboard = ""

hs.timer.doEvery(0.5, function()
    local clipboard = hs.pasteboard.getContents()
    if clipboard == lastClipboard then return end
    lastClipboard = clipboard
    
    -- Check if it's a valid frequency (300-3000 Hz)
    if not clipboard then return end
    local freq = tonumber(clipboard)
    if not freq or freq < 300 or freq > 3000 then return end
    
    -- Find WSJT-X or JTDX
    local app = hs.application.find("WSJT-X") or hs.application.find("JTDX")
    if not app then return end
    
    -- Activate and click on TX field
    app:activate()
    hs.timer.doAfter(0.1, function()
        local win = app:mainWindow()
        if not win then return end
        local frame = win:frame()
        local clickPoint = {x = frame.x + tx_field_x, y = frame.y + tx_field_y}
        
        hs.mouse.absolutePosition(clickPoint)
        hs.eventtap.leftClick(clickPoint)
        
        hs.timer.doAfter(0.05, function()
            hs.eventtap.keyStroke({"cmd"}, "a")  -- Select all
            hs.eventtap.keyStrokes(tostring(freq))  -- Type frequency
            hs.eventtap.keyStroke({}, "return")  -- Confirm
        end)
    end)
end)
```

### Step 4: Reload

Click the Hammerspoon menubar icon → "Reload Config"

### Notes

- The coordinates are relative to the window position, so keep your WSJT-X/JTDX window in a consistent spot
- If it doesn't work, try increasing the delay values (0.1, 0.05)
- This polls the clipboard every 0.5 seconds rather than triggering on change — slightly less elegant than the Windows version but works

**Feedback welcome!** If you get this working (or find issues), let us know in the GitHub Discussions.

---

## Need Help?

Post in the QSO Predictor discussions and we can help debug your setup.

73!
