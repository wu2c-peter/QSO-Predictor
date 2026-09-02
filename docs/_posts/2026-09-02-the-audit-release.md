---
layout: post
title: "The Feature That Never Fired"
description: >-
  v2.8.1 is a bug-fix release with a story: a systematic audit of the code
  found forty defects that all failed the same way — quietly, while showing
  confident output — including the sweep-aware recommendation that had never
  once worked in a packaged build.
---

*v2.8.1 is out. It adds nothing you'll have to learn, which is the point.*

---

Last month's post was about the OH0ERF pileup and the moment the Insights
panel said "position at higher frequencies" while the band map's green line
sat at 1087 Hz. I fixed that in August: when the pattern tracker sees a
target sweeping its pileup from one end of the passband to the other, the
recommendation now tilts toward where they're heading. Nice feature. Shipped
in the code. Tested on my Mac.

It never ran for anyone who installed the app.

The correlation behind it imported scipy. The packaged builds deliberately
leave scipy out (it's 80 MB of numerics the app doesn't otherwise need), and
the code handled that case gracefully — by returning zero. No error, no log
line. Every packaged copy of QSO Predictor classified every pileup as
"Random" and moved on.

That's the shape of almost everything in this release. I ran a systematic
audit of the whole codebase — five passes, one per subsystem, every finding
re-verified against the source before anything was touched — and the list
that came back had a theme. Forty defects, and nearly all of them failed
*quietly*:

- A failed space-weather fetch became "SFI 0, K 0 (Poor)" in the header and
  went straight into the propagation model as physically impossible input.
- The PSK Reporter health check looked for the client on the wrong object,
  so a broker outage never reached the status bar. For two releases.
- Right-click → "Set as Target" raised an error nobody saw. The Insights
  panel's manual-entry box was wired to a method that didn't exist. The
  Appearance settings tab saved your choices and nothing read them.
- Changing bands put "Not Transmitting" on every row for a few minutes,
  while you were calling.
- FT4 was treated as FT8 end to end, cycle clock included.

None of these crashed. All of them produced output that looked fine. That is
a much worse failure mode than a crash, and the fix for it isn't only the
forty patches — it's the tests that now pin each one, and a new conventions
test that fails the build if a controller references something the main
window no longer has (the exact mechanism behind three of the dead
features).

So: the sweep-aware green line now works in the exe and the DMG. The
recommendation is no longer pinned to the bottom of the passband when the
target has no direct spots. The status bar tells you when PSK Reporter is
gone. And I got to write "forty" in release notes, which I hope not to do
again.

The [full release notes](https://github.com/wu2c-peter/QSO-Predictor/blob/main/dev-docs/RELEASE_NOTES_v2.8.1.md)
have the whole list. One compatibility note for the handful of people
running a self-hosted FT8web: the listener now checks the browser's origin,
so add your host to `allowed_origins` in the ini.

73 de WU2C
