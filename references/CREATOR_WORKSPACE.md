# Creator workspace: human thought to a shareable post

Use when someone wants to explore a source, pause to think, inject their own ideas, create or organize material,
and develop a post. This is a creation mode above the existing editing tools. Keep all existing editing modes.

## Who does what

The creator chooses the subject, observations, perspective, examples, sequence and final expression. They can
write, dictate or film an idea; reading and note-taking never start an agent, rewrite or render. The original
thought stays editable and traceable to its source. AI results are optional candidates, never replacements for
someone's opinion or fictional first-person testimony. Tool invocation follows the creator's current action.
Do not require an AI outline or a completed recording before someone can start a workspace.

The output is a shareable post, potentially containing text, source excerpts, a recorded explanation, images,
a screen demonstration or a generated demo. A video is one possible component. A working demo need not look like
a final publication. Do not automatically publish it or confuse generated examples with real evidence.

## Current implemented path

Home's creation starts → Learn and share → create a workspace from a title/question and optional materials.
It opens with no model call. HTTPS links, local videos, page images and notes can be collected. YouTube uses the
official privacy-enhanced embed; websites open in the system browser beside the workspace. A URL is not downloaded
media. Local video time is read from actual playback. YouTube player time messages are checked by origin and frame;
the creator can check/edit source time. Source permissions, network/login and embed restrictions still apply.

A thought or source quotation is saved as a distinct note with source and time. Focusing a thought pauses the
local/player source. Text fields accept ordinary input, system dictation and tools such as Typeless without a
special SDK or a claim of a Typeless partnership. Built-in microphone dictation uses installed local ASR,
returns editable text and never falls back to a cloud provider. Accuracy depends on the actual local model.
Leaving the workspace releases its microphone, including delayed permission/session creation. Failed writes stop
the device and offer a retry; a late transcription never fills a different workspace. Recording sessions close
once even when Stop and navigation overlap.

When YouTube asks for login/verification, offer **Sign in and play in browser**. Open the canonical official
watch page in the user's normal system browser, preserving the last known/manual source time (or original link
start). The creator completes Google's login/verification there and keeps playing there while using this
workspace. Do not claim browser login transfers into the embedded player, automatically sync external playback,
or detect completed login. External-browser notes use manual time calibration. Do not collect passwords/cookies
or route Google account login through a privileged embedded view. A successful handoff is not proof that the
user completed verification or that online playback passed.

Attached `.md` / `.txt` source notes are readable as plain text in the material panel, with stable source IDs for
thoughts and quotations. Reading does not turn them into first-person testimony or invoke a model. A bounded
preview shows an explicit notice past 100,000 characters; missing or non-UTF-8 sources show a visible error.
Raw files are unchanged. Text source notes are reading material, not automatically rendered video passages;
record a personal explanation or attach a visual page to make a demo from them.

Camera/mic capture and the existing user-picked screen/window capture stay beside the source. Raw camera,
microphone and screen tracks remain in the recording session; a muxed derivative becomes a personal material.
Screen capture offers an explicit, default-off option to include materials playing inside Reelfold. This captures
only the app's audio, never system loopback or external browser sound. The screen WebM keeps that audio; the
microphone remains separate, and the viewing derivative mixes both. Recommend headphones to avoid microphone
echo. If no audio track is granted, sharing stops with a visible error. Original footage can also provide its
audio as a separate excerpt. OS permission failures stay visible. These are local
recordings, not remote live broadcasts or a conferencing feature.

The creator marks a passage, adds their own take, orders/removes parts and explicitly requests a video demo.
That action creates a verified edit list for `learning-commentary`, using the shared engine export/QC/player/
second-edit/publishing path. Removing a draft block does not remove source media. A camera-only or screen-demo
post does not need a borrowed excerpt. Book pages can use a selected recording’s audio while keeping the page visible. Finer voice ranges can be
authored in the edit list; source details remain required before rendering.

The text-post action assembles the creator's own thought notes verbatim into an editable draft. Save/copy remains
under their control. Quotes do not silently become the creator's spoken script. An optional explainer-demo action sends only selected thought notes to the existing explainer planner in Ask
mode and keeps a link back to that task. Further image/interactive-demo tools and more post templates should
follow the same explicit selection/action pattern.

## Extensions to explore, not shipped modes

- Learn and share: source passage → my interpretation → experience/application.
- Explain and demonstrate: question → sketch/demo → explanation → evidence.
- Practice and reflect: goal → attempt → observation → revised approach.
- Compare and take a position: sources → differences → my reasoning → conclusion.

Reuse the same material/note/recording/draft objects and existing tools. Keep the creator in one workspace instead
of adding a disconnected wizard for each output format. For a generated demo, offer the relevant installed skill
or provider and a reviewable scope; respect its generation cost controls. Never invent an installed capability.

## Verification boundaries

Feature availability is distinct from actual playback, microphone accuracy, physical device acceptance, editorial
quality or competitive superiority. Test note durability/source anchoring, one explicit tool invocation, separate
tracks, ordering, revision, draft persistence and original-media preservation. Validate YouTube playback on the
actual source/network; source-parser tests do not prove it. Synthetic devices prove integration without accessing
the creator's live devices. Existing editing regressions remain part of the affected checks.

## Learn while using it

Keep the first view focused on the material and the creator's thoughts. Link entry, passage selection and optional
AI tools disclose only when requested. A newly recorded take offers a preview and an explicit add-to-video action
right beside it; do not make the creator locate an internal file. Show video arrangement after a passage exists.
When a video needs the creator's own explanation or source credits, offer contextual guidance and take the user
to the needed fields. Credit text remains a draft until saved; do not enable generation based on unsaved fields.
Posts are available once the creator has thoughts; quotes stay separate. Keep existing editing accessible.

## Browser passages with sound

When the creator watches in their signed-in browser, the source panel offers an optional local browser capture
page. It opens in the normal browser, uses the native tab picker, and records only what the creator selects.
Chrome/Edge tab-audio sharing is supported; no-audio choices fail visibly instead of saving a silent passage.
This local page uses no account access, network uploads, extensions, drivers or local HTTP server. It does not
transfer browser login into the embedded player. The creator stops and saves the passage, then drops the downloaded
WebM anywhere in the workspace to add it as reference material. Native file access consent still applies in Lite.

Each browser passage is explicitly limited to five minutes and saves automatically at that limit to bound
in-memory recording; another passage can be recorded afterward. Browser downloads without duration/cues are
remuxed into a project-owned seekable copy, keeping the original byte-identical and recording its origin in an
adjacent source ledger. This is reference footage, never automatically labeled as the creator's testimony.
The passage then uses the same source credits, personal explanation, ordered draft, demo and second-edit path.
Support here is browser-tab capture, not general OS loopback or remote conferencing. Browser/OS support still
varies; do not claim Safari/Firefox audio support or authenticated YouTube playback without actual acceptance.
