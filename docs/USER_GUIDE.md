# QSO Predictor User Guide

**Version 2.1.0**  
**By Peter Hirst (WU2C)**

> 📋 **See [README](https://github.com/wu2c-peter/qso-predictor/blob/main/README.md) for What's New, Version History, and Installation**

---

## Table of Contents

1. [What is QSO Predictor?](#1-what-is-qso-predictor)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [Understanding the Display](#4-understanding-the-display)
5. [Path Intelligence](#5-path-intelligence)
6. [Local Intelligence](#6-local-intelligence)
7. [Hunt Mode](#7-hunt-mode)
8. [Workflows & Tips](#8-workflows--tips)
9. [Settings](#9-settings)
10. [Troubleshooting](#10-troubleshooting)
11. [FAQ](#11-faq)

---

## 1. What is QSO Predictor?

### The Problem

You're calling a DX station. No response. Is the band dead? Is your signal too weak? Or are you buried under a pileup you can't even hear?

Today's tools show you the band from **your** perspective — who you're decoding, who's spotting you. They don't show you what's happening at the **DX station's** end.

### The Solution

QSO Predictor shows you the "view from the other end." Using PSK Reporter data, it builds a picture of band conditions at the target's location — what signals are arriving there, how crowded each frequency is, and whether your signal path is open.

**The result:** Fewer wasted calls, smarter frequency choices, better target selection.

---

## 2. Installation

### Windows

1. Download the latest `.zip` from [GitHub Releases](https://github.com/wu2c-peter/qso-predictor/releases)
2. Extract to any folder
3. Run `QSO Predictor.exe`
4. **First run:** Windows SmartScreen may warn about an unrecognized app
   - Click "More info" → "Run anyway"

### Running from Source (Windows/Mac/Linux)

```bash
git clone https://github.com/wu2c-peter/qso-predictor.git
cd qso-predictor
pip install -r requirements.txt
python main_v2.py
```

### Configure WSJT-X / JTDX

1. Open Settings → Reporting
2. Set UDP Server: `127.0.0.1`
3. Set Port: `2237` (or `2238` if 2237 is in use)
4. Check "Accept UDP Requests"

---

## 3. Quick Start

### First-Time Setup

1. **Launch QSO Predictor** and wait for connection
2. **Set your callsign:** File → Settings → My Callsign
3. **Set your grid:** File → Settings → My Grid (4 or 6 char)
4. **Start WSJT-X/JTDX** — decodes should appear automatically

### Basic Workflow

1. **Select a target** — click a row in the decode table (or double-click in WSJT-X)
2. **Read the band map** — see what the target is hearing
3. **Check Path Intelligence** — are others from your area getting through?
4. **Choose your frequency** — find a clear spot at the target's end
5. **Call!**

---

## 4. Understanding the Display

### The Band Map

The band map has three sections:

#### Top Section: Target Perspective

What the target station (and nearby stations) are hearing. Color-coded by geographic proximity:

| Color | Source | Meaning |
|-------|--------|---------|
| **Cyan** | Target Station | Signals the target is actually decoding |
| **Bright Blue** | Same Grid | Stations in same 4-char grid hear these |
| **Medium Blue** | Same Field | Stations in same 2-char field hear these |
| **Dark Blue** | Global | Background activity (less relevant) |

**Count numbers** show signal density:

| Count | Meaning |
|-------|---------|
| 1-3 | **Ideal** — proven frequency, not saturated |
| 4-5 | Warning — getting crowded |
| 6+ | Crowded — decoder performance degrades |

#### Middle Section: Score Graph

Visual representation of the frequency recommendation algorithm:

| Score | Color | Meaning |
|-------|-------|---------|
| 85-100 | Green | Excellent — proven with 1-3 signals |
| 60-84 | Cyan | Good — proven or clear gap |
| 40-59 | Yellow | Moderate — unproven or light congestion |
| 20-39 | Orange | Poor — crowded area |
| 0-19 | Red | Avoid — blocked or edge |

**Line style:**
- **Solid line** = Algorithm has tier 1 (proven) data
- **Dotted line** = Gap-based scoring only (less certain)

#### Bottom Section: Your Local Decodes

What your radio is receiving, color-coded by signal strength:

| Color | SNR | Meaning |
|-------|-----|---------|
| Green | > 0 dB | Strong |
| Yellow | -10 to 0 dB | Medium |
| Red | < -10 dB | Weak |

### The Overlay Lines

| Line | Color | Meaning |
|------|-------|---------|
| Target | Magenta | Target station's TX frequency |
| TX | Yellow (dotted) | Your current TX frequency |
| Rec | Green | Recommended TX frequency |

### The Path Column

The decode table's **Path** column shows whether your signal is reaching each station's area:

| Status | Color | Meaning |
|--------|-------|---------|
| **Heard by Target** | Cyan | Target has decoded YOUR signal — call them! |
| **Heard in Region** | Green | Stations near target heard you — path confirmed |
| **Not Heard in Region** | Orange | Reporters exist but haven't heard you yet |
| **Not Transmitting** | Gray | You haven't transmitted recently |
| **No Reporters in Region** | Dark gray | No PSK Reporter data from that area |

### Click-to-Set Frequency

Click anywhere on the band map to manually set the recommended frequency:
- Green line jumps to your click position
- Dwells for 3 seconds (countdown shown)
- Then resumes auto-calculation

Use this to read off a specific frequency from the Rec display.

---

## 5. Path Intelligence

Path Intelligence answers: **"Is anyone from my area getting through?"**

### Phase 1: Near-Me Detection

Shows stations from your geographic area that the target is hearing:

```
At target: 2 from your area heard
✓ Target uploads to PSK Reporter

📍 W2XYZ (FN31) → -12 dB @ 1847 Hz
🗺️ K2ABC (FN30) → -18 dB @ 1523 Hz

💡 Others getting through — you can too!
```

**Icons:**
- 📍 = Same grid square (very close)
- 🗺️ = Same field (regional)

### Phase 2: Analyze Why

Click the **🔍 Analyze** button to understand WHY nearby stations are succeeding:

**Beaming Detection:**
- Compares directional patterns between stations
- If one station is more concentrated than peers → likely beaming

**Power Comparison:**
- Compares SNR to peer stations
- If +6dB or more above peers → likely power/antenna advantage

**Example insights:**
- "📡 Likely beaming — 95% concentrated vs 70% peer avg"
- "⚡ +8dB above others nearby — likely power/antenna advantage"
- "📡 All 4 stations ~90% toward EU — likely propagation"
- "💡 Their freq has light traffic — try 1523 Hz?"

### Interpreting Results

| Insight | What It Means | Can You Act? |
|---------|---------------|--------------|
| Beaming detected | They have directional antenna toward target | Not easily |
| Power advantage | They're running more power or better antenna | Maybe |
| All same direction | Propagation favors that path | Wait or try |
| Light traffic freq | Their frequency is relatively clear | **Yes! Try it** |

---

## 6. Local Intelligence

Local Intelligence predicts DX station **behavior** based on observed patterns.

### Bootstrap (First-Time Setup)

1. Go to **Tools → Bootstrap Behavior**
2. Click **Start Bootstrap**
3. Wait 10-30 seconds (analyzes last 14 days of logs)
4. You'll see: stations analyzed, persona distribution

**Re-run bootstrap** after major operating sessions to update profiles.

### Behavior Prediction

The Insights Panel shows:

**Pattern:** How the target picks callers
- **Loudest First** — favors strong signals
- **Methodical** — works through pileup systematically
- **Random/Fair** — no clear preference

**Persona:** Operating style classification
- **Contest Op** — high rate, picks loudest
- **Casual Op** — slower, more methodical
- **DX Hunter** — opportunistic

**Confidence:** How certain is the prediction
- High (>70%) — based on multiple observations
- Medium (40-70%) — limited data
- Low (<40%) — educated guess

### Strategy Recommendations

Based on all available data:

| Recommendation | Meaning |
|----------------|---------|
| **CALL NOW** | Conditions favorable, go for it |
| **WAIT** | Pileup too heavy or poor timing |
| **TRY LATER** | Path issues or target busy |

---

## 7. Hunt Mode

Hunt Mode tracks specific stations you want to work.

### Adding Targets

1. **Tools → Hunt List** (or Ctrl+H)
2. Click **Add**
3. Enter callsign (and optionally band)
4. Click **OK**

### Alerts

When a hunt target is spotted:
- **System tray notification** pops up
- **Status bar** shows alert briefly
- **Table row** is highlighted (if visible)

**Alert types:**
- 📡 Active — target spotted on band
- 🎯 Working Nearby — target is working stations from your area!

### Managing the List

- **Edit** — modify callsign or band
- **Remove** — delete from list
- **Clear All** — remove all targets
- List is saved between sessions

---

## 8. Workflows & Tips

### Tactical Scenarios

#### Target is a "Contest Op"

**Signs:** Pattern shows "Loudest First", high QSO rate

**Your strategy:**
- Maximize your signal strength
- Power and antenna matter most
- If you're weak, wait for pileup to thin

#### Target is "Methodical"

**Signs:** Pattern shows "Methodical" or "Low → High", steady rate

**Your strategy:**
- Be patient — they'll get to you
- Persistence beats power
- Pick a spot and stay there

#### Heavy Pileup (7+ callers)

**Signs:** Many cyan bars, counts of 6+ at popular frequencies

**Your strategy:**
- Find frequencies with counts of 1-3 instead
- Consider waiting for pileup to thin
- Check Path Intelligence — do you have any advantage?

### Pro Tips

1. **"Heard by Target" is gold** — if Path shows this, call immediately
2. **Count numbers matter** — frequencies showing 1-3 are ideal, 6+ means saturation
3. **Solid vs dotted** — trust solid-line scores more than dotted
4. **Click to explore** — click the band map to read specific frequencies
5. **Proven > Empty** — a frequency where target IS decoding beats an empty gap
6. **Watch the pattern evolve** — classification improves with each QSO you witness
7. **Use Path Intelligence** — if others from your area are getting through, you can too
8. **Analyze before giving up** — the Analyze button might reveal why others succeed
9. **Work one cycle ahead** — select target early, let recommendation stabilize, enter frequency before next cycle starts
10. **Click to copy callsign** — click the target callsign in either panel to copy to clipboard, then paste into WSJT-X/JTDX (or use the auto-paste scripts below)

### Windows Power Users: Auto-Paste to WSJT-X/JTDX

You can set up one-click transfer of **frequencies** and **callsigns** using AutoHotkey (free):

**The workflow:**
1. Click band map → frequency auto-pastes to TX field
2. Click target callsign → callsign auto-pastes to DX Call field

**Quick setup:**

1. Install AutoHotkey v2.0 from https://www.autohotkey.com/
2. Use Window Spy to find your field coordinates (Client x,y) for both:
   - TX Freq field (the Hz offset box)
   - DX Call field (the text box under "DX Call")
3. Create a file `QSOPredictor_AutoPaste.ahk`:

```autohotkey
#Requires AutoHotkey v2.0
; =============================================================
; QSO Predictor Auto-Paste Script
; Automatically pastes frequency OR callsign to WSJT-X/JTDX
; when you click the band map or target callsign in QSO Predictor
; =============================================================

; IMPORTANT: Update these coordinates using Window Spy!
; Hover over each field, note the CLIENT coordinates

; WSJT-X coordinates
WSJTX_TX_X := 800    ; TX frequency field
WSJTX_TX_Y := 630
WSJTX_DX_X := 130    ; DX Call field
WSJTX_DX_Y := 630

; JTDX coordinates
JTDX_TX_X := 800     ; TX frequency field
JTDX_TX_Y := 630
JTDX_DX_X := 130     ; DX Call field (text box under "DX Call")
JTDX_DX_Y := 630

; Monitor clipboard for changes
OnClipboardChange ClipboardChanged

ClipboardChanged(dataType)
{
    ; Only process text
    if dataType != 1
        return

    clip := Trim(A_Clipboard)
    if !clip
        return

    ; Frequency: 3-4 digits, 300-3000 Hz — no Enter needed
    if RegExMatch(clip, "^\d{3,4}$") && clip >= 300 && clip <= 3000 {
        if WinExist("WSJT-X")
            PasteToField("WSJT-X", WSJTX_TX_X, WSJTX_TX_Y, clip, false)
        else if WinExist("JTDX")
            PasteToField("JTDX", JTDX_TX_X, JTDX_TX_Y, clip, false)
        return
    }

    ; Callsign: 3-10 chars, has letter AND digit — Enter required to set
    if RegExMatch(clip, "^[A-Z0-9/]{3,10}$") && RegExMatch(clip, "[A-Z]") && RegExMatch(clip, "\d") {
        if WinExist("WSJT-X")
            PasteToField("WSJT-X", WSJTX_DX_X, WSJTX_DX_Y, clip, true)
        else if WinExist("JTDX")
            PasteToField("JTDX", JTDX_DX_X, JTDX_DX_Y, clip, true)
        return
    }
}

PasteToField(windowTitle, clickX, clickY, text, pressEnter)
{
    try {
        WinActivate windowTitle
        WinWaitActive windowTitle,, 2

        Click clickX, clickY
        Sleep 50

        Send "^a"
        Sleep 20
        Send text
        if pressEnter
            Send "{Enter}"

        ; Confirmation tooltip
        label := pressEnter ? "DX Call" : "TX Freq"
        ToolTip label " → " text
        SetTimer () => ToolTip(), -1500
    } catch {
        ToolTip "Could not paste to " windowTitle
        SetTimer () => ToolTip(), -2000
    }
}
```

4. Double-click to run. Done!

### Mac Power Users: Auto-Paste with Hammerspoon

1. Install Hammerspoon from https://www.hammerspoon.org/
2. Add to `~/.hammerspoon/init.lua`:

```lua
-- =============================================================
-- QSO Predictor Auto-Paste Script (Hammerspoon)
-- Automatically pastes frequency OR callsign to WSJT-X/JTDX
-- when you click the band map or target callsign in QSO Predictor
-- =============================================================

-- UPDATE these coordinates using Hammerspoon console:
--   hs.mouse.absolutePosition()  (then subtract window origin)

-- WSJT-X coordinates
local WSJTX_TX_X, WSJTX_TX_Y = 800, 630   -- TX frequency field
local WSJTX_DX_X, WSJTX_DX_Y = 130, 630   -- DX Call field

-- JTDX coordinates
local JTDX_TX_X, JTDX_TX_Y = 800, 630     -- TX frequency field
local JTDX_DX_X, JTDX_DX_Y = 130, 630     -- DX Call field

local lastClip = ""

hs.timer.doEvery(0.5, function()
    local clip = hs.pasteboard.getContents()
    if not clip or clip == lastClip then return end
    lastClip = clip
    clip = clip:match("^%s*(.-)%s*$")  -- trim

    -- Frequency: 3-4 digits, 300-3000 — no Enter needed
    if clip:match("^%d+$") and #clip >= 3 and #clip <= 4 then
        local freq = tonumber(clip)
        if freq >= 300 and freq <= 3000 then
            local app, tx, ty = findAppCoords("TX")
            if app then pasteToField(app, clip, tx, ty, false) end
            return
        end
    end

    -- Callsign: 3-10 chars, has letter AND digit — Enter required
    if #clip >= 3 and #clip <= 10
       and clip:match("^[A-Z0-9/]+$")
       and clip:match("[A-Z]")
       and clip:match("%d") then
        local app, dx, dy = findAppCoords("DX")
        if app then pasteToField(app, clip, dx, dy, true) end
    end
end)

function findAppCoords(fieldType)
    local app = hs.application.find("JTDX") or hs.application.find("WSJT-X")
    if not app then return nil end
    local name = app:name()
    if fieldType == "TX" then
        if name:find("JTDX") then return app, JTDX_TX_X, JTDX_TX_Y end
        return app, WSJTX_TX_X, WSJTX_TX_Y
    else
        if name:find("JTDX") then return app, JTDX_DX_X, JTDX_DX_Y end
        return app, WSJTX_DX_X, WSJTX_DX_Y
    end
end

function pasteToField(app, text, x, y, pressEnter)
    app:activate()
    hs.timer.doAfter(0.3, function()
        local win = app:mainWindow()
        if not win then return end
        local frame = win:frame()
        hs.eventtap.leftClick({x = frame.x + x, y = frame.y + y})
        hs.timer.doAfter(0.1, function()
            hs.eventtap.keyStroke({"cmd"}, "a")
            hs.eventtap.keyStrokes(text)
            if pressEnter then
                hs.eventtap.keyStroke({}, "return")
            end
            -- Confirmation
            local label = pressEnter and "DX Call" or "TX Freq"
            hs.alert.show(label .. " → " .. text, 1.5)
        end)
    end)
end
```

3. Reload Hammerspoon config (⌘+R in console).

> **Note:** Both scripts auto-detect whether JTDX or WSJT-X is running. If neither is open, clipboard changes are ignored. You can also skip the scripts entirely and just Ctrl+V / ⌘+V manually.

📖 **Finding coordinates:** In AutoHotkey use Window Spy; in Hammerspoon use `hs.mouse.absolutePosition()` while hovering over each field.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+R | Clear target selection |
| Ctrl+Y | Fetch target from WSJT-X/JTDX |
| Ctrl+H | Open Hunt List |
| Ctrl+S | Open Settings |
| F5 | Force refresh spots |

### Click Actions

| Click | What happens |
|-------|-------------|
| Click target callsign (either panel) | Copies callsign to clipboard |
| Click band map | Copies recommended frequency to clipboard |
| ⟳ button (either panel) | Fetches current target from WSJT-X/JTDX |

---

## 9. Settings

### File → Settings

**My Callsign:** Your callsign (required for "who hears me" tracking)

**My Grid:** Your Maidenhead grid (4 or 6 char) — required for Path Intelligence

**UDP Port:** Default 2237. Change if another app uses that port.

### Network Configuration

**Standard (single app):**
```
UDP IP: 127.0.0.1
UDP Port: 2237
```

**Multicast (with JTAlert, N3FJP):**
```
UDP IP: 239.0.0.2
UDP Port: 2237
```

See Troubleshooting section for multi-app setups.

---

## 10. Troubleshooting

### No Decodes Appearing

**Check in order:**

1. **WSJT-X/JTDX UDP settings:**
   - Settings → Reporting → UDP Server: `127.0.0.1`
   - Port: `2237`
   - "Accept UDP Requests" checked

2. **Firewall:**
   - Allow UDP port 2237
   - Add exception for QSO Predictor

3. **Port conflict:**
   - Another app using 2237?
   - Try port 2238 in both apps

4. **Is WSJT-X actually decoding?**
   - Check its own display first

### Running with Multiple Apps

**Problem:** GridTracker, JTAlert, and QSO Predictor all need UDP data.

**Solution 1: Secondary UDP (Simplest)**
```
JTDX → 2237 → GridTracker
    └→ 2238 → QSO Predictor
```
In JTDX: Settings → Reporting → Secondary UDP Server → port 2238

**Solution 2: Multicast**
```
JTDX → 239.0.0.2:2237 → All apps receive
```
Configure all apps to use multicast address.

### VPN Breaking Multicast (Multi-Computer Setups)

If you're using multicast UDP across multiple computers and have VPN software installed:

**Symptoms:**
- Was working, suddenly stops
- No data received even though settings look correct
- MQTT connects fine but UDP shows "No messages received"

**Why it happens:**
- VPNs create a virtual network interface that intercepts traffic
- Multicast only works on local network — can't route through VPN tunnels
- Even when VPN is "disconnected", the software may still interfere

**Solutions:**

1. **Fully quit VPN software** — don't just disconnect, completely exit the app
2. **Restart QSO Predictor** after quitting VPN
3. **Configure split tunneling** — most VPNs let you exclude local network traffic or specific apps
4. **Whitelist local subnet** — exclude `192.168.x.x` or your local network range

**Affected VPN software:** Malwarebytes VPN, NordVPN, ExpressVPN, and most others.

### Band Map Empty

1. **No target selected** — click a station in decode table
2. **No perspective data** — target area may have no PSK Reporter coverage
3. **MQTT not connected** — check status bar for connection

### Path Intelligence Shows "No Reporters in Region"

- Target's area has no PSK Reporter stations uploading
- This is a data gap, not a problem with your setup
- Local Intelligence still works

### Bootstrap Shows 0 Stations

1. **No log files found** — check WSJT-X/JTDX has created ALL.TXT
2. **Log files too old** — bootstrap looks at last 14 days
3. **Custom install path** — only standard locations auto-detected

### Windows SmartScreen Warning

This is normal for unsigned applications:
1. Click "More info"
2. Click "Run anyway"

### High CPU Usage

- Heavy contest activity = more processing
- Try restarting application
- Check if stuck in a loop

### Clearing Data

**Reset behavior history:**
```
del "%USERPROFILE%\.qso-predictor\behavior_history.json"
```
Then run bootstrap again.

**Full reset:**
```
rmdir /s /q "%USERPROFILE%\.qso-predictor"
```

---

## 11. FAQ

**Q: Does QSO Predictor transmit for me?**  
A: No. It's advisory only. You control your radio through WSJT-X/JTDX.

**Q: Does it work with other modes (CW, SSB)?**  
A: Currently FT8/FT4 only. The algorithms are designed for these modes.

**Q: Can I use it without internet?**  
A: Partially. Local Intelligence works offline. Target Perspective requires PSK Reporter (internet).

**Q: Does it work on Mac/Linux?**  
A: Running from Python source works. The .exe is Windows only.

**Q: Is my data uploaded anywhere?**  
A: No. QSO Predictor only downloads PSK Reporter data. Your logs stay local.

**Q: Why does bootstrap take 30 seconds?**  
A: It's parsing up to 500,000 decodes from your log files. This is a one-time operation.

**Q: What if the target isn't uploading to PSK Reporter?**  
A: You'll get Tier 2/3 proxy data from nearby stations. Sometimes you just have to call and see.

**Q: How accurate is beaming detection?**  
A: It compares your target to peer stations. Works best with 3+ peers. Can't distinguish "everyone beaming same direction" from "propagation favors that direction."

**Q: Why do I see "Similar pattern to nearby stations"?**  
A: All near-me stations show the same directional pattern. This is normal — it's likely propagation, not antenna differences.

---

## Getting Help

- **GitHub Issues:** [Report bugs or request features](https://github.com/wu2c-peter/qso-predictor/issues)
- **GitHub Discussions:** [Ask questions, share tips](https://github.com/wu2c-peter/qso-predictor/discussions)

---

**73 de WU2C**
