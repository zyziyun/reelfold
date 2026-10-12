---
title: Vertical versions of landscape footage
description: "How Reelfold makes 9:16 and 3:4 versions from landscape footage: Follow the subject crops shot by shot with a smooth camera, Fill with blur keeps the whole frame, and how to switch per video."
---

Landscape footage (a drone film, a travel vlog, a screen recording) has to fit a vertical screen for Shorts, TikTok, Reels, Douyin or Xiaohongshu. Reelfold does it one of two ways, and you can switch per video.

## Follow the subject (default)

Each shot is cropped around what matters in it: faces, people, moving things and vivid colour. The virtual camera is smooth: it holds still on a static shot, follows movement gently, and eases through crossfades instead of jumping. There is no blurred background.

A shot that can't be cropped well keeps the whole frame on a blurred fill instead, for example two subjects far apart, or a flat panorama with nothing to follow.

## Fill with blur

The whole frame, scaled to the width, over a blurred copy of itself. Nothing is cropped away. Good for wide scenery, text that runs to the edges, or when you want the original framing.

## Switch it

- On the clip page, under **On vertical screens**: **Follow the subject** or **Fill with blur**. The vertical versions are made again; the 16:9 version is not touched.
- Or ask the chat: "follow the subject", "fill with blur".
- On autopilot the choice is recorded in [What the AI decided](/docs/app/autopilot/#what-the-ai-decided) ("Vertical versions follow the subject") and can be changed there.

This also works for projects made before the setting existed: what the clip has now is read from its exports.

## With the Claude Code skill or a terminal

```bash
python -m vstudio.project remake --dir <project> --item <item> --do framing=follow
python -m vstudio.project remake --dir <project> --item <item> --do framing=blur
```

Only the vertical exports are made again; no other step runs. Talking-head videos use their own face-tracked reframing; see [Talking-head shorts](/docs/guides/talking-head/).

## Related

- [Travel vlogs](/docs/guides/vlog/)
- [One master, many platforms](/docs/guides/multi-platform/)
- [Edit a finished clip](/docs/app/clip-page/)
- [Platforms reference](/docs/reference/platforms/)
