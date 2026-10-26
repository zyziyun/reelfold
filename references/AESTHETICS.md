# Aesthetics checklist

Go through this list before delivering any cut. Report each rule as `A3 ✓` or `A3 ✗ (where: shot /
timestamp)`. Breaking a rule on purpose is fine, but write down which rule you broke and why in
the project notes.

The rules cover product promos, vlogs and talking-heads. Audio rules live in [SOUND.md](SOUND.md).

## Premium by default (footage films: drone, travel, landscape, history over aerials)

The 2026-10-12 review of six DJI films: "有点俗气，不够高端大气", "屏闪有点厉害", "中文的语音太难听". What a premium
travel / documentary film looks like, and what the engine now does by default (each one configurable):

**P1. No flicker, ever.** No white flashes, dips through black, light leaks, glitches or whips between shots;
dissolves (0.8 s on aerials) or hard cuts on the beat. Spoken captions switch at their exact cue boundaries; do not crossfade different words at the same
position or extend them into silence. The shade behind them eases in and out independently. Every render is measured by `vstudio.flicker` (flash / blink /
max luma jump) and fails on a flicker (`qc.flicker: fail | warn | off`, persona or recipe config).
*Engine:* vlog `transition` dips -> fade (`allow_dips` to keep), fun reel `transitions: clean` (default; `expressive`
restores flash / leak / glitch / whip), photo-story `LOOK = "cinema"` maps every transition to fade / cut.

**P2. Even motion.** A clip plays at a speed whose frame cadence is even: 60p at 1x or 0.5x, 30p at 1x
(`ffmpeg_filters.retime`; any other speed is resampled with frame blending, never nearest-frame drops that judder an
aerial pan). Default calm speed is 1.0 (was 1.2 / 1.3).

**P3. Matched, restrained grade.** Contrast 1.04, saturation 1.04, no sharpen (a sharpened 4K -> 1080 downscale
makes city lights and water shimmer), `deflicker` evens out the drone's exposure pumping inside a clip, and each
segment's brightness is pulled 60 % toward the film's median (max +-0.06) so no cut jumps in exposure
(`match_exposure`), and each shot's colour (white balance, tint, saturation) 60 % toward the film's reference shot
(`vstudio.colormatch`: MKL chroma + Reinhard luma, capped, one LUT per shot). A film look at 35 % at most
(`cinema-neutral` by default in the cinema look; `kodak-2383-soft`, `portra-warm`, `fuji-cool`, `mono-silver`,
`bleach-soft`). No orange-and-teal push, no vignette.

**P4. Cinematic pacing.** Hold the beautiful aerials: 7-14 s windows (10-14 s on the best ones), motivated cuts on
the music's bars, wide -> closer, the light changing from shot to shot. Fewer, longer shots beat many short ones.
Never a long dissolve between two framings of the same subject (it shows it twice, a ghosted double exposure): a
cut, or a 0.3 s dissolve when it moved little (`vstudio.dissolve`).

**P5. Restrained typography.** One font pair: Noto Serif SC (titles, chapter names, quotes) + Noto Sans SC Regular
(subtitles, labels). Generous letter spacing on small labels (0.14-0.22 em), small sizes, near-white type on a soft
shadow - no boxes, no white quote cards, no thick strokes, no emoji, no saturated colour; one quiet champagne accent
(#C9B48A) for hairlines. Theme `cinema` (`style.footage_theme`, default for vlog / photo-story outputs; her
`style.theme` keeps applying to talking-head work).

**P6. Few words on screen.** A beautiful-footage film gets music and 2-5 refined on-screen lines (or place / time
captions), not a voice-over. History pieces narrate in English (YouTube) with Chinese on-screen subtitles for
Xiaohongshu / Bilibili unless a natural Chinese voice is here: the free Qwen3-TTS voice once downloaded (Settings >
Voice; the plan card offers the download), an OpenAI key, her own voice. Kokoro's robotic Mandarin is opt-in only
(Settings > Voice switch, persona `tts.zh_local`) and never used once Qwen3-TTS is downloaded.

**P7. Title and end.** The film's title sits once over the opening shot, centred, in the serif, a short hairline
and the other language small and spaced under it (an English film shows English only); it fades in over 0.9 s
and out after ~5 s. The end fades to black over 1.5-1.8 s; no "Thanks for watching" card.

**P8. Covers like a travel / documentary thumbnail.** The single best frame full-bleed (no collage, no polaroids,
no blurred pad), a quiet gradient at the bottom, the title in the serif with generous spacing, a small spaced
place line. No stickers, no arrows, no heavy boxes.

**P9. YouTube is English.** Title, on-screen lines, captions, narration and post copy on YouTube / Shorts are
English whatever the request's language; Chinese versions go to Xiaohongshu / Bilibili.

## Rhythm

**A1. Hold key information for at least 1 s.** A title, place name, price, number or logo must
sit fully still for ≥ 1 s after it lands, before the next cut or move. Give the hold to what the
viewer should remember, not to filler.
*Self-check:* Pause on every "remember this" moment. Is there a full second of stillness? Did the
hold go to the right element?

**A2. Speed comes from acceleration, not linear motion.** Fly-ins and pans use easing and
uneven staggers. A group of items arriving should get faster and faster (`cut_plan(...,
"accelerate")`), then rest about 0.5 s when the frame is full. Constant-speed motion reads as a
cheap slideshow. A physical metaphor helps: dealing cards, stamping a passport, pins dropping on
a map.
*Self-check:* Is anything moving at a constant speed in a straight line? Does each burst speed up
and then rest?

**A3. Make the first version slower.** First cuts are nearly always too fast. Give the main action
of the opening a complete arc of ≥ 3 s. Play real interactions (ordering, walking in, typing) at
human speed. Leave hold and rest frames in the timeline budget.
*Self-check:* Watch it as a first-time viewer. Where did you miss something? Could you follow
along?

**A4. Beat sync sets timing, not size. ≤ 3 full-frame hits per video, ≥ 16 beats apart.** A
full-frame hit is anything that moves the whole frame or camera at once: frame-wide scale pump,
shake, flash frame, invert frame (flash frames only in an `expressive` reel; see P1). Treat each as a big slam. Each one goes on a strong hit from
`b.hits`. Other on-beat motion moves only the subject layer: a card, a title, a sticker. Kick
detections are a pool of candidates, not triggers. Count one technique use as one slot, even if it
flashes several times inside.
*Self-check:* Step through any 8 beats of the busiest section frame by frame. Is the whole frame
pulsing on every beat? How many full-frame hits are there in total, and does each sit on a listed
strong hit?

**A5. One transition per cut, taken from the neighbours' budgets.** A transition's length is
borrowed from the two shots it joins: half from the end of one, half from the start of the next.
It does not stretch the video. Use a single transition per cut, never two stacked. A plain hard
cut is the default. Use a styled transition only where the story changes place, day or mood.
*Self-check:* Does every transition steal its frames from its neighbours? Do the neighbour shots
still keep their A1 holds after the steal? Is any cut wearing two effects?

## Look and readability

**A6. Readable text is ≥ 5 % of frame height. Test it at 480 px wide.** Caption and story text
needs an on-screen cap height of at least 5 % of frame height: 54 px on 1080p, about 96 px on a
1920-tall vertical. Secondary text (dates, prices, URLs) needs at least 3 %. Measure the rendered
frame, including any scale or perspective applied, not the font size in code. Text is either
readable or deliberately decorative, never in between.
*Self-check:* Scale one frame from each texted shot down to 480 px wide. Can you still read every
line?

**A7. Each technique stars once.** A signature move (speed ramp, glint sweep, map fly-through,
freeze-frame with stamp, split-screen, crash zoom) is strongest the first time. Use it once as the
star moment. If it appears again, make it smaller and quieter. Never apply a glint or glow to
every item in a group, and clip any glow to the shape that carries it.
*Self-check:* Count each named technique. Does any appear more than once at full strength? Does
any glow spill outside its card's corners?

**A8. One subject in the opening.** The hook opens on one hero image or action with a complete
arc. A crowd of moving pieces can't hold attention.
*Self-check:* How many things does the opening shot ask you to look at?

**A9. Steady camera by default.** Add no fake handheld shake to bright, clean footage. Use shake
only for a deliberate documentary feel, keep it tiny, and check rendered frames for wobble you
didn't mean.
*Self-check:* Is there any camera motion that serves no story purpose?

**A10. The finale is the energy peak.** The ending brings back the best moments, plays on the
loudest section of the music, and carries the riser → impact → sparkle sentence. First versions
of endings are almost always too timid, so push them one notch further.
*Self-check:* Is the finale the most energetic point of the video? Does it bring back each place
or highlight once?

## Sound (summary, details in SOUND.md)

**A11. Choose sounds by genre, and give real actions matching sounds.** Does the soundtrack sound
like this kind of video with your eyes closed? Does every distinctive on-screen action have its
own sound, trimmed to its length?

**A12. Picture first, sound last. Repeated sounds alternate and step down.** Did any shot length
change after the cue sheet was built? If so, rebuild it. Do repeated hits sound countable?

## Delivery

**A13. Deliver with-music and without-music versions** from the same timeline. Both keep voice
and SFX.
*Self-check:* Are both files rendered, and does the no-music version still hold up?

**A14. Verify the beat sync on the rendered file.** Run `beats.verify` on the cut times. Any cut
> 3 frames off is a must-fix. A same-direction offset across all cuts points to an output audio
offset, not to the analysis.

## Travel-fun quick sheet

`beats.energy_arc(duration, "travel-fun", beats=b)` gives this layout:

- Hook (0-8 %): max energy, the best 5-8 shots, ends on a strong hit.
- Intro: where, who and why, with the title held ≥ 1 s.
- 3-5 place or day blocks. Each block is a fast montage that accelerates into a breather (one
  moment that gets to breathe: a reaction, food, a view, a line). Energy rises block to block.
- Peak finale: accelerate cuts, riser → impact → sparkle.
- Outro: a slow wide shot and a sign-off.

### Interpreting a flash report

A `flash` event measures a transient in the frame's mean luminance; it does not establish its cause.
The JSON report also gives `peak_t` and `active_cell_fraction`: the fraction of luma-grid cells whose
activity-adjusted transient exceeds the same flash threshold at that peak. A localized moving object
can change the frame mean. A large fraction can also come from content, so neither value proves an
exposure defect or a clean shot. Compare the source and output around the event before choosing a
repair. These fields are diagnostic only: they do not change thresholds, waive failures or approve
a render. Cropping may amplify a source transient; repeating the same render cannot fix it.
