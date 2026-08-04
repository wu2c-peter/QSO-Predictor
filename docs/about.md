---
layout: page
title: About
permalink: /about/
description: >-
  Who makes QSO Predictor and why: Peter Hirst WU2C — from teenage
  shortwave listener to physics PhD to a COVID-lockdown ham license,
  and the FT8 puzzle that started the project.
---

## The short version

QSO Predictor is written by me — Peter Hirst, **WU2C**, in grid FN42
(northeastern Massachusetts). First licensed in 2022, Amateur Extra,
modest station: wire antenna and a 600-watt tube amplifier. Nearly everything
the app does exists because something puzzled or bit me at my own
station — the rest came from sharp-eyed early users — and everything
ships only after it has worked on the air here.

## The longer version

As a teenager I was a shortwave listener. A license — and the
equipment to do more than listen — both seemed like a long shot. Life
went another way for a while: a degree and PhD in physics, working on
electronics and the physics of high-power microwave devices, including
some experimenting with early neural-network modelling in the early
1990s. Many years later I ended up at MIT, working in management
education.

During the COVID lockdown I discovered that a ham license was within
far easier reach than the teenage SWL remembered — and took my exams
in person at MIT, courtesy of the MIT Radio Society, W1MX. Licensed at
last — as KC1RFZ, soon WU2C — and now with a few resources that
teenager never had. Not unlimited
ones: a wire antenna and an old-school tube amp will only take you so
far on SSB, though a few true DX contacts made it through.

Then one day I installed WSJT-X, and FT8 was a revelation: real DX,
modest station, physics doing the heavy lifting.

But one thing kept nagging me. I'd pick an apparently empty offset,
call a DX station, and… nothing. Again and again — even when PSK
Reporter showed my signal was being decoded *in the DX station's own
region*. The band map said the frequency was clear. The propagation
said I was getting there. So why no answer?

Anyone who has used QSO Predictor knows how that story ends: the
frequency was only clear *on my end*. The competition — the pileup —
was often invisible to me, and the answers were scattered across data
sources nobody had assembled into one live picture.

## The code factory

Over Thanksgiving 2025 I started exploring AI coding tools, and the
idea of a digital-modes helper became the test project. It stopped
being a test very quickly. Working with a variety of AI tools —
eventually converging on Claude Code — turned into what I can only
describe as a one-human code factory: I bring the operating problems,
the radio physics, the design judgment, and the on-air testing; the AI
brings velocity. There's a pleasing symmetry in it, thirty years after
those first neural-net experiments.

Every feature is specified, reviewed, and field-tested by me at this
station before it ships — usually because I needed it the night
before. The hidden-pileup display, the Audio Doctor, the station
checkup, click-to-call: most of them started as my own problems.

But not all of them, and not only mine. A small group of early users
has shaped this app more than its size suggests — reporting the bugs I
couldn't reproduce, suggesting the fixes I wouldn't have found, and
testing on stations and setups I don't have. Brian KB1OPD, Warren
KC0GU, W6IX, and others are credited by name in the release notes and
commit history where their reports and ideas landed. A one-human code
factory still runs better with good field reports.

QSO Predictor is free, open source (GPLv3), and collects no data of
any kind. It never transmits on its own. It exists because I wanted
it, and it's shared because the puzzle it solves isn't unique to me.

**73, Peter WU2C**

---

*Questions, bug reports, or your own hidden-pileup story:
[GitHub](https://github.com/wu2c-peter/QSO-Predictor) or see
[Support](/support/).*
