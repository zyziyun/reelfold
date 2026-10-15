---
title: 常见问题
description: 关于千剪的价格和开源协议、Windows 支持、哪些数据会离开你的电脑、需要什么 AI、支持的语言、品牌字体、发布和商用的解答。
---

## 千剪免费吗？

免费。千剪（Reelfold）以 MIT 协议开源：引擎、Claude Code 技能、Mac 应用和网站都是。只有用付费 API 时才需要付 AI 服务商的钱；用本地模型或你自己已登录的 Claude Code / Codex CLI，就没有 API 账单。内部测试里，一节 72 分钟的课做出 96 个文件，API 花了 0.73 美元。

## 有 Mac 安装包吗？Windows 呢？

有。Mac 应用（Apple Silicon）在 [GitHub Releases](https://github.com/zyziyun/reelfold/releases/latest) 上，已签名并公证，见[安装 Mac 应用](/docs/zh/start/install-mac/)。Mac App Store 版（千剪 Lite）的 AI 用 API 密钥或本地模型。Windows 10 / 11（x64）目前是预览版：每个版本都附带未签名的 Windows 安装包（SmartScreen 会提示），也可以从源码构建，见[在 Windows 上安装](/docs/zh/start/install-windows/)。各版本的区别见[版本区别](/docs/zh/help/editions/)。那里引擎用 faster-whisper 和 `h264_mf` 编码器；大部分测试仍在 Mac 上做。

## 它会替我发帖吗？

只在你让它发的时候。YouTube 走官方 Data API：你在自己的浏览器里用 Google 登录，按下发布或排期，就上传视频、封面和文案（排期的视频先以私享上传，到点由 YouTube 公开）。其他平台都是辅助发布：应用在内置浏览器里打开平台自己的上传页，放好视频，填好标题、正文和标签，你检查之后自己点发布。排好的视频只有在你打开「自动发布排好的视频」后才会到点自己发。见[发布](/docs/zh/concepts/publishing/)。

## 哪些东西会离开我的电脑？

视频和音频都留在你的 Mac 上，转写和渲染都在本地。只有 AI 步骤需要的内容会发给你选的 AI 服务：逐字稿、字幕和标题这类文字，有些步骤还有静帧拼图。云端转写会发送音轨，云端配音会发送稿子。要让 AI 处理留在本地，请为所有任务和备用路由使用本地模型、本地转写和配音，并关闭云端生成。下载、更新和发布是另外的联网操作。应用还可以分享匿名使用次数，但只有你打开才会发送（[具体发送什么](/docs/zh/concepts/usage-counts/)）。见[隐私](/docs/zh/concepts/privacy/)。

## 需要什么 AI？

以下任意一种，每项工作可以分别指定：

- 你自己已登录的 **Claude Code** 或 **Codex** CLI（不用 API key）。
- 你装好并登录的其他 **编程助手**，通过 ACP 接入：Gemini CLI、Cursor CLI、GitHub Copilot CLI、OpenCode、Qwen Code、Kimi CLI、CodeBuddy、iFlow CLI。
- **API key**：Anthropic、OpenAI、DeepSeek、通义千问、Kimi、智谱 GLM、豆包、OpenRouter、Gemini、ElevenLabs。通义千问、Kimi、GLM、豆包可选国内或国际接入点。
- **本地模型**：Ollama、LM Studio、vLLM、llama.cpp、本地 whisper。

完全不配 AI 的话，规划、发布文案和简单修改会退回规则方案；画讲解视频的场景必须有模型。见[AI 服务](/docs/zh/concepts/ai-providers/)。

## 一定要有 Claude Code 吗？

用 Mac 应用不需要，上面任何一种都行。千剪的技能形态是跑在 Claude Code 里的，那个需要。另外讲解视频和课程配方要靠 AI 模型来画动画场景；Claude Code、Codex、API 密钥或本地模型都可以。

## 和 Opus Clip、Descript、剪映有什么不同？

它们都是好工具，只是侧重点不同：Opus Clip 是从长视频里找片段的在线服务，Descript 是基于逐字稿的剪辑器，剪映（CapCut）是带模板的时间线剪辑器。千剪是给批量剪片的人做的：

- **本地优先。** 素材在你自己的 Mac 上处理。
- **批量跑，只审例外。** 很多条并行跑，每个文件都自动检查，你只看被标出来的。
- **一条素材，所有平台。** 20 个平台各自的画布、字幕、响度、封面和文案。
- **自带 AI**，也可以不用 AI。
- **开源**（MIT），可以读、改、扩展。
- **一份素材，中英两种语言。** YouTube、TikTok 出英文版，小红书、B站出中文版。
- **能接你的剪辑软件。** 任何片段都能导出到 Premiere Pro、DaVinci Resolve、剪映 / CapCut 或 OpenTimelineIO。
- **发布由你掌控：** YouTube 走官方接口，其他平台替你填好上传页，你不按发布或排期就不会发出去。

## 支持哪些语言？

应用界面有英文、简体中文和法文。内容方面，中文和英文最完善：口癖识别、字幕规则、双语字幕和两种语言的发布文案。whisper 能转写很多其他语言，但那部分测试得少。

## 能用自己的字体和品牌色吗？

能。在 `persona.local.yaml` 里把任意字体角色（`cjk`、`cjk-bold`、`serif`、`mono` 等）指向你自己的字体文件，再设好品牌色、面板主题、默认话题标签和标题规则。工作室可以给每个客户单独一套品牌。见[主题](/docs/zh/concepts/themes/)和 [persona 参考](/docs/zh/reference/persona/)。

## 能商用吗？

MIT 协议允许商用，包括接客户的活。有两件事需要你自己确认：AI 服务的条款（Claude Code、Codex 这类订阅制 CLI 是给你自己用的，条款有要求时改用 API key 或本地模型），以及你放进去的字体、音乐和素材的授权。封面可选的 RVM 抠图引擎是 GPL-3.0 协议，只有你选了才会下载。

## AI 生成的内容要标注吗？

按各平台的规则来。国内平台要求声明 AI 生成内容（相关标识规定自 2025 年 9 月 1 日起施行），YouTube、TikTok 和 Meta 也各有 AI 标签。千剪从不替你勾选，发布检查清单和客户交付说明会提醒你。AI 视频工作流会为每个平台规划好标注方式。见[发布参考](/docs/zh/reference/engine/publishing/)。

## video-studio 和日剪（Daycut）去哪了？

千剪是新名字。开源的技能和引擎以前叫 **video-studio**，桌面应用以前叫 **日剪（Daycut）**。技能仍然叫 `video-studio`，Python 包仍然是 `vstudio`，装在 `~/.claude/skills/video-studio` 的旧版本照常能用，只是仓库搬到了 [github.com/zyziyun/reelfold](https://github.com/zyziyun/reelfold)。

## 相关

- [千剪是什么](/docs/zh/start/what-is-reelfold/)
- [问题排查](/docs/zh/help/troubleshooting/)
- [参与贡献](/docs/zh/contributing/)
