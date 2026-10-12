---
title: Project chat and clip chat
description: "What you can ask Reelfold's chat on a project or a clip: pause, go on, change the music, re-cut, redo the visuals, follow the subject, rewrite the post copy, and plain-language edits with Undo."
---

Every project page and every clip has a chat beside it (**Ask AI**). Say what you want in your own words, in any language. The chat answers with change cards you can apply, compare and undo, or it acts on the run directly. It folds away and can be resized.

## Project chat

On a project that is running, ready, or open in Details, the chat controls the run itself:

| Say | What happens |
|---|---|
| "Pause it" | The run stops at a safe point. Nothing made so far is lost |
| "Go on" | It continues from where it paused |
| "Change the music" / **Other music** | It goes back to the music step and asks you there (Needs you); everything else is kept |
| "Pick another cover" | The same, for the cover |
| "Cut it again" / **Cut it again** | It goes back to the cut and asks you there |
| "1.1× on every clip", "remove the series label from all of them" | One change card per clip; **Apply to all** or one at a time |

The scope switch above the box chooses which clips a request changes: **All** or **Only** one clip. You can also ask several projects at once from [All projects](/docs/app/all-projects/) with **Change with AI…**.

If nothing is made yet, the chat says what it can do now: pause the run, pick the music or the cover again, or cut it again.

## Clip chat

On a finished clip, the chat edits that clip. Changes apply at once, each with **Undo** (a setting brings back "Ask before applying AI edits"). Typical requests:

- **Timing**: "start at 'so the trick is'", "tighter", "trim the first two seconds", "speed 1.1×".
- **Captions**: "bigger captions", "yellow keywords", "pop the word 'free'", "captions at the top".
- **Versions**: "a Douyin version", "add a 16:9 for YouTube", "drop the 3:4".
- **Cover**: "a new cover", "a calmer cover".
- **Vertical framing**: "follow the subject" or "fill with blur" makes the vertical versions again. See [Vertical versions](/docs/guides/vertical-reframe/).
- **Post copy**: "rewrite the post copy" writes each platform's title, text and hashtags again in that platform's language. See [Post copy per platform](/docs/guides/post-copy/).
- **Visuals of an explainer**: "the visuals are too plain", "redo the visuals", "more diagrams". Every scene is drawn again by the AI and rendered again; the voice and captions stay. See [Course videos from notes](/docs/guides/course-from-notes/#redo-the-visuals).

Type **/** for tools (trim, captions, effects, cover, export) if you would rather do it by hand.

A request that the clip cannot take says why. For example, captions that are burned into the picture of a finished file can be added to but not restyled, and a remake waits while the project is still making something.

## When there is no model, or it doesn't answer

The chat needs an AI model to understand free text. Simple phrases ("tighter", "new cover", "Douyin version", "start at '…'", "pop '…'") work without one.

- **No model** / "No AI model connected": nothing is connected. Press **Connect a model** (Claude Code, Codex, an API key or a local model). See [AI providers](/docs/concepts/ai-providers/).
- "The model didn't answer this time": a model is connected but did not reply. The reason is named:
  - it did not answer within the time limit and is still connected: **Try again** (it gets more time; a CLI model in the clip chat has 180 s);
  - its login expired: sign in again in Settings › AI;
  - it could not answer this time.

If you set a backup, Reelfold tries it and tells you ("Claude Code didn't answer within 120 s, so Codex was used this time").

## Related

- [Edit a finished clip](/docs/app/clip-page/)
- [Output edits](/docs/concepts/output-edits/)
- [The live run page](/docs/app/live-run/)
- [AI providers](/docs/concepts/ai-providers/)
