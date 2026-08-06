---
layout: post
title: "The Pileup I Couldn't Hear"
description: >-
  WU2C works OH0ERF on Åland — a night reconstructed from ALL.TXT and QSO
  Predictor's outcome log: a 5-hour hidden pileup, 43 unanswered calls, and
  the behavior insight that finally put the QSO in the log.
---

*Welcome to the QSO Predictor blog. What better hello-world than a QSO
story? This one is reconstructed entirely from my station's ALL.TXT and QSO
Predictor's own outcome log — I wasn't recording video, but it turns out the
data tells it better anyway.*

---

At 15:42 UTC on Tuesday afternoon, my radio heard W6QUV in Colorado calling
someone. Then another station called the same someone. Then another.

The someone was OH0ERF — and I couldn't hear him at all.

This is the exact situation that made me write QSO Predictor in the first
place: the *hidden pileup*. Stations all around you are working a rare one
that hasn't put a single decode on your screen. All afternoon and evening my
log filled with one side of a conversation. By the end of the night my
receiver had caught **156 different stations** calling OH0ERF. For the first
five hours and forty-four minutes, the DX himself was a ghost — and my
receiver was on 14.074 the whole time, decoding thousands of other signals
an hour. The pileup itself surfaced and sank with propagation, twice fading
to nothing before roaring back.

![Two-panel timeline: stations heard calling OH0ERF per 30 minutes from 15:00 UTC, with the first OH0ERF decode at 21:26; below, a zoomed view of 23:25–00:30 showing WU2C's 43 unanswered calls hopping between five frequencies, OH0ERF parked at 905 Hz, and the answered call at 2508 Hz at 00:23 UTC](/blog/oh0erf-night.svg)

## The ghost materializes

At 21:26:30 UTC, there he was:

```
212630  -13  905 ~  CQ OH0ERF KP00
```

−13 dB, 905 Hz. Grid KP00 — the Åland Islands, a cluster of ~6,700 islands
in the Baltic between Finland and Sweden, and its own DXCC entity. A new one
for me.

And this operator was a *machine*. He parked on 905 Hz and never moved.
From 21:26 to 00:33 UTC I copied him answering **141 different stations** —
one QSO roughly every 80 seconds, for three hours, without a break. Croatia,
Japan, Brazil, Belize, Kentucky. Instant RR73s, next caller.

QSO Predictor was watching too. Its behavior model started the evening
calling him "methodical" at 70% confidence from the ML model; by the time it
mattered, the Bayesian tracker had watched enough cycles to say **methodical,
95%**. That matters: a methodical operator works the queue in order. You
don't need to be loud. You need to be *decodable, distinct, and patient*.

## The grind

At 23:32:45 I joined the pileup.

Twenty-eight transmissions of `OH0ERF WU2C FN42`. I hopped my TX around —
322 Hz, 2446, 1700, 1955, 1660 — thirteen minutes of calling into a wall of
competition. Nothing. The app logged the whole campaign and then wrote the
truth into its outcome file: `NO_RESPONSE`, 30 TX cycles, 43 minutes elapsed.
That's not a failure entry; that's training data.

## The 25% call

Just after 00:15 UTC I re-targeted him and QSO Predictor gave me its honest
assessment: **success probability 25%**. Strategy: `call_blind` — he wasn't
CQing, he was head-down working his queue. The frequency recommender liked
1087 Hz and scored it 100.

But another part of the app disagreed with it. The Insights panel had been
running live pattern analysis on his last several pickups, and it had
figured out *how* he was working the pileup:

> **High → Low** — *"Target working high-to-low. Position at higher
> frequencies."*

He wasn't picking the loudest caller. He was sweeping the passband from the
top down, and the place to be wasn't the recommender's clean spot at 1087 —
it was above the pack, early in his sweep.

I called seven more times at 2147, then committed to the behavior model's
read and climbed to **2508 Hz** — a spot the frequency scorer rated 25 out
of 100. The outcome log doesn't sugarcoat the disagreement:
`followed: false, score_delta: 75`. One subsystem's loss, on the record.

And then the dashboard flipped. **Heard by Target** — PSK Reporter showed
OH0ERF's own receiver decoding WU2C. The path was open. Nothing left to do
but keep calling from the top of the passband and wait for the sweep to
reach me.

Six calls at 2508. Then, at 00:23:30:

```
002330  -5  906 ~  WU2C OH0ERF +00
002345  Tx 2508 ~  OH0ERF WU2C R-05
002400  -8  906 ~  WU2C OH0ERF RR73
002415  Tx 2508 ~  OH0ERF WU2C 73
```

A **+00 report** — after 51 minutes of calling, I wasn't scraping into
Åland, I was *loud* in Åland. 6,106 km on a 37° bearing, logged at 00:24:15
UTC on my **45th transmission** of the night to him.

Thirty seconds later he was working K1HTV. Four minutes after that,
Tasmania. The machine rolled on and never blinked.

## What the log remembers

The part I like best is what QSO Predictor wrote down. It recorded a QSO it
had given 25% odds, on a frequency its own recommender had scored 25/100,
with `followed: false` — because that night, the app argued with itself and
the behavior model won. The frequency scorer knew where the clean spots
were; the pattern tracker knew *this operator*, and knowing the operator
beat knowing the spectrum. The log records that outcome with exactly the
same honesty as my 43-minute faceplant an hour earlier, because that's the
only way any of it gets smarter. Two subsystems voted. The log keeps score
either way.

---

### The numbers

| | |
|---|---|
| First station heard calling OH0ERF | 15:42:30 UTC (W6QUV, Colorado) |
| First decode *of* OH0ERF | 21:26:30 UTC — hidden pileup for 5 h 44 m |
| Distinct callers heard from FN42 | 156 |
| Stations heard working him | 141 in ~3 h (~1 per 80 s) |
| His TX frequency | 905 Hz, all night |
| My calls before the answer | 43 (over 51 minutes, 7 frequencies) |
| Winning frequency | 2508 Hz — per the "High → Low" behavior read; freq scorer said 25/100 |
| Model's success estimate | 25% |
| Exchange | +00 / R−05 / RR73 |
| Distance | 6,106 km, azimuth 37° |
| Band conditions | 20 m, SFI 108, K 0→1 |

*Curious what the panels in this story look like in the app? The
[User Guide](/USER_GUIDE.html) covers the band map, the Insights panel, and
the outcome recorder.*
