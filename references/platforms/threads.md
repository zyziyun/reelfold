---
platform: threads
label: Threads
form: short
lengths:
  history: [30, 60, 120]
  essay: [20, 45, 120]
  film: [15, 30, 90]
  photos: [15, 25, 60]
  reel: [20, 25, 45]
  vlog: [20, 45, 120]
  talking_head: [30, 60, 120]
  course: [45, 75, 120]
aspects: ['9:16', '16:9']
chapters: {use: false}
captions: {style: burned, density: phrase}
title: {max: 0, habit: the post text}
hook: first frame + one line
hashtags:
  count: [0, 1]
  where: post
  note: one topic tag
cover: {size: from the video, habit: first frame}
posting:
  times: ['weekdays 08:00-12:00 local']
  cadence: as it happens
  note: convention
---
# Threads

Up to 5 min; conversational, short.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
