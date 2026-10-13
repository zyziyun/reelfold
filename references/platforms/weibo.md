---
platform: weibo
label: 微博 Weibo
form: short
lengths:
  history: [60, 120, 300]
  essay: [30, 75, 180]
  film: [30, 60, 180]
  photos: [30, 45, 120]
  reel: [20, 30, 60]
  vlog: [45, 120, 300]
  talking_head: [60, 120, 300]
  course: [120, 240, 600]
aspects: ['16:9', '9:16']
chapters: {use: false}
captions: {style: burned, density: full}
title: {max: 30, habit: 标题 + 一段文字}
hook: 前 3 秒
hashtags:
  count: [1, 3]
  where: post
  note: '#话题# double-hash style'
cover: {size: from the video, habit: 清楚的主体}
posting:
  times: ['工作日 12:00、20:00-23:00']
  cadence: 随热点
  note: convention
---
# 微博 Weibo

30 s-5 min; news-like, topical.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
