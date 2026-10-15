---
title: FAQ
description: Answers about Reelfold's price and licence, Windows support, what leaves your Mac, which AI you need, languages, brand fonts, publishing and commercial use.
---

## Is Reelfold free?

Yes. Reelfold is open source under the MIT licence: the engine, the Claude Code skill, the Mac app and the website. You only pay your AI provider, if you use a paid API. With a local model or your own logged-in Claude Code or Codex CLI, there is no API bill. In an internal test, 96 files from one 72-minute lecture cost $0.73 in API calls.

## Is there a download for Mac? What about Windows?

Yes. The Mac app (Apple Silicon) is on [GitHub Releases](https://github.com/zyziyun/reelfold/releases/latest), signed and notarized; see [Install the Mac app](/docs/start/install-mac/). A Mac App Store edition (Reelfold Lite) uses API keys or local models for AI. Windows 10 / 11 (x64) is in preview: each release also carries an unsigned Windows installer (SmartScreen warns), or build it from source; see [Install on Windows](/docs/start/install-windows/). What differs: [Editions](/docs/help/editions/). The engine uses faster-whisper and the `h264_mf` encoder there; most testing still happens on Macs.

## Does it post for me?

Only when you tell it to. YouTube goes through its official Data API: you sign in with Google in your own browser, and Publish or Schedule uploads the video, cover and copy (a scheduled post goes up private and YouTube publishes it at its time). For every other platform publishing is assisted: the app opens the platform's own upload page in its built-in browser, sets the video and types the title, text and tags, and you check it and press publish yourself. Scheduled posts go out on their own only if you turn on automatic posting. See [Publishing](/docs/concepts/publishing/).

## What leaves my Mac?

Your video and audio stay on your Mac: transcription and rendering run locally. Only what an AI step needs goes to the AI provider you chose: text such as the transcript, captions and titles, and for some steps contact sheets of still frames. Hosted transcription sends audio, while hosted narration sends the script. To keep AI processing local, use local models for all tasks and fallbacks, local transcription and voices, and leave hosted generation off. Downloads, updates and publishing are separate network operations. The app can also share anonymous usage counts, only if you turn it on ([what is sent](/docs/concepts/usage-counts/)). See [Privacy](/docs/concepts/privacy/).

## Which AI do I need?

Any of these, per task:

- Your own logged-in **Claude Code** or **Codex** CLI (no API key).
- Another **coding agent** you installed and signed in to, driven over ACP: Gemini CLI, Cursor CLI, GitHub Copilot CLI, OpenCode, Qwen Code, Kimi CLI, CodeBuddy, iFlow CLI.
- An **API key**: Anthropic, OpenAI, DeepSeek, Qwen, Kimi, GLM, Doubao, OpenRouter, Gemini, ElevenLabs. Qwen, Kimi, GLM and Doubao keys use their mainland China or international endpoint.
- A **local model**: Ollama, LM Studio, vLLM, llama.cpp, local whisper.

Without any AI, planning, post copy and simple edits fall back to rules. Drawing an explainer's scenes needs a model. See [AI providers](/docs/concepts/ai-providers/).

## Do I need Claude Code?

Not for the Mac app; any provider above works. The skill form of Reelfold runs inside Claude Code, so that one does. The explainer and course recipes need an AI model to draw their animated scenes; Claude Code, Codex, an API key or a local model all work.

## How is it different from Opus Clip, Descript or CapCut?

They are good tools with a different focus. Opus Clip is a hosted service for finding clips in long videos, Descript is a transcript-based editor, and CapCut is a timeline editor with templates. Reelfold is built for people who cut in batches:

- **Local-first.** Your footage is processed on your own Mac.
- **Batch, then review exceptions.** Many clips run in parallel, every file is checked automatically, and you look at what was flagged.
- **One recording, every platform.** Per-platform canvas, captions, loudness, cover and copy for 20 platforms.
- **Bring your own AI**, including none.
- **Open source** (MIT), so you can read, change and extend it.
- **English and Chinese from one source.** YouTube and TikTok versions in English, Xiaohongshu and Bilibili in Chinese.
- **Works with your editor.** Any clip exports to Premiere Pro, DaVinci Resolve, CapCut / 剪映 or OpenTimelineIO.
- **Publishing you control:** YouTube through its official API, upload pages filled in for the rest, nothing posted until you press Publish or Schedule.

## Which languages does it support?

The app is in English, 简体中文 and Français. For content, Chinese and English are the most developed: filler detection, caption rules, bilingual subtitles and post copy in both. Whisper transcribes many other languages, but those paths are less tested.

## Can I use my own fonts and brand colours?

Yes. In `persona.local.yaml`, point any font role (`cjk`, `cjk-bold`, `serif`, `mono` …) at your own file, and set your brand colours, panel theme, default hashtags and title rules. Studios can keep a separate brand per client. See [Themes](/docs/concepts/themes/) and the [persona reference](/docs/reference/persona/).

## Can I use it for commercial work?

The MIT licence allows commercial use, including client work. Two things to check yourself: your AI provider's terms (subscription CLIs such as Claude Code and Codex are meant for your own use; use an API key or a local model where the terms call for it), and the licences of the fonts, music and footage you put in. The optional RVM matting engine for covers is GPL-3.0 and is downloaded only if you choose it.

## Do I have to label AI content?

Follow each platform's rules. Chinese platforms require a declaration for AI-generated content (rules in force since 1 September 2025), and YouTube, TikTok and Meta have their own AI labels. Reelfold never ticks these for you; the publishing checklist and client delivery notes remind you. The AI video workflow plans a label per platform. See the [publishing reference](/docs/reference/engine/publishing/).

## What happened to video-studio and Daycut?

Reelfold is the new name. The open-source skill and engine were published as **video-studio**, and the desktop app was called **Daycut** (日剪). The skill is still named `video-studio`, the Python package is still `vstudio`, and existing installs in `~/.claude/skills/video-studio` keep working. Only the repository moved, to [github.com/zyziyun/reelfold](https://github.com/zyziyun/reelfold).

## Related

- [What is Reelfold](/docs/start/what-is-reelfold/)
- [Troubleshooting](/docs/help/troubleshooting/)
- [Contributing](/docs/contributing/)
