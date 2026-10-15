# Caption, card and copy text rules

Everything the viewer reads that comes from the transcript (burned captions, notes cards, quote cards, titles,
hooks, post copy, tags) follows these rules.

## 1. After ASR, always verify the names

**After ASR, always run proofread with entity verification before burning captions or writing copy.**

ASR writes proper nouns by sound: 洪都拉斯 (Honduras) comes out as 宏都拉斯, Wells Fargo as "wells fargo". One wrong
name then ends up in the captions, a notes card and the post copy at once.

- `vstudio.proofread.proofread(cues, ...)` runs the check on every caption (also with `provider="none"`); the batch
  `proofread` stage does it for every job. `entities=False` turns it off, `entities="zh_Hant"` sets the content
  locale (default: persona `creator.locale`, else simplified Chinese for Chinese text).
- `vstudio.entities.verify(text, locale, glossary)` is the check itself:
  - **Places (Chinese)**: country / region names from Unicode CLDR (`babel`: zh_Hans, zh_Hant, zh_Hant_HK) plus
    a curated list of major cities. A span that sounds like the content locale's standard name but is written
    differently is corrected (宏都拉斯 → 洪都拉斯 in zh_Hans; 洪都拉斯 → 宏都拉斯 in zh_Hant). This is a sound-alike
    swap, so it passes the faithful validator.
  - **Regional variants that sound different** (纽西兰 vs 新西兰, 澳洲 vs 澳大利亚) are the speaker's own word: they
    are kept, and reported as `variant: regional`.
  - **Other entities** (organisations, products, people, English names): the glossary spelling ("wells fargo" →
    "Wells Fargo"), and the model's `entities` answer inside the one glossary call per source ("standard
    spelling?"). Only a `certain` answer that still sounds like the transcript is applied; everything else is
    flagged as a `guess` for the creator to look at.
- **One source of truth per project**: the same fixes are applied to the captions (proofread), the post copy
  (`vstudio.batch.stages.entity_post` in the export stage), the plan-segments titles / notes cards / hooks / tags,
  and generated copy (`vstudio.publish.generate_copy`). Never fix a name in one place by hand only: add it to the
  creator's glossary / `subtitles.term_fixes` so every text gets it.

## 2. Captions must match the audio

A caption fix may only swap a short mis-heard span for what the speaker said: no deleted or added words, no
translation, no rephrasing (`vstudio.proofread.faithful`). Fillers and repetitions are a cleanup question
(references/CLEANUP.md), not a proofreading one.


For authored narration, use `vstudio.asr.align_script` with the original script for display text and ASR words
for timing. Its shared `alignment_tokens` keeps Unicode letters, combining marks and numbers; do not add
ASCII-only tokenizers in individual workflows. Canonically equivalent spellings match without changing the
visible text. East Asian character matching tolerates different ASR word grouping.

This is token matching with interpolation, not phonetic forced alignment: a valid interval is not proof of
speech sync. Inspect unmatched phrases and cue boundaries against the recording, especially names, mixed
scripts and words the recognizer omitted. Do not replace the authored script with ASR errors just to obtain
a match. For original speech, retain the corrected transcript and follow the source-fidelity rules above.

If a transcription service returns segment times without word times, the shared ASR path preserves the
original Unicode text and marks evenly spread word estimates as `approx_words`. These are not measured
word boundaries: do not describe them as forced alignment or use their mere existence as proof of accurate
word-level edits. Old estimated caches are repaired locally on read; verified word times remain unchanged.
Invalid cached segment times must surface for review, not silently trigger another upload or paid call.

## 3. Preserve words and verify the actual renderer

Use the shared `subs.balanced_wrap` / `draw.wrap` for caption and card lines. In space-delimited scripts,
keep the complete Unicode word and its combining marks together, including highlighted words. A word wider
than the box needs a smaller font or a different layout, never an arbitrary letter break. Keep Arabic and
Indic closing punctuation with the preceding word. This is not dictionary segmentation for Thai or other
scripts without spaces.

Word-preserving text is not proof of correct glyphs or reading order. Review the rendered result with the
actual font and backend. The libass writer selects whole-line shaping and automatic base direction for RTL
dialogue (`Encoding=-1`); an ASS sidecar for legacy VSFilter must explicitly select `encoding=1` and be checked
in that player. The bundled Python loads its pinned FriBiDi before Pillow, enabling the wheel's existing
Raqm/HarfBuzz; both runtime build verification and packaged tests check availability. Source installations
must provide FriBiDi themselves ([Pillow installation](https://pillow.readthedocs.io/en/stable/installation/basic-installation.html)).
Pillow still needs appropriate font coverage; enabling Raqm alone does not add missing glyphs or make
separately drawn highlight runs into a correct mixed-direction paragraph. A successful draw
call alone does not prove Arabic or Indic text is readable. Do not reverse strings or transliterate them to
hide a renderer limitation.
