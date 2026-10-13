---
platform: reddit
label: Reddit
form: short
lengths:
  history: [45, 90, 300]
  essay: [30, 75, 180]
  film: [20, 45, 120]
  photos: [15, 30, 90]
  reel: [20, 30, 60]
  vlog: [30, 75, 180]
  talking_head: [45, 90, 300]
  course: [60, 180, 600]
aspects: ['16:9', '1:1', '9:16']
chapters: {use: false}
captions: {style: sidecar, density: phrase}
title: {max: 300, habit: 'plain, descriptive; the sub''s rules first'}
hook: 'no hook tricks: the title promises, the video delivers'
hashtags:
  count: [0, 0]
  where: none
cover: {size: from the video, habit: first frame}
posting:
  times: ['weekdays 06:00-09:00 US Eastern']
  cadence: per subreddit rules
  note: convention
---
# Reddit

Depends on the subreddit; a clean 30 s-3 min cut without branding fits most.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
