---
platform: wechat-channels
label: 视频号 WeChat Channels
form: short
lengths:
  history: [45, 90, 180]
  essay: [30, 60, 180]
  film: [20, 45, 120]
  photos: [20, 35, 90]
  reel: [20, 25, 45]
  vlog: [30, 60, 180]
  talking_head: [45, 90, 180]
  course: [60, 120, 180]
aspects: ['9:16', '16:9', '6:7']
chapters: {use: false}
captions: {style: burned, density: full}
title: {max: 16, habit: 短标题 16 字以内；描述写清地点和看点}
hook: 前 3 秒画面 + 一句字幕
hashtags:
  count: [1, 3]
  where: caption
cover: {size: 1080x1260, habit: '6:7 主页封面安全区'}
posting:
  times: ['工作日 12:00、20:00-22:00']
  cadence: 每周 2-4 条
  note: convention
---
# 视频号 WeChat Channels

Shared through WeChat: 30 s-2 min is the habit.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.
