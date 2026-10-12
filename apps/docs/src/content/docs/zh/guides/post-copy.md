---
title: 各平台的发布文案
description: 千剪怎样按平台限制、用对的语言（publish.copy_lang）给每个平台写标题、正文和话题，以及怎样重写做好的视频的发布文案。
---

每条做好的视频，都会给你选的每个平台配一份发布文案：标题、正文和话题，都在平台的限制之内。没有语音的视频（vlog、航拍片、照片故事）按事实来写：地点、月份、你的原话、你的标题和配乐。

## 包括什么

| 部分 | 说明 |
|---|---|
| 标题 | 按平台限制调整（比如 YouTube 100、B站 80、抖音 30、小红书 20）。超长的会标出来，不会截断 |
| 正文 | 几行字；YouTube 上是更长的简介。正文里不放话题 |
| 话题 | 只在相关时加，数量在平台限制之内 |
| 地点 | 离线获取，素材带 DJI 飞行记录时从里面读 |
| 配乐署名 | 曲子要求署名时加上（比如 CC BY 的曲子） |

你自己起的标题，在同语言的平台上会保留。连了 AI 时由 AI 来写，写完会检查，缺的部分用规则补上。没有模型时按规则根据事实来写，并注明。两份草稿都会保留，所以在自动驾驶下这是一个可以改的选择（「发布文案由 AI 写」或「发布文案按事实写」）。

## 用什么语言

- **海外平台**（YouTube、TikTok、X、Instagram）：你 persona 里设的语言，默认英文。
- **国内平台**（小红书、抖音、B站）：跟你请求的语言一致。用中文提的请求，这几个平台的文案就是中文。

在 `persona.local.yaml` 里改：

```yaml
publish:
  copy_lang: {intl: en}          # YouTube / TikTok / X / Instagram
  # copy_lang: {intl: fr, tiktok: zh}   # 或者按平台单独设
```

## 重写发布文案

在成片页面点**重写发布文案**，或者跟对话说「重写发布文案」。每个平台的标题、正文和话题按各自的语言重写，写好后替换各版本的发布文字。

在终端里：

```bash
python -m vstudio.project remake --dir <项目> --item <成片> --do copy
```

## 相关页面

- [排期和发布](/docs/zh/guides/scheduling-publishing/)
- [Vlog](/docs/zh/guides/vlog/)
- [平台参考](/docs/zh/reference/platforms/)
- [persona 参考](/docs/zh/reference/persona/)
