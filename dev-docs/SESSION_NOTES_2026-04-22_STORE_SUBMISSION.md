# Session Notes — 2026-04-22 — Microsoft Store Submission

## Summary

Submitted QSO Predictor v2.5.4 to the Microsoft Store via Partner Center. Status when session ended: **In certification** (Pre-processing stage, awaiting automated and manual review).

## What happened

Sequential walk through every Partner Center submission page, filling each field based on the pre-written PARTNER_CENTER_SUBMISSION_GUIDE.md. Discovered several discrepancies between the guide's assumptions and Partner Center's actual behavior; guide revised to v2 at end of session.

## Submission values (final, for the record)

### Pricing and availability
- Currency: USD, Retail price: Free
- Markets: All worldwide markets (Recommended)
- Make available in future markets: ✓
- Audience: Public
- Schedule: Publish as soon as certification passes

### Properties
- Primary category: Utilities + tools (no subcategory — available subs don't fit)
- Secondary category: Productivity
- Privacy policy URL: https://qsop.wu2c.net/privacy/
- Website: https://qsop.wu2c.net/
- Support contact: qsop@wu2c.net (email)
- Address/phone: Home address used (already public via FCC ULS database)
- Privacy declaration: Yes
- System requirements: ALL Not specified / blank
- Display mode: both unchecked (VR/MR only, N/A)
- Product declarations: all unchecked

### Age ratings
- IARC questionnaire all No → 3+ / Everyone / PEGI 3

### Packages
- QSOPredictor_2.5.4.0_x64.msix uploaded, validated
- Device family: Windows 10/11 Desktop only
- "Let Microsoft decide for future device families": ✓

### Store listings (English US)
- Product name: QSO Predictor (pre-reserved)
- Description: ~3,200 char version from submission guide
- What's new: blank (first submission)
- Product features: 8 bullets pasted
- Screenshots (3): screenshot.png, QSOP-heardbytarget.png, QSOP-RR73.png
- Store logos: all 6 slots blank (package icons used)
- Keywords (7): FT8, FT4, WSJT-X, JTDX, amateur radio, ham radio, PSK Reporter
- Copyright: © 2025 Peter Hirst (WU2C). Released under GPL v3.
- Additional license terms: blank
- Developed by: Peter Hirst (WU2C)

### Submission options
- runFullTrust justification: ~400 char short version
- Notification audience: default (peter@wu2c.net)

### Additional Testing Information
- Description: ~1,750 char testing guidance for reviewers
- Credentials: none (empty)

---

## Discoveries and corrections to the original guide

### 1. Pricing "Free" is not a simple toggle

**Original guide assumption:** set a Price dropdown to Free.

**Actual behavior:** Partner Center's Pricing page is structured for paid products with "Base price" (Currency dropdown + Retail price dropdown). For free apps, select a Currency, then "Free" appears as an option in the Retail price dropdown.

### 2. Utilities + tools subcategories are very narrow

**Original guide assumption:** primary category has a usable subcategory.

**Actual behavior:** Utilities + tools has only two subcategories: "Backup + manage" and "File managers". Neither fits QSOP. Leave subcategory blank.

### 3. EU DSA-driven physical address requirement

**Original guide didn't anticipate this.** Microsoft now requires developer address and phone number displayed publicly on the product page, driven by regulatory compliance (likely EU Digital Services Act).

**Decision made this session:** use home address. Rationale:
- FCC ULS database already makes amateur radio operators' name/address publicly searchable via callsign
- Individual Developer account + free OSS + Publisher Display Name = "individual developer" identity, not commercial activity
- Zoning, tax, and insurance implications of listing address on Store are minimal for free software distribution
- Same logic Apple App Store and Google Play already require for all developer accounts

### 4. "Support contact info" accepts URL OR email

**Original guide:** recommended email only based on Microsoft's instructional text.

**Actual behavior:** field error message explicitly says accepts "URL or email." Either works. Email simpler; URL would point to the Support page (https://qsop.wu2c.net/support/) as a more structured alternative.

### 5. System requirements should be "Not specified" everywhere

**Original guide recommendation:** "4 GB minimum, 8 GB recommended" for Memory.

**Actual behavior:** Minimum values trigger Store warnings for users whose hardware doesn't meet them. For a general desktop utility, over-specifying exclude users unnecessarily. **Leave everything Not specified.**

### 6. Display mode is VR/MR only

**Original guide didn't clarify.** The "PC / HoloLens / Seated+standing" fields are specifically for **Windows Mixed Reality apps**, not general desktop PCs. Leave unchecked for any non-VR app.

### 7. Product declarations may be pre-checked wrong

**Discovery:** Partner Center pre-checked three boxes by default that were wrong for QSOP:
- "Customers can install to alternate drives or removable storage" → unchecked (MSIX managed)
- "Windows can include data in OneDrive backups" → unchecked (personal data, keep local)
- "Customers can record and broadcast clips" → unchecked (games-only per Microsoft's own warning)

**Lesson:** go through product declarations deliberately; don't assume defaults are correct.

### 8. Generative AI vs Predictive ML distinction

**Important clarification:** QSOP uses:
- scikit-learn behavior classification (predictive)
- numpy-based IONIS neural net for propagation (predictive)

The "generative AI" product declaration is specifically for apps that CREATE content (text, images, audio, video, code). QSOP analyzes and predicts but doesn't generate content. **Leave unchecked.**

### 9. Notes for certification field is narrowly scoped

**Original guide assumption:** ~1800 char field for general reviewer testing notes.

**Actual behavior:** the field on the Submission Options page labeled "Why do you need the runFullTrust capability, and how will it be used in your product?" is specifically the **restricted capability justification**, ~500 char limit.

**Correction:** the longer reviewer notes belong on a **separate** page accessed via Partner Center sidebar → Supplemental info → **Additional Testing Information**. That page has a Description field with more generous length (successfully pasted ~1,750 chars).

### 10. Store logos section can be fully skipped

**Decision:** leave all 6 Store logo slots blank. Microsoft's own text: *"By default, the Store will use the logo images from your package when displaying your product's listing to customers."*

Our MSIX contains 28 embedded icons. These display correctly without additional uploads. Promotional poster art is optional polish; primarily benefits featured-app slots which a niche utility won't receive regardless.

### 11. Short description field didn't appear in our flow

**Observation:** Microsoft's docs describe a "Short description" field (1000 char limit, 270 recommended for display). In our MSIX submission flow, this field didn't appear. The main Description field was the only narrative field visible.

**Action taken:** proceeded without Short description. Not a submission blocker. If it appears in future submissions, the 268-char version exists in the submission guide.

---

## Pre-submission sanity checks (executed)

- ✓ Privacy URL loads: https://qsop.wu2c.net/privacy/
- ✓ Support URL loads: https://qsop.wu2c.net/support/
- ⚠️ Email alias qsop@wu2c.net test — noted as pending Peter's GoDaddy configuration verification
- ✓ Description spell-checked
- ✓ All 6 sections showed Complete before clicking Submit

---

## Current status and what to watch

**Status as of 04/22/2026 end of session:** In certification, Pre-processing stage.

**Microsoft's stated timeline:** *"The certification step usually takes a few hours, but in some cases can take up to 3 business days."*

**Email notifications will arrive at:** peter@wu2c.net

**Expected outcomes:**
- Pass → status becomes "Certification passed" → publishing begins → goes live (Microsoft says within ~15 minutes)
- Reject → rejection email describes specific issue → fix and resubmit

**If passed, the Store URL should be approximately:** `https://apps.microsoft.com/detail/9mwcw2ftb866` (verify exact format when live)

---

## Post-approval task list (prioritized)

1. Update README.md to add "Install from Microsoft Store" alongside GitHub Releases
2. Update docs/index.md landing page with Microsoft Store badge/link
3. Update docs/USER_GUIDE.md Section 2 (Installation) with both install paths
4. Update wiki Home page with Store install option
5. Consider announcements (QRZ, Reddit r/amateurradio, Groups.io WSJT-X)
6. Ship v2.5.5 updating About dialog privacy URL from github.com/.../PRIVACY.md → https://qsop.wu2c.net/privacy/ directly

---

## Files produced/modified this session

- `dev-docs/PARTNER_CENTER_SUBMISSION_GUIDE.md` — revised to v2 incorporating discoveries
- `dev-docs/SESSION_NOTES_2026-04-22_STORE_SUBMISSION.md` — this file
- (Optional) `dev-docs/MICROSOFT_STORE_IDENTITY.md` — append post-submission tracking info

No code changes. No MSIX rebuild. No website changes.

---

## Milestone significance

Starting this session: QSOP had an MSIX built, signed, and installed locally; Jekyll site live with custom domain and HTTPS; privacy policy published; name reserved.

Ending this session: submission in certification. Full end-to-end path from "has an app" to "app submitted to Microsoft Store" complete.

Full submission walkthrough took one focused session. No significant blockers. Multiple small surprises (form behaviors, field interpretations) captured above for future reference.

73 de WU2C
