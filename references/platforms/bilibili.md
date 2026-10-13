---
platform: bilibili
label: B站 Bilibili
form: long
lengths:
  history: [180, 420, 900]
  essay: [180, 300, 600]
  film: [120, 240, 600]
  photos: [90, 180, 420]
  reel: [60, 90, 240]
  vlog: [180, 420, 900]
  talking_head: [180, 420, 900]
  course: [300, 720, 1800]
aspects: ['16:9']
chapters: {use: true, from_s: 180, note: 分段章节 in the uploader (and timestamps in 简介); long series as 分P}
captions: {style: burned, density: full, note: 中文字幕；B站 viewers expect full subtitles}
title: {max: 80, habit: 信息量足：主题 + 看点 + 地点，可带【】栏目名}
hook: 开头 15 秒内交代看什么，可以有片头但要短
hashtags:
  count: [5, 10]
  where: tags field
cover: {size: 1146x717, habit: '16:10 封面，大字 + 主体，4:3 / 16:9 裁切都要安全'}
posting:
  times: ['工作日 18:00-23:00；周末下午']
  cadence: 每周 1-2 条
  note: convention
---
# B站 Bilibili

Long-form 3-15 min with 分段章节; a history explainer 5-12 min; a trip film 4-8 min. Series of parts go out as 分P.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
