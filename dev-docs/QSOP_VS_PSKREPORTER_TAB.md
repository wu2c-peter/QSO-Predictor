# "Doesn't PSK Reporter already do this?"

*Draft for wiki / README / article sidebar — WU2C, July 2026*

It's the most common question about QSO Predictor, and it deserves a straight answer: the pskreporter.info map genuinely can show you signals *received by* a specific callsign — pick "rcvd by" and enter the call. The raw data QSOP uses is the same public data everyone can see. So what are you actually getting?

## The honest comparison

**Cadence.** The PSK Reporter website is built around polling, with guidance to query no more often than about every five minutes, and reports themselves can take minutes to appear. QSOP subscribes to PSK Reporter's live MQTT stream instead, so spots arrive within seconds — inside the 15-second FT8 cycle you're actually operating in. Five-minute-old pileup data describes a pileup that has already been worked.

**Scale.** A browser tab answers one question about one station, manually. QSOP computes path status for *every station in your decode table, continuously* — the difference between looking up a target you've already picked and having the data help you pick. Our outcome data shows why that matters: targets that had already decoded us converted at 76%, versus a ~30% overall baseline. That signal existed in public data all along; nobody can extract it by hand for thirty stations every fifteen seconds.

**Resolution.** The map shows *that* a station heard someone. QSOP reconstructs *where in the passband* the target is decoding — which 60 Hz of the waterfall is proven, which is saturated, which is a suspicious gap — and scores it. Field data: calling on a frequency where the target was provably decoding converted at 48%, versus 27–33% elsewhere.

**Fusion.** The map knows nothing about your radio. QSOP fuses PSK Reporter's view with your live UDP decode stream, your log history (behavioral profiles), and IONIS propagation forecasts — target-side reality cross-referenced with local reality in one display.

**Judgment.** A map presents data; you do the tiering, weighting, and recency math by eye. QSOP applies geographic tiering, density scoring, and recommendation logic every cycle, then tells you what it thinks — and shows its reasoning on hover.

**Honesty.** This one no browser tab will ever match: QSOP instruments itself. Every calling attempt is logged with the tactical picture at decision time and the outcome, so claims like the 76% and 48% figures above aren't marketing — they're measured from 547 real calling attempts at WU2C, and the same instrumentation will tell us when a feature *isn't* working (it already has, twice).

## The one-sentence version

QSO Predictor doesn't have secret data — it makes the same public data *decision-ready at operating tempo*, for every station you can hear, and then measures whether its advice actually worked.

---
*Numbers from `OUTCOME_ANALYSIS_2026-07.md` (n=547, single station, Apr–Jul 2026): observational correlations from one operator's logs, offered as evidence, not universal constants. Sources for PSK Reporter website capabilities and query-cadence guidance: pskreporter.info map and developer documentation, checked 2026-07-01.*
