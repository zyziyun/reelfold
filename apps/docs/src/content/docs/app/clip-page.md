---
title: Edit a finished clip
description: "Open a ready clip in Reelfold: change its cover, captions and versions, switch vertical framing, rewrite the post copy, redo an explainer's visuals, edit by transcript or timeline, and export to editing software."
---

A clip that is **Ready to post** has its own page: the player, then everything about the clip beside it, with the chat on the right. Clicking a ready clip (or one of its versions) on a project page opens the editor.

<!-- SCREENSHOT PLACEHOLDER: a ready clip's page: player, cover row, captions, versions, post (re-captured in apps/site). -->

## The clip page

- **Title**: the AI's title by default. Click it to edit; the post titles follow it.
- **Cover**: pick one of the suggested frames, or **Use the frame on screen**. The title goes on it.
- **Captions**: the look (**Clean**, **Bold outline**, **Box**), the position and the **Keyword colour**. If the captions are part of the picture in this clip (a finished file with no clean master), their look stays as it is.
- **Versions**: one switcher for every version of the clip, grouped by language, for example **YouTube 16:9** and **Shorts · TikTok 9:16** in English, and, for a video made in two languages, its Chinese **Xiaohongshu 3:4** and **Bilibili 16:9**. Click one to play that file in the player at once (selecting never renders). Under the row: the platforms that post it, its post copy, **Show in Finder** and **Export…**. A size the clip doesn't have yet is offered as **Make the … version**, made in the background.
- **On vertical screens**: **Follow the subject** or **Fill with blur**, for landscape footage made into vertical versions. Changing it makes the vertical versions again. See [Vertical versions](/docs/guides/vertical-reframe/).
- **Rewrite post copy**: each platform's title, text and hashtags written again in its language. See [Post copy per platform](/docs/guides/post-copy/).
- **Redo the visuals** (explainers): every scene drawn again by the AI and rendered again, the voice and captions kept. See [Course videos from notes](/docs/guides/course-from-notes/#redo-the-visuals).
- **Post**: per-platform copy, **Schedule**, or **Export file**. Reelfold fills in each upload page (YouTube: its publish form); you press Publish.

Changes to the cover, captions and versions re-render in the background ("Updating the video · 40%"). Publishing always uses the edited clip. If an update stops, the clip keeps its last good video and offers **Try again**.

## The editor

The editor opens on the **Transcript** when the clip has speech, and on the **Timeline** when it has none (a vlog with music, a photo story, a drone film). Both are there in either case.

- **Transcript**: select words and press Delete to cut them; cuts snap to word edges. The chips **Fillers**, **Pauses** and **Typos** find every filler word, every pause over 0.6 s and every word the transcription was unsure of; remove them one by one or all at once. **Fix text** changes only the caption, not the sound.
- **Timeline**: the video, the effects and the audio on tracks. Select a span and tell the chat what to do with it, or trim with the edges. The **Shots** lane shows each shot of the cut with the take it plays; click one to see why it is cut that way and pick another take. AI-generated shots are marked **AI**.
- **Pickups**: select words and **Re-record** (R) or **Add after** (⇧R). Your camera opens, you say the line again, and it is put in with the loudness and room tone matched.
- **Export**: pick the platforms; each gets its own version, captions inside its safe area, loudness at its target, and your [watermark](/docs/guides/watermark/) unless you untick it for this video.

Every edit is one Undo step (⌘Z).

## Your edits survive the AI

What you change by hand (caption text and style, effects and where they sit, the title, the cover, start and end, speed) is kept when the AI edits the clip, when you ask the whole project something, and when the video is made again. The AI is told about your edits and leaves them unless you point at or name that part. They are listed under **Your edits the AI keeps**, each with **Reset to AI version**.

## Export for editing software

To keep cutting in another editor, choose **Export for editing software…** on the clip's Export card (or for every clip of a project):

| Format | For |
|---|---|
| **Premiere Pro / DaVinci Resolve** | An XML timeline (FCP7 XML); captions as an SRT next to it |
| **CapCut** / **剪映 (Jianying)** | A draft that shows on the app's home screen, captions as a text track |
| **OpenTimelineIO** | Resolve and other editors that read `.otio` |

Every cut, the speed, the sound levels and the music bed come along, pointing at the clip's own media. Tick **Copy the media next to it** to get one folder to hand to an editor. What an editor can't be told (overlays, the title band, transitions) is listed in `README.txt`.

## Related

- [Project chat and clip chat](/docs/app/chat/)
- [Output edits](/docs/concepts/output-edits/)
- [Covers and thumbnails](/docs/guides/covers/)
- [Scheduling and publishing](/docs/guides/scheduling-publishing/)
