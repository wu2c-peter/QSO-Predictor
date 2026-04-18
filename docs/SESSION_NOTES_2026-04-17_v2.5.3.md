# QSO Predictor Session Notes

**Date:** April 17, 2026  
**Version:** 2.5.3  
**Session:** Orphaned file discovery & cleanup

---

## The Find

Peter shared a screenshot of `%USERPROFILE%\.qso-predictor\` showing:

```
behavior_history.json          2,426 KB
file_positions.json                2 KB
outcome_history.jsonl             30 KB
pending_observations.jsonl  293,909,778 KB  ← 280 GB
```

That's roughly ten million times larger than any other file in the folder.
Peter flagged it with characteristic understatement: *"pending file getting
rather large."*

---

## Diagnostic Path

### First hypothesis (wrong)

Initial read of the code: `pending_observations.jsonl` looked like
it held "future training" data for an ML pipeline — wired to the `Start
Training` button that's been disabled in the .exe since v2.0.2.

### Peter's pushback

> *"I assumed the pending file was holding data about attempted QSOs until
> there was an outcome to be recorded?"*

A reasonable mental model given the filename, and exactly the kind of
architectural question that disambiguates two systems with overlapping
names. This forced a proper trace of both systems.

### What the code actually does

Three distinct paths exist in the codebase:

1. **Bayesian heuristic (active, shipping)** — `behavior_predictor.py`
   updates posteriors from observations. Reads/writes `behavior_history.json`.
   This is what powers the Insights panel today.

2. **ML trainer (exists, dormant)** — `training/trainer_process.py` is a
   real classifier trainer that runs as a subprocess. Its feature builders
   read `ALL.TXT` directly via `HistoricalSessionReconstructor`. The
   `Start Training` button was disabled in v2.0.2 because the .exe doesn't
   carry a Python interpreter for subprocess spawning.

3. **`pending_observations.jsonl` (orphan)** — staged as live-session feed
   data for *some future* online-learning path that was never built.
   Neither (1) nor (2) reads this file. Zero consumers anywhere in the repo.

Peter's recollection — "we thought about ML, implemented a Bayesian
heuristic instead" — was accurate in spirit. The extra wrinkle: "ML
considered" produced scaffolding (path 2) that still sits dormant in the
repo, and the orphan file was staged for a speculative third path that
never materialized.

---

## The Bug

`_save_pending_observations()` wrote to disk in append mode but never
cleared the in-memory buffer afterward. The trigger was
`if len(buffer) >= 100`, so once the buffer crossed that threshold,
**every subsequent observation** fired another save, each one re-dumping
the entire (growing) list.

Growth pattern within a process lifetime after threshold:

* Observation 100: writes 100 records
* Observation 101: writes 101 records
* Observation 102: writes 102 records
* ...
* Observation N: writes N records

Total records written ≈ N²/2. At ~380 bytes per record and ~400,000
observations cumulative (plausible across months of operation), that
compounds to the 280 GB Peter observed.

The in-memory buffer was only cleared at the end of `bootstrap_history()`
or on process restart — neither of which fires during normal operating.

---

## The Fix

Not a one-line patch. Since the file has no consumer at all — not the
active Bayesian path, not the dormant ML trainer, not any planned feature
in the backlog — the correct fix is to remove the capture entirely.

Five symbols removed from `behavior_predictor.py`:

* `self._pending_observations` (list attr)
* `_record_observation()` (private)
* `_save_pending_observations()` (private)
* `get_pending_training_data()` (public, zero callers)
* `clear_pending_data()` (public, zero callers)

One symbol added:

* `_cleanup_orphaned_pending_file()` — one-time migration called from
  `__init__`. Idempotent, logs size-freed at WARNING level for ≥100 MB
  cleanups, handles PermissionError gracefully (antivirus lock case),
  never blocks app startup.

---

## Key Architectural Principle (earned)

**When a filename implies a role, verify the role — don't infer it.**

The file was named `pending_observations.jsonl`. "Pending" strongly
suggests "pending outcome resolution" — especially adjacent to an
`outcome_history.jsonl` in the same directory. But the code reality was
"pending write to a training pipeline that doesn't exist." Two very
different things behind identical-feeling names.

Peter's instinct to challenge the initial attribution ("I assumed the
pending file was...") is exactly the pattern that caught the
QDateTime-bytes issue in v2.0.3 and several data-source labeling issues
in v2.4.x. Human review catches shape-level mismatches that pure code
reading misses.

---

## Should OutcomeRecorder Have Crash-Resilient On-Disk Pending State?

Raised but deferred. Current OutcomeRecorder holds pending state entirely
in memory — a mid-QSO crash (Windows update, app crash, power loss)
loses that target's outcome record. Not catastrophic (outcome data is a
best-effort performance signal, not a QSO log), but worth considering
separately if crashes ever prove non-rare in practice.

**Not this patch. Open as backlog.**

---

## Files Modified

| File | Change |
|------|--------|
| `VERSION` | `2.5.2` → `2.5.3` |
| `local_intel/behavior_predictor.py` | Orphan code removed (~60 lines), cleanup method added (~40 lines) |
| `docs/README.md` | v2.5.3 "What's New"; v2.5.0–v2.5.2 in Previous Releases |
| `docs/RELEASE_NOTES_v2.5.3.md` | New |
| `docs/SESSION_NOTES_2026-04-17_v2.5.3.md` | This file (new) |

---

## Lessons for the AI-Assisted Development Write-Up

1. **Filename-driven inference is a trap.** AI will grep a keyword, find
   the first match, and build a mental model from it. If the user's mental
   model differs, the user's question is usually the signal — not the
   AI's initial read.

2. **"No consumer anywhere" deserves a full grep, not a guess.**
   Verifying `pending_observations.jsonl` had zero readers took about
   three grep calls and was load-bearing for the decision to remove
   rather than patch. Worth the minute.

3. **Scope honesty.** Early in the session I offered to "package the
   patch" twice before Peter had actually made the architectural
   decision. The right move was the third exchange — where he asked
   whether the feature was needed at all. Waiting for that question
   produced a much better outcome than jumping to a one-line fix.

4. **280 GB silently accumulating on disk is a real-user harm, not just
   a code-quality issue.** Worth prominent release-note treatment, not
   just "bug fix."

---

## Backlog Added This Session

* Evaluate OutcomeRecorder crash-resilience (optional on-disk pending
  state). Priority: low. Insertion point documented in `outcome_recorder.py`
  around `_pending_session`.

---

## Wellness Note

Dense session — rapid-fire diagnostic with a genuinely startling find and
multiple architectural pivots. Peter kept asking sharper questions rather
than accepting quick fixes, which is the right mode but also mentally
taxing. Decision to ship v2.5.3 today was his; the file isn't growing
anymore with QSOP closed, so tomorrow would have been equally valid.

**73 de WU2C**
