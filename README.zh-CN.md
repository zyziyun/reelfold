<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/wordmark-on-dark.svg">
    <img alt="Reelfold 千剪" src="docs/brand/wordmark-on-light.svg" width="340">
  </picture>
</p>

<p align="center"><b>开源自媒体工作者工作台。</b><br>
千剪：一句话，把你的素材批量剪成多平台、中英双语、可直接发布的成片，开源免费，全在本地。</p>

<p align="center">
  <a href="https://reelfold.com/zh/demo/">观看演示</a> ·
  <a href="https://reelfold.com/docs/zh/">使用文档</a> ·
  <a href="https://github.com/zyziyun/reelfold/releases/latest">下载 macOS 版</a> ·
  <a href="https://reelfold.com/zh/">官网</a> ·
  <a href="LICENSE">MIT</a>
</p>

素材进来，剪辑、封面、每个平台和语言各出一版、发布：给自媒体和课程创作者的一站式工作台，按批量来做。

- **一句话，做一整组。** 指向一个文件夹或一张 SD 卡，说“做 12 条左右，每条一个主题”。它把素材按故事分组，规划出你要的那一组
  （比如 10 到 20 条），自动驾驶地几条几条做完。一次跑几百条剪辑；每个决定都记下理由，随时能改。
- **每个平台，各剪一版、各用一种语言。** 先 YouTube、TikTok、Instagram、X、LinkedIn，再小红书、抖音、B站、视频号：20 个平台，
  各自的尺寸、时长（YouTube 出带章节的长版，Shorts、TikTok 出短版）、字幕、响度、封面和文案。YouTube、TikTok 用英文，
  小红书、B站用中文。
- **剪你拍的真实素材，讲究手艺。** 按视频类型选模板，剪点卡在节拍上（Beat This!），自动找镜头，逐镜头统一色彩，
  跳剪平滑、慢动作干净（RIFE），竖屏跟着主体走，内置 52 首 CC0 免费配乐。AI 生成只用来补缺，先报价，你同意才生成。
- **封面和质检。** 封面挑清楚的一帧、抠出主体、放大清晰，标题避开人脸和各平台按钮，YouTube 给三个 A/B 封面。
  每个文件检查闪烁、构图、响度、字幕语言和画面文字；讲解类旁白核对事实。你只看被标出来的。
- **在哪做的都能接着改。** 导入做好的成片接着改；你亲手改的地方，AI 重新渲染也会保留；可以开提词器自己录、加水印，
  任何片段都能导出到 Premiere Pro、DaVinci Resolve、剪映 / CapCut 或 OpenTimelineIO。
- **在日历上发布。** YouTube 走官方 Data API 上传和定时发布；其他平台由千剪填好上传页，发布按钮由你自己点。你不点头，什么都不会发出去。
- **本地、私密、免费，用你自己的 AI。** 渲染、转写和免费配音（英文 Kokoro，中文 Qwen3-TTS）都在你的 Mac 上跑。AI 用你自己的：
  Claude Code、Codex、ACP 编程助手（Gemini CLI、Qwen Code、Kimi CLI 等）、API Key（包括国内可用的服务商），或本地模型；
  每个请求都能换 AI 和模型，对话里输入 `/model` 也行。MIT 协议。

![口播 · 切片 · 文艺片 · 卡点 vlog · 播客遮脸 · 讲解短片](docs/demos/strip.jpg)

## 安装

**Mac 版**（Apple 芯片，免费）：从 [Releases](https://github.com/zyziyun/reelfold/releases/latest)
下载已签名、已公证的版本，或者[从源码构建](https://reelfold.com/docs/zh/start/install-mac/)。自动驾驶下，
一句话就能做到成片，每个选择都有记录；Windows 版是预览版。

**Claude Code 技能**（同一套引擎，技能名仍是 `video-studio`）：

```bash
git clone https://github.com/zyziyun/reelfold ~/.claude/skills/video-studio
~/.claude/skills/video-studio/install.sh
cp ~/.claude/skills/video-studio/persona.example.yaml ~/.claude/skills/video-studio/persona.local.yaml
```

AI 用你已有的：Claude Code / Codex 登录、其他 ACP 编程助手、自己的 API key，或者本地模型。

**使用文档 → [reelfold.com/docs/zh](https://reelfold.com/docs/zh/)**

## 这样说就行

| 你想要 | 可以这样说 |
|---|---|
| 一张卡剪出好几条 | 「把这张大疆卡里的素材做成几条视频，每条一个主题，发 YouTube 和小红书」 |
| 成片导入接着改 | 「这是上周做好的视频：开头再紧一点，换个封面，再出一个抖音竖屏版」 |
| 口播精剪 | 「把这个口播剪一下：去气口、去口头禅和重复，1.1 倍速，加字幕、记笔记、进度条，发小红书」 |
| 长课切片 | 「这个 70 分钟的课切成 3 条竖屏短视频，每条一个知识点，代码放大，带封面和发布文案」 |
| 播客切片 | 「从这个 Zoom 播客里找一段最有意思的 1 分钟，嘉宾遮脸、名字打码，竖屏」 |
| 卡点 vlog | 「迪士尼照片和片段剪一个快节奏卡点 vlog，DAY 标签、地点、音效、弹字，9:16」 |
| 一条发多平台 | 「同一条导出小红书 3:4、抖音、YouTube Shorts，各自的安全区和响度」 |

更多说法：[示例指令](https://reelfold.com/docs/zh/examples/)。

## 了解更多

[快速开始](https://reelfold.com/docs/zh/start/what-is-reelfold/) ·
[使用指南](https://reelfold.com/docs/zh/guides/talking-head/) ·
[核心概念](https://reelfold.com/docs/zh/concepts/projects/) ·
[参考](https://reelfold.com/docs/zh/reference/) ·
[常见问题排查](https://reelfold.com/docs/zh/help/troubleshooting/) ·
[参与贡献](https://reelfold.com/docs/zh/contributing/)

## 许可

MIT，包括桌面应用（`apps/desk`）、官网（`apps/site`）和文档（`apps/docs`）。字体和模型在安装时从上游下载，
遵循各自的许可（SIL OFL 1.1、Apache-2.0）。HTML 转视频的工作流基于 [HyperFrames](https://hyperframes.heygen.com)。

千剪的前身是 **video-studio**（技能和引擎）和 **Daycut / 日剪**（桌面应用）。已经装在 `~/.claude/skills/video-studio`
的技能照常可用，把远程地址改到新仓库即可：
`git -C ~/.claude/skills/video-studio remote set-url origin https://github.com/zyziyun/reelfold`。
