---
title: Vlog
description: Edit travel, drone or phone clips into a calm cinematic vlog or a fast beat-cut travel reel, with grading, transitions, music, sound effects and a cover.
---

You get one polished vlog from a pile of clips: either **calm** (graded, gently sped up, long crossfades, music laid underneath) or **fun** (cut to the beat, speed ramps and slow-mo, zoom punches, text pops, a route map, sound effects, and your talking-to-camera bits captioned over a ducked music bed). Both come with a cover.

![Contact sheet of a fun travel vlog on a vertical canvas: a title pop, DAY stamps, location tags, a route map card, photo cards, a glitch frame and an end card](../../../assets/shots/fun-vlog.jpg)

## Pick a style

| | Calm | Fun |
|---|---|---|
| Feel | Slow crossfades, long holds, ambience, music laid on after | Cut to the beat, speed ramps, zoom punches, text pops, sound effects |
| Footage | Drone, nature, walks; long smooth takes | Trips with many places, people, food, action; 60/120 fps clips; photos |
| Sound | Silent or ambient master, music added on top | Music-led: bed, sound effects, and speech clips with the music ducked under them |
| Length | 1 to 5 minutes, often horizontal 4K | 20 to 90 seconds, vertical first, also YouTube |
| Say | "calm", "cinematic", "slow", "healing" | "beat-cut", "fast", "fun travel reel" |

## Before you start

- **Your clips**, any size, landscape or portrait, SDR or iPhone HDR, 24 to 120 fps. Photos work too, mostly in the fun style.
- **Music**: nothing to bring. Describe the vibe in your own words and Reelfold picks a track from its music library (see [Music](#music)). For fun, you can also bring a track with a clear beat that you have the rights to.
- **Places and days**, if you want location tags, day stamps or a map.

If the video is mostly you talking, use [Talking-head shorts](/docs/guides/talking-head/) instead. A few talking-to-camera clips in a vlog are fine.

## In the Mac app

1. On Home, describe the vlog and add the clips. Say calm or fun and the platform.
2. The **plan** shows the style, the platform and the title.
3. **Windows and pacing.** Reelfold makes contact sheets of every clip (one tile every 4 seconds) so nothing is edited blind. The good windows, the order, the music, the title and the map go into one edit list. Ask the agent to draft it, then adjust.
4. The **batch** renders on your Mac. For the fun style it also writes a report: every cut with its beat check, transitions, overlays, the sound effects cue sheet and loudness.
5. **Pick the cover.**
6. Review and publish.

## With the Claude Code skill

Hand Claude the footage folder and say calm or fun. The skill follows `workflows/vlog`: it probes every clip, reads the contact sheets, writes `work/edit.json`, and renders. For fun it does a dry run first so you can read the plan.

```bash
python3 $VSTUDIO/workflows/vlog/scripts/probe.py footage/* --init work/edit.json --style fun \
    --music music/track.mp3 --platform xiaohongshu:full
python3 $VSTUDIO/workflows/vlog/scripts/build_fun.py work/edit.json --dry-run
```

## Music

Reelfold has a built-in music library of 52 real tracks, all CC0 or public domain (from FreePD.com and Musopen): free in published videos, no credit needed. It downloads on first run; until it is there, videos use built-in beds that Reelfold makes on your Mac.

- **Picked to fit.** Each video's track is chosen for its mood and style from your words (piano, acoustic, cinematic, electronic, lo-fi, documentary, Chinese style …) and for the edit's pace. A fun reel gets a track with a steady tempo, and its tempo sets the cut budget.
- **No repeats.** Videos made together (a goal, or one request's videos) never share a track until the library runs out, and the tracks of your last few videos are pushed down.
- **Settings › Music** lists the library with a preview of each track, its BPM and licence. Mark a track **Favourite**, or **Never use** to keep it out.
- **Your own music.** Tracks you have the rights to in `~/Music/Reelfold` come first when they fit. A CC BY track's credit goes into every platform's post copy.

On autopilot the top-ranked track is taken (a decision you can change); with **Ask me first** you get the list. Changing a fun reel's track re-cuts the reel.

## What each style does

**Calm.** HDR clips tone-mapped, a gentle grade, shots matched in colour (each shot's white balance and tint move toward the film's reference shot, so colour doesn't jump at a cut), a speed per segment (scenery a little faster than subject shots), stabilise where it's shaky, crossfades with no black first frame and a fade-out at the end. Music is looped to fit, faded and normalised; with ambient sound kept, the place's sound sits under the music. The cover is a torn-paper scrapbook collage.

**Fun.** The music is analysed first: Beat This! (once its model is downloaded) finds its beats and bars, and the cuts land on them. The edit opens on a hook of the best moments, then a title pop, then your shots in order, with a cut exactly on the music drop, then an accelerating finale and a slow outro. On top:

- speed ramps, true slow-mo from 120 fps clips, freeze-frames into a photo card;
- transitions: a straight cut on the beat by default, with zoom punches on the big hits. Whips, flashes, light leaks and a glitch are off by default because they read as strobing; ask for them ("expressive transitions"), or ask for one on a single shot;
- text: title pop, location tags, DAY stamps, date stamps, word pops, a route map card, an end card, all inside the platform's safe area and never overlapping;
- sound effects (synthesised, nothing to license): whooshes on whips, impacts on drops, a riser into the finale, shutters on photos;
- speech clips: kept at 1×, cleaned of hesitations and long pauses, captioned, with the music ducked under them.

A version without music ships too, as a stem for re-scoring.

## Options worth knowing

| Option | Style | What it does |
|---|---|---|
| Platform | both | Sets canvas, fps, safe area, caption box and loudness. Default 小红书 9:16. |
| Grade, brightness | both | "Too dark" raises brightness, never adds a vignette. |
| Colour match, film look | calm | Colour match is on by default. A film look (`grade_look` in the edit list) is optional: Cinema neutral, Kodak 2383 soft, Portra warm, Fuji cool, Silver mono or Soft bleach, mixed in at 35 %. |
| Transitions | fun | Clean (default: cuts and zoom punches) or expressive (whips, flashes, light leaks, a glitch). |
| Segment speed | calm | Per segment; persona defaults for subject and scenery shots. |
| Pace | fun | `fast` or `relaxed` (double length). |
| Music start, drops | fun | Where the music starts, and where the big cuts land. |
| Map, title, end card, word pops | fun | Turn each on or off. |
| Sound effects | fun | On by default; `sfx: false` turns them off. |
| Music level, duck amount | fun | Lower the bed, or duck it harder under speech. |
| Speech cleanup | both | Fun: gentle, automatic edits only by default. Calm: opt-in per segment. |

## Example prompts

- "Cut these drone clips into a calm 3-minute 4K vlog with soft music and a cover."
- "Fun travel reel for Xiaohongshu from this Tokyo trip, cut to this track. Add a map of the cities and a DAY stamp for each day."
- "Slow-mo the jump at the beach and put a whip into the night market."
- "Different music: something with piano, less upbeat."
- "Too fast. Make it relaxed and turn the music down under my talking bits."

## Related

- [Sound reference](/docs/reference/engine/sound/)
- [Aesthetics reference](/docs/reference/engine/aesthetics/)
- [Photo story](/docs/guides/photo-story/)
- [Covers](/docs/guides/covers/)
- [One master, many platforms](/docs/guides/multi-platform/)
- [vlog workflow reference](/docs/reference/workflows/vlog/)
- [Examples](/docs/examples/)
