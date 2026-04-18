# Release Notes — v2.5.3

**Date:** April 17, 2026  
**Theme:** Disk Space Reclamation & Dead Code Removal

---

## Summary

This release removes an orphaned data-capture pipeline that was writing to a
file (`pending_observations.jsonl`) with no consumer anywhere in the codebase.
A bug in that write loop caused the file to grow unboundedly on long-running
installations — some users saw files in the hundreds of gigabytes. v2.5.3
deletes the orphan file automatically on first launch and removes the code
that created it.

No active feature is affected. The Bayesian behavior predictor, Local
Intelligence, path analysis, scoring, OutcomeRecorder, and all user-facing
functionality are unchanged.

---

## What Changed

### Automatic Cleanup on First Launch

When you first launch v2.5.3, QSOP will:

1. Look for `~/.qso-predictor/pending_observations.jsonl`
2. If present, delete it and log the amount of space freed
3. Do nothing further — the cleanup is one-time and idempotent

**Log output examples:**

Large file (≥100 MB):

```
WARNING  Removed orphaned pending_observations.jsonl (287,342.1 MB freed).
         This file was an unused artifact from a planned training pipeline
         and grew due to a bug fixed in v2.5.3. No user data is lost.
```

Small residual or fresh install:

```
INFO     Removed orphaned pending_observations.jsonl (1.23 MB).
         Legacy artifact, no user data lost.
```

If the file is locked by antivirus or Windows Search Indexer, QSOP logs a
warning and retries automatically on the next startup. It never blocks app
launch.

### Dead Code Removed

Five symbols removed from `local_intel/behavior_predictor.py`:

| Symbol | Role |
|--------|------|
| `self._pending_observations` (list) | In-memory buffer for the orphaned file |
| `_record_observation()` | Private method that appended to the buffer |
| `_save_pending_observations()` | Private method that flushed the buffer to disk |
| `get_pending_training_data()` | Public API (zero external callers) |
| `clear_pending_data()` | Public API (zero external callers) |

One method added:

| Symbol | Role |
|--------|------|
| `_cleanup_orphaned_pending_file()` | One-time migration called from `__init__` |

### The Bug That Caused the Growth

For the record, since future-us will ask:

`_save_pending_observations()` appended the in-memory buffer to disk every
time it reached 100 items — but never cleared the in-memory buffer after
writing. Because the save trigger was `if len(buffer) >= 100`, once the
buffer crossed that threshold, **every subsequent observation** fired
another save. Each save wrote the full accumulated list in append mode.

Records written to disk grew as ~N²/2 where N is the total number of
observations in the process lifetime. The in-memory buffer was only cleared
at the end of `bootstrap_history()` or if the process restarted.

---

## What Didn't Change

* **Bayesian behavior prediction** — the live Bayesian update loop
  (`update_with_observation`, `get_prior`, session beliefs) is untouched.
  Prediction quality is identical.
* **Historical behavior records** — `behavior_history.json` is written and
  read exactly as before. Your accumulated behavior data is preserved.
* **OutcomeRecorder** — `outcome_history.jsonl` (introduced in v2.5.1)
  is unrelated to the removed file and is unaffected. It continues to
  record QSO attempt outcomes for planned Phase 2 self-evaluation.
* **ML trainer scaffolding** — the dormant `training/` directory is
  untouched. Its feature builders work off `ALL.TXT` directly, not the
  removed file. Separate decision whether to ever wire that path up.

---

## Upgrading

Standard upgrade path. No user action required — the cleanup runs
automatically.

**Before upgrading, optional:** if you want to see the old file's size
before QSOP deletes it, check:

* **Windows:** `%USERPROFILE%\.qso-predictor\pending_observations.jsonl`
* **macOS/Linux:** `~/.qso-predictor/pending_observations.jsonl`

Don't delete it manually unless QSOP is closed — that's just good Windows
hygiene for large files. QSOP will handle the deletion cleanly on first
launch of v2.5.3.

---

## Files Modified

| File | Change |
|------|--------|
| `VERSION` | `2.5.2` → `2.5.3` |
| `local_intel/behavior_predictor.py` | Dead code removed, cleanup method added |
| `docs/README.md` | v2.5.3 "What's New" section; v2.5.0–v2.5.2 moved to Previous Releases |
| `docs/RELEASE_NOTES_v2.5.3.md` | This file (new) |
| `docs/SESSION_NOTES_2026-04-17_v2.5.3.md` | Diagnostic record (new) |

---

## Credits

Peter Hirst (WU2C) spotted the 280 GB file in his own `.qso-predictor`
directory during a routine check — a great example of how hands-on
observation beats code review for bugs of this particular shape. The file
had been silently growing since v2.0 (December 2025); no automated test or
code-read would have surfaced it because the growth was slow relative to
session length and only visible as a filesystem artifact.

---

**73 de WU2C**
