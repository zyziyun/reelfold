# Intake: say what you want, drop the materials (`python -m vstudio.intake`)

The Reelfold desktop app's "new batch" form asked for a recipe, a segments file and budgets. Intake replaces it: the creator
describes the job in plain language and drops any mix of files and folders (video, audio, photos, pdf / docx /
pptx / md / srt). Intake inventories the materials, picks one or more recipes (mixed plans are fine), shows an
editable **plan**, and creates the projects (`vstudio.project`, references/PROJECTS.md) ready for a pilot run.

```
materials + "把后面对于自媒体的思考单独剪出来发小红书"
  -> analyze (inventory, cached)  -> plan (model or rules; validated)  -> [revise "每条 60 秒内"]*  -> apply -> projects (+ series)
```

Code: `lib/vstudio/intake/` (inventory, docs, rules, plan, estimate, apply, cli). Plan schema:
`lib/vstudio/intake/plan.schema.json` (`python -m vstudio.intake schema --json`).

## 1. Commands (run from `lib/` or with `PYTHONPATH=$VSTUDIO/lib`; every command takes `--json`)

| command | what |
|---|---|
| `analyze --inputs PATH... [--asr off\|sample\|full] [--out analysis.json] [--full]` | the material summary (compact: no paths, short excerpts) + content hashes; `--out` keeps the full analysis |
| `plan --prompt "..." --inputs PATH... [--client C] [--provider P] [--asr auto] [--auto hook,cover] [--out plan.json]` | the plan (section 3); `--analysis analysis.json` instead of `--inputs` |
| `revise --plan plan.json --prompt "只要小红书" [--in-place \| --out new.json]` | the plan updated from a follow-up instruction; the history is kept in `revisions` |
| `apply --plan plan.json [--out DIR] [--dry-run] [--run] [--autopilot]` | creates the project folders (a series when the plan has several), returns ids, dirs and the pilot run commands; `--run` starts each pilot; `--autopilot` creates them on autopilot (no pilot, the engine decides every checkpoint and records why: references/PROJECTS.md §3) and the run commands say `--autopilot`; exit 5 on an invalid plan |
| `goal --prompt "..." [--inputs DIR...] [--platforms P...] [--ui-lang en\|zh\|fr] [--out goal.json] [--json-events]` | a goal-style request (several videos from one folder / SD card): the survey + a plan of videos (section 8); folders named in the prompt (`/Volumes/dji/DCIM`) are read too |
| `goal-edit --goal goal.json --ops JSON [--in-place]` | the plan card's edits (`drop` / `restore` / `rename` / `kind` / `length` / `merge` / `platforms`); each touched video's `request` is rebuilt |
| `schema` | the plan JSON Schema |

## 2. Inventory (`analyze`)

Folders are walked recursively (hidden files, VCS / dependency / `state` / `exports` folders and symlinks
skipped; 2000 files, depth 8). Inputs are read-only: nothing is written next to them (ASR samples are decoded to a
temp folder; the cache lives under `$VSTUDIO_CACHE/intake/`, keyed by a content hash + the analyzer version, so a
second analyze / plan / revise is instant).

| kind | facts |
|---|---|
| video | duration, size, orientation, fps, HDR, audio; speech from a short ASR sample (one 20 s window, three for files over 75 s; `--asr full` = whole track, transcript cached); on 6 frames: faces per frame (`vstudio.face`), talking head, multi-person, screen share (low saturation + flat UI), burned-in captions (bright text with a dark outline concentrated in the lower / middle band, absent elsewhere); filename hints (zoom / meet / recording / 录屏 / final / 成片 / 课 / 培训). The first 40 videos get the heavy checks, the rest probe facts only |
| audio | duration, speech vs music |
| image | size, orientation, EXIF capture time, coarse GPS (1 decimal, about 10 km), faces on up to 12 images; a folder of photos / clips becomes one group (count, time span, faces share) |
| text | pdf (pypdf or PyMuPDF), docx (python-docx), pptx (python-pptx), md / txt / srt / vtt / ass / json: title, up to 12 headings, a 300-char excerpt, language, shape (`script` 剧本 with scenes + dialogue, `slides`, `outline`, `notes`, `article`, `subtitles`), episode count, URLs found (listed, never fetched). A missing extractor is a note, not an error |

Every material also gets a **role** (what the rule planner keys on): `call`, `lecture`, `screen-recording`,
`talking-head`, `finished-edit` (burned captions or a final export with speech), `footage`, `podcast-audio`,
`voice`, `music`, `photo`, `script`, `slides`, `doc`, `notes`, `subtitles`.

### Requests with no files, links, "my Notion"

A request with no files is planned from its words (`plan --prompt "..."` with no `--inputs`): an explainer / a
series, 口播 scripts to record (preproduction), an AI video, slides - never "no inputs". What only she can give comes
back as `needs` (message dicts) and the plan waits for it (no model call until she gives it):

* `intake.need.footage` - the request cuts / edits her own recordings and none came with it (no project is made up);
* `intake.need.notion` - it names her Notion and no Notion link or exported notes (a folder of .md / .html, e.g.
  Notion > ••• > Export > Markdown & CSV, unzipped) came with it;
* `intake.need.notion-private` / `intake.need.page-unreadable` - a pasted link could not be read.

Links in the request are read first (`vstudio.intake.sources`): a web page (plain GET, 2 MB / 20 s, HTML -> Markdown
with its headings) or a public Notion page (Notion's public page endpoint `/api/v3/loadPageChunk`, no login), kept
as Markdown in `$VSTUDIO_CACHE/intake/sources/` and planned from like a dropped .md. A private page is said to be
private; nothing is guessed. `--ignore-needs` plans without what is missing. No AI connector (MCP) is used by the
planner: it plans from what was read on this machine (for private pages: export them, or share them to the web).
A request that cannot be planned at all raises `PlanError` with a `code` (`plan-empty`: no words and no files); the
`--json-events` error event carries it as `code: plan-<code>` for the app to word.

## 3. Plan

The routed model (task `intake` of `vstudio.llm`: `llm.tasks.intake` or `llm.default` in the persona / client;
e.g. `claude-code` = the creator's own Claude Code login; `--provider` overrides) gets the request, the compact
materials, the persona / client defaults, the recipe catalog (every manifest: inputs, item sources, params with
enums / defaults, platforms, checkpoints), the SKILL.md phrase table and, when the request selects content from a
recording ("剪出来", "截取", "有意思的部分", "单独发"), the time-coded transcript of that recording (`--asr auto`:
transcribed once, cached, for videos up to 45 min). The code then validates and completes the answer:

* recipe ids, input keys, input kinds / extensions, param names and values (each param's JSON Schema from the
  manifest), item keys: anything unknown or invalid is dropped or reset to the default and listed in `warnings`;
  a sub-project with an invented recipe or without its required input is dropped. **No recipe is ever invented.**
* params: recipe default < persona / client (`platforms`, body `speed`, `cleanup_profile`, `language`) < materials
  (a finished edit with burned captions -> talkinghead `captions: false`, gentle cleanup, 1.0x; a screen share ->
  longform `layout_mode: split`) < the model < what the request literally says (platforms, counts, "每条 60 秒内",
  "1.2 倍", 英文, 剪干净, 遮脸 / 不遮脸, 卡点). `param_sources` says where each value came from.
* platforms are mapped to the recipe's ids (`小红书` -> `xiaohongshu:full` for talkinghead, `xiaohongshu:vertical`
  for longform slices).
* focus rows: ranges are clamped to the media; a focus sub-project without rows gets them from the rule matcher
  (focus terms + position words 前面 / 中间 / 后面 over the transcript); if no transcript exists yet, `apply`
  transcribes and resolves it.
* checkpoints from the manifest (`needs_you`: `auto: never` ones, budget / consent always, the rest unless listed in
  `--auto`), estimates (section 4), a template Chinese summary when the model gave none.

When no model is routed, the call fails (expired login, network) or nothing survives validation, the **rule
planner** builds the plan: the phrase table per clause (`另外` / `以及` / `；` split the request), material roles
(a call -> call-clips, a lecture -> longform-to-short, photos + clips -> photo-story or vlog, a 剧本 -> ai-video, a
PDF -> explainer topics from its headings, notes -> preproduction), negations ("不要讲解视频") and the same
parameter extraction. `planner.fallback: true` + `planner.reason` say so.

```jsonc
{
  "version": 1, "kind": "vstudio.intake.plan", "id": "20261006-124604-x", "prompt": "...", "client": null,
  "planner": {"provider": "codex", "model": "...", "route": "argument", "fallback": false, "cost_usd": 0, "seconds": 26},
  "analysis": {"digest": "...", "inputs": ["/abs/..."], "totals": {...}, "asr": "sample"},
  "materials": [{"id": "f1", "path": "/abs/x.mp4", "kind": "video", "role": "finished-edit", "duration": 653.2,
                 "burned_captions": true, "transcript": "<cache>/....transcript.json"}],
  "projects": [{
    "id": "p1", "recipe": "talkinghead", "recipe_label": "口播精剪", "name": "...", "why": "...", "materials": ["f1"],
    "inputs": {"video": ["/abs/x.mp4"]},                       // project-level inputs (abs paths or text)
    "items": {"method": "focus",                                // per-file | single | planner | focus | episodes | list
              "count": 3, "focus": "后面关于自媒体的思考；中间的感悟",
              "rows": [{"id": "s01", "inputs": {"video": "/abs/x.mp4"}, "params": {"range": [535.0, 610.0], "title": "..."},
                        "why": "..."}]},
    "params": {"platforms": ["xiaohongshu:full"], "captions": false, "speed": 1.0, "cleanup_profile": "gentle"},
    "param_sources": {"platforms": "prompt", "captions": "material", "speed": "planner"},
    "checkpoints": [{"id": "filler", "kind": "filler-confirm", "label": "确认去口癖", "needs_you": true, "auto": "default"}],
    "estimate": {"machine_min": 3.7, "wall_min": 1.8, "storage_mb": 383, "api_usd": 0.0, "credits": null,
                 "measured": true, "paid_steps": [], "basis": {"source_s": 653, "output_s": 222, "items": 3, "platforms": 1}},
    "outputs": {"platforms": ["xiaohongshu:full"], "videos": 3, "workflow_md": "workflows/talkinghead/WORKFLOW.md"}
  }],
  "series": null,                                               // {id, name} when there are several sub-projects
  "questions": [{"id": "q1", "project": "p1", "text": "...", "options": [...], "default": "..."}],
  "risks": ["..."], "warnings": ["..."],
  "estimate": {"machine_min": ..., "wall_min": ..., "api_usd": ..., "paid_steps": [...]},
  "run": {"pilot": 1, "auto": []},
  "summary_zh": "一段中文说明：做什么、用什么、关键设置、需要你确认什么、时间 / 费用",
  "revisions": [{"prompt": "每条 60 秒内", "at": "...", "planner": {...}, "changes": [...]}]
}
```

The plan is plain JSON: the app (or the creator) may edit params, rows, ranges, names or drop a sub-project before
`apply`; `apply` validates it again.

Questions are only for what can't be defaulted and changes the result (whose face to hide, narration vs music);
everything a checkpoint already covers (segment approval, filler cuts, cover, publish review, budget) is not asked
up front.

## 4. Estimates

Speech recipes: the `vstudio.batch` bench table (this machine's measured seconds per unit when a batch has run
here - `measured: true` - else the built-in guesses) over the stages probe / extract / asr / (geometry) / cleanup /
apply / compose / export x platforms / verify / qc / preview, with source seconds and planned output seconds
(rows' ranges, planner count x the mean of min_s / max_s, or the files' durations). Render recipes: seconds per
output second (explainer 6, promo 4, photo-story 2, vlog 1.5). API cost: 0 when the LLM tasks route to a
subscription CLI, a local server or none; else about $0.01 per source minute; OpenAI TTS about $0.015 per narrated
minute; AIGC credits are quoted at the ai-video budget checkpoint (never auto). Wall time assumes two lanes.

## 5. Revise

`revise` sends the current plan + the instruction to the model ("keep what the instruction does not change") and
validates the result like a new plan. Without a model, rules handle the common follow-ups: `只要 / 只发 <平台>`
(replace) or a platform alone (add), `每条 N 秒内` (max_s; rows longer than that get a note), `N 条`, `不要 <配方词>`
(drop those sub-projects), `1.2 倍` / `原速`, `英文`, `剪干净 / 轻一点`, `遮脸 / 不遮脸`, `加 / 不要 hook`, `横屏 / 竖屏`,
`卡点 / 舒缓`. An instruction nothing understood leaves the plan unchanged with a warning.

## 6. Apply

One sub-project -> `<out>/<NN>-<name>/` via `Project.create` (recipe, params, client, auto policy; rows become
items with their `range` / inputs; `per-file` -> one item per file; `episodes` -> N episodes; planner recipes
without rows keep their segment planner, run at the first `run` and approved at the `segments` checkpoint).
Several sub-projects share a **series** (`intake-...`; the first recipe is the series recipe, each project names its
own) so the desk shows them as one job. `<out>/intake.json` = the plan as applied + the project dirs. Default
`<out>`: `$VSTUDIO_HOME/projects/<plan id>`. Next step per project: `python -m vstudio.project run --dir D --pilot 1
--json-events` (exit 4 = the pilot waits for review, 7 = a checkpoint needs the creator).

## 7. Validated

Golden tests (`tests/test_intake.py`, mocked model + rule planner, no media work): 12 request x material mixes -
lesson -> 20 vertical slices, 口播 -> cleaned 小红书 short, finished horizontal edit with burned captions -> focus
ranges in its later part, photos + clips -> 文艺片, PDF -> 5 explainer shorts, 剧本 -> 6 AI episodes, Zoom podcast
-> clips with face masks + consent, a mixed course folder -> longform + explainer + 口播稿 (series), DJI clips ->
卡点 vlog for 抖音, a finished export -> polish, screen recordings -> course for B站, notes -> 3 scripts; plus revise
(rules and model), apply (projects, series, ranged items), the inventory on synthetic media / documents, the CLI.
A real run (a 10.9 min finished horizontal 口播 with burned captions, "把后面对于自媒体的思考，以及中间的一些感悟剪出来，单独发小红书",
provider codex): role finished-edit detected (talking head, burned captions, final export), whole track transcribed
for the focus, plan = talkinghead x 3 focus rows (301-363 s and 450-535 s: 副业 / 跨行业 感悟; 535-610 s: 自媒体), captions
kept (`captions: false`), gentle cleanup, 1.0x, `xiaohongshu:full`, about 2 min wall, $0 (subscription CLI), in
about 70 s end to end on first analysis.

## 8. Goals: several videos from one folder (`goal`)

"在 /Volumes/dji/DCIM 做多个视频，每个主题不同，可以并行" is not one plan but a **goal**: `goal.py` surveys the folder and
proposes several videos, each of which then starts as an ordinary request (`plan --prompt <video.request> --inputs
<its clips>`). `is_goal(prompt, inputs)` recognises one (several / as many as possible videos + a folder dropped or
named in the words); the desk sends it there (its composer also has 「Several videos」).

* **Survey** (read-only: nothing is written next to the footage, so an SD card stays untouched): the walk follows
  symlinked files; DJI `PANORAMA/<nnn_nnnn>` tile folders count as one panorama each. Per clip `vstudio.footage.facts`
  (length, shape, the `.SRT` flight log: time + GPS, the nearest well-known city from `vstudio.places`) and one small
  keyframe (cached under the intake cache by path + size + mtime); per photo its EXIF time + GPS (cached).
* **Stories**: items in time order; a new story after a 3 h pause, a move of more than 5 km or a new day, then a
  split where the light jumps (mean brightness by 0.2+) across a pause of 15+ min (golden hour -> night). One
  contact sheet per story is what the model looks at.
* **Plan**: the routed model (task `intake`) proposes up to 8 videos: `title` / `title_zh`, `kind` (`history` - the
  place has a story; the request asks for well-known, verifiable facts only; `film` - just beautiful: music and a few
  short lines; `reel` - action, cut on the beat, vertical first; `vlog` - a trip across stories; `essay` - a
  reflective voice-over; `photos`), its stories, a one-line English `brief`, and the plan card's `theme` / `why` in
  the UI language. The model does not set lengths. No model (or no usable answer): one music film per
  story with enough footage (`planner.fallback`). YouTube is always English, Xiaohongshu / Bilibili / Douyin Chinese:
  each `request` names the languages per platform.
* **Lengths per platform**: every video gets `lengths` {platform: seconds} from each platform's habit for its kind
  (`vstudio.platform_habits`, references/platforms/<name>.md; her own range from Settings › Publishing), capped by
  what its footage carries, and `cuts`: the platforms grouped by length (a long cut for YouTube / B站 with chapters,
  a short cut for Shorts / 小红书 / TikTok). `length_s` is the longest. Her words ("按 90-120 秒讲解") set every
  platform's length (hard limits only clamp them). The request carries them as `Cuts: 300 s for YouTube and Bilibili
  (long cut, chapters); 60 s for Xiaohongshu (short cut).` Plan-card edits: `{op: length, video, length_s, platform?
  | cut?}` (her numbers are kept in `lengths_own` and survive a change of kind).
* **What the footage carries** (`footage_max`, shown as "about 4 min possible"): every usable moment of the story's
  clips (`vstudio.shots` moments with score >= 0.35 when the clip was analysed before - cache only, no decode at
  survey time - else one moment per 12 s of the clip minus take-off and tail) held for its kind (film 8 s, history 9 s
  x 1.6 reuse under a voice, reel 1.6 s x 2), little variety (under four moments) x 0.8. No cut is cut shorter than
  15 s (a reel: 20 s); a length she sets above it is marked `over_footage`.
* **One project, a long and a short cut**: `rules.cut_lengths` reads the per-platform lengths back out of the request
  (also her own pairs: "YouTube 5 min, 小红书 60 秒"); `plan.split_by_cut` (after the language split) gives a
  photo-story / explainer / vlog project one item per length: `items.rows` `long` / `short` with params
  `{platforms, length_s, cut}`. Each item is drafted for its own length and cut (the drafter is told "LONG cut ...
  chapters" / "SHORT cut ... hook in 2 s", `platform_habits.cut_note`) and rendered on its own - never one length
  reframed. One length: the project's `length_s`.
* **Script top-up** (`vstudio.topup`): a drafted photo-story spec or explainer script more than 15 % shorter than its
  target is sent back to the model to extend it (more beats, verified facts only) up to two rounds; the fact guard
  runs on the final text; the draft record keeps `length` {target_s, first_s, final_s, rounds, short} and the review
  says when it is still short. **Beat shorts**: at least 20 s - the drafter pads the body to the beat budget with more
  moments (then longer holds), and a render that still comes out short is re-cut once (`recut` / `short` in the
  render result).
* The desk keeps the goal (desk `engine/desk_engine/goals.py`): a group whose videos run a few at a time on
  autopilot; a failure or a stall is retried once, then the video is dropped with its reason; the goal is done when
  every video is made or dropped, and the unfinished ones can be cleared.


## 9. The editor brain (`vstudio.brain`): template, shot treatment, generation proposals

Three judgements an editor makes, each recorded with who made it (`rules` | `her` | `ai`) and a reason in English
and Chinese, each changeable by her (desk: the project page's "How it's cut" section; CLI: `python -m vstudio.brain`).

* **Template** (`brain/template.py`, templates in `brain/presets.py`): the inputs' signals (speech share, talking
  head / several people / screen recording, a DJI flight log, motion from `shots`, photos vs clips, music, length,
  evening / night) + the request's words (en / zh) -> a template = recipe + params + a shot policy: `travel-calm`,
  `beat-short`, `trip-vlog`, `history-explainer`, `documentary`, `essay`, `photo-story`, `th-refined` (口播精剪),
  `lecture-shorts`, `conversation-clips`, `concept-explainer`, `product-promo`, `launch-film`, `ai-short`. Her words
  win (`by: her`) but only for templates the materials can make (口播 over silent drone footage stays a footage
  film); a close call may go to the routed AI (`--ai`), else the rules' pick says it was close. The plan carries it
  per sub-project (`projects[].template`, the plan card's "Cut as … · why"); `apply` keeps it in project.yaml
  (`brain.template`); a vlog without a style takes the template's (English "fast cuts on the beat" -> `fun`). Goal
  kinds map onto templates (`goal.RECIPE` comes from `presets.for_goal_kind`). "A history explainer from these drone
  shots" is a narrated photo-story, not the 3b1b explainer.
* **Shot treatment** (`brain/treat.py` over `brain/tiles.py`): every shot tile (`vstudio.shots` moments when the
  engine has them, else one tile per clip) gets hold length, speed (1x | slow motion only where the cadence stays even:
  60p at 0.5x or RIFE frames | one speed ramp in a beat short), reframe (follow face / subject / steady centre for a
  wide view, when the output aspect differs), the join (cut | beat cut | dissolve where the light / place / time of
  day changes | match cut | a morph for a jump cut inside one take, a small punch-in without RIFE | continuous),
  exposure / colour match against the film's median and hero shot, deflicker for a pumping drone, where text may
  sit, stabilise; each used shot names the effect-catalogue entries it is made with (`effects`: `xfade-joins`,
  `morph-cuts` (`vstudio.morphcut` / `vstudio.rife` when the RIFE model is downloaded), `punch-in`, `speed-ramps`,
  `stabilize`). Quality and darkness are measured against the film's own light (a night film keeps its night
  shots). Each choice keeps its candidates with a 0-1 fit (`choices`) so "why this effect" can say "dissolve .95 vs
  cut .55"; close ones go to the AI judge when asked; her changes (`brain shot --set transition=cut`) win.
* **Generation proposals** (`brain/genplan.py`): by stage (`planned` -> `cut` -> `review`): an establishing shot
  when the film opens close, extra shots when the usable footage is well under the asked length, a cover background
  when no frame is clean, a first+last-frame bridge across a place / time jump in a narrated piece, a steady
  image-to-video take of a moment whose only shot is too dark / shaky, one illustrative shot after 25 s of talking
  head alone. Each is a brief (mode, prompt, source still, seconds) with a price from the Create rate cards (Kling
  first). **Nothing is spent**: autopilot only proposes; her Approve carries the proposal's confirm code (this price,
  `brain decide --approve --code`), is recorded in project.yaml (`brain.gen`), and the generation itself goes through
  the Create spend gate. Generated shots are labelled AI.

* **Steering the builders** (`brain/steer.py`): the plan (her per-shot changes in it) is each builder's own edit
  decisions. Calm vlog (build_vlog): segments with the window, `xfade` = the join into it (a dissolve's seconds, 0 = a
  hard cut), `speed: 0.5` where slow motion is planned, `stabilize`, `brain` = the shot id. Beat short (build_fun):
  beat-aligned holds (1 / 2 / 4 beats), the one speed ramp (`ramp: fast-slow-fast`, 4 beats), `ramp: slowmo` where
  planned (RIFE in-betweens under 50p). Photo story: the drafter gets the moments with their in-points, joins and the
  text-safe third, plus the stills worth cutting for the cover; the drafted spec's video shots get `tr` (fade | cut)
  and `label_at` (upper | lower) where the drafter left them open - always where she chose. Talking head: each jump
  cut of the cleaned body is smoothed as the plan of its span says - `morph` (RIFE) | `punch` (a small punch-in, compose
  `PUNCH`) | `cut` - and her placed B-roll is a cut-away at its sentence (compose `BROLL`); the stage keys carry them.
  The AI drafter's own windows get the plan's treatment where they overlap (`steer.annotate`); her change of a shot
  reaches the drafted edit files at once (`steer.restyle`) and the desk re-renders.
* **Per-shot edit list**: every builder writes `<master>.edl.json` (talking head: the compose stage's `edl.json`):
  `shots [{i, t0, t1, src, src_in, src_out, join, speed, role, brain}]`. `brain shots --dir P --output <id>` joins it
  with the plan (why, choices, her changes; a generated take with its proposal) - the clip timeline's Shots lane.
* **Generating a proposal** (`brain/generate.py` over `vstudio.create.oneoff`, the Create spend gate for one job
  outside an episode): `brain estimate` prices it (rate card, the month cap, the service ready, its credits, its own
  quote) with an 8-hex confirm code that expires in 15 min - nothing is sent; her click in the gate runs `brain
  generate --estimate --confirm --max-cny --code`: her approval at this price, ONE submit (never retried; a timeout
  after the request left is `unknown-charge` in `state/brain/gen/spend.jsonl`, counted in the month), poll, download
  to `state/brain/gen/`, then `place`: a calm / fun vlog's edit.json gets an `ai: true` segment / shot at the anchor
  (the opening, after the shot a bridge leaves, where the weak shot was, the end), a photo story's spec a video shot,
  a talking head a cut-away; the render watches those files. `brain place --undo` takes it out again (the paid take
  is kept; a generated proposal cannot be "undone" like an idea). Only her click calls `generate`; the autopilot,
  `show` and every stage never do. Tests use Create's provider stand-ins (`tests/create_fake.py`).

`python -m vstudio.brain show --dir <project> [--refresh] --json` computes what is missing (tiles, signals, plan,
proposals: `state/brain/`, the tile stills in `state/brain/thumbs/`) and returns the doc the desk shows.
