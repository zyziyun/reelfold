---
platform: youtube
label: YouTube (long-form)
form: long
lengths:
  history: [240, 480, 720]
  essay: [180, 360, 600]
  film: [120, 240, 480]
  photos: [90, 180, 360]
  reel: [60, 120, 240]
  vlog: [240, 480, 900]
  talking_head: [240, 480, 900]
  course: [300, 600, 1200]
aspects: ['16:9']
chapters: {use: true, from_s: 180, note: '3+ chapters, each >= 10 s, the first at 0:00, in the description'}
captions: {style: sidecar, density: full, note: upload the .srt; burn only short on-screen labels}
title: {max: 100, habit: 'what it is + where, under 60 characters; English; no clickbait caps'}
hook: the strongest picture in the first 5 s; say what the video is in one line before 0:15
hashtags:
  count: [0, 3]
  where: description
  note: the first 3 show above the title
cover: {size: 1280x720, habit: 'one subject, 3-5 words of title max, readable at 320 px wide'}
posting:
  times: ['Thu-Sat 12:00-16:00 local']
  cadence: weekly
  note: 'convention: your own analytics win'
---
# YouTube (long-form)

Long-form lives on watch time: chapters, a calm intro under 15 s, the full story. A trip film can run 4-8 min when the footage carries it; a history explainer 6-10 min with 4-6 chapters. A reel posted here goes to Shorts instead (youtube-shorts).

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
