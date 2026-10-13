---
platform: kwai
label: Kwai
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
aspects: ['9:16']
chapters: {use: false}
captions: {style: burned, density: phrase}
title: {max: 0, habit: caption + hashtags}
hook: first second
hashtags:
  count: [2, 5]
  where: caption
cover: {size: 1080x1920, habit: first frame}
posting:
  times: [evenings local (BRT)]
  cadence: daily
  note: convention
---
# Kwai

15-60 s, posted from the phone.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
