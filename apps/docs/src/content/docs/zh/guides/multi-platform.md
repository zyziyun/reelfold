---
title: 一个母版发多个平台
description: 一个项目导出到你发的每个平台：各自的时长、语言、画布、避开 App 界面的字幕位置、响度、封面和发布文案，一次全部出齐。
---

一个项目，每个平台出一个文件：时长和语言对得上，画布对得上，字幕的大小和位置避开这个 App 的按钮，响度统一，封面单独一张，发布文案用对的语言、不超字数，最后还有一份记录所有检查结果的清单。

## 每个平台一种时长

不是每个平台都发同一条视频。每个平台的版本按这个平台对这类视频的习惯来剪：

- **长版，带章节**：YouTube 和 B站（素材撑得起时按分钟算）。
- **短版**：Shorts、TikTok、Instagram、LinkedIn 和小红书。

两种版本都从同一个项目做出来，各自按自己的时长起稿、渲染，不是从另一版裁出来的。在 **设置 › 发布账号 › 视频时长** 里按平台设置你自己的最短和最长，每次规划都会遵守。「多条视频」的计划卡片会显示并可修改每个平台的时长，以及素材够做多长（「素材够做约 4 分钟」）。

## 每个平台一种语言

YouTube 总是英文：标题、字幕、旁白和发布文案都是。小红书、B站 和其他国内平台用中文。两种都要时，会做一个英文版和一个中文版，各自只用于自己的平台：英文版的排期打开 YouTube，中文版打开小红书和 B站。需求里点名的平台优先于输入框里的平台标签。

## 开始之前

- **一个干净的母版**：剪好的成片，**不要烧录字幕**。烧在 16:9 母版上的字，到 3:4 和 9:16 上会被裁掉。
- **字幕单独一个文件**（`cues.json` 或 `.srt`），每个平台导出时按自己的位置重新排。两种语言就每种语言一个文件。
- **封面。** 最好每种画幅一张，见[封面和缩略图](/docs/zh/guides/covers/)。
- 可选：一个 `post.json`，写好标题、开头一句、正文、章节、链接和标签；中英文都发的话分 `en` 和 `zh` 两块。

一共有 20 个平台的配置，从 YouTube、TikTok、Instagram 到小红书、抖音、视频号、B站。完整的尺寸和限制见[平台参考](/docs/zh/reference/platforms/)。

## 在 Mac 应用里

1. 在需求里直接说要发哪些平台，或者在计划里加上，比如「发 Shorts、小红书和抖音」。
2. 片子做完后，用 **打包发布** 选片子和平台。每个平台一个文件夹，里面是对应版本的视频、封面和文案，并且按这个平台的限制检查过。
3. 清单确认一次，然后到发布页的周历上排期。

## 用 Claude Code 技能

跟 Claude 说要导出多个平台，它会调用共用的导出工具：

```bash
python3 -m vstudio.export work/master.mp4 --platforms youtube,xiaohongshu:vertical,douyin \
    --out exports/ --cues en=work/cues.en.json --cues zh=work/cues.zh.json \
    --cover work/cover-16x9.png --cover work/cover-3x4.png --post work/post.json
```

如果是在别的软件里剪好的，`workflows/polish` 可以先把母版收尾一次，再按平台导出。

## 每个平台会做什么

- **画布。** 画幅变了就重新构图，在安全区里跟着主要人脸走；找不到人脸就用模糊背景填充。同画幅的母版只做缩放。
- **字幕**：按语言给了多条字幕时，每个平台用自己语言的那条（YouTube 和 Shorts 用英文，小红书、B站、抖音用中文）；某个平台的语言没有对应字幕，就用另一条并给出提醒。字幕放进这个平台的字幕区，按两行排版，避开它的界面：顶栏、底部文案区、右侧按钮列。母版上有烧录的记笔记面板或印章的话，在 `cues.json` 里加 `keepouts`，字幕会在它们出现时挪到上方或下方。
- **字幕文件。** 上传页能传字幕文件的平台（YouTube 和 Shorts、X、Facebook、LinkedIn）还会在视频旁边得到 `<文件名>.<语言>.srt`，每种字幕语言一个。`--captions sidecar` 让这些平台的视频保持干净（观众自己打开字幕），没有字幕上传的平台（比如小红书、抖音）照样烧录。
- **响度。** 默认整体 −14 LUFS、真峰值 −1.5 dBTP。只有 YouTube 公布了响度标准，其他平台用的是一个稳妥的约定值，可以按平台单独改。
- **编码。** H.264 High、yuv420p、AAC 48 kHz，每个平台有自己的码率上限；超过平台上传大小会提醒。
- **封面。** 每个平台用画幅最接近的封面，也可以用 `--cover douyin=cover_9x16.png` 指定。画幅不一致的封面会放在模糊背景上并给出提醒。信息流会裁封面的平台，会多一张 `.feed.jpg` 预览。
- **发布文案。** 标题、正文、标签按平台限制检查（YouTube 标题 100，X 按权重 280，小红书标题 20 字）。英文内容在 X、Instagram、TikTok 和 YouTube 上用英文文案；`--bilingual` 先英文后中文。
- **清单。** `manifest.json` 记录文件大小、时长、实测响度、构图找到人脸的比例和所有提醒。

输出文件名是 `<平台>-<方向>.mp4`，旁边是 `.cover.jpg`、`.post.md` 和 `.crop.json`，平台能传字幕文件时还有 `.srt`。

## 值得了解的选项

| 选项 | 默认 | 作用 |
|---|---|---|
| `--platforms` | persona 里的默认 | 逗号分隔的 `平台[:方向]`，例如 `xiaohongshu:full,douyin`。 |
| `--mode` | face | 构图方式：`face`、`center`、`pad-blur` 或 `letterbox`。 |
| `--cues` | 无 | 一条字幕，或每种语言一条：`--cues en=cues.en.json --cues zh=cues.zh.json`。 |
| `--captions` | both | `both` 烧录字幕并写 `.srt`；`sidecar` 让能传字幕的平台保持干净；`burn` 只烧录。 |
| `--no-captions` | 关 | 母版已经有字幕，不再烧录。 |
| `--lang` / `--bilingual` | 自动识别 | 文案语言：`en`、`zh` 或双语。 |
| `--account` | 普通 | 账号等级，影响限制，例如 X 的 `premium`。 |
| `--encoder` | libx264 | `h264_videotoolbox` 用 Mac 的硬件编码。 |

## 示例指令

- 「同一条导出 YouTube Shorts、小红书 3:4、抖音，各自安全区和响度。」
- 「YouTube 出一个带章节的长版，TikTok 和小红书出 60 秒的短版。」
- 「这条再出 X 和 Instagram Reels，加一个 4:5 的信息流版本，英文字幕、英文文案。」
- 「母版已经有字幕了，别再加，只做构图、响度和封面。」
- 「每个平台的发布文案都写中英双语。」

## 相关

- [平台参考](/docs/zh/reference/platforms/) 和 [字幕参考](/docs/zh/reference/captions/)
- [封面和缩略图](/docs/zh/guides/covers/)
- [排期和发布](/docs/zh/guides/scheduling-publishing/)
- [发布](/docs/zh/concepts/publishing/)
- [polish 工作流参考](/docs/zh/reference/workflows/polish/)
