---
title: What is Reelfold
description: "Reelfold (千剪) is the open-source workbench for creators: your own footage, edited into videos for every platform and scheduled, on your Mac. Learn how it works."
---

Reelfold (千剪) is the open-source workbench for creators. It starts from the footage you shot and carries it all the way to publishing: you describe what you want in plain language and drop in a recording, a folder or an SD card, or a finished video you want to keep editing. Reelfold plans the videos, edits many at once on your own Mac (on autopilot, with local models if you like), checks every file and shows you only what needs a look. Each platform gets its own export, cover, title, caption and tags, YouTube, TikTok, Instagram, X and LinkedIn first, then Xiaohongshu, Douyin, Bilibili and WeChat Channels, and the publishing calendar lines up the week.

It is free, MIT licensed and open source. The code lives at [github.com/zyziyun/reelfold](https://github.com/zyziyun/reelfold).

## Footage first

Reelfold is not a tool that generates a film from a prompt. It works on what you already shot: talks, lectures, interviews, travel clips, photos, finished videos. The work it takes off your hands is everything after the camera: cutting, captions, covers, a version per platform, post copy and the posting schedule. Where a shot is missing it can suggest a generated one, with a price, and nothing is spent until you approve.

## Two ways to use it

Both forms run the same engine, so a recipe that works in one works in the other.

| | Reelfold for Mac | The Claude Code skill |
|---|---|---|
| What it is | A desktop app (`apps/desk`, Electron) | The engine as a skill for [Claude Code](https://claude.com/claude-code) (the repo root) |
| How you talk to it | One sentence on Home, then a chat on every project and clip | Plain language to Claude in your terminal |
| Good for | Hands-off batches on autopilot, hundreds of videos in one list, assisted publishing | Working inside a folder, scripting, one-off edits |
| Platform | macOS on Apple Silicon (Windows x64 in preview) | Anywhere Claude Code, Python 3.10+ and ffmpeg run |
| Install | [Install the Mac app](/docs/start/install-mac/) | [Install the skill](/docs/start/install-skill/) |

In the skill, `SKILL.md` routes each request to a workflow (`workflows/<name>/WORKFLOW.md`) with tested scripts and a shared Python library, `vstudio`.

## How a job flows

1. **Describe.** Say what you are making and add files: a talking-head clip, a 70-minute lecture, a folder of travel footage, a script. For example: "Cut this lecture into 10 vertical clips for TikTok and Shorts, under a minute each."
2. **Plan.** Reelfold reads the material and plans it: which workflow, how many clips, which platforms, how long it will take and what it may cost.
3. **Make.** The edits run on your Mac. On [Autopilot](/docs/app/autopilot/) (the default) the AI makes the everyday choices itself (unsure filler cuts, the opening, the cover, the music) and writes down each one with its reason, so you can change any of them later. With **Ask me first**, you confirm the plan and check one pilot clip before the rest is made. You can watch it happen on the [live run page](/docs/app/live-run/).
4. **Review.** Every file goes through automatic checks (missing words, frozen frames, loudness, length). Only real blockers and flagged clips reach your Inbox. Open any finished clip to change it in plain words.
5. **Publish.** Publishing is assisted. The Mac app opens each platform's own upload page in its built-in browser and fills in the file and the copy. You press publish. Reelfold never posts on its own.

More on each step: [Home](/docs/app/home/), [Autopilot and Ask me first](/docs/app/autopilot/), [Batch and review](/docs/concepts/batch-review/), [Publishing](/docs/concepts/publishing/).

## Who it is for

- **Batch creators** who record once and publish all week, in the shape, length and loudness each platform expects.
- **Podcasters and interviewers** who want many clips from one long conversation, with guests' faces masked when needed.
- **Teachers and course makers** who slice lectures and webinars into vertical clips or episodes, or [turn notes into narrated course videos](/docs/guides/course-from-notes/).
- **Talking-head creators (口播)** who want pauses, filler words and repeats gone, with captions, notes panels and a cover.
- **Studios** running client batches side by side, each with its own style and glossary.

## What runs on your Mac

Transcription, cutting, effects, rendering and the quality checks all run locally. AI is bring-your-own: your logged-in Claude Code or Codex CLI (no API key needed), an API key (Anthropic, OpenAI, DeepSeek, Qwen, Kimi, GLM, OpenRouter, Gemini, ElevenLabs), or a local model (Ollama, LM Studio, vLLM, llama.cpp, local whisper).

When an AI model is used, it receives text only (transcript, captions, titles, your notes), never your video or audio. In an internal test, one 72-minute lecture became 24 clips for 4 platforms (96 files) for $0.73 in AI API cost, about $0.03 per clip. See [AI providers](/docs/concepts/ai-providers/) and [Privacy](/docs/concepts/privacy/).

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
