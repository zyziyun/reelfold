# Purpose, sources and execution

`vstudio.formats detect` names the editorial intent. `vstudio.intake` combines that intent with the inspected
sources to choose an executable recipe. Preserve an explicit workflow, requested language and source performance.
Mode recognition is not evidence that its final film has passed a quality audit.

| Purpose / actual material | Execution | What the edit must prove |
|---|---|---|
| Interviews/courses/books plus your own explanations | learning-commentary | Source excerpt → your real commentary → experience/application; source citations and recording gaps stay explicit |
| Travel / observational footage | vlog / photo-story | A coherent route or observation, meaningful selection and paced shots; not every clip's opening seconds |
| Personal / expert speech | talkinghead / longform-to-short | Source-faithful argument, actual cleanup and visual explanation; see SPOKEN_EDITING.md |
| Presenter plus screenshots / product inserts | promo-recut | The spoken point and its visible demonstration stay aligned |
| Software UI launch / update | launch-kit | Actual operations, readable controls, verified feature claims and one action |
| Product / ecommerce photos or footage, no presenter | photo-story with the product brief | Use → visible feature → supporting view → product hero + one supplied CTA; identity, colour and proportions survive |
| Company / corporate footage, no presenter | photo-story with the company brief | Real place/team → actual process → visible result → supplied CTA; coherent identity |
| Company / product introduction with a presenter | promo-recut | Keep the original voice; insert genuine proof, not unrelated stock |
| Product/company brief with no visual sources | preproduction | A shootable script and source list; do not pretend a finished film exists |
| Recorded comedy, including silent physical comedy | performance-edit, original speed/audio/frame, no speech-cleanup prerequisite | Setup → escalation → payoff → reaction; pauses and deliberate repeats can carry the joke |
| Unrecorded comedy idea | preproduction | Separate shot/action notes and character dialogue; no compulsory educational insight paragraph |
| Explicit AIGC / generated sketch | ai-video | Consistent characters, visible action and verified shot continuity; generation remains subject to provider/budget approval |

Product claims come from the supplied brief or a visible demonstration. Do not invent prices, discounts,
sales, performance or testimonials. Company claims need evidence for customers, certificates, rankings,
results and logos. A generated/stock shot must not imply it depicts the actual company or product.

## Photo planning and rendering

The automatic photo-story drafter now sees labelled contact sheets of supplied photos, as well as videos.
It copies source photos to `work/source_photos/pNNNN.<ext>` and uses those same IDs in the spec. Originals stay
untouched, duplicate original basenames remain distinct, and an unknown photo ID fails before rendering.
Never use a contact-sheet preview itself as a finished shot.

The render contract is `SCRIPT = [(section_index, [(en, zh), ...], [(source, weight, motion, opts), ...]), ...]`.
Dictionary units and imaginary `CTA`/`DURATION`/`ART_DIRECTION` globals are not executable video instructions.
Use an ordinary final cue/shot for a CTA and `MUSIC.length` for music-mode duration. Generated specs get a
structural check and one model repair before frame extraction or narration.

For a complete product/artwork photo, `opts=dict(fit="contain")` preserves the whole source on a matte derived
from its edge colours. This is photo composition, not permission to pad an already finished movie for a new ratio.
Recompose each requested canvas and inspect the product, label and copy there.

For finished speech films, automatic talkinghead and longform slicing retain the source aspect and baked captions.
The talkinghead route uses the native-frame fast pipeline, with optional editorial finishing, rather than first
creating a portrait V-track master. Explicit requested shapes override the default; inspect their recomposition
separately. A horizontal source exported unchanged for a platform that supports landscape is a valid deliverable.

Product defaults disable scenic grading/grain and floating film title/chapter cards. Source-photo captions use
a bounded high-contrast label plate; product photos reserve the measured caption band within their composition,
using source-edge colours behind it so multi-line copy cannot cover the product or its zoomed detail.
For photo-only product drafts without an explicit caption position, `LAYOUT.photo_caption_side=True`
uses the spare horizontal space on landscape canvases: copy on the left, complete photo on the right.
It reuses the same measured caption and contain/detail renderer; portrait canvases keep the top/bottom layout.
Set `photo_caption_side=False` to keep a full-width photo with the reserved caption band. Mixed photo/video
drafts do not enable this automatically, because a moving shot may need its full frame. Inspect both hero and
detail views: enlarging a photo must not crop product identity or turn its label into an unreadable texture.
`LAYOUT.photo_caption_safe=False` disables this treatment for an explicitly reviewed composition. A short explicit end fade is respected. These defaults are
editable in the spec. `PRESERVE_COLOUR` also gives the designed cover an ungraded, uncropped source with a
separate title area, rather than shading the product to carry a headline. Planning sheets/previews are not cover
candidates. These defaults cannot establish that a detail is legible, a shot proves its line, or the text avoids
the product: inspect those at actual phone size and revise the plan/layout when they fail.

Company process films use measured, high-contrast lower-third labels by default in music mode, without
floating scenic title/chapter cards, automatic scenic grading or grain. Explicit spec layout and colour choices
remain available. The label plate stays within each target's safe width; inspect its position against equipment,
faces and source text. Corporate footage is not evidence of certifications, throughput or client identity.
A process label also makes a claim: a worker beside cans does not establish loading, and a nozzle above
containers does not alone establish filling. Select the interval showing interaction and result; inspect its
start, action and end in each target crop, then play it continuously. Keep the hand/tool and target object
readable together. A centred portrait crop may lose the action, while an enlarged blurred background cannot
restore it. If no supplied view proves the action, use a truthful descriptive label and explicitly record the
missing demonstration; this is not full process-film acceptance. Do not fabricate an action to complete a story.

Both narrated and music timelines give the final shot only its visible closing hold. Do not inflate that duration
to keep it active after playback: motion interpolation and source preparation also consume the same duration.
A closing move must complete visibly, and source preparation must not decode unused extra footage.

Product photo sequences should reveal the product, approach a source-visible detail, then return to a complete
hero. Use the native `in`/`out` photo motions where they explain the design; keep a steady reading hold where
needed. `contain` keeps the complete image visible with a restrained 4% scale move; `cover` uses a 12% move
around the authored focus. Vary shot weights to match reading and evidence, rather than defaulting to equally
timed static slides. Do not simulate new object angles or rotate branding from a single flat photograph.
Moving source footage does not need an added camera move by default. Verify actual start/middle/end frames;
writing a motion name in the plan alone does not establish useful movement.

For short product films, review the rendered shot durations as well as the motion. Multiple subtitle cues can
occupy one unchanged picture: cue count is not visual progression. Give the brief CTA a reading hold, not an
automatic oversized share of the film. For example, a 12-second film can allocate roughly 2/3/4/3 seconds to
reveal/detail/supporting view/CTA. Adapt this to real reading and action; a slow brief or complex instruction
may need a longer hold. If the material cannot support another meaningful view, shorten the film unless its
duration is explicit. Do not fill the gap with repeated zooms or fabricated angles. Review the last third in
continuous playback, not only a contact sheet; a clean still frame cannot reveal a dragging ending.

## Acceptance by purpose

Audit source fidelity, editorial sequence, type/contrast, subject visibility, motion, audio, timing, output shape
and publishing copy separately. Product/company acceptance also needs a claim-to-source check. Comedy needs
playback of the setup, punchline and reaction with original sound; shorter is not automatically better.
An AIGC animatic with placeholder sketches is a storyboard, never a finished generated video.

After a fix, rerender and inspect the failed moments plus the opening, busiest frame and ending. Run the
appropriate flicker/media checks without loosening their thresholds to pass. Record unresolved issues and
actual evidence; source fixtures and a structural test do not establish professional commercial quality.
