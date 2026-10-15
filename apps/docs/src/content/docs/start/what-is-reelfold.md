---
title: What is Reelfold
description: "Reelfold (千剪) is the open-source workbench for creators: one sentence turns your footage into a batch of ready-to-post videos for every platform, in English and Chinese, on your Mac."
---

Reelfold (千剪) is the open-source workbench for self-media and course creators: one sentence turns your footage into a batch of ready-to-post videos for every platform, in English and Chinese. Open source, free, and all on your Mac.

You describe what you want in plain language and start from whatever you have: a folder or an SD card, a recording, a recorded class, a finished video you want to keep editing, or just notes and a topic. Reelfold plans the videos (ask for "12 or so" and it plans a set of that size, each with its own angle), edits them on your own Mac on autopilot, a few at a time, makes the covers, checks every file and shows you only what needs a look. Each platform gets its own version: its own length, language, captions, cover, title and tags. YouTube, TikTok, Instagram, X and LinkedIn first, then Xiaohongshu, Douyin, Bilibili and WeChat Channels; the publishing calendar lines up the week.

It is free, MIT licensed and open source. The code lives at [github.com/zyziyun/reelfold](https://github.com/zyziyun/reelfold).

## Create, edit, publish

Reelfold covers the whole job, so you do not switch tools between the idea and the post:

- **Create.** Turn notes, an exported Notion page or a topic into a [course video](/docs/guides/course-from-notes/), an [explainer](/docs/guides/explainer/), an AI short or a [launch film](/docs/guides/launch-videos/), or record yourself with the teleprompter. Before any paid AI generation it shows the plan and the price, and nothing is spent until you approve. In footage projects, generation only fills gaps (a missing establishing shot, a cover background), and only when you approve that card.
- **Edit.** Work on what you already shot: talks, [recorded classes](/docs/guides/course-slicing/), interviews, travel clips, photos, finished videos. A template per kind of video, cuts on the beat, shot detection, colour matched per shot, smooth jump cuts and slow motion, captions, [covers](/docs/guides/covers/), music from a built-in CC0 library and a version per platform. Your own edits in the clip editor survive when the AI renders again, and any clip can go to Premiere Pro, DaVinci Resolve, CapCut / 剪映 or OpenTimelineIO.
- **Publish, at scale.** Post copy and the posting schedule for every platform, for one video or for [hundreds in one batch](/docs/guides/batch-100/), reviewed and acted on together in All projects. YouTube uploads through its official Data API; other platforms get their upload page filled in.

## Two ways to use it

Both forms run the same engine, so a recipe that works in one works in the other.

| | Reelfold for Mac | The Claude Code skill |
|---|---|---|
| What it is | A desktop app (`apps/desk`, Electron) | The engine as a skill for [Claude Code](https://claude.com/claude-code) (the repo root) |
| How you talk to it | One sentence on Home, then a chat on every project and clip | Plain language to Claude in your terminal |
| Good for | Hands-off batches on autopilot, hundreds of videos in one list, publishing from a calendar | Working inside a folder, scripting, one-off edits |
| Platform | macOS on Apple Silicon (Windows x64 in preview) | Anywhere Claude Code, Python 3.10+ and ffmpeg run |
| Install | [Install the Mac app](/docs/start/install-mac/) | [Install the skill](/docs/start/install-skill/) |

In the skill, `SKILL.md` routes each request to a workflow (`workflows/<name>/WORKFLOW.md`) with tested scripts and a shared Python library, `vstudio`.

## How a job flows

1. **Describe.** Say what you are making and add files: a talking-head clip, a 70-minute lecture, a folder of travel footage, a script. For example: "Cut this lecture into 10 vertical clips for TikTok and Shorts, under a minute each", or "Make about 12 videos from my DJI card, each with its own theme, for YouTube and Xiaohongshu".
2. **Plan.** Reelfold reads the material and plans it: which workflow and template, how many videos, which platforms and how long each platform's version is, how long it will take and what it may cost.
3. **Make.** The edits run on your Mac. On [Autopilot](/docs/app/autopilot/) (the default) the AI makes the everyday choices itself (unsure filler cuts, the opening, the cover, the music) and writes down each one with its reason, so you can change any of them later. With **Ask me first**, you confirm the plan and check one pilot clip before the rest is made. You can watch it happen on the [live run page](/docs/app/live-run/).
4. **Review.** Every file goes through automatic checks (missing words, frozen frames, flicker, loudness, length, caption language, on-screen text; history and explainer narration is fact-checked). Only real blockers and flagged clips reach your Inbox. Open any finished clip to change it in plain words.
5. **Publish.** YouTube goes through its official Data API: you sign in with Google in your own browser, and Publish or Schedule uploads the video, cover and copy. For the other platforms the Mac app opens the platform's own upload page in its built-in browser and fills in the file and the copy, and you press publish. Nothing is posted until you press Publish or Schedule (or turn on "Post scheduled videos automatically" yourself).

More on each step: [Home](/docs/app/home/), [Autopilot and Ask me first](/docs/app/autopilot/), [Batch and review](/docs/concepts/batch-review/), [Publishing](/docs/concepts/publishing/).

## Who it is for

- **Batch creators** who record once and publish all week, in the shape, length and loudness each platform expects.
- **Podcasters and interviewers** who want many clips from one long conversation, with guests' faces masked when needed.
- **Teachers and course makers** who slice lectures and webinars into vertical clips or episodes, or [turn notes into narrated course videos](/docs/guides/course-from-notes/).
- **Talking-head creators (口播)** who want pauses, filler words and repeats gone, with captions, notes panels and a cover.
- **Studios** running client batches side by side, each with its own style and glossary.

## What runs on your Mac

Transcription, cutting, effects, rendering and the quality checks all run locally. The free voices run locally too: Kokoro for English and Qwen3-TTS for Chinese (Apple silicon). AI is bring-your-own: your logged-in Claude Code or Codex CLI (no API key needed), another coding agent over ACP (Gemini CLI, Cursor CLI, GitHub Copilot CLI, OpenCode, Qwen Code, Kimi CLI, CodeBuddy, iFlow CLI), an API key (Anthropic, OpenAI, DeepSeek, Qwen, Kimi, GLM, Doubao, OpenRouter, Gemini, ElevenLabs; Qwen, Kimi, GLM and Doubao with their mainland China or international endpoint), or a local model (Ollama, LM Studio, vLLM, llama.cpp, local whisper). Pick the AI and model per request, project or chat (`/model`).

When an AI model is used, it receives text (transcript, captions, titles, your notes) and, for visual planning, contact sheets of still frames. Hosted transcription sends the audio track to the configured service; hosted generation receives the reference inputs it needs. In an internal test, one 72-minute lecture became 24 clips for 4 platforms (96 files) for $0.73 in AI API cost, about $0.03 per clip. See [AI providers](/docs/concepts/ai-providers/) and [Privacy](/docs/concepts/privacy/).

## Formerly video-studio and Daycut

Reelfold is the new name of this project. The skill and engine were published as **video-studio**, and the desktop app was called **Daycut** (日剪). Some names stay the same so existing setups keep working:

- the Claude Code skill is still called `video-studio` and installs to `~/.claude/skills/video-studio`
- the Python package is still `vstudio`
- only the repository URL moved, to `github.com/zyziyun/reelfold`

## Related

- [Install the Mac app](/docs/start/install-mac/)
- [Install the Claude Code skill](/docs/start/install-skill/)
- [Your first project](/docs/start/first-project/)
- [Example prompts](/docs/examples/)
