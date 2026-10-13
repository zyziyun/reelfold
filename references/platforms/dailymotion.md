---
platform: dailymotion
label: Dailymotion
form: long
lengths:
  history: [180, 360, 900]
  essay: [120, 240, 600]
  film: [90, 180, 480]
  photos: [60, 120, 300]
  reel: [60, 90, 240]
  vlog: [180, 360, 900]
  talking_head: [180, 360, 900]
  course: [300, 600, 1800]
aspects: ['16:9']
chapters: {use: true, from_s: 180, note: timestamps in the description}
captions: {style: sidecar, density: full}
title: {max: 255, habit: 'descriptive, searchable'}
hook: the first 10 s
hashtags:
  count: [3, 10]
  where: tags
cover: {size: 1280x720, habit: '16:9 thumbnail'}
posting:
  times: [weekday evenings CET]
  cadence: weekly
  note: convention
---
# Dailymotion

Long-form like YouTube: 3-10 min.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
