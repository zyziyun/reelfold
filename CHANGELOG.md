# Changelog

All notable changes to Reelfold (the Mac app, the engine and the Claude Code skill) are listed here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: minor versions may change behaviour).

App releases are tagged `v*`; engine-only releases are tagged `engine-v*`.

## [Unreleased]

### Added

- **More AI agents, including ones that work in mainland China**: Reelfold now drives any coding agent you installed
  and signed in to over the Agent Client Protocol (ACP): Gemini CLI, Cursor CLI, GitHub Copilot CLI, OpenCode,
  Claude Code / Codex through their ACP adapters, and Qwen Code (Alibaba), Kimi CLI (Moonshot), CodeBuddy (Tencent)
  and iFlow CLI. It runs your own program with its own sign-in, in an empty folder, with every tool refused, and never
  sees your account. Settings › AI › Coding agents shows which are installed and signed in, whether each works in
  China, a one-click test, sign-in, the agent's own model list, and the install command of the others; any of them
  can be the AI of a job or a fallback (Claude Code → Qwen Code → a DeepSeek key). New API key: Doubao (Volcengine
  Ark, the same key as Seedance). Qwen, Kimi, GLM and Doubao keys pick their mainland China or international
  endpoint. "Not available in your region" is said plainly and the fallback answers.
- **Export for editing software**: any clip (or every clip of a project) goes to Premiere Pro / DaVinci Resolve
  (FCP7 XML), 剪映 / CapCut (a draft that shows on the app's home screen) or OpenTimelineIO, pointing at the clip's
  own media (or a copy of it next to the timeline): every cut, the speed, the sound level and the music bed come
  along, captions as a text track (剪映 / CapCut) or an SRT beside the XML; what an editor cannot be told (overlays,
  title band, transitions) is listed in a README. Media moved later: `output nle-relink` points the timeline at it.
  The clip's Export card has "Export for editing software…". Ported from OpenFilm (MIT).
- **Your hand edits survive the AI**: what you change yourself in the clip editor (caption text and style, effects
  and where they sit, the title, the cover, trim, speed) is kept when the AI edits the clip, when you ask the whole
  project something and when the video is made again (Redo the visuals, a re-run): the AI is told about them and
  leaves them unless you point at or name that part, and each has "Reset to AI version" in the clip's history.
- **The look check for HTML-made scenes**: explainer scenes (also after Redo the visuals), launch-kit films and any
  HyperFrames project are drawn twice at sampled times in two shuffled orders and compared (a picture that changes is
  not seek-safe), and checked for fonts that did not load, text cut off or in the caption band, and sounds that are
  missing; a scene that fails is redrawn by the AI with the findings, and `python -m vstudio.look DIR` (or
  `vstudio.firstpass --hf DIR`) gives the findings with a contact sheet. After OpenFilm's `look`.
- **The editor brain**: each project says how it is cut and why ("Cut as Calm travel film: drone footage, no
  talking, evening light"), from the footage and your words, and you can change it. A shot plan shows what each
  shot gets (hold, cut or dissolve, slow motion only where it stays smooth, follow the subject for vertical) with the
  reason, and you can change any shot. "Could be generated" cards suggest AI shots where they would help (a missing
  establishing shot, a dark or shaky moment with no other take, a bridge, a cover background) with a price; nothing
  is generated or spent until you approve.
- **Choose the AI model**: Settings › AI picks the model of each provider (Claude Code: Opus 5.5, Sonnet 5.5,
  Haiku 5.5, Fable 5.1 or the CLI default; Codex: the models your login can use; API keys: the provider's list), a
  job can still have its own, and the AI chip shows and switches it. In the clip chat, `/model` shows what runs with
  a picker and `/model 5.5` / `/model sonnet` switch (said in the thread); `/` lists /model, /trim, /captions,
  /effect, /cover, /export, /help, and no slash command is ever sent to the model. The live pane names the model.
- **Codex model your login cannot use**: a `model` in `~/.codex/config.toml` that a ChatGPT login rejects is
  flagged in Settings › AI with a one-click fix, and a call that hits it says so plainly instead of a raw 400.
- **Import a finished video to edit it again**: drop videos made anywhere (another Reelfold run, CapCut / 剪映, Final
  Cut, Premiere, a phone app) with or without the footage they came from, or use File › Import Finished Video… (⌘I).
  The composer tells finished videos from footage; each folder of platform versions becomes one clip with its
  covers and post copy, several clips one project. Your files stay as they are: Reelfold edits copies (APFS clones)
  and only reads the footage. The clip opens in the editor on its words (transcribed in the background), and every
  second-pass tool works on it: chat edits, cuts, captions, music (a new bed can replace the old soundtrack), covers,
  new sizes, Rewrite post copy.
- **Shots matched to the footage**: the shots of an imported video are found in its footage by their frames; pick
  another take of any shot from stills (or ask the chat), and a wider version (a 16:9 cut of a vertical video) is
  rebuilt from the full source frame with the finished grade.
- **A version in another language**: what is said is translated, voiced again and captioned (an English YouTube
  version of a Chinese clip); with footage linked the picture comes without the old burned text.
- **Several videos from one folder (goal mode)**: say "make several videos from my DJI card, each with its own theme"
  (or turn on 「Several videos」 in the composer) and Reelfold reads the folder or SD card (DJI flight logs for time
  and place, photos, panoramas; nothing is written to the card), groups the footage into stories, and the AI proposes
  a plan of videos - a history explainer where the place has a story, a music film where it is simply beautiful, a
  beat short for action. Rename, drop or merge them on the plan card, then they are made a few at a time as one group
  in the Studio list, on Home and on its own page ("4 of 6 made"). A video that fails or stalls is tried once more,
  then dropped with the reason; the summary lists each video's files per platform and its post, and "Remove
  unfinished" clears the rest (`python -m vstudio.intake goal`).

### Fixed

- **No more "Chromium" notifications prompt on macOS**: the optional browser for HTML covers, slides and HyperFrames
  is now `chrome-headless-shell` (a bare executable with no app bundle, 98 MB instead of 176 MB on Apple silicon),
  also used by HyperFrames instead of its own copy. An installed Chromium.app is replaced by itself in the background
  (Settings › Downloads) and removed once the engine runs on the new one.

## [0.2.7] - 2026-10-11

### Added

- **Home**: the app opens on what needs you — a composer, suggestions from real signals (a new recording, a request
  you repeat, a post missing some platforms), the top of the Inbox with one action each (with Undo), running jobs
  with their step in words, and today's posts. Sidebar: Home · Inbox · All projects · Publish (⌘1–4).
- **All projects for hundreds of videos**: search, platform / project / date filters, J/K / ↵ / E / S / X keys, and
  bulk Approve, Schedule, Try again, Archive and Change with AI; 220 projects archive in about a second.
- **Redo the visuals** of a finished explainer, the voice kept: the clip / project page button, or ask the chat
  ("画面太素了" / "redo the visuals" / "plus de schémas"); every scene is drawn again by your AI, then rendered and
  exported again (`vstudio.project remake --do visuals`).
- **Vertical versions follow the subject**: landscape footage made for 9:16 or 3:4 is cropped shot by shot around
  faces, people, moving things and vivid colour, with a smooth camera that holds still on static shots and eases
  through crossfades; only a shot that cannot be cropped (two far-apart subjects, a flat panorama) keeps the blurred
  fill. Switch per video on the clip page ("Follow the subject" / "Fill with blur").
- **Real post copy per platform** for vlogs: title, body, hashtags within each platform's limit, the place (offline
  from DJI flight logs) and the music credit; Chinese platforms in your request's language, YouTube and TikTok in the
  persona's (`publish.copy_lang`). Recorded as a decision you can change.
- **See how it is being made**: the project page shows the pieces as they appear (graded segments, contact sheets,
  master, cover options) — open one big, ask AI about it, or pause the run.
- **Chat on every project page** again (running, ready, Details): it can pause, go on, change the music, pick another
  cover or re-cut, beside the page and resizable.
- **A free offline voice in the Mac app (Apple silicon)**: explainers and courses without an OpenAI key are narrated
  by Kokoro on this computer (Chinese `zf_xiaobei`, English `af_heart` / `am_michael` / `bf_emma`). The voice is a
  one-time 330 MB download (Settings › Downloads), started when a video first takes the free voice; before it, the
  voice step says so and offers the download instead of stopping at "No OpenAI key". Works offline and in the Mac
  App Store sandbox. Intel Macs and Windows still need a key for narration.
- **Vlog music is picked for you**: a vlog without your own track gets the best fit for your words and the style
  from the license-free library (your `~/Music/Reelfold` tracks, else Reelfold's built-in beds), laid under the
  picture at -14 LUFS. On autopilot it is a decision you can change; with Ask me first you pick from three tracks
  or no music. A CC BY track's credit is added to the post copy.
- **Live run page**: one calm view of a planning or running project — what it is doing in one sentence, % and time
  left, what happened per step (files, minutes, decisions, tokens) — and a terminal-style Live pane with the real
  Claude Code / Codex stream and the engine log (secrets redacted; copy, search, filter). "Watch all" tiles every
  running job.
- **Row actions in the Studio**: ⋯ / right-click on any row — Archive (undo), Delete (requests; projects to the
  Trash, recordings kept), Rename, Show in Finder, Stop, Try again; multi-select; an Archived filter with Restore.
- **Course videos from notes**: explainers narrate in Chinese end to end (voice, checks, captions, timing); lecture
  notes or exported Notion pages are drafted into an episode for the requested length instead of being locked as
  the script, with a rules fallback when no model is available.
- **AI presenter (Hedra)**: an optional talking presenter behind the spend gate; the key lives in the keychain
  (Settings › Video generation).

### Changed

- The composer's platform chip applies to this request only, with "Make this my default".
- After sending a request the Studio opens it.

### Fixed

- **Redo the visuals no longer throws the whole redo away for one scene**: the scene brief forbids the network up
  front (no `fetch()`, XHR, WebSocket, outside files: data inline), a refused scene is repaired with the check's exact
  finding and its fix, and a scene that still fails keeps its old version (or a simple diagram from its cues) while
  the others are redrawn and rendered — "13 of 14 scenes redrawn; scene 14 kept as before", with Redraw scene 14.
  A code card that only shows `fetch(...)` as text is no longer refused.
- **A redo that stopped is a notice, not a broken project**: the clip stays Ready to post (its video is unchanged)
  and says which scene and why, in English, 简体中文 and Français, with Try again — which draws only the scenes still
  missing. A failure pinned on a clip shows its reason and Try again, never Confirm.
- **Explainer scenes are drawn by the AI, never as text lines**: each scene is a diagram / animation on the voice's
  cue times, checked and linted before it is kept; the storyboard's "TODO" shots are planned by the AI. When no model
  answers, the project waits in Needs you ("The visuals need an AI model — Claude Code didn't answer") instead of
  rendering a text-only video; the autopilot never approves a draft that still says TODO.
- Claude Code gets a reasoning effort for big generations (`--effort medium` for a scene: ~1 min instead of 5).

- A finished vlog, explainer or other single-export project read "Not started" / "0 of 1 ready" with no cover: the
  desk only looked for batch-style exports. It now reads Ready to post with its cover, and clicking a ready clip (or
  one of its versions) opens the editor — on the timeline when the video has no speech.
- **Vlog export** stopped at "Missing: 'out.music.master'": the export read the music step without depending on
  it. It now does, a recipe that reads a step it does not depend on is rejected, and Try again on such a project
  finishes it without re-rendering.
- **Vlog, talking-head, photo-story and promo renders in the app**: the bundled ffmpeg is LGPL and has no `eq`,
  `hqdn3d` or `boxblur`, so a graded render stopped at "No such filter". Grades are now built from LGPL filters
  (`vstudio.ffmpeg_filters`, pixel-identical to `eq`); old `eq=` grade strings in projects and configs are
  translated when they run. A guard checks every filter the engine can emit against the bundled build.
- A render that fails because of the app (a missing filter or encoder) now says it is a bug in Reelfold with
  "Report this problem", instead of "One of the files couldn't be read". A file that really can't be read is
  named, and a drive that isn't connected is called out.
- **Try again on a failed project** really runs again: the failed step is re-run (finished steps are kept), a
  project made on autopilot is retried on autopilot, and a pilot that stopped on its failure goes on. Before, it
  replayed the old error in the same second without running anything.
- **Explainer voice without an OpenAI key**: a new explainer uses the voice this computer has — your persona's,
  OpenAI only when its key is set, else the free local voice (a Mandarin voice for Chinese narration). A project
  that chose OpenAI without a key no longer stops on "OPENAI_API_KEY is not set": on autopilot it uses the free
  voice and says so; in Ask me first it asks "Use the free voice" / "Add an OpenAI key"; Try again recovers a
  project that already failed. With no free voice installed, it asks for the key instead. A missing key anywhere
  now names the service and the fix.
- A course request stopped at "no '## Line N' blocks in SCRIPT.md"; the reason is now said in plain words and Try
  again really re-runs the step.
- Lecture notes were taken for a screenplay or asked for recordings; drafts read the whole source.
- The folder watcher no longer shows Reelfold's own work folders as "Waiting its turn".
- Colour grades failed to render in the app (its LGPL ffmpeg has no `eq`): grades are built from LGPL filters, old
  `eq=` settings are translated, and CI checks every filter exists; ffmpeg errors are worded as app bugs, not as an
  unreadable file.
- One Studio row per video (a project's question joins its clip); many attached files collapse into one row; DJI .SRT
  files are read as shooting data; very short clips say so; parallel status writes no longer race.

## [0.2.6] - 2026-10-11

### Added

- Every split in the Studio and the editor resizes: drag (or arrow keys on a focused divider), double-click to reset,
  sizes kept on this Mac; the video list folds to a strip (⌘B) and the list's groups fold.

### Changed

- The clip header has room: project · position · length above a larger title, the full title on hover, buttons that
  shrink to icons in narrow windows; the clip page stacks below 700px; one left edge for every section.
- Switching videos returns each column to where it was; the clip page shows its own skeleton while loading and a
  Try again when a clip does not open; the AI panel slides in and out.

## [0.2.5] - 2026-10-11

### Added

- **Studio** (now the main screen): every video in one list — 要你看 / 进行中 / 可以发 / 已排期, each with its current
  step, time left and progress — and one page per clip: editable title, player with covers, caption looks and
  versions, the question that needs you, the transcript, per-platform copy and schedule, and one AI bar. Inbox is a
  filter; the nav is Studio · Calendar · Settings; "＋ New video" (⌘N) starts text, files, Record yourself or Create.
  Title + copy + cover + schedule takes 4 clicks on one screen (was 14+ across 4).
- **Pickups**: stopping a recording opens it in the editor with the automatic cleanup marked; select words and
  Re-record (R) or Add after (⇧R) — loudness, room tone and joins are matched.
- **Update prompt**: "Update ready — Restart to update" with What's new, download progress, and "Restart when done"
  while projects run; Settings › General shows the version and Check for updates (not in the App Store edition).
- **Attention**: Dock badge with what needs you, notifications that open the exact clip, ⌘K to any video, ↑/↓ and
  ⌘1–9 to switch.
- A live "see the process" log per running project; the step bar follows the engine's real stages, with time left.

### Changed

- One title per clip: the AI's title by default, editable in the editor header and synced to the post titles.
- A clip opens with its transcript (no "listen first"); cover, caption and other edits re-render in the background,
  and publishing uses the edited clip.
- One status vocabulary everywhere; plain words instead of job ids, stage ids and recipe jargon; strict i18n checks.
- Captions follow the requested language (translated when a model is routed), stay inside the safe area, and keep
  the brand spelled right; hashtags are added only when relevant; clips end on whole sentences; repeated takes are
  removed consistently; fixed-intent requests (record / talking head) skip the planning model.
- Home's default platforms follow her choice and accounts, international first.

### Fixed

- "Share a screen too" did nothing (the media permission refused screen capture; the system picker timed out); a
  denied Screen Recording permission now says how to allow it.
- The engine no longer exits on SIGUSR1 (it dumps thread stacks); crash reports name the signal; quitting or
  restarting to update is not reported as a crash.
- The transcript's Restore popover can be clicked with the mouse.

## [0.2.4] - 2026-10-10

### Added

- **Autopilot** (default for new projects): a request sent from Home becomes a project at once and runs to finished
  clips without a plan to confirm; the AI judges unsure filler cuts, every decision is logged with its reason and can
  be changed later. Up to 2 projects run at once, the rest queue (and survive a restart). "Ask me first" restores the
  confirm step (Settings › General, or per project). CLI: `vstudio.project run --autopilot`, `decisions`, `reopen`.
- **Control room**: All projects lists Needs you / Running / Ready / Scheduled & out with a live pipeline per project,
  what the AI decided, clips, and publishing. The old grid stays one click away.
- **Requests without files**: planned from the words (explainer, series, scripts, AI video, slides); links are read
  first (web pages, public Notion pages, exported Notion folders). What only the creator can give comes back as a
  plain "needs" item instead of an error.
- **Drafts instead of files to write**: author steps (promo keep spans and packaging, scripts, cues, configs …) are
  drafted by the AI or the rules and reviewed in plain words (e.g. the transcript with cut sentences crossed out);
  seeded templates are never taken as an answer.
- **Skin smoothing** (磨皮 / 美颜): a face-tracked `portrait-retouch` effect the chat can apply, with strength and a
  beauty mode.
- **Record yourself, redesigned**: script or speak freely, teleprompter under the lens, one record button with a
  countdown, device popovers with a live mic level, takes with thumbnails, and "Finish — make my video".

### Changed

- Transcript cuts and AI chat edits apply at once with Undo (no "Apply cuts" step); a setting brings back
  "Ask before applying AI edits".
- Publish cards, the drawer and the published list open the clip page; posted items link to the post.

### Fixed

- Record yourself: record, retake, camera, mic and Studio sound did nothing with an empty script or were not buttons.
- Home could get stuck on "Couldn't make a plan"; plan errors now say why in plain words.
- The Inbox showed raw YAML for promo steps and a letter instead of a thumbnail.
- Concurrent run-store reads could hang the engine; stalled compose renders and ffmpeg are stopped.
- Cuts render audio and video chains as separate filter graphs; Windows and Linux show Ctrl+ shortcut hints.

## [0.2.3] - 2026-10-09

### Added

- **App Store lint** (`apps/desk/scripts/appstore/appstore_lint.py`, CI `appstore-lint.yml`): fails a build whose
  code references Tcl/Tk or non-public Accelerate BLAS symbols, whose Python carries "itms-services", whose
  entitlements are not sandboxed / include `network.server`, or that has quarantine flags.

### Changed

- The Mac app's engine (and the App Store build's HTML renderer) listen on a Unix domain socket in the app's own
  folder instead of a `127.0.0.1` port; the UI reaches the engine through `app://desk/api`. Windows keeps
  `127.0.0.1`. The App Store build has no `network.server` entitlement and leaves out the YouTube API sign-in (its
  OAuth redirect needs a local port); YouTube posts go through the built-in browser there.
- The engine no longer needs scipy (loudness filters, body-slim smoothing and WAV writing use numpy / numba /
  soundfile); the app's runtime ships without scipy and tkinter (App Review 2.5.1).

### Fixed

- With no usable AI (no key yet, or a local model server without the routed model) a talking-head clip no longer
  fails at its post copy: the title and body are drafted from the spoken lines, as without an AI route.
- The plan card's questions and no-AI plan texts follow the app's language (they could come out in Chinese).
- The in-app sign-in terminal no longer drops a CLI's first output when it prints before the terminal is ready.
- Windows: the engine starts again (the Unix socket server is only defined where Python has one).

### Added

- **Archive projects** (Mac app): 「Remove from list」 is now **Archive** (归档 / Archiver) in a project's menu and in
  bulk select, with an undo toast. An **Archived** tab at the end of All projects shows archived projects dimmed with
  their archive date and a **Restore** button (single or bulk); search and type filters work there, and an archived
  project still opens. Nothing on disk is deleted, and a project with a run going is never archived. Engine:
  `POST /api/history/archive` / `restore` (`{dir}` or `{dirs}`), `GET /api/history?archived=1`.
- **Promo montage from b-roll**: `montage.clips` entries can name a source, `[source, start, end, label]` (a `broll`
  index or file name; the old `[start, end, label]` still reads `highlights`). Each clip is re-encoded onto the
  canvas (vertical clips get a blurred-fill pillarbox, 16:9 is cover-fit) with the privacy crop resolved per source.

### Fixed

- Promo post copy no longer appends the persona's default (career) hashtags: it uses `publish.tag_sets.promo`, or
  only the post's own tags when the persona has none.
- Delivered promos are no longer ~15 Mbps when ffmpeg has no libx264: the render is re-encoded to the platform's
  bitrate target (8 Mbps at 1080p30 for YouTube / 小红书, 6 Mbps for B站) and the delivered size is reported.
- The planner waits long enough for Claude Code on a typical intake (150 s floor, measured) before using Codex.
- The promo footage map no longer flags an `about:` label that is on the card itself (scene title / items, pip tag).
- The promo build no longer crashes when the subset fonts are not installed (system fallback + a warning).
- An engine-port reload during the first page load is no longer reported as "a problem in the app".

## [0.2.2] - 2026-10-08

### Added

- **Promo template**: `pip:` windows (screen full-screen, speaker tile bottom-right), card `scene:` kinds (tiles,
  flow, bars, stat, toast, ranking, columns, checklist, swatch) and card `video:`, a `hooks:` montage at the start,
  `crop: auto` that removes browser bars from screen recordings, and a footage map printed at build.
- Live progress while a plan is made; an agent's live status on the project page.
- **Watermark**: your handle, your own PNG logo, or a logo generated from your handle (drawn locally) on every
  export. Settings › Watermark in the Mac app has live previews on a 9:16 and a 16:9 frame, a corner picker, size,
  opacity, per-platform switches and "Add to every video by default"; the Export card can turn it off for one video.
  The mark sits inside each platform's safe area and above the captions. Off until you set it up.
  Engine: `python -m vstudio.watermark`, `--watermark on|off` on `vstudio.export` and `output render`, and
  `watermark: false` per batch job; settings in `$VSTUDIO_HOME/watermark.json` or persona `watermark:`.

### Fixed

- Attached recordings and folders are kept as promo-recut b-roll instead of being dropped by the planner.
- Author checkpoints show their label, help and file instead of a bare "1 0"; Review lists waiting checkpoints.
- Large plans give Claude Code enough time; a nested `claude -p` no longer attaches to a host Claude Code session.
- Rendering picks a Node.js that runs; delivery creates its output folder; stage errors keep the real stderr;
  external-tool failures say which tool and how to fix it.
- The app reads the creator's persona; covers no longer warp faces; CJK quotes no longer render as tofu.
- `project touch` on a recipe project only writes live status (it no longer drops the project from the list).
- Delivered audio is exactly as long as the picture; montage length is verified; captions never overlap.
- Talking-head speed caps allow a persona's 1.5x body / 2x hooks.

## [0.2.1] - 2026-10-07

### Changed

- Talking-head jobs default to the notes look, with keywords you review before the render.
- The Mac App Store (Lite) build names no other download and links nowhere; its limits are explained neutrally.

### Added

- A draft post title and body for each clip, written from the final captions.

## [0.2.0] - 2026-10-07

The first public release: the macOS app for Apple silicon, signed with a Developer ID and notarized by Apple, plus
an unsigned Windows x64 preview installer. Nothing before it was published as a release; the earlier history lives
in the commit log (formerly `video-studio` and `Daycut`).

### Added

- **Mac app (Reelfold · 千剪)**, MIT, in `apps/desk`:
  - Home composer: describe the job in one sentence and drop the footage; AI proposes a plan card with an estimate,
    then runs a pilot before the full batch.
  - Projects of many clips running in parallel, an inbox that shows only what needs you, and an All work view of
    batches, projects and skill work folders.
  - Chat-first clip editor: big player, a chat column that proposes changes as cards, a timeline with a scrub bar,
    selective undo of one earlier step, before/after compare.
  - Project-level "edit with AI" across every clip at once.
  - Assisted publishing: the upload page is filled in per platform and you press publish (never auto-posts).
  - AI accounts: sign in with your Claude Code or Codex subscription, an API key, or a local model, and switch per task.
  - First-run wizard with queued model downloads; bundled Python runtime and LGPL ffmpeg; auto-update.
  - UI in English, 中文 and Français.
  - Create page (behind a setting): series studio with formats, bible, storyboard and a spend gate.
  - A week of posts in one step: drop this week's footage on Home or Publish; Reelfold plans and makes every clip,
    then lays them out over the week (your words, else each account's usual time, else the platform's rhythm) as a
    preview you confirm with one button.
  - Send feedback (Help menu, Settings, empty states) and Report this problem (failed jobs, crashes): a redacted
    report you read first, opened as a prefilled GitHub Discussion or Issue. Nothing is sent by the app; automatic
    crash reports are off by default.
  - First run in minutes: a built-in sample recording (CC0) and a path that works without any AI account.
  - Transcript editing: cut by words in the transcript, suggestions in the chat, space plays a selection.
  - Publish as a week board with a drawer, plain-language planning, reminders and fill-in of each upload page.
  - Plugins on the Create page: board importers (HyperFrames, CSV / JSON shot lists) and agent runners that make
    shots in parallel lanes, each in its own job folder, with takes and Inbox items for failures.
  - Optional anonymous usage counts, asked once and off until you agree.
- **Windows x64 preview** (unsigned NSIS installer `Reelfold-<v>-win-x64-setup.exe`, attached to the release): the app, its engine sidecar
  and the bundled runtime run on Windows (Media Foundation or OpenH264 for H.264, faster-whisper for speech).
- **Engine**:
  - `vstudio.intake`: one sentence plus the material becomes a validated plan (rule fallback when no model is set).
  - `vstudio.project`: every workflow is a recipe with checkpoints, series, inbox and publishing calendar.
  - Batch orchestration: segment planning, client workspaces, job edits with stale-stage reruns, delivery packages,
    metrics, caption proofreading with a cache.
  - Clip-level editing (`project output list|show|edit|render|undo|redo|ai|effects`) with a cached stage render.
  - `vstudio.llm`: one interface for Anthropic, OpenAI, OpenAI-compatible servers (DeepSeek, Qwen, Kimi, GLM,
    OpenRouter, Ollama…) and the Claude Code / Codex CLIs, with per-route fallback chains and timeouts.
  - ASR and TTS backend registries, including self-hosted Whisper servers.
  - `vstudio.formats` (defaults per recurring format) and `vstudio.firstpass` (a check before every handover:
    audio, resolution, speed, loudness, first frame, caption terms, cover).
  - Named-entity verification after ASR (place names and cities).
  - One design-theme system for every overlay (editorial default).
  - Recipes for teachers and interview / podcast creators: `lesson-clips` (a lesson cut by teaching point, with
    "Today's phrase" title cards, key-term cards, a recap and study notes in Markdown / PDF; a screen share and a
    camera synced by sound, with screen / picture-in-picture / band layouts) and `interview-qa` (question and answer
    clips that open on the question, tight answers, speakers by role, optional face masks).
  - Bilingual captions (`vstudio.bilingual`): the spoken line plus a translated second line in the theme's
    secondary ink, or the translation only; glossary enforced; per-language SRT / VTT with every export.
  - Launch kits (`vstudio.launch`, `launch-kit` recipe): product launch videos from screen recordings and a
    Playwright capture, with idle stretches speed-ramped, gallery stills, a music bed and per-platform post copy.
  - Studio sound (speech clean-up) and a license-free music library shared by every recipe.
  - Share for review: a page a client can comment on, and the feedback imported back as edits.
  - Plugin registry (`vstudio.plugins`): manifests, permissions, cost kinds; paid plugins only run through the
    spend gate.
- **Platforms**: 20 profiles, each with its own canvas, safe zones, caption box, length, loudness, cover and copy
  limits: YouTube, YouTube Shorts, TikTok, Instagram, X, Facebook, LinkedIn, Threads, Reddit, Pinterest, Snapchat
  Spotlight, Dailymotion, Kwai, 小红书, 抖音, 视频号, B站, 快手, 微博, 知乎.
- **Docs site** at [reelfold.com/docs](https://reelfold.com/docs/) in English, 中文, Français and Español; reference
  pages generated from the engine sources.
- **Website** at [reelfold.com](https://reelfold.com) in four languages.
- Repo: CONTRIBUTING, Code of Conduct, security policy, issue and pull-request templates, roadmap, this changelog.

### Changed

- Renamed to **Reelfold (千剪)**. The repo moved from `zyziyun/video-studio` and `zyziyun/daycut` (old URLs
  redirect). The Claude Code skill keeps the name `video-studio`, and existing installs keep working.
- Monorepo: the engine and skill at the root, the app, website and docs under `apps/`.
- SKILL.md rewritten as a five-step job flow with one routing table.
- Source recordings are never deleted automatically; delivery cleanup is off by default.
- One cache root, `~/.cache/video-studio` (the legacy `~/.cache/vstudio` is still read).
- English is the default language for the app and the website.
- Talking-head projects default to the creator's look: 记笔记 panels, progress-bar chapters and highlighted keywords
  drafted from the clip by the routed text model, strict filler cleanup, 1.25x body / 1.5x hooks from the
  `talking-head` format (one source for the recipe, intake, the desk and the compose scripts; persona
  `formats:` overrides it), a retouched cover, and the hook menu on the default engine too.

### Fixed

- The bundled macOS runtime ships every engine dependency: babel, pypinyin and jsonschema were missing, so in the
  app the named-entity check found nothing and plan / recipe validation fell back to key checks. The runtime build
  and the packaged-app tests now check every package of `requirements.txt`.
- Agent-runner lanes no longer shrink to one on machines with few cores.
- Create: Send to Publish finds an assembled episode also when its folder is reached through a symlink
  (`/var` and `/private/var` on macOS).
- Windows preview: the engine no longer stops answering right after it starts (numpy is loaded before the engine
  starts any thread).
- Projects resume after their last Inbox answer; a run waiting at a checkpoint is listed once; waiting and
  interrupted jobs show on the project board.
- The engine is restarted when it dies after start (never while the app quits), and engine errors are translated
  instead of shown raw.
- Media is served with byte ranges (seeking works), also through symlinked folders.
- English transcripts keep spaces after punctuation and between English words; English sub-word tokens are joined in
  Chinese transcripts; captions split on word boundaries with one shared line breaker.
- Proofreading needs ASR evidence before changing an English word and keeps the glossary off common words.
- Cover runs close their face landmarkers (no deadlock); captions stay clear of talking-head note cards.
- AI fallback works on every path (segment planning, proofreading, chat edit), Codex gets a strict JSON schema,
  and an all-attempts error says what was tried.
- Chat edits always answer; the capability probe no longer misses `--context`.
- Pilot and project failures are visible, with a retry; planning can be stopped.
- Filler cuts keep the word they trim in the captions; AABB reduplication (起起落落) is no longer cut as a stammer.
- A dropped word's tail cut in promo recuts no longer runs into the next word.
- Burned-in finished edits default to the band layout (old captions cropped, new ones below).
- A 9:16 小红书 export gets a 9:16 cover (the 3:4 cover is only for the 3:4 version); the feed's centre 3:4 is
  previewed.
- Post titles fit each platform's title limit when they are written (deterministic shortener, reported in the
  export warnings); exports draft a title when none is given, and the first-pass check no longer reads the hashtag
  line as the title.
- Talking-head posts are no longer empty when you write no copy: a title and a short body are drafted from the final
  captions (your AI account in your voice, else lines you say), fitted to every platform's title limit and shown in
  the review as a draft to edit. Your own title and body are kept.

### Security

- Electron fuses on the packaged app (no run-as-node, no `NODE_OPTIONS` / `--inspect`, asar integrity), hardened
  runtime and notarization.
- API keys in the OS keychain; every IPC call validated; the local engine needs a per-session token.
- No silent mock engine or demo mode in the product: a packaged app always runs the real engine.

[Unreleased]: https://github.com/zyziyun/reelfold/compare/v0.2.7...HEAD
[0.2.7]: https://github.com/zyziyun/reelfold/compare/v0.2.6...v0.2.7
[0.2.6]: https://github.com/zyziyun/reelfold/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/zyziyun/reelfold/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/zyziyun/reelfold/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/zyziyun/reelfold/compare/v0.2.1...v0.2.3
[0.2.1]: https://github.com/zyziyun/reelfold/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/zyziyun/reelfold/releases/tag/v0.2.0
