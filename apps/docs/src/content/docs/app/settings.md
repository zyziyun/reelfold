---
title: Settings
description: "A tour of Reelfold's Settings: General (Autopilot, platforms, watched folders), AI, Voice, Watermark, Music, Publishing and Advanced (Downloads, the engine, diagnostics)."
---

Open Settings with ⌘, (Ctrl+, on Windows). The status line at the top says whether everything is ready, and if not, the one thing to fix: the engine isn't running, an AI login expired, a download is missing, or a publishing account is signed out.

## General

- **Appearance**: language (the app's; captions and post copy keep each project's own language), light or dark theme, accent colour.
- **New projects**: **Autopilot** or **Ask me first**. See [Autopilot and Ask me first](/docs/app/autopilot/).
- **Platforms for new projects**: where your videos go by default. Home's platform chip can change it for one request.
- **Folders to look in**: All projects finds your work in these folders, and a new recording in one of them becomes a suggestion on Home.
- **Tidy up raw footage**: optional clean-up after delivery. You confirm every file, and it only goes to the Bin.
- **I make videos for other people**: adds clients to projects, delivery and numbers.
- The version and **Check for updates** (the App Store edition updates through the App Store). Optional usage counts are off unless you turn them on; see [Privacy: what Reelfold sends](/docs/concepts/usage-counts/).

## AI

The AI that plans and edits with you: your default, whether it is working, when it was last checked, and **Switch AI…**. Pick another AI for one request with the AI chip in the composer, or switch a project's AI on its page.

- **Sign in** to Claude Code or Codex (your browser opens; paste a code if asked), **Test**, **Sign out**.
- **Model**: the model of each provider, for example Opus 5.5 or Sonnet 5.5 for Claude Code.
- **Coding agents**: Gemini CLI, Cursor CLI, Copilot CLI, OpenCode, Qwen Code, Kimi CLI, CodeBuddy, iFlow and others you installed and signed in to, with whether each works in China and the install command of the others.
- **API keys**: DeepSeek, Qwen, Kimi, OpenAI, Anthropic and more. Kept in the system keychain; Reelfold only ever learns whether a key is set. Qwen, Kimi, GLM and Doubao keys have an **Endpoint**: Mainland China or International. A changed key needs an engine restart (the page offers it).
- **Models on this computer**: Ollama, LM Studio or vLLM, found when they run.
- **Change order**: which AI is tried next when the first doesn't answer. Reelfold tells you whenever it switches.
- **Advanced: a different AI for specific jobs**: planning, picking segments, captions, post copy, AI edit.

Details and troubleshooting: [AI providers](/docs/concepts/ai-providers/).

## Video generation

Shown when the Create page is on. Keys for video services such as Hedra (an optional AI presenter) live here, in the keychain. Paid generation always asks before it spends.

## Voice

The free voices that narrate your videos, offline on Apple silicon. **Chinese voice**: Qwen3-TTS (about 3 GB, downloaded once) with five voices to preview and pick, and a switch to use the older built-in Chinese voice until it is downloaded. **English voice**: Kokoro (about 330 MB). See [Voices](/docs/guides/voices/).

## Watermark

Your handle, your logo or a generated logo on every export. See [Watermark](/docs/guides/watermark/).

## Music

The CC0 music library every video's music is picked from: preview each track, mark it **Favourite** or **Never use**. Built-in beds fill in when nothing fits, and your own tracks in `~/Music/Reelfold` come first when they fit. See [Vlog › Music](/docs/guides/vlog/#music).

## Publishing

The accounts Reelfold publishes to. You sign in once (YouTube: with Google in your own browser); Reelfold never sees your password. Names and posting times are in Publish › Accounts.

- **YouTube**: sign in for the official YouTube Data API, and **Post scheduled videos automatically** (off by default).
- **Post automatically (official APIs)**: TikTok, X and Instagram, not yet.
- **Video length**: your own shortest and longest per platform.

See [Scheduling and publishing](/docs/guides/scheduling-publishing/).

## Advanced

You rarely need these.

- **Downloads**: fonts, face models, speech recognition and the free voice, each **Installed** or with **Download**, its size and whether it is required or optional. Downloads run in the background, resume if interrupted, and are checked before use. **Licences** lists each download's licence.

  | Download | Size | Needed for |
  |---|---|---|
  | Fonts and face models | about 62 MB | Captions, covers, face tracking, retouch |
  | Speech recognition (Whisper large-v3-turbo) | about 1.6 GB | Transcription |
  | Free voice (Kokoro, Apple silicon) | about 330 MB | English narration without an OpenAI key. See [Voices](/docs/guides/voices/) |
  | Chinese voice (Qwen3-TTS, offline; optional, Apple silicon) | about 3 GB | Chinese narration. Downloaded from Settings › Voice |
  | Music library (CC0, 52 tracks) | about 290 MB | Background music. See Settings › Music |
  | Designed covers and slides (optional browser, not in the App Store edition) | about 100 MB | HTML covers, slides, some workflows |

- **Engine**: the video engine in use (built into the app, or a folder you point at), the Python, the engine's data folder, **Restart the engine**.
- **Style defaults**: import a style file (fonts, brand colours, platform habits) or go back to the Reelfold default.
- **First-run setup**: walk through AI, downloads and platforms again.
- **Help and diagnostics**: **Copy diagnostic report** (versions, engine state and settings; no keys, passwords or video) and **Open the logs folder**.

## Related

- [Install the Mac app](/docs/start/install-mac/)
- [AI providers](/docs/concepts/ai-providers/)
- [Privacy](/docs/concepts/privacy/)
- [Editions: Mac, App Store, Windows](/docs/help/editions/)
