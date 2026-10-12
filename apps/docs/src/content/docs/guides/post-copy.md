---
title: Post copy per platform
description: "How Reelfold writes a title, text and hashtags for each platform within its limits and in the right language (publish.copy_lang), and how to rewrite the post copy of a finished video."
---

Every finished video comes with post copy for each platform you chose: a title, the post text and hashtags, each within that platform's limits. For videos without speech (vlogs, drone films, photo stories) it is written from the facts: the place, the month, your words, your title and the music.

## What is in it

| Part | Notes |
|---|---|
| Title | Fitted to the platform's limit (for example YouTube 100, Bilibili 80, Douyin 30, Xiaohongshu 20). A title over the limit is marked, never cut |
| Text | A few lines; a longer description on YouTube. No hashtags inside the text |
| Hashtags | Only when relevant, within the platform's tag count |
| Place | Offline, from DJI flight logs when the footage has them |
| Music credit | Added when the track asks for one (for example a CC BY track) |

Your own title is kept on the platforms in its language. The copy is written by your AI when one is connected, checked, and any missing part is filled by the rules. With no model, the rules write it from the facts and say so. Both drafts are kept, so on autopilot it is a decision you can change ("Post copy written by the AI" or "Post copy written from the facts").

## Which language

- **International platforms** (YouTube, TikTok, X, Instagram): your persona's language, English by default.
- **Chinese platforms** (Xiaohongshu, Douyin, Bilibili): the language of your request. A request in Chinese gets Chinese copy there.

Change it in `persona.local.yaml`:

```yaml
publish:
  copy_lang: {intl: en}          # YouTube / TikTok / X / Instagram
  # copy_lang: {intl: fr, tiktok: zh}   # or per platform
```

## Rewrite the post copy

On the clip page, press **Rewrite post copy**, or ask the chat "rewrite the post copy". Each platform's title, text and hashtags are written again in its language; each version's post text is replaced when it is done.

From a terminal:

```bash
python -m vstudio.project remake --dir <project> --item <item> --do copy
```

## Related

- [Scheduling and publishing](/docs/guides/scheduling-publishing/)
- [Travel vlogs](/docs/guides/vlog/)
- [Platforms reference](/docs/reference/platforms/)
- [Persona reference](/docs/reference/persona/)
