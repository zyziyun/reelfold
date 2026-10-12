---
title: 配音
description: 千剪怎样选配音（你在 persona 里设的、有密钥时的 OpenAI，或 Apple 芯片上免费离线的 Kokoro），中文讲解里的英文术语怎么读，以及生僻词的小技巧。
---

讲解视频、课程视频和 AI 短剧都需要配音。千剪会选一个这台电脑真正能用的声音，不会因为付费配音没有密钥就停下。

## 用哪个声音

按顺序：

1. **你在 persona 里设的声音**（`persona.local.yaml` 里的 `tts.engine`，比如你自己的克隆声音）。
2. **OpenAI**（`gpt-4o-mini-tts`），只在设置 › AI 里有 OpenAI 密钥时才用。每分钟配音约 0.015 美元。
3. **免费配音**：Kokoro，在这台 Mac 上离线运行（Apple 芯片）。中文讲解用 `zf_xiaobei`；英文用 `af_heart`，也可以换成 `am_michael` 或 `bf_emma`。

自动驾驶时，设成 OpenAI 却没有密钥的项目会改用免费配音，并在 [AI 做的选择](/docs/zh/app/autopilot/#ai-做的选择)里写明。选了**先问我**时会问你：**用免费配音**，还是**添加 OpenAI 密钥**。连免费配音也没有时，就请你添加密钥。

## 下载免费配音

免费配音只需下载一次，大约 330 MB。第一次有视频要用它时会开始下载，也可以在设置 › 高级 › **下载内容**里手动下载。下载完成之前，配音这一步会提示「这台电脑上还没有下载免费配音。」，并给出**下载免费配音**；下载完点**再试一次**。

它离线可用，Mac App Store 版也能用。Intel Mac 和 Windows 没有免费配音，那里的配音需要 OpenAI 密钥（或你在 persona 里设的其他声音）。

## 中文讲解里的英文术语

中文课程里到处是英文术语：MCP、API、Tool Calling、USB-C。免费的中文配音会把中文读成中文，把每一段英文读成英文：

- **全大写的缩写**按字母读：「MCP」读作 M-C-P。
- **认识的单词**按单词读：「Tool Calling」「server」。
- **驼峰写法的名字**拆开读：「LangChain」读作 Lang Chain，「OpenAI」读作 Open A I。
- 完全不认识的词会按字母拼出来，不会跳过。
- 单独的数字跟着中文，用中文读。

## 生僻词和长句的小技巧

- **生僻词读错了，就换个说法**，或者换个常用词。按读音写也可以，但字幕跟着脚本走，字幕上也会显示成那样。
- **要按字母读的缩写写成大写**（写「API」，不要写「Api」）。
- **英文讲解里的数字按读法写**（「zero point five one」「F P thirty-two」），字幕会再变回数字。
- **句子短一点。** 特别长的句子会被拆开，好让配音一口气读完。如果配音还是漏了什么，千剪会告诉你是哪一幕、哪一句（见下）。

## 配音停下了

每一条配音都会转写出来和脚本对比。漏了一句就重新生成；总是失败的那句会拆成两半再试。还不行，运行就停下，并给出明白的提示：

| 提示 | 怎么办 |
|---|---|
| 配音几次都漏读了第 N 幕的一句：「…」 | 在脚本里把这句改个说法或拆成两句，再点**再试一次** |
| 配音读不出第 N 幕，分成两半也不行：「…」 | 同上：句子短一点、说法简单一点、生僻词换个说法 |
| 千剪里还没有 OpenAI 密钥，这一步没法运行 | **用免费配音**，或在设置 › AI 里添加密钥 |

## 用 Claude Code 技能

```yaml
# persona.local.yaml
tts:
  engine: kokoro        # 或 openai、clone、edge、openai-compatible、elevenlabs
```

`tts_engine: auto`（默认）和应用的顺序一样。你自己的克隆声音（`tts.clone`，Apple 芯片上的 Qwen3-TTS）也能在中文里读英文术语。引擎细节见 [声音](/docs/zh/reference/engine/sound/)。

## 相关页面

- [讲稿做成课程视频](/docs/zh/guides/course-from-notes/)
- [讲解视频](/docs/zh/guides/explainer/)
- [设置](/docs/zh/app/settings/)
- [问题排查](/docs/zh/help/troubleshooting/)
