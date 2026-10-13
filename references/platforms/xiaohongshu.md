---
platform: xiaohongshu
label: 小红书 RedNote
form: short
lengths:
  history: [45, 90, 180]
  essay: [30, 75, 180]
  film: [30, 60, 120]
  photos: [30, 45, 120]
  reel: [20, 30, 60]
  vlog: [45, 90, 180]
  talking_head: [45, 90, 180]
  course: [60, 150, 180]
aspects: ['3:4', '9:16']
chapters: {use: false, note: a 时间线 list in the body instead of chapters}
captions: {style: burned, density: full, note: 中文字幕 throughout; keyword colour sparingly}
title: {max: 20, habit: 20 字以内，具体：地点 + 看点 / 结论；可加 1 个 emoji 不必}
hook: 封面即钩子：3:4 封面大字标题；视频前 3 秒给出看点
hashtags:
  count: [3, 8]
  where: body end
  note: '#话题 at the end of the body'
cover: {size: 1080x1440, habit: '3:4 大字封面，标题在中间三分之一'}
posting:
  times: ['工作日 12:00-13:00、19:00-22:00；周末上午']
  cadence: 每周 3-5 条
  note: convention
---
# 小红书 RedNote

30 s-3 min is the habit (longer uploads work but are watched less); 3:4 vertical reads best in the feed. A history piece fits in 1.5-3 min with 中文旁白 or 字幕.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
