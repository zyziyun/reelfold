# Learn and share

Use when a creator studies an interview, podcast, course or book and shares their own understanding,
experience, disagreement or practical application alongside specific source passages.

This is an editorial purpose, distinct from a transcript summary or a collection of someone else's clips.
Use one point per short video: a brief source passage → the creator's explanation → a real example → an application.
Repeat that pair for a longer discussion. The creator's ideas carry the argument; do not enforce an arbitrary quote ratio.

## Creation comes first

The app's [creator workspace](../../references/CREATOR_WORKSPACE.md) starts before recording, without any model
call: watch/read → stop and think → write/dictate/record → organize materials → develop a post/demo. The creator
chooses and orders the parts; this workflow executes that edit list. The AI drafter below is an optional helper
for an explicit draft request, not the default owner of the creative process. Existing editing features remain.

## Inputs and recording

Attach original footage under `references`, book pages/source images under `pages`, the creator's actual
recordings under `takes`, and source details/thoughts under `notes` (UTF-8 Markdown/text).
Keep these roles explicit. A reference speaker's story must never become the creator's first-person testimony.
An interview URL is a citation, not a substitute for local footage. Do not claim the linked movie was watched
or downloaded when only metadata or a web transcript was read. Keep supplied link timestamps as search anchors;
a start timestamp is not the end boundary of an excerpt.

Notes should identify title, author/speaker and source URL, or book title, edition and page. Cite only supplied
information. Ask for missing details instead of guessing a quote, translation, page number or personal experience.
If no personal recording exists, the project creates `RECORDING.md` with prompts and waits at the source/perspective
review. Use Home > Record for a camera/mic take or attach an existing recording; then add it to `takes` and refresh
the project. The creator workspace can record beside the playing source; its camera/mic and user-picked screen capture reuse the existing recorder. No TTS or paid generation is implied.

## Montage contract

`work/sources.json` contains stable source IDs, explicit roles, actual durations and audio availability.
`work/montage.json` is JSON:

```json
{"title":"One idea I tried","segments":[
  {"source":"reference-ID","start":12.0,"end":24.0,"point":"The original claim",
   "citation":{"title":"Supplied episode title","creator":"Supplied speaker","locator":"Supplied URL"}},
  {"source":"commentary-ID","start":1.0,"end":20.0,"point":"My explanation and experience"}
]}
```

Use actual source IDs, not the illustrative IDs above. Reference excerpts preserve original speed and audio;
commentary video uses its own original sound. A page segment uses start=0, end=hold seconds, citation with
book/edition/page, `voice` set to a commentary recording ID, and `voice_start` in that recording.
Pages retain their complete aspect within the deliberately composed canvas. Do not turn invented text into a book quote.
Audio-only takes require an attached visual/page. Never mix a reference speaker over a creator's speaking take.

The drafter reads actual ASR with timestamps from the attached audio. Selected times must stay inside each
source, with citation details grounded in notes. One invalid-plan repair is allowed; errors stay visible.
The recording is authoritative: written notes may guide a point but do not become spoken audio.
Authoring the JSON is the agent/engine's responsibility; the creator reviews the plain-language outline.

## Export and acceptance

Export preserves the approved montage canvas, source/creator handoffs and sound. Platform post copy includes
source citations with source timestamps; the timeline ledger maps output times to source ranges. Review the
original question/qualifiers so a short excerpt does not reverse its meaning. Citation is provenance, not a license.
A landscape montage cannot silently become a YouTube Short; explicitly compose a portrait version when needed.

Listen across every handoff, compare original excerpts against their context, inspect page text and source labels
at phone size, and run normal audio/media/flicker checks without relaxing thresholds. No automatic upload.
Current scope: alternating video/commentary and page+own voice; simultaneous picture-in-picture, automatic
YouTube acquisition, PDF page extraction and live pause-to-record need further work. ASR can mishear technical
terms; proofread against the original before publishing. Integration tests do not prove editorial quality.
