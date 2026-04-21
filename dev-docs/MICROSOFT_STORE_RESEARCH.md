# Microsoft Store Distribution — QSO Predictor Research Notes

**Date:** April 20, 2026
**Purpose:** Comprehensive research on distributing QSOP via Microsoft Store as the SAC/SmartScreen solution

---

## TL;DR — The updated picture

**Microsoft Store is now the obvious answer for QSOP's signing problem:**

- **Free individual developer account** (Microsoft dropped the $19 fee in mid-2025)
- **Microsoft signs your MSIX package for you** — no code-signing cert needed
- **Bypasses SAC entirely** — Microsoft-signed packages are trusted at the OS level
- **Bypasses SmartScreen entirely** — Store apps inherit Microsoft's reputation
- **No annual renewal** — one-time setup
- **Works with your existing PyInstaller build** — wrap it in MSIX, done
- **GPL-compatible** — Store policies explicitly allow open-source apps

The only real cost is time to set up MSIX packaging. Roughly 4-8 hours of one-time work based on community reports.

This makes SignPath Foundation and EV sole proprietor paths unnecessary unless Store turns out to be blocked for a surprising reason.

---

## Part 1: Microsoft Store Developer Account

### Cost

- **Individual account: FREE as of mid-2025**
- Company account: $99 USD one-time (not relevant for you)
- No annual renewal for either type

This is a change Microsoft made in May 2025 and rolled out broadly in late 2025 / early 2026. Some older docs still reference the old $19 fee — outdated. The fee is waived for individual developers in "nearly 200 markets worldwide" including the US.

If you sign up and hit a fee page, you may have landed on the legacy flow. Start from the "Get started for free" entry point at the Microsoft Store marketing page.

### What you need to sign up

- Microsoft account (MSA) — you almost certainly have one
- Government-issued ID (for identity verification via selfie — same workflow as the EV sole proprietor cert used)
- No credit card required for individual accounts under the new free flow
- No business entity, no DBA, no D&B listing

### Sign-up URL

Starting point: `developer.microsoft.com/en-us/microsoft-store/register`

Partner Center (where you actually manage submissions once signed up): `partner.microsoft.com`

### Account type choice: pick Individual

Individual accounts are "intended for solo developers, hobbyists, or small-scale creators." QSOP fits perfectly.

Company account would require more verification, a business name, and the $99 fee — pointless for your situation.

---

## Part 2: Microsoft Store Policies — the GPL/OSS angle

### Can QSOP be in the Store?

**Yes.** Microsoft removed restrictions on open-source apps in July 2022 after backlash from the OSS community. As long as:

- You're the original developer (or have appropriate license from the original developer)
- The app isn't misrepresented as a different project
- Normal policy compliance (no malware, no deceptive behavior, no IP violations, etc.)

QSOP passes all of these trivially:
- You're the author
- GPLv3 license, explicitly allowed
- No payment processing, no PII collection, no deceptive behavior
- Uses only public data sources (PSK Reporter, NOAA)

### Policy documents to review before submission

Current version of Store Policies is 8.10 (published September 2025). Worth reading once. Key areas relevant to QSOP:

- Section 10 (intellectual property): you're clear — you own your code, all dependencies are properly licensed
- Section 11 (privacy): you're clear — you collect no PII
- Section 4 (security): you're clear — no malware behavior, no exploitation
- Section 12 (financial terms): not applicable — you're free, no payments

### Privacy policy requirement

The Store requires a privacy policy URL for any app that accesses user data. QSOP accesses:
- Local WSJT-X/JTDX log files (user's own data, stays local)
- PSK Reporter MQTT stream (public data, no upload from QSOP)
- NOAA solar API (public data)

**A minimal privacy policy is still recommended even though QSOP doesn't transmit user data anywhere.** Say explicitly: "QSOP does not transmit, collect, or store any personal information. All data read from log files remains on your local device." A simple markdown file on your GitHub Pages or in the wiki would work.

---

## Part 3: MSIX Packaging from PyInstaller

### The packaging path

Your current build pipeline produces a PyInstaller `.exe`. For the Microsoft Store, you wrap that (or use a different PyInstaller mode) inside an MSIX package.

**Recommended approach based on community best practices:**

1. Use `pyinstaller --onedir` (NOT `--onefile`)
2. Package the resulting folder as MSIX
3. Submit the MSIX to the Store

**Why `--onedir` not `--onefile`:**
The one-file PyInstaller executable extracts all files to Windows Temp on every launch. This:
- Slows startup significantly
- Is unnecessary inside MSIX (users already get a single-file install)
- Frequently triggers antivirus false positives (because malware often uses `--onefile`)
- Makes the MSIX much larger than needed

The `--onedir` mode produces a folder with your `.exe` and all its dependencies. Wrapping that folder in MSIX gives you fast startup and clean structure.

### Tools for creating the MSIX

Three main paths, from easiest to most flexible:

**Option A: MSIX Packaging Tool (Microsoft, free)**
- Available from the Microsoft Store (meta moment)
- GUI-driven wizard
- Can convert existing `.msi` or `.exe` installers
- Probably the simplest path for QSOP
- Download: search "MSIX Packaging Tool" in the Microsoft Store

**Option B: Advanced Installer (third-party)**
- Professional installer tool with MSIX support
- Free tier covers what QSOP needs
- GUI-driven with more options than MSIX Packaging Tool
- Handles Python/PyInstaller scenarios well
- URL: `advancedinstaller.com`

**Option C: MakeAppx.exe + manual manifest (command-line, free)**
- Comes with the Windows SDK (Windows App Certification Kit component)
- Full programmatic control
- Best for GitHub Actions CI/CD integration (automated builds)
- More initial setup but reproducible
- Example workflow exists for Python/PyInstaller on dev.to

**My recommendation for you:**
Start with **Option A (MSIX Packaging Tool)** for your first submission to understand the structure. Once you have a working MSIX, migrate to **Option C (MakeAppx in GitHub Actions)** to match your existing build automation. Your current GitHub Actions workflow builds Windows .exe — add an MSIX packaging step after the PyInstaller step.

### Required MSIX manifest elements

An MSIX package includes an `AppxManifest.xml` file declaring:

- **Identity**: package name, publisher (gets filled in by Partner Center after you associate with Store), version
- **Properties**: display name ("QSO Predictor"), publisher display name ("WU2C"), description
- **Applications**: the .exe entry point, visual assets (icons, tile images)
- **Capabilities**: what the app needs to do (file system access, network, etc.)

For QSOP you need these capabilities:
- `runFullTrust` — required for PyInstaller/Python apps (they need desktop-app privileges)
- `internetClient` — for MQTT and NOAA connections
- File system access (for reading ALL.TXT logs) — likely `broadFileSystemAccess` or use user-selected pickers

### Required visual assets

Microsoft Store requires multiple icon sizes:
- Store Logo: 50x50
- Square 44x44 logo (various scales: 100%, 125%, 150%, 200%, 400%)
- Square 150x150 logo (various scales)
- Square 310x310 large tile (optional)
- Wide 310x150 tile (optional)
- Splash screen: 620x300

You can auto-generate all sizes from a single high-res source using the Windows App Manifest Generator or Visual Studio's Manifest Designer. Your existing QSOP icon (if you have one) would work as the base.

### Identity constraints

You'll need to reserve the name **"QSO Predictor"** in Partner Center. 3-month hold, free. Since USPTO trademark search came up clean earlier today, this should pass without issues.

Package Identity Name convention: typically `<PublisherName>.<AppName>` — e.g., `WU2C.QSOPredictor` or similar. Partner Center generates this for you.

---

## Part 4: Submission Process

### Step-by-step

1. **Reserve the app name** in Partner Center (5 minutes)
2. **Create a new MSIX submission** from the Apps & Games dashboard
3. **Pricing and Availability**: Set to Free, all markets (for QSOP)
4. **Properties**: Category (Utilities & Tools probably fits), age rating (3+, trivial questionnaire)
5. **Age Ratings**: Complete the IARC rating questionnaire. For QSOP, you'll answer "no" to basically everything — no violence, no user-generated content, no gambling, etc.
6. **Packages**: Upload your `.msix` or `.msixbundle`
7. **Store Listings**: Description, screenshots (you have these), search terms, privacy policy URL
8. **Submission options** (optional): Notes for testers, e.g., "Free open-source amateur radio tool. No account required. Requires WSJT-X or JTDX decoder running locally to display decoded FT8/FT4 traffic. Source code at github.com/wu2c-peter/qso-predictor"
9. **Submit for certification**

### Certification timeline

- **Typical**: a few hours to 1 business day
- **Documented worst case**: 3 business days
- **Practical reality**: most indie apps pass in 24-48 hours on first submission

If your app is novel (which QSOP is — niche ham radio domain), certification reviewers may take slightly longer the first time because they need to understand what it does. Good "Notes for certification" help substantially.

### What gets tested

1. **Security scan**: automated malware/virus detection on your MSIX
2. **Technical compliance**: Windows App Certification Kit (WACK) validates the MSIX manifest, capabilities, API usage
3. **Content review**: humans review your store listing, screenshots, description for policy compliance

### Pre-flight testing with WACK

Critical: **run the Windows App Certification Kit locally BEFORE submission.** It's free, comes with the Windows SDK, and catches most problems before Microsoft does.

Usage:
```
cd C:\Program Files (x86)\Windows Kits\10\App Certification Kit
WACK.exe
```

Or from Start menu: search "Cert Kit". Point it at your MSIX, run all tests, fix anything it flags.

### Common certification failures to avoid

- **Missing or wrong privacy policy URL** — provide one even though QSOP collects no PII
- **Non-working screenshots** — test your store listing before submitting
- **Incomplete app functionality** — app must be shippable, not a beta placeholder (you're fine at v2.5.3)
- **Missing "Notes for certification"** — always explain anything non-obvious. For QSOP: explain that the app requires WSJT-X/JTDX running locally, and may show an empty/loading state without a decoder
- **Crashes without internet** — since QSOP has offline (Local Intelligence) mode, test this path specifically before submission
- **Undeclared capabilities** — declare everything your app actually uses

---

## Part 5: What Changes About Your Development Workflow

### Before (current):

```
Git tag v2.X.Y → Push → GitHub Actions → Windows .exe in release zip → Users download
```

### After (with Store):

```
Git tag v2.X.Y → Push → GitHub Actions → Windows .exe + .msix → 
  ├── GitHub Release (direct download, existing users)
  └── Partner Center submission (Store users)
```

The GitHub Release path continues to work exactly as today — users who prefer direct download still get that option. The Store becomes an additional channel, not a replacement.

### Release cadence impact

Store submissions add a certification step (few hours to ~1 day typically). For QSOP's current cadence (sometimes multiple releases per week during active development), this means:

- **Minor releases (bug fixes)**: might skip the Store for rapid iteration, update Store monthly/quarterly with stable rollups
- **Major releases (v2.5.X → v2.6.0)**: submit to Store
- **Hotfixes**: GitHub direct first for existing users, Store update when convenient

You control the Store submission cadence — Microsoft doesn't force you to submit every release.

### Update delivery

Store users get automatic updates when you publish a new Store version. They don't have to visit GitHub, they don't have to re-download. This is a significant UX improvement over your current model.

---

## Part 6: The Tradeoffs

### What you gain

- ✓ SAC bypass (the original problem, solved)
- ✓ SmartScreen bypass
- ✓ No code-signing cert needed, ever
- ✓ Automatic updates for Store users
- ✓ Discoverability — people searching "FT8" in the Store find you
- ✓ Clean uninstall (MSIX guarantees this)
- ✓ Legitimacy signal — Store presence makes QSOP look more professional
- ✓ No legal entity required (sole prop/LLC conversation becomes moot)
- ✓ Zero ongoing cost (free account, no cert renewal)

### What you give up

- **Direct control over initial install experience**: Users tap Install in Store, Microsoft handles the rest. Fine for most users, loss of control for you.
- **Release velocity**: Certification delay between tag and Store availability. Typically <1 day but can hit 3 days.
- **Identity exposure**: Developer account is tied to real identity. Same concern as EV but without the notarized-ID-forms overhead.
- **Some dependency on Microsoft's infrastructure**: If Store has an outage, your Store distribution is affected. GitHub direct download is your backup.

### What stays the same

- GPL-3.0 license
- GitHub as the canonical source
- Direct download via GitHub Releases
- macOS and Linux distribution (unchanged, Store is Windows-only)
- Your beta testers' workflow (Brian, Bob, etc.)

---

## Part 7: Practical Roadmap

### Phase 1: Research and setup (1-2 hours)

- [ ] Sign up for free Microsoft Store developer account at `developer.microsoft.com/en-us/microsoft-store/register`
- [ ] Verify account activated (identity verification step)
- [ ] Reserve name "QSO Predictor" in Partner Center
- [ ] Write a minimal privacy policy, publish it somewhere stable (GitHub Pages, wiki, or simple gist)

### Phase 2: First MSIX build (3-4 hours)

- [ ] Install MSIX Packaging Tool from Microsoft Store (ironic, but easiest)
- [ ] Install Windows App Certification Kit (part of Windows SDK)
- [ ] Generate required icon sizes from QSOP's existing icon
- [ ] Create initial MSIX manually using MSIX Packaging Tool wizard pointing at your PyInstaller `--onedir` output
- [ ] Test install/uninstall on your Mac's Windows 11 VM or real Windows box
- [ ] Run WACK against the MSIX, fix anything it flags

### Phase 3: Submission (1-2 hours)

- [ ] Create submission in Partner Center
- [ ] Upload MSIX
- [ ] Fill out store listing: description, screenshots (you already have them), search terms ("FT8", "ham radio", "amateur radio", "WSJT-X", "JTDX", "propagation", "tactical assistant")
- [ ] Fill out "Notes for certification" explaining the decoder dependency
- [ ] Submit for review
- [ ] Wait for certification result

### Phase 4: Automation (2-4 hours, optional but recommended)

- [ ] Add MSIX packaging step to `.github/workflows/build-release.yml`
- [ ] Use `MakeAppx.exe` to generate MSIX automatically on tag push
- [ ] Publish MSIX as release artifact alongside the existing .zip
- [ ] Explore Microsoft's Store API for automated submissions (optional, advanced)

### Phase 5: Ongoing (per release)

- [ ] Publish to GitHub Releases as before
- [ ] Upload new MSIX to Partner Center
- [ ] Submit for certification
- [ ] Celebrate when Store version goes live

---

## Part 8: Questions I Can't Answer Until You Try

A few things that are situation-specific and will only become clear when you actually start:

1. **Will WACK catch anything unexpected in QSOP?** PyInstaller builds are generally fine, but specific dependencies can trigger warnings. Need to run and see.

2. **How will Microsoft's content reviewers handle QSOP?** It's novel enough that they may ask clarifying questions. Good certification notes reduce this risk but don't eliminate it.

3. **Will the IONIS model weights raise flags?** The 805 KB `.safetensors` file is just data, but automated malware scanners sometimes get confused by binary blobs. Almost certainly fine, but worth noting.

4. **Does your PyInstaller build work correctly inside MSIX?** The `--onedir` output typically does, but edge cases exist (especially around file-system access patterns).

None of these are showstoppers. They're the kind of things you find out during a real submission and iterate on.

---

## Part 9: The Honest Bottom Line

**This is the right path for QSOP.** Given:

- Free account (no cost barrier)
- Microsoft signs for you (no cert needed)
- One-time setup, no renewal (no ongoing burden)
- GPL-compatible, policy-friendly (no legal concerns)
- Works with your existing PyInstaller pipeline (modest change to build)

...the only reason not to do this is workload cost. And that cost is modest — probably one weekend of focused work to ship v1 of the Store version, plus ongoing 10-15 minutes per release.

The SignPath application becomes redundant if this works. The EV sole proprietor analysis becomes moot. Your legal entity analysis becomes moot. The "can my beta testers see the download page on Windows" concern disappears.

**What I'd do if I were you:**

1. Sleep. For real this time.
2. Tomorrow or later this week: sign up for the free developer account. Ten minutes of work.
3. Next weekend: Phase 2, create a first MSIX, test locally.
4. Following week: submit to Store.
5. Once it's in the Store, re-evaluate whether SignPath / EV are still worth pursuing. (They probably aren't.)

This is a clean path that didn't exist a year ago (before the free fee change). Worth taking.

---

## Appendix: Useful URLs

- Microsoft Store developer registration: `developer.microsoft.com/en-us/microsoft-store/register`
- Partner Center: `partner.microsoft.com`
- Microsoft Store Policies (v8.10): search "Microsoft Store Policies" on learn.microsoft.com
- Python + MSIX tutorial (PyInstaller-based): `82phil.github.io/python/2025/04/24/msix_pyinstaller.html`
- GitHub Actions Python → MSIX example: `dev.to/freerave/how-i-automating-python-to-msix-publishing-for-the-microsoft-store-using-github-actions-3dd6`
- Windows App Certification Kit docs: search "WACK" on learn.microsoft.com
- MSIX Packaging Tool (from Store): search "MSIX Packaging Tool"

---

**73 de Claude**
