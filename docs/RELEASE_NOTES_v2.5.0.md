# Release Notes — v2.5.0

**Date:** April 2026  
**Theme:** Regional Consensus Scoring & Score Transparency

---

## Smarter Frequency Recommendations

The scoring engine that drives the green recommendation line has been 
substantially reworked. The core improvement: QSO Predictor now uses the 
**number of independent PSK Reporter stations** near the target to gauge 
confidence in its frequency assessments.

### Why This Matters

In FT8, every receiver decodes the full passband simultaneously. If a 
PSK Reporter uploader near the target is active — uploading spots from any 
frequency — then their silence at a particular frequency is meaningful. 
They had the opportunity to decode signals there and found nothing.

One reporter's silence is a sample. Five reporters' silence is a consensus.

Previously, the algorithm treated all "empty" frequencies the same — whether 
zero reporters or twenty were covering the target's area. Now, confidence 
scales continuously with reporter count.

### What Changed

**Regional consensus scoring (Steps 4b + 5b):**
Quiet frequencies near the target score higher when confirmed by multiple 
regional reporters. The confidence curve is continuous — no hard threshold. 
Scores range from 50 (no reporters, unknown) through 66 (3 reporters) up 
to 82 (6+ reporters, strong consensus). The recommendation engine's 
existing ≥65 threshold naturally requires about 3 reporters before acting 
on regional data.

**Suspicious gap detection (Step 5c):**
If the target station is actively decoding signals on both sides of a 
frequency gap but nothing in the gap itself, that empty slot is more likely 
to contain local QRM at the target than to be clear air. These gaps are now 
dampened by up to 30% based on the density of flanking activity.

**Regional consensus recommendation (Step 7b):**
When no proven (Tier 1) data exists but regional reporters provide 
meaningful coverage, the recommendation now uses the enhanced score map 
rather than falling back to blind gap-finding. This produces better 
recommendations for targets that don't upload to PSK Reporter but are 
located near stations that do.

---

## Score Reason Tooltips

**Hover over the score graph** to see why any frequency has its current 
score. The tooltip shows the score value, frequency, and a plain-English 
explanation of the scoring reason.

Examples:
- `95  @1440 Hz — Proven: 2 signal(s) decoded by target`
- `76  @1800 Hz — Regional quiet: 5 reporter(s) in area, clear`
- `72  @1200 Hz — Regional light: 2 signal(s), 4 reporters`
- `44  @1500 Hz — Suspicious gap: flanked by 5 target decodes`
- `55  @900 Hz — Regional quiet: 1 reporter(s) in area, clear`
- `10  @1700 Hz — Local QRM (your receiver)`

This makes the recommendation algorithm transparent — you can see exactly 
what data the system has and why it's scoring each slot the way it is.

---

## Score Hierarchy

| Rank | Condition | Score |
|------|-----------|-------|
| 1 | Proven: 1-3 signals decoded by target | 90-100 |
| 2 | Regional quiet: 6+ reporters, clear | 82 |
| 3 | Regional light: few signals, multiple reporters | 72 |
| 4 | Regional quiet: 4 reporters | 71 |
| 5 | Proven but crowded: 4+ signals at target | 30-70 |
| 6 | Regional quiet: 3 reporters | 66 |
| 7 | Regional quiet: 2 reporters | 61 |
| 8 | Light congestion | 55 |
| 9 | Regional quiet: 1 reporter | 55 |
| 10 | No data (baseline) | 50 |
| 11 | Moderate congestion | 45 |
| 12 | Suspicious gap (dampened) | varies |
| 13 | Heavy congestion | 25-35 |
| 14 | Local QRM | 10 |
| 15 | Band edge / Hound zone | 0 |

---

## Technical Notes

- Confidence function: `min(1.0, regional_reporters / 6.0)`
- Quiet slot score: `50 + confidence × 32`
- Suspicious gap dampening: 6% at adjacency=4, up to 30% at adjacency=8+
- Score reason data stored in parallel int8 array (minimal memory overhead)
- No new dependencies or configuration required
- All existing proven-frequency (Tier 1) scoring unchanged

---

**73 de WU2C**
