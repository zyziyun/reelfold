---
platform: douyin
label: 抖音 Douyin
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
captions: {style: burned, density: full, note: 避开右侧按钮列和底部描述区}
title: {max: 55, habit: 一句话钩子 + 2-4 个话题}
hook: 前 2 秒定生死：直接从动作或结论开始
hashtags:
  count: [2, 5]
  where: caption
cover: {size: 1080x1920, habit: '竖屏封面，主体居中，信息流裁 3:4'}
posting:
  times: ['工作日 18:00-22:00']
  cadence: 每天或隔天
  note: convention
---
# 抖音 Douyin

15-90 s is the habit; 卡点 reels 20-40 s.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
