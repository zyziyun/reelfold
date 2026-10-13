---
platform: tiktok
label: TikTok
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
aspects: ['9:16']
chapters: {use: false}
captions: {style: burned, density: phrase, note: keep clear of the right button column and bottom 25 %}
title: {max: 55, habit: the caption is the hook line; 1 sentence + 3-5 hashtags}
hook: 'the first 1-2 s decide it: start mid-action, text on screen at 0:00'
hashtags:
  count: [3, 5]
  where: caption
  note: specific > generic
cover: {size: 1080x1920, habit: 'a frame with the subject centred; the grid crops to 3:4'}
posting:
  times: ['Tue-Thu 18:00-22:00 local']
  cadence: daily if you can
  note: convention
---
# TikTok

Uploads can be long, but the feed habit is 15-90 s; a story over 60 s needs a reason to keep watching.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
