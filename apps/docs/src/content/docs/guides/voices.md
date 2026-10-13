---
title: Voices for narration
description: "How Reelfold picks a narration voice (your persona's, OpenAI with a key, or the free offline voices on Apple silicon: Kokoro for English, Qwen3-TTS for Chinese), how English terms are read in Mandarin narration, and tips for rare words."
---

Explainers, course videos and AI shorts are narrated by a voice. Reelfold picks one this computer can actually use, so a video never stops because a paid voice has no key.

## Which voice is used

In order:

1. **Your persona's voice**, if you set one (`tts.engine` in `persona.local.yaml`, for example your own cloned voice).
2. **OpenAI** (`gpt-4o-mini-tts`), only when an OpenAI key is set in Settings › AI. About $0.015 per minute of narration.
3. **The free voices**, which run offline on this Mac (Apple silicon). English uses Kokoro (`af_heart`, with `am_michael` and `bf_emma` as alternatives). Chinese uses Qwen3-TTS once you have downloaded it (see below).

On autopilot, a project set to OpenAI with no key uses the free voice and says so in [What the AI decided](/docs/app/autopilot/#what-the-ai-decided). With **Ask me first** it asks: **Use the free voice** or **Add your OpenAI key**. With no free voice either, it asks for the key.

## The free voice download

The free English voice (Kokoro) is a one-time download of about 330 MB. It starts the first time a video needs it, or from Settings › Advanced › **Downloads**. Until it is there, the voice step says "The free voice isn't downloaded on this computer yet" with **Download the free voice**; press **Try again** when the download is done.

The free voices work offline and in the Mac App Store edition. Intel Macs and Windows don't have them: narration there needs an OpenAI key (or another voice you set in the persona).

## The free Chinese voice

Chinese versions are narrated by Qwen3-TTS (Apache-2.0), an optional one-time download of about 3 GB in Settings › **Voice** › **Chinese voice**. It reads tones and English terms naturally. You pick one of five voices there, and you can listen to each before downloading:

| Voice | Sound |
|---|---|
| Serena | Warm and calm (the default) |
| Vivian | Bright and young |
| Uncle Fu | Mature, low male voice |
| Dylan | Male, Beijing accent |
| Eric | Male, Sichuan accent |

Once it is downloaded, it narrates every Chinese version. Until then:

- Chinese versions use **English narration with Chinese subtitles**. When you ask for a Chinese version, the plan card says so and offers **Download the Chinese voice**; versions written after the download finishes are narrated in Chinese.
- The older built-in Mandarin voice (Kokoro, `zf_xiaobei`) is off by default because it sounds robotic. To use it until Qwen3-TTS is downloaded, turn on **Use the built-in Chinese voice until then** in Settings › Voice. Once Qwen3-TTS is there, it is always used.

With an OpenAI key, narration uses OpenAI's voices instead, in Chinese too.

## English terms in Mandarin narration

A Chinese course is full of English terms: MCP, API, Tool Calling, USB-C. Qwen3-TTS reads them by itself, with no dictionary. The older built-in Mandarin voice (Kokoro), if you turned it on, reads Chinese as Chinese and each run of English as English:

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
  engine: kokoro        # or qwen, openai, clone, edge, openai-compatible, elevenlabs
  zh_local: true        # optional: Kokoro's Mandarin voice until Qwen3-TTS is downloaded
```

`tts_engine: auto` (the default) follows the same order as the app; a Chinese line on the free voice goes to Qwen3-TTS when it is installed. Your own cloned voice (`tts.clone`, Qwen3-TTS on Apple silicon) also reads English terms inside Chinese. Engine details: [Sound](/docs/reference/engine/sound/).

## Related

- [Course videos from notes](/docs/guides/course-from-notes/)
- [Explainers](/docs/guides/explainer/)
- [Settings](/docs/app/settings/)
- [Troubleshooting](/docs/help/troubleshooting/)
