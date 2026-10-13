---
platform: linkedin
label: LinkedIn
form: short
lengths:
  history: [45, 90, 180]
  essay: [30, 75, 180]
  film: [30, 60, 120]
  photos: [30, 45, 120]
  reel: [20, 30, 60]
  vlog: [45, 90, 180]
  talking_head: [45, 90, 180]
  course: [60, 120, 180]
aspects: ['16:9', '1:1', '4:5']
chapters: {use: false}
captions: {style: sidecar, density: full, note: 'most watch muted at work: captions always'}
title: {max: 0, habit: the first 2 lines of the post carry it (the rest folds)}
hook: say the point in the first 3 s; no music-only intros
hashtags:
  count: [0, 3]
  where: post
cover: {size: from the video, habit: a clear frame with a face or the result}
posting:
  times: ['Tue-Thu 08:00-10:00 local']
  cadence: 1-2 a week
  note: convention
---
# LinkedIn

Professional feed: 30 s-3 min, captions on, one idea per video.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
