---
title: Voices for narration
description: "How Reelfold picks a narration voice (your persona's, OpenAI with a key, or the free offline Kokoro voice on Apple silicon), how English terms are read in Mandarin narration, and tips for rare words."
---

Explainers, course videos and AI shorts are narrated by a voice. Reelfold picks one this computer can actually use, so a video never stops because a paid voice has no key.

## Which voice is used

In order:

1. **Your persona's voice**, if you set one (`tts.engine` in `persona.local.yaml`, for example your own cloned voice).
2. **OpenAI** (`gpt-4o-mini-tts`), only when an OpenAI key is set in Settings › AI. About $0.015 per minute of narration.
3. **The free voice**: Kokoro, which runs offline on this Mac (Apple silicon). Mandarin narration uses `zf_xiaobei`; English uses `af_heart`, with `am_michael` and `bf_emma` as alternatives.

On autopilot, a project set to OpenAI with no key uses the free voice and says so in [What the AI decided](/docs/app/autopilot/#what-the-ai-decided). With **Ask me first** it asks: **Use the free voice** or **Add your OpenAI key**. With no free voice either, it asks for the key.

## The free voice download

The free voice is a one-time download of about 330 MB. It starts the first time a video needs it, or from Settings › Advanced › **Downloads**. Until it is there, the voice step says "The free voice isn't downloaded on this computer yet" with **Download the free voice**; press **Try again** when the download is done.

It works offline and in the Mac App Store edition. Intel Macs and Windows don't have it: narration there needs an OpenAI key (or another voice you set in the persona).

## English terms in Mandarin narration

A Chinese course is full of English terms: MCP, API, Tool Calling, USB-C. The free Mandarin voice reads Chinese as Chinese and each run of English as English:

- **Acronyms** in capitals are read letter by letter: "MCP" is M-C-P.
- **Words** it knows are read as words: "Tool Calling", "server".
- **CamelCase** names are read in their pieces: "LangChain" is Lang Chain, "OpenAI" is Open A I.
- A word it doesn't know at all is spelled out rather than skipped.
- Numbers on their own stay with the Chinese and are read in Chinese.

## Tips for rare words and long sentences

- **If a rare word is misread, reword the sentence** or use a more common word. Writing the word the way it sounds also works, but the captions follow the script, so they will show that spelling too.
- **Write acronyms in capitals** when they should be spelled out ("API", not "Api").
- **Spell numbers the way they should be spoken** in English narration ("zero point five one", "F P thirty-two"); captions turn them back into digits.
- **Keep sentences short.** A very long sentence is split to fit what the voice can read in one breath. If the voice still leaves something out, Reelfold says which scene and which sentence (see below).

## When the voice stops

Every take is transcribed and compared with the script. A take that drops a sentence is made again, and a line that keeps failing is tried in two halves. If it still fails, the run stops with a plain message:

| Message | What to do |
|---|---|
| The voice kept leaving out a sentence in scene N: "…" | Reword or split that sentence in the script, then **Try again** |
| The voice could not read scene N, even in two halves: "…" | Same: simpler wording, shorter sentences, a rare word written as it sounds |
| There's no OpenAI key in Reelfold, so this step couldn't run | **Use the free voice**, or add the key in Settings › AI |

## With the Claude Code skill

```yaml
# persona.local.yaml
tts:
  engine: kokoro        # or openai, clone, edge, openai-compatible, elevenlabs
```

`tts_engine: auto` (the default) follows the same order as the app. Your own cloned voice (`tts.clone`, Qwen3-TTS on Apple silicon) also reads English terms inside Chinese. Engine details: [Sound](/docs/reference/engine/sound/).

## Related

- [Course videos from notes](/docs/guides/course-from-notes/)
- [Explainers](/docs/guides/explainer/)
- [Settings](/docs/app/settings/)
- [Troubleshooting](/docs/help/troubleshooting/)
