# Purpose, sources and execution

`vstudio.formats detect` names the editorial intent. `vstudio.intake` combines that intent with the inspected
sources to choose an executable recipe. Preserve an explicit workflow, requested language and source performance.
Mode recognition is not evidence that its final film has passed a quality audit.

| Purpose / actual material | Execution | What the edit must prove |
|---|---|---|
| Travel / observational footage | vlog / photo-story | A coherent route or observation, meaningful selection and paced shots; not every clip's opening seconds |
| Personal / expert speech | talkinghead / longform-to-short | Source-faithful argument, actual cleanup and visual explanation; see SPOKEN_EDITING.md |
| Presenter plus screenshots / product inserts | promo-recut | The spoken point and its visible demonstration stay aligned |
| Software UI launch / update | launch-kit | Actual operations, readable controls, verified feature claims and one action |
| Product / ecommerce photos or footage, no presenter | photo-story with the product brief | Use → visible feature → supporting view → product hero + one supplied CTA; identity, colour and proportions survive |
| Company / corporate footage, no presenter | photo-story with the company brief | Real place/team → actual process → visible result → supplied CTA; coherent identity |
| Company / product introduction with a presenter | promo-recut | Keep the original voice; insert genuine proof, not unrelated stock |
| Product/company brief with no visual sources | preproduction | A shootable script and source list; do not pretend a finished film exists |
| Recorded comedy | talkinghead, 1.0x, gentle cleanup, no notes/morphs by default | Setup → escalation → payoff → reaction; pauses and deliberate repeats can carry the joke |
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

Product defaults disable scenic grading/grain and floating film title/chapter cards. Source-photo captions use
a contrasting theme ink in the upper safe area; a short explicit end fade is respected. These defaults are
editable in the spec. `PRESERVE_COLOUR` also gives the designed cover an ungraded, uncropped source with a
separate title area, rather than shading the product to carry a headline. Planning sheets/previews are not cover
candidates. These defaults cannot establish that a detail is legible, a shot proves its line, or the text avoids
the product: inspect those at actual phone size and revise the plan/layout when they fail.

## Acceptance by purpose

Audit source fidelity, editorial sequence, type/contrast, subject visibility, motion, audio, timing, output shape
and publishing copy separately. Product/company acceptance also needs a claim-to-source check. Comedy needs
playback of the setup, punchline and reaction with original sound; shorter is not automatically better.
An AIGC animatic with placeholder sketches is a storyboard, never a finished generated video.

After a fix, rerender and inspect the failed moments plus the opening, busiest frame and ending. Run the
appropriate flicker/media checks without loosening their thresholds to pass. Record unresolved issues and
actual evidence; source fixtures and a structural test do not establish professional commercial quality.
