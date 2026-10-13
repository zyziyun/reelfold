---
platform: x
label: X
form: short
lengths:
  history: [30, 60, 140]
  essay: [20, 45, 140]
  film: [15, 40, 120]
  photos: [15, 30, 90]
  reel: [20, 25, 45]
  vlog: [20, 45, 140]
  talking_head: [30, 60, 140]
  course: [45, 90, 140]
aspects: ['16:9', '1:1', '9:16']
chapters: {use: false}
captions: {style: sidecar, density: phrase, note: 'autoplay is muted: burned words or an .srt'}
title: {max: 0, habit: 'the post text is the title: one line, under 200 weighted characters'}
hook: 'the first 3 s carry it muted: picture + a word on screen'
hashtags:
  count: [0, 2]
  where: post
  note: hashtags cut reach above two
cover: {size: from the video, habit: the first frame shows in the timeline}
posting:
  times: ['Tue-Thu 09:00-12:00 local']
  cadence: as it happens
  note: convention
---
# X

140 s on a free account (premium tiers are longer). Short, muted-friendly cuts travel furthest.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
