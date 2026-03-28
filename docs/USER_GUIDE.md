# QSO Predictor User Guide

**Version 2.3.1**  
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
8. [Fox/Hound & SuperFox Mode](#8-foxhound--superfox-mode)
9. [Workflows & Tips](#9-workflows--tips)
10. [Settings](#10-settings)
11. [Troubleshooting](#11-troubleshooting)
12. [FAQ](#12-faq)

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

### Target Activity State (v2.3.0)

The dashboard shows what the target station is doing **right now**, parsed from your local FT8 decodes:

| Status | Meaning |
|--------|---------|
| **CQing** | Target is calling CQ — open for contacts, call now |
| **Working YOU** | Target is in QSO with you — Fox is controlling TX |
| **Working [call]** | Target is in QSO with another station |
| **Idle** | No target activity in last 2 minutes |

This is derived entirely from local decodes — no internet required. It updates in real time as the target's transmissions are decoded.

**In Fox/Hound mode:** When "Working YOU" is detected during F/H operation, QSOP automatically disables click-to-set (since the Fox controls your TX frequency at that point) and shows "FOX CONTROLLING TX FREQUENCY" in the recommendation area.

### Tactical Observation Toasts (v2.2.0)

A notification bar appears above the decode table with real-time tactical alerts:

| Alert | Style | Meaning |
|-------|-------|---------|
| **⚠️ Hidden pileup** | Orange | You see few callers locally but PSK Reporter shows heavy competition at the target's end |
| **📈 Competition increasing** | Orange | Caller count at target has jumped significantly |
| **📉 Competition dropping** | Green | Pileup is thinning — opportunity window |
| **🎯 Target decoded YOU** | Green | Your signal confirmed at target — call now! |
| **🟢 Path confirmed** | Green | Propagation to target's region is open |
| **🔴 Path lost** | Orange | Path to target's region no longer confirmed |
| **📡 Spotted near target** | Green | You've been spotted near the target station |

Toasts auto-dismiss after 8 seconds, or click ✕ to dismiss immediately. Rate-limited to 1 per 15 seconds to avoid distraction.

### Column Header Tooltips (v2.2.0)

Hover over any column header in the decode table to see what it means and where the data comes from. Particularly useful for **Prob %** and **Path** columns, which combine multiple data sources.

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

### How Path Data Works Together (v2.2.0)

QSO Predictor uses three independent data sources for path information:

- **PSK Reporter (my signal)** — has any receiver near the target heard YOUR signal?
- **PSK Reporter (target's receivers)** — is the target hearing stations from YOUR area?
- **Local decodes** — have you directly decoded a response from the target?

These can sometimes show different things. For example, the Path column might show "Not Heard in Region" (your signal not confirmed) while Path Intelligence shows 3 stations from your area getting through (the path IS viable).

**v2.2.0 reconciliation:** When near-me evidence exists but PSK Reporter hasn't confirmed your specific signal, the strategy recommendation now accounts for both pieces of information — giving you "CALL NOW" instead of the old "TRY LATER" that ignored the evidence.

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

### Pileup Contrast (v2.2.0)

The Insights panel now shows target-side competition from PSK Reporter alongside your local pileup count. This reveals **hidden pileups** — situations where you see a clear band locally but the target has heavy competition you can't hear.

When a hidden pileup is detected, you'll see:
- A yellow warning in the Insights panel: "⚠️ Hidden pileup — you can't hear your competition!"
- A tactical toast notification bar above the decode table
- Strategy recommendation adjusted to account for the real competition level

This is one of the most common reasons calls go unanswered — now you can see it happening.

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

## 8. Fox/Hound & SuperFox Mode

QSO Predictor is aware of Fox/Hound operating modes and adjusts its recommendations accordingly.

### What Is Fox/Hound Mode?

Fox/Hound (F/H) is a special FT8 operating mode used by rare DXpeditions to handle high pileup rates. The DX station (Fox) transmits in a reserved low-frequency zone; calling stations (Hounds) transmit above it.

There are two variants:

| Mode | Fox transmits | Hounds transmit | Max simultaneous QSOs |
|------|--------------|-----------------|----------------------|
| **F/H** (old style) | 300–900 Hz | ≥1000 Hz | 5 |
| **SuperFox** | ~750–2262 Hz (1512 Hz wide) | ≥200 Hz (anywhere) | 9 |

**SuperFox** is used by major DXpeditions from 2024 onward (CY0S, TX5EU, etc.) and produces a visibly different wide signal on the waterfall.

### Setting F/H Mode in QSOP

The toolbar has a three-state combo box:

| Setting | Use when |
|---------|----------|
| **F/H Off** | Normal FT8 operation |
| **F/H** | Old-style Fox/Hound |
| **SuperF/H** | SuperFox/SuperHound |

**Auto-detection:** QSOP detects F/H from two sources:
1. **WSJT-X UDP** — when WSJT-X reports Hound mode via the special_mode field
2. **Manual selection** — always available via the combo box

When UDP auto-detection fires, a **disambiguation dialog** appears asking you to confirm which mode you're in — because WSJT-X cannot distinguish old-style Hound from SuperHound in UDP. Select F/H, SuperF/H, or Ignore.

Additionally, QSOP auto-detects **SuperFox** when "verified" or "$VERIFY$" appears in decoded messages — this upgrades F/H to SuperF/H automatically.

> **JTDX note:** JTDX does not populate the UDP special mode field. For JTDX users, manual selection via the combo box is the reliable detection path.

### What Changes in F/H Mode

**Old-style F/H:**
- Frequency recommendations clamped to ≥1000 Hz
- Fox zone (0–1000 Hz) dimmed red on band map with boundary marker
- Click-to-set below 1000 Hz is blocked

**SuperF/H:**
- No frequency clamping (Hounds may call anywhere ≥200 Hz)
- Fox zone overlay not shown (SuperFox occupies 750–2262 Hz)

**Both modes:**
- When Fox picks you up ("Working YOU" detected), click-to-set is fully disabled
- "FOX CONTROLLING TX FREQUENCY" replaces the green recommendation line
- Returns to normal when Fox moves to another station

### Working a SuperFox DXpedition — Step by Step

SuperFox DXpeditions operate on **non-standard frequencies** — the 1512 Hz wide signal would obliterate normal FT8 traffic if transmitted on 14.074.

1. **Find the frequency** — check the DXpedition's website or DX cluster for their published FT8 frequency (e.g. CY0S on 20m uses **14.091 MHz**, not 14.074)
2. **Tune your rig** to that exact frequency — even 1 kHz off means no decodes
3. **Set RX audio offset** to ~750 Hz in WSJT-X
4. **Set QSOP combo** to SuperF/H
5. **Watch the waterfall** — you'll see a massive wide block of signal (1512 Hz wide), nothing like normal FT8
6. **Wait for a Fox decode** to appear in WSJT-X Band Activity window — the SuperHound label turns **green** when verified
7. **Double-click the Fox decode line** — WSJT-X starts transmitting automatically
8. **Do not touch Enable TX** manually — it flashes momentarily if no Fox decoded yet, which is normal
9. **Let WSJT-X auto-sequence** — once in QSO, it handles everything including sending your R+report and receiving RR73
10. **QSO logs automatically** on RR73

> **WSJT-X SuperHound quirks:** The TX frequency field is locked by WSJT-X — AHK scripts cannot set it. Decode window clicks do not send target-selection UDP packets. Set your target manually in QSOP when operating SuperHound.

### Known Limitations

- WSJT-X UDP reports `special_mode=7` for both old-style Hound AND SuperHound — there is no automatic distinction. The disambiguation dialog handles this.
- JTDX always returns `special_mode=0` — manual selection is required for JTDX users.

---

## 9. Workflows & Tips

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

#### Hidden Pileup (v2.2.0)

**Signs:** Orange toast "Hidden pileup", yellow warning in Insights panel, few callers visible locally but high competition shown at target

**What's happening:** You can't hear the stations competing with you because propagation is one-way — they can reach the target but not you. This is extremely common on long paths.

**Your strategy:**
- Don't assume the band is clear just because your waterfall looks empty
- Trust the PSK Reporter data — the competition IS there
- Wait for the pileup to thin, or find a gap in the target's perspective (cyan bars with low counts)
- Watch for the "📉 Competition dropping" toast — that's your window

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
11. **Watch the toast bar** — tactical alerts appear above the decode table when conditions change. A green "target decoded YOU" toast means drop everything and call
12. **Don't trust an empty waterfall** — if the Insights panel shows a hidden pileup warning, there's competition you can't hear. Wait for the "competition dropping" toast

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
;
; NOTE: Check JTDX first! JTDX's title bar contains "WSJT-X"
; so WinExist("WSJT-X") matches both apps.

; JTDX coordinates
JTDX_TX_X := 800     ; TX frequency field
JTDX_TX_Y := 630
JTDX_DX_X := 130     ; DX Call field (text box under "DX Call")
JTDX_DX_Y := 630
JTDX_ENTX_X := 480   ; Enable TX button
JTDX_ENTX_Y := 365

; WSJT-X coordinates
WSJTX_TX_X := 800    ; TX frequency field
WSJTX_TX_Y := 630
WSJTX_DX_X := 130    ; DX Call field
WSJTX_DX_Y := 630
WSJTX_ENTX_X := 480  ; Enable TX button
WSJTX_ENTX_Y := 365

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

    ; Frequency: 3-4 digits, 300-3000 Hz — no Enter needed, no Enable TX
    if RegExMatch(clip, "^\d{3,4}$") && clip >= 300 && clip <= 3000 {
        ; JTDX first — its title contains "WSJT-X" so must check first!
        if WinExist("JTDX")
            PasteToField("JTDX", JTDX_TX_X, JTDX_TX_Y, clip, false, 0, 0)
        else if WinExist("WSJT-X")
            PasteToField("WSJT-X", WSJTX_TX_X, WSJTX_TX_Y, clip, false, 0, 0)
        return
    }

    ; Callsign: 3-10 chars, has letter AND digit — Enter + Enable TX
    if RegExMatch(clip, "^[A-Z0-9/]{3,10}$") && RegExMatch(clip, "[A-Z]") && RegExMatch(clip, "\d") {
        if WinExist("JTDX")
            PasteToField("JTDX", JTDX_DX_X, JTDX_DX_Y, clip, true, JTDX_ENTX_X, JTDX_ENTX_Y)
        else if WinExist("WSJT-X")
            PasteToField("WSJT-X", WSJTX_DX_X, WSJTX_DX_Y, clip, true, WSJTX_ENTX_X, WSJTX_ENTX_Y)
        return
    }
}

PasteToField(windowTitle, clickX, clickY, text, pressEnter, enTxX, enTxY)
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

        ; Click Enable TX after setting callsign
        if (enTxX > 0 && enTxY > 0) {
            Sleep 100
            Click enTxX, enTxY
        }

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
--
-- NOTE: Check JTDX first! JTDX's title bar contains "WSJT-X"
-- so hs.application.find("WSJT-X") matches both apps.

-- JTDX coordinates
local JTDX_TX_X, JTDX_TX_Y = 800, 630       -- TX frequency field
local JTDX_DX_X, JTDX_DX_Y = 130, 630       -- DX Call field
local JTDX_ENTX_X, JTDX_ENTX_Y = 480, 365   -- Enable TX button

-- WSJT-X coordinates
local WSJTX_TX_X, WSJTX_TX_Y = 800, 630      -- TX frequency field
local WSJTX_DX_X, WSJTX_DX_Y = 130, 630      -- DX Call field
local WSJTX_ENTX_X, WSJTX_ENTX_Y = 480, 365  -- Enable TX button

local lastClip = ""

hs.timer.doEvery(0.5, function()
    local clip = hs.pasteboard.getContents()
    if not clip or clip == lastClip then return end
    lastClip = clip
    clip = clip:match("^%s*(.-)%s*$")  -- trim

    -- Frequency: 3-4 digits, 300-3000 — no Enter, no Enable TX
    if clip:match("^%d+$") and #clip >= 3 and #clip <= 4 then
        local freq = tonumber(clip)
        if freq >= 300 and freq <= 3000 then
            local app, x, y = findAppCoords("TX")
            if app then pasteToField(app, clip, x, y, false, 0, 0) end
            return
        end
    end

    -- Callsign: 3-10 chars, has letter AND digit — Enter + Enable TX
    if #clip >= 3 and #clip <= 10
       and clip:match("^[A-Z0-9/]+$")
       and clip:match("[A-Z]")
       and clip:match("%d") then
        local app, x, y, ex, ey = findAppCoords("DX")
        if app then pasteToField(app, clip, x, y, true, ex, ey) end
    end
end)

function findAppCoords(fieldType)
    -- JTDX first! Its title contains "WSJT-X" so must check first
    local app = hs.application.find("JTDX") or hs.application.find("WSJT-X")
    if not app then return nil end
    local name = app:name()
    local isJTDX = name:find("JTDX")
    if fieldType == "TX" then
        if isJTDX then return app, JTDX_TX_X, JTDX_TX_Y, 0, 0 end
        return app, WSJTX_TX_X, WSJTX_TX_Y, 0, 0
    else
        if isJTDX then return app, JTDX_DX_X, JTDX_DX_Y, JTDX_ENTX_X, JTDX_ENTX_Y end
        return app, WSJTX_DX_X, WSJTX_DX_Y, WSJTX_ENTX_X, WSJTX_ENTX_Y
    end
end

function pasteToField(app, text, x, y, pressEnter, enTxX, enTxY)
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
            -- Click Enable TX after setting callsign
            if enTxX > 0 and enTxY > 0 then
                hs.timer.doAfter(0.1, function()
                    hs.eventtap.leftClick({x = frame.x + enTxX, y = frame.y + enTxY})
                end)
            end
            -- Confirmation
            local label = pressEnter and "DX Call" or "TX Freq"
            hs.alert.show(label .. " → " .. text, 1.5)
        end)
    end)
end
```

3. Reload Hammerspoon config (⌘+R in console).

> **Note:** Both scripts check for JTDX first because JTDX's title bar contains "WSJT-X" (it's a fork). If you check WSJT-X first, it will match JTDX and use the wrong coordinates. You can also skip the scripts entirely and just Ctrl+V / ⌘+V manually.

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

## 10. Settings

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

## 11. Troubleshooting

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

### SuperFox — Enable TX Flashes But Won't Transmit

WSJT-X prevents transmitting in SuperHound mode until you have decoded the Fox. Enable TX flashing momentarily then returning to white means no Fox decode has been received yet.

**Check:**
1. Is your rig on the DXpedition's exact published frequency (not 14.074)?
2. Is the RX audio offset set to ~750 Hz?
3. Can you see a wide block signal on the waterfall? If not, the Fox may not be transmitting on your current band or the path may be closed.
4. Once a Fox decode appears in the Band Activity window, double-click it — WSJT-X will then enable TX.

### SuperFox — Clicking Decodes Does Nothing

In SuperHound mode, WSJT-X suppresses decode window clicks and does not send target-selection UDP packets. This is intentional WSJT-X behaviour. Set your target manually in QSOP's target field.

---

## 12. FAQ

**Q: Does QSO Predictor transmit for me?**  
A: No. It's advisory only. You control your radio through WSJT-X/JTDX.

**Q: Does it work with other modes (CW, SSB)?**  
A: Currently FT8/FT4 only. The algorithms are designed for these modes.

**Q: Can I use it without internet?**  
A: Partially. Local Intelligence works offline. Target Perspective requires PSK Reporter (internet).

**Q: Does it work on Mac/Linux?**  
A: Yes — Windows (.exe) and macOS (.dmg) builds are available on the Releases page. Linux users should run from Python source.

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

**Q: What is SuperFox mode and how is it different from Fox/Hound?**  
A: SuperFox is an enhanced DXpedition mode introduced in WSJT-X 2.7.0. Instead of up to 5 simultaneous narrow FT8 signals, the Fox transmits a single 1512 Hz wide constant-envelope signal that can work up to 9 Hounds simultaneously with no signal-strength penalty. It also includes a digital signature that WSJT-X verifies to confirm the Fox is a legitimate DXpedition. Most major DXpeditions from 2024 onward use SuperFox.

**Q: Why can't I click on decodes in WSJT-X when in SuperHound mode?**  
A: WSJT-X intentionally suppresses decode window interaction in SuperHound mode — the protocol is almost fully automated. Double-click only works on the Fox's own decode line, which triggers WSJT-X to start calling. All other clicks are blocked.

**Q: Why won't Enable TX stay on in SuperHound mode?**  
A: WSJT-X prevents blind calling in SuperHound mode to keep the bands clean. You must first receive and decode a transmission from the Fox, then double-click that decode. Enable TX will then latch on properly.

**Q: The SuperFox is on 14.091 but I'm tuned to 14.074 — why does this matter?**  
A: SuperFox stations must use non-standard frequencies because their 1512 Hz wide signal would obliterate all normal FT8 traffic if transmitted on 14.074. Always check the DXpedition's published frequency on their website or the DX cluster before trying to work them on FT8.

**Q: How do I know if a DXpedition is using SuperFox or old-style Fox/Hound?**  
A: Check their website — it will be stated explicitly. Visual clues: SuperFox produces a wide block signal on the waterfall; old-style Fox produces narrow multiple streams. In WSJT-X, the SuperHound label turns green when the Fox signal is verified (old-style Hound shows red).

**Q: What is a "hidden pileup"?**  
A: When you see few or no callers on your waterfall but PSK Reporter shows heavy competition at the target's location. This happens because propagation is often asymmetric — stations from other regions can reach the target but their signals don't reach you. The v2.2.0 pileup contrast feature detects this and warns you.

**Q: Why does the Path column show "Not Heard" but the recommendation says "CALL NOW"?**  
A: v2.2.0 uses "effective path status" — if Path Intelligence shows stations from your area getting through (even though YOUR specific signal hasn't been confirmed), the recommendation accounts for that evidence. The Path column still shows the factual status of your signal, while the recommendation considers the broader picture.

---

## Getting Help

- **GitHub Issues:** [Report bugs or request features](https://github.com/wu2c-peter/qso-predictor/issues)
- **GitHub Discussions:** [Ask questions, share tips](https://github.com/wu2c-peter/qso-predictor/discussions)

---

**73 de WU2C**
