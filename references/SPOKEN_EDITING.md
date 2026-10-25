# Edited talking-head shorts

Read for personal-story, expert, coaching or founder clips requesting polished / premium / 强剪辑 delivery.
A long source does not make the output a lecture. Use the longform planner for locating stories, then apply
this editorial pass; a range extraction plus export is only an assembly, not the finished edit.

## Source decision before layout

Inspect representative frames including changing cards/subtitles, and compare source speech with ASR. Record
whether captions, titles and music are baked in, which clean originals exist, and usable crop boundaries.
With baked captions choose one visible caption system: retain them intact, rebuild from clean sources, or
remove them geometrically only when the remaining frame has enough space and resolution for the person.
Never add a second transcript below the first, blur-fill a large duplicate face by default, or use generated
repair over hair/face as if it were a clean master. If a clean vertical remake is impossible, retain landscape
and make a platform cover/orientation hint. Ask only for a truly missing source or consequential choice;
Autopilot chooses and records routine editorial decisions itself.

## Three editorial passes

1. **Argument and speech.** Read the whole story before choosing the range. Identify the promise, original
   spoken opening, concrete example, causal link, qualifications and payoff. Move an existing strong sentence
   forward only if doing so preserves its meaning and chronology. Remove logistics, unrelated branches,
   redundant explanation, fillers and failed starts with the shared `vstudio.cleanup`; retain meaningful
   emphasis and natural breath. Keep a sentence-based EDL with source ranges and reasons. Neither a fixed
   speed-up nor a target percentage of deletions demonstrates good editing.
2. **Visual explanation.** Write a beat sheet against the actual edited clock. For each change record the
   spoken cue, viewer question, visual answer, asset/source, start/end and return to the speaker. Examples:
   contrast -> two-column comparison; causal chain -> a few connected nodes; concrete story -> verified
   screenshot or contextual insert; payoff -> brief takeaway. Label conceptual illustrations so they do not
   impersonate real evidence. If material is unavailable, use typography/diagram, not invented receipts,
   testimonials or statistics. Use changes of scale sparingly when source detail permits. No automatic zoom
   every few seconds, no obligatory effect count, and no copying another creator's distinctive design.
3. **Sound and finishing.** Preserve original speech and intentional emotion. Smooth edit boundaries, balance
   dialogue and use a low music bed only where the format benefits. A subtle sound cue should support a real
   visual event, not every word. Check the actual mix. Design one coherent caption/graphic system, with short
   semantic lines, verified terms, readable phone scale and space around the mouth. A cover is an intentional
   design, not an arbitrary export frame.

## Execution contract

Keep `editorial-plan.json` (or equivalent documented timeline) in the new project's work area, describing
source findings, EDL, beats, caption strategy, assets/rights and intended verification. Respect existing
request mode; do not insert another approval gate into Autopilot. Use supported operations in
`references/OUTPUT_EDIT.md` and the promo-recut workflow for material-based cards/compositing. If the selected
batch renderer cannot express a planned visual, add a supported finishing pass or state that limitation;
never silently replace the requested treatment with an unadorned range export. Every intended beat must
resolve to a real rendered operation or an explicitly explained omission.

`longform-slices` now has an optional `finishing: editorial` pass after caption proofreading. It uses the
routed `edit` model to anchor short comparison, causal-chain and takeaway cards to actual edited caption
indices, stores `finish/editorial-plan.json`, and renders the cards after each target's reframe. The clean
master and baseline effects remain available to second-pass edits, including removing individual cards.
Intake selects this pass for identified talking-head recordings; screen-share courses retain their own layout.
Finished sources keep their existing captions and, where the platform supports it, their original aspect.
The planner is shared by supported spoken modes, not tied to a sample title, language, source path or timestamp.
Read the complete argument even when caption boundaries split a sentence; retain later corrections and personal
qualifications. Validate model output before applying it. An invalid plan gets one correction with the original
captions and the exact validation error; a second invalid result fails visibly. Save the correction history in the
plan. Provider/authentication errors retain their own recovery flow. Cross-topic fixtures test the contract, while
actual model replays and rendered playback are required to assess semantic and visual quality.

This does not yet perform argument-level EDL restructuring, acquire contextual B-roll or audit the final audio
by listening. Those remain separate editorial passes; argument cards alone are not proof of premium quality.

## Delivery checks

- Review first 5 seconds, every edit/graphic boundary, the main example and final sentence; sample the rest.
  A contact sheet alone cannot verify animation, timing or sound: play those intervals too.
- Confirm title-to-payoff alignment, intact qualifiers, source-faithful wording and natural sentence endings.
- Reject doubled captions, a cropped face/mouth, stale source subtitle fragments, unreadable diagrams, or
  large empty/blur padding used merely to match a platform aspect.
- Verify cuts with ASR; compare corrected captions with the recording. Run shared flicker and audio checks.
- Deliver the file, cover, captions/post copy, EDL/beat plan and a short audit of actual results. Do not describe
  an intended effect as applied, promise retention, or use a price label as proof of quality.

## Research behind this procedure

Primary written guidance, reviewed 2026-10-14 (references, not licensed footage to reuse):
- [Ali Abdaal's editing workflow](https://aliabdaal.com/youtube/the-ultimate-guide-to-youtube/): assembly,
  contextual B-roll/graphics, then sound/colour polish.
- [Ariyan Khan's expert-video case study](https://ariyankhan.com/case-studies/talking-head-editing-case-study-clearer-learning-video.html):
  visual changes at concepts, comparisons and evidence; consistency and dialogue clarity.
- [Adobe: B-roll](https://www.adobe.com/creativecloud/video/discover/b-roll.html): images support the story
  and cover editorial transitions; choose material for its meaning.
- [Blackmagic official training](https://www.blackmagicdesign.com/products/davinciresolve/training): separate
  edit, visual effects, sound design and mixing disciplines. These are not evidence of a guaranteed market price.

### Preserve the relationship when choosing a graphic

Chain cards draw arrows. Use them for stated causes and consequences or ordered procedural steps, not conditional resilience, concessions, or hypothetical outcomes. Keep “even if”, “unless”, and other qualifications with the conclusion in a takeaway. A contrast needs real alternatives or differences. Audit the visible labels as well as the quoted evidence: an accurate quote does not make an inaccurate diagram acceptable.

The visual plan may use `evidence_from` to include the beginning of the same argument up to 12 seconds before the display. Evidence ends at the display’s `to` cue, never in future speech. This context window supplies missing subjects and qualifications without holding a card on screen for the entire argument. It is a locality bound, not proof of semantic relevance; review the actual relationship. Existing plans without this field keep their selected-cue evidence.
