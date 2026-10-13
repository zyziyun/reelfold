---
platform: youtube-shorts
label: YouTube Shorts
form: short
lengths:
  history: [30, 50, 180]
  essay: [30, 45, 180]
  film: [20, 40, 120]
  photos: [20, 35, 90]
  reel: [20, 30, 60]
  vlog: [25, 45, 180]
  talking_head: [30, 50, 180]
  course: [30, 60, 180]
aspects: ['9:16']
chapters: {use: false}
captions: {style: burned, density: phrase, note: short lines in the safe zone}
title: {max: 100, habit: 'under 40 characters, English, the payoff in words'}
hook: motion or the best frame in the first second; no logo intro
hashtags:
  count: [1, 3]
  where: description
  note: '#Shorts is optional; YouTube decides by shape + length'
cover: {size: 1080x1920, habit: picked from the video in the app; keep the title off the bottom 20 %}
posting:
  times: ['daily 11:00-14:00 or 19:00-22:00 local']
  cadence: 3-5 a week
  note: convention
---
# YouTube Shorts

Vertical, up to 3 min (over 3 min YouTube treats it as long-form). Loops well when the last frame leads back into the first. 20-60 s is the habit; a told piece can take 1-2 min.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
