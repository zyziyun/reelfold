---
title: "Editions: Mac, App Store, Windows"
description: "What differs between Reelfold for Mac from GitHub, the Mac App Store edition (Reelfold Lite) and the Windows preview: AI sign-in, folders, updates, the free voice, publishing and known limits."
---

Reelfold is one app built three ways. Projects, transcription, cleanup, captions, renders, review, the calendar and the recorder are the same code in all of them. This page lists what differs.

## At a glance

| | Mac (GitHub Releases) | Mac App Store (Reelfold Lite) | Windows (preview) |
|---|---|---|---|
| Hardware | Apple silicon | Apple silicon | Windows 10 / 11, x64 |
| AI | Claude Code or Codex sign-in, API keys, local models | API keys, local models (Ollama, LM Studio, vLLM) | Claude Code or Codex sign-in, API keys, local models |
| Files and folders | Any path; watched folders | Only the files and folders you pick (it asks once for a dropped file's folder) | Any path; watched folders |
| Updates | Built in, from GitHub Releases | The Mac App Store | Built in, from GitHub Releases |
| Free offline voice (Kokoro) | Yes | Yes | No: narration needs an OpenAI key or a voice you set |
| Speech recognition | MLX Whisper on the GPU | MLX Whisper on the GPU | faster-whisper on the CPU (slower; NVIDIA GPU optional) |
| Chromium download | Optional (HTML covers, slides) | Not downloaded; the app renders those itself | Optional |
| Publishing | Built-in browser with assisted fill; YouTube API optional | Built-in browser for every platform, YouTube included | Built-in browser (less tested) |
| Opt-in usage counts | Available, off by default | None | Available, off by default |
| Installer | Signed and notarized DMG | App Store | Unsigned installer (SmartScreen warns) |

## Mac App Store edition

The App Store edition is listed as **Reelfold** (it calls itself Reelfold Lite inside the app) and runs in Apple's sandbox. It is waiting for Apple's review, so it isn't on the store yet. In practice:

- **AI**: add an API key (Anthropic, OpenAI, DeepSeek, Qwen and more) or run a model on this Mac with Ollama or LM Studio. A sandboxed app can't run the Claude Code or Codex command-line tools you installed, so those sign-ins aren't offered. Explainer scenes and other AI steps work the same with a key or a local model.
- **Folders**: Reelfold can read the files and folders you choose in an Open panel or drop on the window, and keeps that permission. Folders to look in are limited to ones you picked.
- **Updates** come from the App Store.

## Windows preview

Windows is newer and less tested. Besides the table above:

- Paths over 260 characters can fail unless long paths are enabled; keep projects in a short folder such as `D:\Reelfold`.
- The publish browser, scheduled publishing and the recorder are less tested.
- Shortcuts use Ctrl where the Mac uses ⌘.

Install and details: [Install on Windows](/docs/start/install-windows/).

## Related

- [Install the Mac app](/docs/start/install-mac/)
- [Install on Windows](/docs/start/install-windows/)
- [AI providers](/docs/concepts/ai-providers/)
- [Privacy](/docs/concepts/privacy/)
