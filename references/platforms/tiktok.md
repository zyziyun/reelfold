---
platform: tiktok
label: TikTok
form: short
lengths:
  history: [30, 60, 90]
  essay: [20, 45, 90]
  film: [15, 30, 60]
  photos: [15, 25, 60]
  reel: [20, 25, 45]
  vlog: [20, 45, 90]
  talking_head: [30, 60, 90]
  course: [45, 75, 90]
aspects: ['9:16']
chapters: {use: false}
captions: {style: burned, density: phrase, note: keep clear of the right button column and bottom 25 %}
title: {max: 55, habit: the caption is the hook line; 1 sentence + 3-5 hashtags}
hook: 'the first 1-2 s decide it: start mid-action, text on screen at 0:00'
hashtags:
  count: [3, 5]
  where: caption
  note: specific > generic
cover: {size: 1080x1920, habit: 'a frame with the subject centred; the grid crops to 3:4'}
posting:
  times: ['Tue-Thu 18:00-22:00 local']
  cadence: daily if you can
  note: convention
---
# TikTok

Uploads can be long, but the feed habit is 15-90 s; a story over 60 s needs a reason to keep watching.

Lengths are seconds per content kind: [min, target, max]. Kinds: history (narrated explainer of a place), essay (reflective voice-over), film (music film), photos (photo story), reel (beat-cut short), vlog, talking_head, course. Numbers are conventions (the platform's habits), not limits - the hard limits live in lib/vstudio/platform.py. Override them per platform in Settings > Publishing or persona.local.yaml (platforms.<name>.lengths / platforms.<name>.limits).

The front matter above is the source of truth: the engine reads it (vstudio.platform_habits); edit it to change this platform's habits.

## Publishing from Reelfold

This build uses assisted browser upload; the official TikTok adapter is not connected yet. A successful file
transfer or a filled form does not establish that a post is published. Keep the creator's publication step and
TikTok's processing result visible.

The official APIs have distinct outcomes:

- **Upload to inbox** requires an approved `video.upload` scope and the creator's authorization. The creator
  opens the inbox notification in TikTok to finish editing and post. Report this as a draft awaiting the creator.
- **Direct Post** requires `video.publish` and an API-client audit for public visibility. Fetch current creator
  information, validate duration, and let the creator explicitly choose privacy and interactions. Do not infer
  these choices from Autopilot or copy settings from another platform. Show the preview and editable copy before
  consent to transfer. Follow status updates before reporting delivery.

Direct Post clients must serve a wider creator audience; a private utility for the developer's own accounts is
not an acceptable intended use. Check app-added promotional branding against TikTok's watermark guidelines;
prepare a suitable export with the creator rather than silently removing branding from an existing video.

See TikTok's [Upload guide](https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content)
and [Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines).
