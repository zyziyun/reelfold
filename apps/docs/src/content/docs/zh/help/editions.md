---
title: 版本区别：Mac、App Store、Windows
description: 从 GitHub 下载的千剪 Mac 版、Mac App Store 版（千剪 Lite）和 Windows 预览版有什么不同：AI 登录、文件夹、更新、免费配音、发布和已知限制。
---

千剪是同一个应用，有三种构建方式。项目、转写、去口癖、字幕、渲染、审片、日历和录制在三者里都是同一套代码。这一页列出不同的地方。

## 一览

| | Mac（GitHub Releases） | Mac App Store（千剪 Lite） | Windows（预览版） |
|---|---|---|---|
| 硬件 | Apple 芯片 | Apple 芯片 | Windows 10 / 11，x64 |
| AI | Claude Code 或 Codex 登录、API 密钥、本地模型 | API 密钥、本地模型（Ollama、LM Studio、vLLM） | Claude Code 或 Codex 登录、API 密钥、本地模型 |
| 文件和文件夹 | 任意路径；可监看文件夹 | 只能用你选过的文件和文件夹（拖进来的文件，会问一次它所在的文件夹） | 任意路径；可监看文件夹 |
| 更新 | 应用内更新，来自 GitHub Releases | Mac App Store | 应用内更新，来自 GitHub Releases |
| 免费离线配音（Kokoro） | 有 | 有 | 没有：配音需要 OpenAI 密钥或你设的声音 |
| 语音识别 | MLX Whisper，用 GPU | MLX Whisper，用 GPU | faster-whisper，用 CPU（较慢；可选 NVIDIA GPU） |
| 下载 Chromium | 可选（HTML 封面、幻灯片） | 不下载；这些由应用自己渲染 | 可选 |
| 发布 | 内置浏览器辅助填写；可选 YouTube API | 所有平台都用内置浏览器，YouTube 也是 | 内置浏览器（测试较少） |
| 可选的使用统计 | 有，默认关闭 | 没有 | 有，默认关闭 |
| 安装包 | 签名并公证的 DMG | App Store | 未签名的安装程序（SmartScreen 会警告） |

## Mac App Store 版

App Store 版叫**千剪 Lite**，运行在苹果的沙盒里。实际使用中：

- **AI**：添加 API 密钥（Anthropic、OpenAI、DeepSeek、通义千问等），或用 Ollama、LM Studio 在这台 Mac 上跑模型。沙盒里的应用不能运行你自己装的 Claude Code 或 Codex 命令行，所以没有这两个登录。讲解视频的画面等 AI 步骤，用密钥或本地模型一样能做。
- **文件夹**：千剪能读你在打开面板里选的、或拖到窗口上的文件和文件夹，并记住这个授权。监看的文件夹只能是你选过的。
- **更新**来自 App Store。

## Windows 预览版

Windows 版比较新，测试也少一些。除了上表：

- 超过 260 个字符的路径可能出错，除非开启了长路径；把项目放在短一点的文件夹里，比如 `D:\Reelfold`。
- 发布浏览器、定时发布和录制测试得较少。
- 快捷键用 Ctrl 代替 Mac 上的 ⌘。

安装和细节：[在 Windows 上安装](/docs/zh/start/install-windows/)。

## 相关页面

- [安装 Mac 应用](/docs/zh/start/install-mac/)
- [在 Windows 上安装](/docs/zh/start/install-windows/)
- [AI 模型](/docs/zh/concepts/ai-providers/)
- [隐私](/docs/zh/concepts/privacy/)
