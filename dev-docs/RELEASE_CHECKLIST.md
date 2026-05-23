# Release Checklist

Run through this before tagging a new version. Captures all the
release-time doc and metadata touches, including the easy-to-miss ones.

---

## Pre-flight

- [ ] All in-flight refactor/fix branches merged to `main`.
- [ ] App tested on **both** Mac and Windows with live WSJT-X / JTDX.
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
- [ ] **Wiki** (`https://github.com/wu2c-peter/QSO-Predictor/wiki`) —
      maintained outside the commit flow, so a manual edit. Only needed if
      this release changes user-facing features or install instructions
      that the Wiki covers. For pure bug-fix or refactor releases, skip.
      See `BACKLOG.md` § Documentation for the open Wiki items.

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

*Last reviewed: May 2026 (v2.5.6 release)*
