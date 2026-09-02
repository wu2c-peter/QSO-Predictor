# Partner Center Submission Guide — QSO Predictor

**Purpose:** Field-by-field reference for submitting QSO Predictor to the Microsoft Store via Partner Center.

**Revision history:**
- v1 — Written 2026-04-21 during v2.5.4 prep (pre-submission)
- **v2 — Revised 2026-04-22 after successful submission to certification**

This revision incorporates real-world discoveries from the actual submission walkthrough. Items marked **[CORRECTED]** differ from the v1 guide.

---

## Section 0 — Post-submission record (reference)

**First successful submission:** 2026-04-22, status: In certification as of that date.

**v2.7.1 submission:** 2026-07-28, package QSOPredictor_2.7.1.0_x64.msix.
Certification PASSED and published to the Store same day (2026-07-28). Listing changes: new what's-new text,
feature bullet #10 (Station diagnostics), and a Station Diagnostics
KEY CAPABILITIES paragraph — exact copy recorded in Sections 8 below.

**v2.8.0 submission:** 2026-08-03, package QSOPredictor_2.8.0.0_x64.msix.
Certification PASSED and published to the Store same day (2026-08-03). Listing changes: new what's-new text
(click-to-call + UDP hardening), bullet 7 revised to plain-truth
transmit framing, bullet 11 added (click-to-call), description
paragraph 2 revised + Click-to-call KEY CAPABILITIES paragraph added
first — exact copy recorded below.
Supersedes v2.6.0's never-submitted Store cycle (Store users go
2.5.x -> 2.7.1 directly).

**v2.8.1 submission:** 2026-09-02, package QSOPredictor_2.8.1.0_x64.msix
(104.03 MB, built on the shack PC from `main` @ 3a753d6; manifest
2.8.1.0). Bug-fix release — submitted despite the checklist's
"batch bug fixes" rule because it makes the sweep-aware recommender
work in packaged builds for the first time. Listing changes: new
what's-new text only (below); description, bullets, screenshots,
runFullTrust justification reused unchanged from 2.8.0. Certification
result: pending at time of writing — update this line when it lands.

What's-new text submitted:

> v2.8.1 — the audit release. A systematic code review fixed forty
> defects, each now covered by a regression test. What you'll notice:
> sweep-aware frequency recommendations now work in the packaged app
> (when a station works its pileup high-to-low or low-to-high, the
> recommendation follows); the green line is no longer stuck at the
> bottom of the passband when the target has no direct spots; PSK
> Reporter and solar-data outages are reported honestly instead of
> showing stale or zero values; "Not Transmitting" only appears when
> you really are off the air; FT4 is handled as FT4; right-click "Set
> as Target" and the Insights manual-target entry work again; Settings
> → Appearance takes effect; behavior bootstrap no longer freezes the
> window. No changes to how you operate the app.

**Values submitted:**
- Product name: QSO Predictor
- Package: QSOPredictor_2.5.4.0_x64.msix (102.53 MB)
- Price: Free, all worldwide markets, public audience
- Primary category: Utilities + tools (no subcategory — available subs Backup + manage and File managers don't fit)
- Secondary category: Productivity
- Privacy policy URL: https://qsop.wu2c.net/privacy/
- Website: https://qsop.wu2c.net/
- Support contact: qsop@wu2c.net (email form)
- Age rating: 3+ / Everyone / PEGI 3 (all IARC questions answered No)
- Screenshots: screenshot.png, QSOP-heardbytarget.png, QSOP-RR73.png (3 PNGs)
- Device family: Windows 10/11 Desktop only
- Additional declarations: ALL unchecked (specifically NOT generative AI)

---

## Section 1 — Pre-submission readiness checklist

Before starting the submission in Partner Center, confirm the following.

- [ ] **Reserved name still valid.** Re-reserve if the 3-month hold expired.
- [ ] **MSIX package available locally.** Identity must match what Partner Center has reserved.
- [ ] **Privacy policy page loads over HTTPS.** Test `https://qsop.wu2c.net/privacy/` in a fresh incognito browser.
- [ ] **Support page loads over HTTPS.** Test `https://qsop.wu2c.net/support/`.
- [ ] **Email alias configured and tested.** Send a real test message to `qsop@wu2c.net` and confirm delivery to `peter@wu2c.net`.
- [ ] **Screenshots prepared.** See Section 10 below.
- [ ] **About dialog shows correct version.** Launch installed MSIX one final time, confirm.

---

## Section 2 — MSIX package identity reference

These values must match what Partner Center has reserved.

| Field | Value |
|---|---|
| Package Identity Name | `PeterHirstWU2C.QSOPredictor` |
| Package Identity Publisher | `CN=66D60A45-A38B-4C72-BFF6-F710FB0E496D` |
| Publisher Display Name | `Peter Hirst (WU2C)` |
| Package Family Name | `PeterHirstWU2C.QSOPredictor_8m0mce250zbcc` |
| Store ID | `9MWCW2FTB866` |

Source of truth: `dev-docs/MICROSOFT_STORE_IDENTITY.md`.

---

## Section 3 — Submission overview

Partner Center organizes an MSIX app submission into six main sections plus one supplemental page:

1. **Pricing and availability** — free/paid, markets, audience
2. **Properties** — category, support info, system requirements, product declarations
3. **Age ratings** — IARC questionnaire
4. **Packages** — upload the MSIX, select device family
5. **Store listings** — description, screenshots, keywords, copyright
6. **Submission options** — runFullTrust justification, notification audience
7. **Additional Testing Information** (sidebar → Supplemental info) — reviewer guidance

**[CORRECTED]** The original guide treated the reviewer notes as belonging in "Submission options." In reality, that page's textarea is specifically for the `runFullTrust` justification (~500 char limit). The broader reviewer testing notes belong on the separate **Additional Testing Information** page.

---

## Section 4 — Pricing and availability

**Set these fields:**

- **Currency:** USD (or your local)
- **Retail price:** Free
  - **[CORRECTED]** The UI doesn't have a simple "Free toggle" — you set it via the Retail price dropdown in the Market groups → Default section. "Free" appears as an option in that dropdown once a currency is selected.
- **Markets:** All worldwide markets (Recommended)
- **Make my product available in any future market:** Checked
- **Audience:** Public audience
- **Discoverability:** Default
- **Schedule:** Publish as soon as certification passes

---

## Section 5 — Properties

### Category selection

**Primary category:** `Utilities + tools`
- **[CORRECTED]** Available subcategories under this primary are only `Backup + manage` and `File managers`. Neither fits QSOP. Leave subcategory unselected.

**Secondary category:** `Productivity` (no subcategories on Productivity)

### Support info

- **Privacy policy URL:** `https://qsop.wu2c.net/privacy/`
- **Website:** `https://qsop.wu2c.net/` (include `https://`)
- **Support contact info:** `qsop@wu2c.net`
  - **[NOTE]** The field error message says "Support contact is not a valid URL or a valid email address" — meaning the field accepts either. Microsoft's instructional paragraph says "(email only)" but the actual validation is more permissive. An email is simpler and what we used.

### Developer contact info (EU DSA-driven regulatory requirement)

**[CORRECTED]** Microsoft requires a publicly-displayed physical address and phone number due to regulatory compliance (likely EU Digital Services Act). These fields are required:

- Address line 1
- City
- State/Province
- Postal code
- Country/Region
- Phone number

**This information displays publicly on the Store listing.** For an individual developer who already has a publicly-traceable address (e.g., via FCC amateur radio license database), using a home address is reasonable. Alternatives: virtual mailbox service, PO Box (may be rejected for requiring street address).

The address is framed by Microsoft as developer contact information, not business address — using a home address does NOT imply running a business from home. An Individual Developer account + free app + OSS framing reinforces non-commercial identity.

### Privacy declaration

Answer: **Yes** — we have a privacy policy at the URL above. Conservative answer; requires the privacy URL which we have.

### System requirements

**[CORRECTED]** The original guide suggested "4 GB minimum, 8 GB recommended" for Memory. **Actual recommendation: leave ALL fields Not specified or blank.**

Microsoft's own text on the page: *"If the Store detects that a customer is using hardware that doesn't meet the Minimum requirements... the customer may see a warning before they download your product and they won't be able to rate or review it."*

You don't want warnings blocking users who can run QSOP fine. For a general desktop utility:

- Touch screen, Keyboard, Mouse, Camera, NFC, Bluetooth LE, Telephony, Microphone → all unchecked
- Xbox controller, Windows Mixed Reality motion controllers, Windows Mixed Reality immersive headset → all unchecked
- Memory, DirectX, Video memory → Not specified
- Processor, Graphics → blank

### Display mode

**[CORRECTED]** Display mode (PC, HoloLens, Seated + standing, etc.) is for **Windows Mixed Reality apps only**. QSOP is a 2D desktop app — leave both PC and HoloLens unchecked. The "Seated + standing" default radio button is irrelevant when neither checkbox is selected.

### Product declarations

**[CORRECTED]** Partner Center may pre-check some boxes that are WRONG for a simple utility. Go through these deliberately:

**Uncheck all of these (even if pre-checked):**
- Customers can install to alternate drives or removable storage → uncheck (MSIX managed by Windows)
- Windows can include this product's data in OneDrive backups → uncheck (QSOP data is personal, keep local)
- Customers can use Windows 10/11 features to record and broadcast clips → uncheck (Microsoft's own warning says "Games only")

**Leave unchecked (these should never be checked):**
- This product allows purchases outside Microsoft Store commerce → no purchases at all
- This product has been tested to meet accessibility guidelines → don't claim untested
- This product supports pen and ink input → not supported
- This product incorporates **generative AI** features → **important: QSOP uses PREDICTIVE ML (behavior classification, propagation modeling) not generative AI.** The box specifically refers to apps that CREATE new content (text, images, audio, video, code) via AI. QSOP does not generate content.

---

## Section 6 — Age ratings (IARC)

All questionnaire answers: **No.**

Expected rating: **3+ / Everyone / PEGI 3.**

---

## Section 7 — Packages

**Upload:** `packaging/QSOPredictor_X.Y.Z.0_x64.msix`

**Device family selection (CRITICAL):**
- ✅ Windows 10/11 Desktop
- ❌ Windows 10 Mobile (discontinued)
- ❌ Windows 10/11 Xbox (not a game)
- ❌ Windows 10 Team (Surface Hub)
- ❌ Windows 10 Mixed Reality (VR)
- ✅ "Let Microsoft decide for future device families" (forward-looking consent)

Package validation runs automatically after upload. Expected: green "Validated" status.

**[NOTE]** Our self-signed MSIX with Publisher matching the reservation uploaded and validated without issue. Microsoft re-signs packages on ingestion, so local signing is for install-testing only.

---

## Section 8 — Store listings (English — United States)

### Language selection page

First, at "Manage Store listing languages": only English (United States) pre-selected. **Don't add additional languages** unless you have actual translations of description, features, privacy policy, and UI ready. Click Save; that takes you to the English listing.

### Product name

Pre-populated as reserved: `QSO Predictor`

### Description

**[CORRECTED]** No "Short description" field appeared in the MSIX submission flow we experienced. If it appears in yours, use the 270-char version below. Otherwise the Description field is the only narrative field.

Description is ~3,200 chars (within 10,000 limit), plain text:

```
QSO Predictor is a real-time tactical assistant for FT8 and FT4 digital-mode amateur radio operating. It shifts your perspective from what your own receiver is hearing to what the DX station's region is experiencing — reconstructing band activity at the target's location so you can choose cleaner transmit frequencies, confirm your signal is actually reaching the target's area, and time your calls more effectively.

QSO Predictor integrates with WSJT-X and JTDX via UDP. It does not transmit on your behalf and never takes control of your radio. Every recommendation is advisory; you keep full operational responsibility.

KEY CAPABILITIES

Target-perspective band map. Using real-time PSK Reporter data filtered by geographic proximity to your selected target, QSO Predictor reconstructs what stations near the DX target are decoding on your chosen band. Signals are color-coded by reporter proximity, with density indicators showing frequency congestion at the target's location — information your own receiver cannot give you.

Frequency recommendations. QSO Predictor identifies transmit frequencies that are clear in the target's region, not just in yours. Recommendations prefer frequencies where the target (or stations near them) are already successfully decoding activity — proven paths, not just empty air.

Propagation confirmation. The path status indicator shows whether your signal is reaching reporters in the target's area. A confirmed path before you call is more valuable than wasted cycles on a closed band.

Local intelligence. QSO Predictor analyzes your own WSJT-X/JTDX log history to learn the operating patterns of stations you have observed. It classifies them along behavioral dimensions — loudest-first, methodical, random — and offers pileup-strategy guidance based on the target's likely calling style. All analysis runs locally; nothing is uploaded.

Propagation prediction (IONIS). Built-in ionospheric propagation modeling combines solar index data from NOAA with statistical models to estimate whether a given path at a given band is open, marginal, or closed. Predictions are compared in real time with PSK Reporter observations so you can see when conditions are exceeding or falling below predictions.

Outcome tracking. Each QSO attempt — no-response, exchange-started, fully-logged — is recorded locally for self-evaluation and future coaching features.

PRIVACY AND OPEN SOURCE

QSO Predictor does not collect, store, or transmit any personal information. It reads data only from sources you already use locally (your own WSJT-X/JTDX log files) and public amateur radio data services (PSK Reporter, NOAA). No telemetry, no analytics, no user accounts.

QSO Predictor is open-source software released under the GNU GPL version 3. Complete source code, issue tracker, and documentation are available on GitHub.

WHO THIS IS FOR

QSO Predictor is designed for licensed amateur radio operators who work the HF bands using FT8 and FT4 digital modes. It assumes familiarity with WSJT-X or JTDX and standard amateur radio concepts including grid squares, propagation, SNR, and pileup dynamics. A working HF station is required.

This is a desktop utility, not a learning tool. If you are new to amateur radio, other resources are better-suited for getting started. Once you have a station on the air and are chasing DX, QSO Predictor can measurably improve your call timing and frequency selection.

73.
```

### What's new in this version

**Leave blank for first submission.** Microsoft's own field hint confirms this.

**v2.6.0 submission (2026-07-21):**

> NEW: Audio Doctor (Tools menu, Windows) — find out why your TX audio
> went silent, in seconds. Windows can silence WSJT-X invisibly: a
> per-app mixer mute that survives reboots, communications ducking
> triggered by a browser using the microphone, or a stale device entry
> after a USB port change. Audio Doctor runs a read-only 11-point audit
> of the audio path between WSJT-X/JTDX and your rig, plus a live TX
> check: press Tune, and it watches the Windows peak meters and reports
> exactly which layer is silent. Findings link straight to the exact
> Windows settings panel where each fix lives. QSO Predictor also now
> warns automatically in the status bar if WSJT-X reports transmitting
> while no audio is reaching the rig. Works with FT8web browser
> transmissions too. Audio Doctor changes nothing on your system — it
> is diagnosis only. Plus smaller fixes and a larger automated test
> suite.

(The GitHub-release IONIS disclosure is deliberately absent here —
Store builds were never affected.)

**v2.7.1 submission (submitted 2026-07-28; 1,288 chars):**

> NEW: The Doctors — full station diagnostics (Diagnostics menu, all
> platforms). Run Full Checkup examines your whole station passively —
> system clock vs internet time, app configs, the UDP decode chain,
> serial/CAT ports and adapter chips, power-management traps, and the
> Windows TX-audio path — and builds one shareable report designed to
> be pasted into a forum post or an AI assistant when you need help.
> Findings come first with fixes; every passed check is listed so
> "checked and fine" is distinguishable from "not examined"; usernames
> are scrubbed and your callsign is included only if you choose. Five
> new doctors join the Audio Doctor: Clock (FT8's silent killer is a
> clock one second off), Config (duplicate config files, stale
> audio-device bindings), Network (verifies who is actually listening
> on your UDP chain and names the broken link), Serial/CAT (identifies
> adapter chips, catches missing COM ports and the counterfeit-Prolific
> driver trap — without ever opening a port), and System (Fast Startup,
> USB selective suspend, sleep, autostart). Nothing is changed, opened,
> or transmitted. Audio Doctor moved from Tools to the new Diagnostics
> menu. Also: the status bar's "reporting" count now shows distinct
> receivers on your current band. Plus a much larger automated test
> suite.

**v2.8.0 submission (2026-08-03; 1,262 chars):**

> NEW: Click-to-call — double-click a station in QSO Predictor and it
> is set up in WSJT-X, no window switching. A station calling CQ gets
> a native reply: WSJT-X behaves exactly as if you double-clicked that
> decode in its own window, honoring your auto-TX-enable setting. Any
> other callsign is placed in the DX Call box with standard messages
> generated, ready for you to press Enable TX — something Reply-based
> tools cannot do. QSO Predictor never transmits on its own. (JTDX: CQ
> replies supported; for other stations the callsign is copied to the
> clipboard.) Also in this release: multicast reception now joins
> every network interface — a VPN adapter could previously capture the
> connection and leave the app deaf while other programs received
> fine; the Network Doctor gains a "Shared unicast ports" check that
> names which app silently starves when two programs bind one port;
> UDP forwarding accepts host:port targets to feed apps on another
> machine; callsign and grid changes apply without a restart; and the
> silent-TX warning now requires two consecutive silent transmissions
> before it appears, so one interrupted cycle no longer flashes a
> warning. New setup guides for running WSJT-X, GridTracker, JTAlert
> and QSO Predictor together: qsop.wu2c.net/integrations/

### Product features (up to 20 bullets, 200 chars each)

Eight bullets:

1. `Real-time view of band activity from the DX station's regional perspective, not just yours`
2. `Transmit frequency recommendations based on what the target's area is actually decoding`
3. `Signal path confirmation — know whether your signal reaches the target's region before you call`
4. `Behavioral analysis of stations you observe — identifies operating patterns to refine your call strategy`
5. `Ionospheric propagation prediction (IONIS) compared in real time with live PSK Reporter data`
6. `Seamless integration with WSJT-X and JTDX via UDP; no separate radio control required`
7. `Advisory only — you keep full control of your radio; QSO Predictor never transmits for you`
8. `No telemetry, no tracking, no personal data transmitted; open source under GPLv3`

**Added at v2.5.8 submission:** the WSJT-X bullet (#6) was extended to
mention FT8web, plus a new FT8web UDP-bridging bullet — exact live
wording is in Partner Center (this file wasn't updated at the time;
reconcile when convenient).

**Added at v2.6.0 submission:**

9. `Audio Doctor (Windows): one-click diagnosis of silent TX audio — hidden mixer mutes, ducking, device traps — with a live meter check and links to the exact Windows setting to fix`

Description field also gained an "Audio Doctor." paragraph under KEY
CAPABILITIES at v2.6.0 (see chat/RELEASE_NOTES_v2.6.0.md for the text
as entered).

**Added at v2.7.1 submission (submitted 2026-07-28; 186 chars —
existing bullets 1–9 unchanged, #9 Audio Doctor still accurate):**

10. `Station diagnostics: one Full Checkup verifies clock, configs, UDP chain, serial/CAT ports and power traps — and builds a shareable report made to paste into a forum post or AI assistant`

Description KEY CAPABILITIES paragraph to add at v2.7.1 (before or
after the Audio Doctor paragraph):

> Station Diagnostics. One Full Checkup passively examines the system
> clock, app configs, the UDP decode chain, serial/CAT hardware, and
> OS power-management traps, then builds a single shareable report —
> written to be pasted into a forum post or an AI assistant, with
> findings first and your identity included only if you choose.
> Nothing on your system is changed, opened, or transmitted.

**Changed at v2.8.0 submission (2026-08-03):**

Bullet 7 REVISED (144 chars — the old "Advisory only … never
transmits for you" wording; keep the plain-truth framing, not
over-cautious):

7. `You stay in control — QSO Predictor never transmits on its own; TX only ever starts from your double-click, governed by your own WSJT-X settings`

Bullet 11 ADDED (189 chars):

11. `Click-to-call: double-click a station and it's set up in WSJT-X — a fresh CQ gets a native reply, anyone else lands in the DX Call box ready for your Enable TX. Same UDP link, all platforms`

Description paragraph 2 REVISED (same framing rationale):

> QSO Predictor integrates with WSJT-X and JTDX via UDP. It never
> transmits on its own — the only time it touches TX is when you
> double-click a station to call it, and even then WSJT-X applies
> your own settings. You keep full operational responsibility.

Description KEY CAPABILITIES paragraph ADDED (first position, before
"Target-perspective band map"):

> Click-to-call. Double-click a station — in the decode table or on
> the target dashboard — and it is set up in WSJT-X over UDP. A
> station calling CQ gets a native reply, exactly as if you had
> double-clicked the decode in WSJT-X itself; any other callsign is
> placed in the DX Call box with standard messages generated, ready
> for you to press Enable TX. No window switching, no helper scripts.

### Screenshots (at least one required)

Upload in this order:
1. `screenshot.png` — main window overview (hero image)
2. `QSOP-heardbytarget.png` — intelligence layers aligned, CALL NOW
3. `QSOP-RR73.png` — completed QSO with exchange visible

Format requirements: PNG, under 50 MB each. Captions optional.

### Store logos

**[CORRECTED / NEW]** Leave all six slots blank. The MSIX package's 28 embedded icons will be used automatically. Adding promotional poster art here is optional polish that primarily benefits featured-app slots which QSOP (a niche utility) won't receive.

If Peter wants to add promotional art in a future submission:
- 9:16 Poster art (720×1080 or 1440×2160) — "highly recommended" per Microsoft
- 1:1 Box art (1080×1080 or 2160×2160) — "recommended for best display"
- PNG only, under 50 MB each

### Additional information

**Keywords** (up to 7, 40 chars each, 21 words total):
- `FT8`
- `FT4`
- `WSJT-X`
- `JTDX`
- `amateur radio`
- `ham radio`
- `PSK Reporter`

**Copyright and trademark info:**
```
© 2025 Peter Hirst (WU2C). Released under GPL v3.
```

**Additional license terms:** leave blank (don't add custom terms on top of Microsoft's Standard Application License Terms).

**Developed by:** `Peter Hirst (WU2C)` (matches Publisher Display Name and Copyright)

---

## Section 9 — Submission options

### runFullTrust justification (~500 character limit)

**[CORRECTED]** This field is specifically the restricted-capability justification, not general reviewer notes. The original guide's longer text belongs on the Additional Testing Information page.

Paste this:

```
QSO Predictor reads user-selected WSJT-X and JTDX log files (ALL.TXT format) from standard OS locations using standard Win32 file I/O. This is a desktop utility migrated from unpackaged distribution and requires full trust to access user log files that live outside the MSIX package sandbox. No privileged system access or elevation is required.
```

~400 characters — fits with room to spare.

### Submission notification audience

Leave default (account owner, peter@wu2c.net).

---

## Section 10 — Additional Testing Information page

**[CORRECTED / NEW SECTION]** This is a separate page in the Partner Center sidebar under "Supplemental info". This is where the longer reviewer testing notes go.

### Description field

Paste this (~1,750 chars):

```
QSO Predictor is a utility for licensed amateur radio operators working the FT8 and FT4 digital modes on HF bands.

HOW TO TEST

The application is designed to launch standalone and show its main window without requiring amateur radio hardware or WSJT-X/JTDX to be running. Reviewers can verify install, launch, About dialog, and Settings dialog without any external dependencies.

Expected behavior with no other software running:
- Main window opens with a band map (initially empty — no decodes yet) and a target panel
- Help → About shows version 2.5.4, copyright, and a link to the privacy policy
- Settings dialog opens and displays all configuration options
- The app remains running and responsive

Full operational testing would require:
- WSJT-X or JTDX installed and running with UDP configured
- An amateur radio transceiver on the air decoding FT8 or FT4 signals

This is not expected of certification reviewers. An empty band map with no decodes is NORMAL and EXPECTED behavior without WSJT-X/JTDX feeding the app.

STARTUP BEHAVIOR

On launch, the app attempts connections to:
- PSK Reporter MQTT (mqtt.pskreporter.info) — public amateur radio spot data
- NOAA Space Weather API (services.swpc.noaa.gov) — public solar index data

Both are public, read-only, no authentication required. If blocked by network policy, the app still runs; it just shows reduced propagation context.

If WSJT-X or JTDX is installed, the app reads their ALL.TXT log files from standard locations (%LOCALAPPDATA%\WSJT-X\ or %LOCALAPPDATA%\JTDX\). If not installed, no logs are read; the app runs with reduced functionality.

PRIVACY

No user data is collected, stored, or transmitted by the app. Privacy policy is published at https://qsop.wu2c.net/privacy/ and linked from the About dialog.

OPEN SOURCE

Released under GPL v3. Source code at https://github.com/wu2c-peter/qso-predictor

CONTACT

Support: qsop@wu2c.net

73 de WU2C
```

### Credentials section

**Leave empty.** For apps that require login; QSOP doesn't.

### Save

Click "Save description" at the top of the page. Then return to Application overview / Product release.

---

## Section 11 — Language precision reference

Throughout all submission copy and marketing materials, use precise language about what QSOP does regarding pileup intelligence.

**Preferred phrasing:**
- "Reconstructs what the DX station's region is decoding"
- "Shows how crowded each frequency is at the target's location"
- "Regional decode activity"

**Avoid:**
- "Who is in the pileup" — QSOP does not identify specific competitors calling the target
- "Who is calling" the target
- "See the pileup" without qualification

**Why:** PSK Reporter data is `<reporter> heard <sender>`. QSOP shows decoded senders near the target but cannot determine which are specifically calling this target.

---

## Section 12 — Pre-submit final checklist

Final checks just before clicking "Submit for certification":

- [ ] All six sections in Product release page show Complete (green pills)
- [ ] Package Validated status
- [ ] Privacy URL loads in fresh incognito: `https://qsop.wu2c.net/privacy/`
- [ ] Support URL loads: `https://qsop.wu2c.net/support/`
- [ ] Email test: sent test to `qsop@wu2c.net`, received it
- [ ] Spell-check the description one more time
- [ ] Confirm Additional Testing Information has been filled in (not required but useful)

Then click **Submit for certification**.

---

## Section 13 — After submission

### Expected certification timeline

Per Microsoft's own text on the certification status page: *"The certification step usually takes a few hours, but in some cases can take up to 3 business days."*

Email notifications at peter@wu2c.net as status progresses.

### Status progression

1. **Submission** → complete immediately on click
2. **Pre-processing** → automated checks (identity, manifest, malware, policy); typically minutes
3. **Certification** → automated and manual review; hours to days
4. **Publishing** → automatic on certification pass

### If certification fails

Read the specific rejection reason in the email and in Partner Center. Common first-submission issues:
- Privacy policy URL rejected (our URL is a real policy page, mitigated)
- Screenshots don't meet requirements (pre-verified)
- Manifest identity mismatch (verified)
- App crashes on clean VM (verified install locally)

Fix specific issue, resubmit.

### Post-approval tasks (when Store goes live)

When the listing becomes live:

1. **Get the live Store URL** — likely format `https://apps.microsoft.com/detail/9mwcw2ftb866` (verify exact format when live)
2. **Update README.md** — add "Install from Microsoft Store" link alongside GitHub Releases
3. **Update docs/index.md** — add Microsoft Store badge/link
4. **Update docs/USER_GUIDE.md Section 2 (Installation)** — document both install paths
5. **Update wiki Home page** — Store install option
6. **Announce** (optional) — QRZ, Reddit r/amateurradio, Groups.io WSJT-X group
7. **v2.5.5 planning** — update About dialog privacy URL from github.com/.../PRIVACY.md to `https://qsop.wu2c.net/privacy/` directly

### Submitting updates (v2.5.5+)

Partner Center lets a new submission inherit most fields from the prior. Only changed sections (Packages, What's new) need updating.

---

## Section 14 — Reference URLs

- Partner Center dashboard: https://partner.microsoft.com/dashboard
- Privacy policy: https://qsop.wu2c.net/privacy/
- Support page: https://qsop.wu2c.net/support/
- Website: https://qsop.wu2c.net/
- GitHub repo: https://github.com/wu2c-peter/qso-predictor
- Microsoft Learn — Categories (MSIX): https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/categories-and-subcategories
- Microsoft Learn — App submissions: https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/create-app-submission

---

## Changelog

**v2 (2026-04-22):**
- Added Section 0 (post-submission record)
- Corrected Pricing flow (Free via Retail price dropdown, not a simple toggle)
- Corrected category subcategory availability (Backup + manage and File managers are the only options under Utilities + tools)
- Added developer address/phone regulatory requirement (EU DSA)
- Corrected system requirements recommendation to "Not specified everywhere"
- Corrected Display mode interpretation (VR/MR only, not desktop PC)
- Added product declaration corrections (uncheck pre-checked wrong boxes)
- Clarified generative vs predictive AI distinction
- Corrected runFullTrust justification field scope (~500 chars, restricted-capability-only)
- Added Additional Testing Information section (separate page, ~1,750 chars usable)
- Added Store logos guidance (leave blank, package icons used)
- Reordered post-approval tasks

73 de WU2C
