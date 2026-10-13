---
platform: facebook
label: Facebook Reels
form: short
lengths:
  history: [30, 60, 90]
  essay: [20, 45, 90]
  film: [15, 30, 60]
  photos: [15, 25, 60]
  reel: [20, 25, 45]
  vlog: [20, 45, 90]
  talking_head: [30, 60, 90]
  course: [45, 75, 90]
aspects: ['9:16', '4:5', '16:9']
chapters: {use: false}
captions: {style: sidecar, density: phrase}
title: {max: 0, habit: first caption line is the title}
hook: movement in the first second, muted-friendly
hashtags:
  count: [1, 3]
  where: caption
cover: {size: 1080x1920, habit: 'centre 4:5 safe'}
posting:
  times: ['Wed-Fri 09:00-13:00 local']
  cadence: 2-3 a week
  note: convention
---
# Facebook Reels

Most uploads publish as Reels now; 15-90 s is the habit.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
