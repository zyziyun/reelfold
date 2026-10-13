---
platform: zhihu
label: 知乎 Zhihu
form: long
lengths:
  history: [120, 300, 900]
  essay: [90, 180, 480]
  film: [60, 120, 300]
  photos: [60, 90, 240]
  reel: [60, 60, 120]
  vlog: [120, 240, 600]
  talking_head: [120, 300, 900]
  course: [300, 600, 1800]
aspects: ['16:9']
chapters: {use: true, from_s: 180, note: 时间点 in the description}
captions: {style: burned, density: full}
title: {max: 30, habit: 问题式或结论式标题}
hook: 开头直接给结论或问题
hashtags:
  count: [1, 5]
  where: topics
cover: {size: 1920x1080, habit: 信息型封面}
posting:
  times: ['工作日 20:00-23:00']
  cadence: 每周 1-2 条
  note: convention
---
# 知乎 Zhihu

Under 1 min earns no 创作分: explainers 2-10 min.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
