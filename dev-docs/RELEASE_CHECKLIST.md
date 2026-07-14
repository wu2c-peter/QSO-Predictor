# Release Checklist

Run through this before tagging a new version. Captures all the
release-time doc and metadata touches, including the easy-to-miss ones.

---

## Pre-flight

- [ ] All in-flight refactor/fix branches merged to `main`.
- [ ] App tested on **both** Mac and Windows with live WSJT-X / JTDX.
- [ ] If the release touched the data-ingest path (`udp_handler.py`,
      `ft8web_handler.py`, `utils/wsjtx_protocol.py`, UDP forwarding), also
      test against a live FT8web browser client (ft8web.ok1cdj.com →
      Settings → External Data Stream → `ws://localhost:2442`; QSOP side:
      Settings → Network → "Listen for FT8web data stream") and confirm the
      WSJT-X UDP re-broadcast still reaches a downstream app.
- [ ] No uncommitted changes (`git status` clean).

## Code + metadata

- [ ] Update `VERSION` (e.g. `2.5.5.1` → `2.5.6`).
- [ ] Update `packaging/AppxManifest.xml` `Version="X.Y.Z.0"` to match — even
      when not submitting to the Store this cycle. Keeps the build
      self-consistent for whenever the next Store submission happens.

## Documentation (the easy-to-forget ones)

- [ ] Write **`dev-docs/RELEASE_NOTES_v<version>.md`** — full release notes,
      matching the format of recent files in the same folder.
- [ ] Update **`README.md`** § "What's New" — replace with new version's
      highlights; move the previous "What's New" content to
      "Previous Releases" as a one-paragraph entry with a link to its
      release notes file.
- [ ] Update **`docs/USER_GUIDE.md`** — the "**Current as of Version X.Y.Z**"
      line near the top. Easy to forget; it's the only version reference in
      the guide and bumping it keeps qsop.wu2c.net's user-guide page fresh.
- [ ] For feature releases, re-read **`docs/index.md`** (the "What it does"
      list and the "Works alongside WSJT-X or JTDX" line) and
      **`docs/llms.txt`** (the summary paragraph) — both describe the app's
      capabilities and integrations, and a new user-facing capability makes
      them silently stale. Skip for pure bug-fix or refactor releases.
- [ ] **Wiki** is a separate git repo at
      `/Users/peterhirst/projects/QSO-Predictor.wiki` (remote:
      `git@github.com:wu2c-peter/QSO-Predictor.wiki.git`, `master` branch).
      Edit locally, commit, `git push origin master`. GitHub publishes
      directly — no build step. For each release, at minimum bump the
      "Content current as of v..." marker at the top of every page that
      carries one — currently `Quick-Usage-Guide.md`,
      `QSO-Predictor-How-and-Why-It-Works.md`, and
      `Doesnt-PSK-Reporter-Already-Do-This.md` (run
      `grep -l "current as of" *.md` in the wiki repo to catch pages added
      since this list was written). Skip content edits for pure bug-fix or
      refactor releases.

## Release

- [ ] Commit all of the above as a single `release: v<version> — <theme>`
      commit. Push to `main`.
- [ ] `git tag -a v<version> -m "..."` and `git push origin v<version>`.
- [ ] The `build-release.yml` workflow fires automatically on the tag push.
      Watch it with `gh run watch <run-id>` or via the Actions tab.
- [ ] Once workflow finishes: verify the GitHub Release page has both
      artifacts attached (Windows `.zip` + macOS `.dmg`).
- [ ] (Optional, until the workflow improvement in `BACKLOG.md` lands)
      Edit the GitHub Release body to include the user-facing highlights
      from `RELEASE_NOTES_v<version>.md`. The workflow currently writes a
      generic boilerplate body.

## Microsoft Store (only when warranted)

The Store submission overhead (Partner Center, certification, hours-to-days
turnaround) is **not justified for pure bug-fix or refactor releases**. Store
users get updates batched into substantive feature releases.

For releases that *do* warrant a Store push:

- [ ] Build the MSIX locally with `qso_predictor_msix.spec`.
- [ ] Submit via Partner Center. See `dev-docs/PARTNER_CENTER_SUBMISSION_GUIDE.md`.
- [ ] Wait for certification.

---

*Last reviewed: July 2026 (v2.5.8 release prep)*
