---
title: Settings
description: "A tour of Reelfold's Settings: General (Autopilot, platforms, watched folders), AI, Watermark, Publishing and Advanced (Downloads, the engine, diagnostics)."
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

The AI that plans and edits with you: which one is working, when it was last checked, and **Switch AI…**.

- **Sign in** to Claude Code or Codex (your browser opens; paste a code if asked), **Test**, **Sign out**.
- **API keys**: DeepSeek, Qwen, Kimi, OpenAI, Anthropic and more. Kept in the system keychain; Reelfold only ever learns whether a key is set. A changed key needs an engine restart (the page offers it).
- **Models on this computer**: Ollama, LM Studio or vLLM, found when they run.
- **Change order**: which AI is tried next when the first doesn't answer. Reelfold tells you whenever it switches.
- **Different AI for specific jobs**: planning, picking segments, captions, post copy, AI edit.

Details and troubleshooting: [AI providers](/docs/concepts/ai-providers/).

## Video generation

Shown when the Create page is on. Keys for video services such as Hedra (an optional AI presenter) live here, in the keychain. Paid generation always asks before it spends.

## Watermark

Your handle, your logo or a generated logo on every export. See [Watermark](/docs/guides/watermark/).

## Publishing

The accounts Reelfold publishes to. You sign in once inside Reelfold; it never sees your password. Names and posting times are in Publish › Accounts. See [Scheduling and publishing](/docs/guides/scheduling-publishing/).

## Advanced

You rarely need these.

- **Downloads**: fonts, face models, speech recognition and the free voice, each **Installed** or with **Download**, its size and whether it is required or optional. Downloads run in the background, resume if interrupted, and are checked before use. **Licences** lists each download's licence.

  | Download | Size | Needed for |
  |---|---|---|
  | Fonts and face models | about 62 MB | Captions, covers, face tracking, retouch |
  | Speech recognition (Whisper large-v3-turbo) | about 1.6 GB | Transcription |
  | Free voice (Kokoro, Apple silicon) | about 330 MB | Narration without an OpenAI key. See [Voices](/docs/guides/voices/) |
  | Chromium (optional, not in the App Store edition) | 100–120 MB | HTML covers, slides, some workflows |

- **Engine**: the video engine in use (built into the app, or a folder you point at), the Python, the engine's data folder, **Restart the engine**.
- **Style defaults**: import a style file (fonts, brand colours, platform habits) or go back to the Reelfold default.
- **First-run setup**: walk through AI, downloads and platforms again.
- **Help and diagnostics**: **Copy diagnostic report** (versions, engine state and settings; no keys, passwords or video) and **Open the logs folder**.

## Related

- [Install the Mac app](/docs/start/install-mac/)
- [AI providers](/docs/concepts/ai-providers/)
- [Privacy](/docs/concepts/privacy/)
- [Editions: Mac, App Store, Windows](/docs/help/editions/)
