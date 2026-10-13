---
platform: pinterest
label: Pinterest
form: short
lengths:
  history: [20, 40, 60]
  essay: [15, 30, 60]
  film: [10, 25, 60]
  photos: [10, 20, 45]
  reel: [20, 25, 45]
  vlog: [15, 30, 60]
  talking_head: [20, 40, 60]
  course: [30, 45, 60]
aspects: ['9:16', '2:3', '1:1']
chapters: {use: false}
captions: {style: burned, density: sparse}
title: {max: 100, habit: 'searchable words: what + where'}
hook: a beautiful first frame (it is the pin)
hashtags:
  count: [0, 0]
  where: none
  note: keywords in title / description instead
cover: {size: 1000x1500, habit: '2:3, text large'}
posting:
  times: [evenings and weekends local]
  cadence: steady, several a week
  note: convention
---
# Pinterest

Idea pins: 6-60 s, silent-friendly, inspirational.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
