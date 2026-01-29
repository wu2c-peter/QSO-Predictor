# AutoHotkey Guide: Paste TX Frequency to WSJT-X / JTDX

**For Windows users who want to quickly paste QSO Predictor's recommended frequency**

## Overview

This guide shows you how to set up **one-click frequency transfer** from QSO Predictor to WSJT-X or JTDX.

**The magic workflow:**
1. Click band map or Rec frequency in QSO Predictor
2. **That's it!** — Frequency automatically appears in WSJT-X/JTDX

No hotkeys needed — the script detects when you copy a frequency from QSO Predictor and auto-pastes it.

---

## Quick Start (Recommended Method)

### Step 1: Install AutoHotkey

1. Download AutoHotkey v2.0 from: https://www.autohotkey.com/
2. Run the installer
3. Choose "AutoHotkey v2" (recommended)

### Step 2: Find Your Control Name

1. After installing AutoHotkey, search for **"Window Spy"** in your Start menu and open it
2. Open WSJT-X or JTDX
3. Hover your mouse over the **TX frequency input field** (the "Tx" box with Hz value)
4. Note the **ClassNN** value (e.g., `Qt6514QSpinBox1`)

### Step 3: Create the Auto-Paste Script

Create a file called `QSOPredictor_AutoPaste.ahk` with this content:

```autohotkey
#Requires AutoHotkey v2.0

; =============================================================
; QSO Predictor Auto-Paste Script
; Automatically pastes frequency to WSJT-X/JTDX when you click
; the band map or Rec frequency in QSO Predictor
; =============================================================

; IMPORTANT: Update these ClassNN values using Window Spy!
WSJTX_CONTROL := "Qt6514QSpinBox1"   ; For WSJT-X 3.0
JTDX_CONTROL := "Qt5QSpinBox1"       ; For JTDX

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
        PasteToTxFreq("WSJT-X", WSJTX_CONTROL, freq)
    else if WinExist("JTDX")
        PasteToTxFreq("JTDX", JTDX_CONTROL, freq)
}

PasteToTxFreq(windowTitle, controlClassNN, freq)
{
    try {
        WinActivate windowTitle
        WinWaitActive windowTitle,, 2
        
        ControlFocus controlClassNN, windowTitle
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

### Step 4: Run It

1. Double-click `QSOPredictor_AutoPaste.ahk`
2. You'll see a green "H" icon in your system tray
3. Now just click the band map in QSO Predictor — frequency auto-pastes!

### Step 5: Auto-Start (Optional)

To run automatically when Windows starts:
1. Press Win+R, type `shell:startup`, press Enter
2. Copy your `.ahk` file into this folder

---

## How It Works

The script monitors your clipboard. When ALL of these conditions are met:
1. QSO Predictor is the active window
2. You copy something to clipboard (clicking band map does this)
3. The clipboard contains a valid frequency (300-3000 Hz)

...it automatically activates WSJT-X/JTDX and pastes the frequency.

**Safety:** It only triggers from QSO Predictor, so copying frequencies from other apps won't cause unexpected behavior.

---

## Alternative: Manual Hotkey Method

If you prefer to control when the paste happens, use this hotkey-based script instead:

### Combined Script (Ctrl+Shift+T for WSJT-X, Ctrl+Shift+J for JTDX)

```autohotkey
#Requires AutoHotkey v2.0

; IMPORTANT: Update these ClassNN values using Window Spy!
WSJTX_CONTROL := "Qt6514QSpinBox1"
JTDX_CONTROL := "Qt5QSpinBox1"

; Ctrl+Shift+T = Paste to WSJT-X
^+t::PasteToTxFreq("WSJT-X", WSJTX_CONTROL)

; Ctrl+Shift+J = Paste to JTDX  
^+j::PasteToTxFreq("JTDX", JTDX_CONTROL)

PasteToTxFreq(windowTitle, controlClassNN)
{
    freq := A_Clipboard
    
    ; Validate frequency format
    if !RegExMatch(freq, "^\d{3,4}$")
    {
        MsgBox "Clipboard doesn't contain a valid frequency: " freq
        return
    }
    
    try {
        WinActivate windowTitle
        WinWaitActive windowTitle,, 2
        ControlFocus controlClassNN, windowTitle
        Sleep 50
        Send "^a"
        Sleep 20
        Send freq
        Send "{Enter}"
    } catch {
        MsgBox "Could not find " windowTitle " or TX frequency control"
    }
}
```

**Workflow with hotkeys:**
1. Click band map in QSO Predictor → copies frequency
2. Press Ctrl+Shift+T → pastes to WSJT-X
3. (Or Ctrl+Shift+J for JTDX)

---

## Finding Your Control Names (Window Spy)

The ClassNN values vary by WSJT-X/JTDX version. Here's how to find yours:

1. After installing AutoHotkey, search for **"Window Spy"** in Start menu
2. Open WSJT-X or JTDX
3. Hover mouse over the **TX frequency input field**
4. Note the **ClassNN** value shown in Window Spy

**Common ClassNN values:**

| Program | Version | Likely ClassNN |
|---------|---------|----------------|
| WSJT-X | 3.0.x (Qt6) | `Qt6514QSpinBox1` or `Qt651514QSpinBox1` |
| WSJT-X | 2.x (Qt5) | `Qt5QSpinBox1` |
| JTDX | 2.x | `Qt5QSpinBox1` or `Qt515QSpinBox1` |

Update the script with your actual ClassNN value.

---

## Troubleshooting

### "Could not find TX frequency control"

The ClassNN doesn't match your version. Re-run Window Spy and update the script.

### Window not activating

Make sure the window title in the script matches. `"WSJT-X"` will match `"WSJT-X   v3.0.0   by K1JT et al."`.

### Frequency not being accepted

Try increasing the delay in the script:
```autohotkey
Sleep 100  ; Increase from 50
```

### Fallback: Coordinate-based clicking

If control focus doesn't work, you can click by coordinates instead:

```autohotkey
; Replace the ControlFocus line with:
Click 595, 485  ; Adjust coordinates using Window Spy
```

---

## Summary

| Method | Workflow |
|--------|----------|
| **Auto-paste (recommended)** | Click band map → frequency appears in WSJT-X automatically |
| **Hotkey** | Click band map → Press Ctrl+Shift+T → frequency appears |

Both methods start with QSO Predictor's click-to-clipboard feature (new in v2.1.0).

---

## Need Help?

If you can't get it working, post your Window Spy output and we can help figure out the correct ClassNN for your setup.

73!
