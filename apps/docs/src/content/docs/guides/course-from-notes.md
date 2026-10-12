---
title: Course videos from notes
description: "Turn lecture notes, a document or a Notion page into narrated course episodes with Reelfold: a drafted script, AI-drawn scenes, a voice, captions, and Redo the visuals or Redraw one scene afterwards."
---

You have notes, not footage: a lecture outline, a document, a Notion page. Reelfold drafts an episode from them for the length you ask, narrates it, draws every scene as a diagram or animation, adds captions and exports it per platform. No recording is needed.

<!-- SCREENSHOT PLACEHOLDER: a finished course episode's clip page with Redo the visuals (re-captured in apps/site). -->

## Before you start

- **Your notes**: a file (Markdown, text or another document), a public Notion page link, or an exported Notion folder. Links are read first.
- **An AI model** connected in Settings › AI. The scenes are drawn by your AI (Claude Code, Codex, an API key or a local model); without one the visuals can't be made. See [AI providers](/docs/concepts/ai-providers/).
- **A voice**: the free voice on Apple silicon, an OpenAI key, or your own. See [Voices for narration](/docs/guides/voices/).

## Make an episode

1. On Home, describe it and add the notes:

   > Make a 6-minute course video from these notes about MCP, in Chinese, for YouTube and Bilibili.

   or

   > Turn this Notion page into a 90-second vertical explainer for Shorts and TikTok.

2. **Make it.** Your notes are read in full and drafted into an episode for the length you asked: one idea per scene, your examples and analogies kept, stage directions cut. Your notes stay as they are; they are not locked in as the script. With no model, a simple rules draft is made and labelled as such.
3. **Script.** On autopilot the draft is used. With **Ask me first** you check it under **Lock the script**.
4. **Voice.** The narration is read, transcribed and compared with the script. A missing sentence is read again.
5. **Visuals.** Each scene is drawn by the AI as a diagram or animation timed to the voice. Every scene is checked before it is kept: it must play inside the video, without loading anything from the internet, and draw rather than put sentences on screen.
6. **Captions and export.** Captions follow the narration (Chinese narration gets Chinese captions, with English optional). One version per platform, with a cover and post copy.

**Chinese narration** works end to end: voice, checks, captions and timing. English terms inside it are read in English; see [Voices](/docs/guides/voices/#english-terms-in-mandarin-narration).

## Redo the visuals

If the scenes look too plain or don't fit, redo them without touching the voice:

- On the clip or project page, press **Redo the visuals**, or
- Ask the chat: "the visuals are too plain", "redo the visuals", "more diagrams".

Every scene is drawn again by your AI, then the video is rendered and exported again. The voice and captions stay.

### When one scene can't be redrawn

A scene that fails its check is repaired with the exact problem and tried again. If it still fails, it keeps its old version (or a simple diagram for now) while the others are redrawn, and the page says so: "13 of 14 scenes redrawn; scene 14 kept as before", with **Redraw scene 14**.

If a redo stops entirely, your video is unchanged and stays Ready to post. The notice names the scene and why, for example "the AI kept loading data from the internet, which a video can't do". **Try again** draws only the scenes still missing.

## When it stops

| Message | What to do |
|---|---|
| The visuals need an AI model — Claude Code didn't answer | Try again, or choose another model in Settings › AI. The project waits in Needs you; it never renders a text-only video |
| The script wasn't written in scenes yet — it was still your notes | **Try again**: Reelfold drafts the scenes from your notes |
| The voice kept leaving out a sentence in scene N | Reword or split that sentence. See [Voices](/docs/guides/voices/#when-the-voice-stops) |
| The free voice isn't downloaded on this computer yet | **Download the free voice** (about 330 MB), then Try again |

## With the Claude Code skill or a terminal

The recipe is `explainer` ([workflow reference](/docs/reference/workflows/explainer/)). To redo the visuals of a finished item:

```bash
python -m vstudio.project remake --dir <project> --item <item> --do visuals            # every scene again
python -m vstudio.project remake --dir <project> --item <item> --do visuals=missing    # only the scenes kept as before
```

## Related

- [Explainers](/docs/guides/explainer/)
- [Voices for narration](/docs/guides/voices/)
- [Cut a course into a series](/docs/guides/course-slicing/) (from recordings)
- [Edit a finished clip](/docs/app/clip-page/)
