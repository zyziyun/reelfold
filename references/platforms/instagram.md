---
platform: instagram
label: Instagram Reels
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
aspects: ['9:16', '4:5']
chapters: {use: false}
captions: {style: burned, density: phrase, note: bottom 20 % holds the caption UI}
title: {max: 0, habit: no title field; the first caption line is the title}
hook: a strong first frame (it is also the grid tile) and movement in the first second
hashtags:
  count: [3, 5]
  where: caption
  note: at most 5 (2025 rule)
cover: {size: 1080x1920, habit: 'the grid shows the centre 3:4 / 4:5: keep the title there'}
posting:
  times: ['Mon-Fri 11:00-13:00 or 19:00-21:00 local']
  cadence: 3-4 a week
  note: convention
---
# Instagram Reels

Reels up to 90 s reach non-followers best; over 3 min they are not recommended outside your followers.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
