// v0.4 engine documents: outputs (player + second-pass editor), intake (composer -> plan card), inbox, calendar.
// Mirrors engine/desk_engine/{outputs,intake,inbox,calendar}.py.

import type { YtPublishResult, CaptionArtifact, CaptionIssue } from './publish/apiPlatforms';
import type { ImportedDoc } from './imports';

export type Aspect = '3:4' | '9:16' | '16:9' | string;

export interface ClipFile {
  sidecars?: CaptionArtifact[];
  caption_issues?: CaptionIssue[];
  path: string;
  aspect: Aspect;
  /** shown on the size chip instead of the aspect (e.g. "Edited" / "Original") */
  label?: string;
  /** the content's version (an edit's render key): a render replaces its file in place, so the player's URL carries
   * this to load the new bytes instead of the ones Chromium cached for the same URL */
  v?: string | number | null;
  w?: number | null;
  h?: number | null;
  fps?: number | null;
  duration?: number | null;
  platform?: string;
  /** every planned platform this file is for (a photo story's out/story.mp4: 小红书; out/bilibili/story.mp4: B站) */
  platforms?: string[];
  safe_box?: number[] | null;
  caption_box?: number[] | null;
}

export interface PostCopy {
  title: string;
  body: string;
  tags: string[];
}

export interface Clip {
  id: string;
  /** one title per clip: her own (title_custom), else the AI's post title, else the plan's segment title */
  title: string;
  title_custom?: boolean;
  /** done | running | queued | (batch job states) approved | packaged | failed ... */
  state: string;
  qc?: string | null;
  review?: string | null;
  files: ClipFile[];
  cover: string | null;
  /** the cover's version (its render's key): a render writes renders/<target>.cover.jpg again in place */
  cover_v?: string | number | null;
  post: PostCopy | null;
  duration: number | null;
  extra?: boolean;
  letter?: string | null;
  /** edited in the editor and rendered: files / cover are the edit's fresh final renders (what goes out) */
  edited?: boolean;
  /** edited since its last render: the original still goes out until the background render is done */
  edited_stale?: boolean;
  /** the post copy of every version, by platform (imported clips; a photo story's per-platform post.md) */
  posts?: Record<string, PostCopy>;
  /** the platforms its project plans (project.yaml params.platforms): one with no file shows as not made */
  targets?: string[];
  imported?: { sources: number } | null;
}

/** One piece of a project's making (a graded segment, a contact sheet, the cover options, the master): what the recipe
 * declares per stage (``wip`` while it runs, ``preview`` once done) and a waiting checkpoint's options. */
export interface Piece {
  job: string;
  /** its video's title */
  title: string;
  job_state?: string;
  stage: string;
  kind: 'image' | 'images' | 'video' | 'videos' | 'audio' | 'sheet';
  path: string;
  /** the recipe's words for it ({en, zh, fr?}); absent: the desk says the stage */
  label?: { en: string; zh: string; fr?: string } | null;
  /** its place among the stage's files (Segment 3 of 10) */
  n: number;
  of: number;
  state: 'running' | 'done' | 'waiting';
  checkpoint?: string;
  mtime: number;
}

export interface PiecesDoc {
  item: string;
  kind: 'batch' | 'project' | 'work';
  pieces: Piece[];
}

export interface Confirmation {
  clip: string | null;
  text: string;
  source: string;
}

export interface ClipsDoc {
  item: string;
  kind: 'batch' | 'project' | 'work';
  clips: Clip[];
  confirm: Confirmation[];
}

export interface Word {
  w: string;
  t: number;
  te: number;
  /** ASR confidence 0..1 when the transcript has it (low ones get a dotted underline) */
  p?: number;
}

/** A filler / pause / low-confidence span of the transcript (the transcript's filter chips). */
export interface TextMark {
  kind: 'filler' | 'pause' | 'lowconf';
  i0: number;
  i1: number;
  text: string;
  save_s: number;
  group: string;
}

/** What one transcript Apply did to the rest of the clip (the applied cut card). */
export interface Retimed {
  captions?: { retimed?: number; shortened?: number; removed?: number };
  effects?: { trimmed?: { id: string; effect: string; label?: { en: string; zh: string }; from_s: number; to_s: number }[]; removed?: { id: string; effect: string; label?: { en: string; zh: string } }[] };
  sfx_removed?: number;
  targets?: string[];
}

/** Kept source ranges if pending cuts were applied (engine preview_edl: same snapping / segments as the render). */
export interface PreviewEdl {
  ok: boolean;
  keep: [number, number][];
  cuts: [number, number][];
  duration: number;
  source_duration?: number;
  dropped?: { index: number; error: EngineMsg }[];
}

/** Every engine message: a code the desk localises + params, with the engine's own English / Chinese text. */
export interface EngineMsg {
  code: string;
  params?: Record<string, string | number | boolean | null>;
  message?: string;
  message_zh?: string;
}

export interface CaptionCue {
  id: string;
  start: number;
  end: number;
  text: string;
  added?: boolean;
  removed?: boolean;
}

export interface EffectInstance {
  id: string;
  effect: string;
  label?: { en: string; zh: string } | string;
  start: number;
  end: number;
  params: Record<string, unknown>;
}

/** The engine's op vocabulary (OUTPUT_EDIT.md section 3); one edit call = one undo step. */
export type EditOp =
  | { op: 'trim'; start?: number | null; end?: number | null }
  | { op: 'cut'; start: number; end: number; why?: string; words?: [number, number]; gap?: number; keep?: number; sig?: string }
  | { op: 'cut_remove'; index: number }
  | { op: 'speed'; value: number }
  | { op: 'caption_text'; cue: string; text: string }
  | { op: 'caption_style'; style: { size?: number; color?: string; highlight?: string; keywords?: string[]; position?: 'bottom' | 'middle' | 'top' } }
  | { op: 'caption_add'; start: number; end: number; text: string }
  | { op: 'caption_remove'; cue: string }
  | { op: 'title'; text: string; sub?: string }
  | { op: 'effect_add'; effect: string; start: number; end?: number; params?: Record<string, unknown> }
  | { op: 'effect_update'; id: string; start?: number; end?: number; params?: Record<string, unknown> }
  | { op: 'effect_remove'; id: string }
  | { op: 'cover'; t?: number; text?: string; style?: 'card' | 'plain' | 'band'; aspect?: '3:4' | '9:16' | '16:9'; clear?: boolean }
  | { op: 'export_add'; target: string; layout?: 'auto' | 'band'; lang?: string }
  | { op: 'shot_swap'; shot: number; source?: string; t?: number; restore?: boolean }
  | { op: 'export_remove'; target: string }
  | { op: 'reset' }
  /** one of her hand edits back to the AI version (OUTPUT_EDIT.md 6a) */
  | { op: 'override_reset'; key: string };

/** A hand edit the AI keeps (caption text / style, an effect, the title, cover, trim ...): `key` for override_reset. */
export interface Override {
  key: string;
  label?: EngineMsg | null;
  at?: string | null;
  /** she created it: "reset" removes it */
  added?: boolean;
}

/** Editing software a clip / project goes to (engine output nle): Premiere / Resolve XML, 剪映, CapCut, OTIO. */
export type NleFormat = 'xmeml' | 'jianying' | 'capcut' | 'otio';

export interface NleResult {
  ok: boolean;
  format: NleFormat;
  dir: string;
  /** the timeline file (xml / otio) or the draft folder */
  main?: string;
  files?: string[];
  notes?: string[];
  cues?: number;
  clips?: number;
  in_app?: boolean;
  /** a whole project: one result per clip */
  outputs?: NleResult[];
  failed?: { output: string; error: string }[];
}

export interface Step {
  id: string;
  at?: string;
  by?: string;
  note?: string | null;
  describe: EngineMsg[];
  retimed?: Retimed | null;
  /** cancelled by a later revert step */
  reverted?: boolean;
}

export interface OutputCaps {
  mode?: string;
  trim?: boolean;
  cut?: boolean;
  speed?: boolean;
  effects?: boolean;
  title_band?: boolean;
  cover?: boolean;
  export?: boolean;
  ai?: boolean;
  captions_ours?: boolean;
  caption_text?: boolean;
  caption_style?: boolean;
  caption_add?: boolean;
  caption_placements?: string[];
  relayout_layouts?: string[];
  [k: string]: unknown;
}

export interface OutputDoc {
  id: string;
  item: string;
  title: string;
  /** her own title (set in the editor header / on a publish card) rather than the AI's */
  title_custom?: boolean;
  state: string;
  output_id: string | null;
  file: string | null;
  files: ClipFile[];
  cover: string | null;
  cover_v?: string | number | null;
  post: PostCopy | null;
  duration: number;
  fps: number;
  w?: number | null;
  h?: number | null;
  mode: 'pipeline' | 'flattened' | string;
  caps: OutputCaps;
  caps_notes: EngineMsg[];
  words: Word[];
  /** signature of `words` (a cut by word index is refused as stale-words when it changed) */
  words_sig?: string | null;
  marks?: TextMark[];
  waveform: number[];
  captions: CaptionCue[];
  caption_style: { size?: number; color?: string; highlight?: string; keywords?: string[]; position?: string };
  effects: EffectInstance[];
  trim: { start: number; end: number } | null;
  /** why: the cut's reason (transcript, filler, pause, retake, ...; the first one when cuts merged) */
  cuts: { start: number; end: number; index: number; why?: string }[];
  /** pickups spliced in (补录), on the current timeline: their words are the ones inside [start, end] */
  pickups?: Pickup[];
  /** the clip is a take from Record yourself: Finish / Takes / Record another take */
  recording?: { session: string; dir: string; script: boolean; group?: string | null; created?: string | null; studio?: boolean } | null;
  speed: number;
  title_band: { text: string; sub?: string } | null;
  cover_edit: { t?: number; text?: string; style?: string; aspect?: string } | null;
  exports: { target: string; layout?: string; lang?: string | null }[];
  /** the platforms the clip is made for (its project's own): what its schedule offers on by default */
  targets?: string[];
  /** a finished video imported for second-pass editing: its footage and matched shots */
  imported?: ImportedDoc | null;
  steps: Step[];
  /** her hand edits the AI keeps (each can go back to the AI version) */
  overrides?: Override[];
  undo: number;
  redo: number;
  renders: { target: string; quality?: string; file: string; fresh?: boolean; simulated?: boolean; key?: string | number | null; at?: string | null; cover?: string | null }[];
  warnings: EngineMsg[];
  safe_box?: number[] | null;
  caption_box?: number[] | null;
  engine: 'real' | 'desk';
}

export interface Pickup {
  id: string;
  start: number;
  end: number;
  text: string;
  replaced: string;
}

export interface EffectDef {
  id: string;
  label: { en: string; zh: string };
  description?: { en: string; zh: string };
  category?: string;
  stage?: string;
  default_dur?: number;
  whole?: boolean;
  /** JSON-Schema subset: {type, default, minimum, maximum, enum, required, format, x-zh} */
  params: Record<string, { type?: string; default?: unknown; minimum?: number; maximum?: number; enum?: string[]; required?: boolean; format?: string; 'x-zh'?: string }>;
  thumbnail?: string | null;
}

export interface Proposal {
  id: string;
  op: EditOp;
  describe?: EngineMsg | null;
  why?: EngineMsg | string | null;
}

export interface AskResult {
  summary?: string | null;
  proposals: Proposal[];
  dropped?: { op?: unknown; error?: EngineMsg | string }[];
  warnings?: EngineMsg[];
  engine?: string;
  /** who answered ('rules': the desk's rule-based fallback), the provider the route chose, and the fallback record
   * when another provider answered instead (vstudio.llm complete -> output ai) */
  provider?: string | null;
  model?: string | null;
  routed?: string | null;
  fallback?: { from: string; to: string; code: string; error?: string } | null;
  /** the routed provider failed and no fallback answered: rules were used */
  failed?: { provider?: string | null; code?: string | null } | null;
}

// ---------------------------------------------------------------- project-level 让 AI 改 (every clip of the page)
export type ProjectAskStage = 'read' | 'check' | 'ask' | 'plan';

export interface RerenderAction {
  kind: 'copy-prompt' | 'open-file' | 'regenerate' | 'reveal';
  label: EngineMsg;
  prompt?: string;
  file?: string;
  line?: number;
  items?: string[];
}

export interface RerenderPath {
  kind: 'rerender-scripts' | 'regenerate' | 're-export';
  message: EngineMsg;
  files?: { file: string; line: number; text: string }[];
  prompt?: string;
  items?: string[];
  actions: RerenderAction[];
}

/** The change cannot be made on these (flattened) clips: why, and the real way to get it. */
export interface NeedsRerender {
  clips: string[];
  titles: string[];
  code: string;
  reason: EngineMsg;
  targets: string[];
  /** true: the rule check answered (no model call) */
  rule?: boolean;
  paths: RerenderPath[];
}

export interface ProjectGroup {
  clip: string;
  title: string;
  mode?: string | null;
  proposals: Proposal[];
  dropped?: { op?: unknown; error?: EngineMsg | string }[];
  summary?: string | null;
  source?: string | null;
}

/** A project-level answer's control (pause, go on, take a decision back so the run asks her there). */
export interface ProjectAction {
  kind: 'stop' | 'resume' | 'reopen';
  label: EngineMsg;
  checkpoint?: string;
  item?: string;
}

export interface ProjectAskResult {
  answer: 'changes' | 'needs_rerender' | 'mixed' | 'nothing' | 'actions' | 'remake';
  /** a request about the whole project's run (pause, the music, the cover, cut it again): its controls */
  actions?: ProjectAction[];
  intent?: 'pause' | 'resume' | 'music' | 'cover' | 'recut' | null;
  groups: ProjectGroup[];
  needs_rerender: NeedsRerender | null;
  summary?: string | null;
  warnings?: EngineMsg[];
  provider?: string | null;
  model?: string | null;
  routed?: string | null;
  fallback?: { from: string; to: string; code: string; error?: string } | null;
  /** the model call failed and no fallback answered: the rule answer is what is shown */
  failed?: { provider?: string | null; code?: string | null } | null;
  cost_usd?: number | null;
  seconds?: number | null;
  model_called?: boolean;
  engine?: string;
}

export interface ProjectAskJob {
  job: string;
  item: string;
  prompt: string;
  state: 'running' | 'done' | 'failed' | 'cancelled';
  stages: { stage: ProjectAskStage; at: number; n?: number | null; provider?: string | null }[];
  notices: { kind: 'fallback' | 'watchdog'; from?: string; to?: string; code?: string; at?: number; seconds?: number }[];
  clips: string[];
  timeout: number;
  elapsed: number;
  /** the rule answer (needs_rerender) sent before the model call */
  partial?: NeedsRerender | null;
  result: ProjectAskResult | null;
  error: EngineMsg | null;
}

// ---------------------------------------------------------------- intake
export interface IntakeMaterial {
  id: string;
  path: string;
  name: string;
  kind: string;
  role?: string;
  duration?: number;
}

export interface IntakeRow {
  id: string;
  params: { range?: [number, number]; title?: string };
  why?: string;
}

export interface IntakeProject {
  id: string;
  recipe: string;
  recipe_label?: string;
  type?: string;
  name: string;
  why?: string;
  items: { method: string; count: number; rows?: IntakeRow[]; focus?: string };
  params: Record<string, unknown> & { platforms?: string[]; aspects?: string[]; max_s?: number; min_s?: number };
  checkpoints: { id: string; kind: string; label: string; needs_you: boolean }[];
  estimate: { machine_min?: number; wall_min?: number; api_usd?: number; credits?: number | null };
  outputs?: { platforms?: string[]; videos?: number };
  /** the editing template the engine picked (vstudio.brain): shown as "Cut as … · why"; changed on the project page */
  template?: { id: string; label: string; label_zh: string; by: 'rules' | 'her' | 'ai'; confidence?: number; reason: BrainText; alternatives?: { id: string; recipe: string; label: string; label_zh: string }[] };
}

export interface IntakePlan {
  version: number;
  kind: 'vstudio.intake.plan';
  id: string;
  prompt: string;
  planner: {
    provider?: string;
    model?: string | null;
    /** true: the rule planner made this plan */
    fallback?: boolean;
    seconds?: number;
    routed?: string | null;
    /** another provider answered instead of the routed one */
    provider_fallback?: { from: string; to: string; code: string; error?: string } | null;
    failure?: string | null;
  };
  materials: IntakeMaterial[];
  projects: IntakeProject[];
  series: { id: string; name: string } | null;
  /** text in ``ui_lang``; with a code (references/MESSAGES.md) the UI words it itself */
  questions: { id: string; project?: string; text: string; code?: string; params?: EngineMsg['params']; options?: string[]; default?: string }[];
  risks: (string | EngineMsg)[];
  /** each risk's message dict (code + params), in the order of ``risks`` */
  risks_info?: EngineMsg[];
  warnings: string[];
  estimate: { machine_min?: number; wall_min?: number; api_usd?: number };
  /** what only she can give before it runs (her recordings, her Notion pages): the request waits (state needs) */
  needs?: EngineMsg[];
  /** links in the request that were read (web pages, public Notion pages) */
  sources?: { url: string; title?: string; chars?: number; notion?: boolean }[];
  /** the plan's paragraph (despite the name: in ``summary_lang``) */
  summary_zh: string;
  /** the language summary_zh is written in (two-letter code; older plans: none) */
  summary_lang?: string;
  /** the language the planner wrote the questions, risks and reasons in (the UI's when the desk asked; older plans: none) */
  ui_lang?: 'en' | 'zh' | 'fr';
  revisions?: { prompt: string; at: string; changes?: string[] }[];
}

/** What a running plan / revision is doing now (the engine's ``vstudio.intake plan --json-events``, folded by the desk
 * engine): the current stage with its file / counters, and the stages seen so far. */
export type IntakeStage = 'scan' | 'probe' | 'listen' | 'faces' | 'transcribe' | 'model' | 'write';
export interface IntakeProgress {
  stage: IntakeStage;
  /** the file the stage works on (as named under the dropped folder) */
  file?: string;
  /** file i of n while reading the materials */
  i?: number;
  n?: number;
  kind?: string;
  /** transcription: seconds heard so far of total_s */
  done_s?: number;
  total_s?: number;
  /** probe: facts from the cache; transcribe: an earlier transcript was reused (shared | sidecar | audio | analysis) */
  cached?: boolean | string;
  /** the model the plan was asked of (stage model) */
  provider?: string;
  model?: string;
  /** files found under the inputs */
  files?: number;
  /** a transcript made earlier was used (kept after the transcribe stage) */
  reused?: boolean;
  seen?: IntakeStage[];
  at?: number;
}

export interface IntakeJob {
  id: string;
  /** needs: the plan waits for something only she can give (``needs``: her recordings, her Notion pages) */
  state: 'running' | 'done' | 'error' | 'stopped' | 'needs';
  started?: number;
  step?: string;
  progress?: IntakeProgress | null;
  prompt?: string;
  inputs?: string[];
  /** the planner's language for this job (``--ui-lang``): en | zh | fr */
  lang?: string | null;
  plan: IntakePlan | null;
  /** stopped: who stopped it (you | stall | goal) */
  stopped_by?: 'you' | 'stall' | 'goal' | null;
  error?: string | null;
  error_code?: import('./v02').FailureCode | null;
  error_provider?: string | null;
  applied?: { dir: string; name: string; recipe: string }[];
  /** how long the last plan / revision really took, reading the files and the AI call included (seconds) */
  seconds?: number | null;
  /** a request from Home: autopilot (applied and run at once) or ask (the plan waits for her Start) */
  mode?: 'autopilot' | 'ask' | null;
  name?: string | null;
  needs?: EngineMsg[] | null;
}

/** GET /api/intake/open: requests from Home that are not projects yet (planning, a plan waiting for her, a failure). */
export interface OpenRequest {
  id: string;
  /** stopped: she stopped it while it planned (Try again / Delete from its row menu) */
  state: 'running' | 'done' | 'error' | 'needs' | 'stopped';
  step?: string | null;
  mode: 'autopilot' | 'ask';
  prompt?: string | null;
  inputs: string[];
  started?: number | null;
  progress?: IntakeProgress | null;
  error_code?: import('./v02').FailureCode | null;
  error?: string | null;
  /** the plan's first project name once planned */
  name?: string | null;
  projects?: number | null;
  failed_apply?: boolean;
  /** state needs: what it waits for */
  needs?: EngineMsg[] | null;
  /** only in GET /api/intake/open?archived=1 (the Studio's Archived filter) */
  archived?: boolean;
  archived_at?: number | null;
  /** a video of a goal (goal mode): the goal's id and the video's (the lists show it under its group) */
  goal?: string | null;
  goal_video?: string | null;
  /** a goal's video: its title (the row says it, never the request's raw words) */
  goal_title?: string | null;
  goal_title_zh?: string | null;
  /** stopped: who stopped it - she did (you), or the app did (stall: planning showed no progress; goal) */
  stopped_by?: 'you' | 'stall' | 'goal' | null;
  /** the AI picked for this request in the composer (absent = the app's default) */
  ai?: import('./projectAi').ProjectAi | null;
}

/** What Delete picks (POST /api/delete/*): project / batch / work folders, single videos, requests. */
export interface DeleteSel {
  goals?: string[];
  dirs?: string[];
  clips?: { item: string; clip: string }[];
  requests?: string[];
}

/** One thing in the Delete plan (engine/desk_engine/purge.py): what Reelfold made and would go, and what stays. */
export interface DeletePlanItem {
  key: string;
  kind: 'project' | 'batch' | 'work' | 'import' | 'clip' | 'request' | 'goal';
  name: string;
  ok: boolean;
  /** running | nothing-made | unsafe | not-found | made (a request already made into projects) */
  reason?: 'running' | 'nothing-made' | 'unsafe' | 'not-found' | 'made';
  dir?: string;
  id?: string;
  item?: string;
  clip?: string;
  /** a video's project */
  project?: string;
  /** the Reelfold-made paths that go */
  targets: string[];
  /** the folder goes as a whole */
  whole?: boolean;
  files: number;
  bytes: number;
  /** her footage / recordings it points at: they stay */
  keep: string[];
  /** other files of hers in the folder: they stay */
  other: string[];
}

export interface DeletePlan {
  items: DeletePlanItem[];
  keep: string[];
  files: number;
  bytes: number;
  /** signs exactly the targets she was shown (stage / hard refuse a changed plan) */
  sig: string;
}

/** POST /api/history/trash-plan: what Delete would move to the Trash, per project folder (her footage stays). */
export interface TrashPlanItem {
  dir: string;
  id?: string;
  name: string;
  ok: boolean;
  /** not-in-list | own-folder (her own folder or a batch: archive it) | running | unsafe | footage-inside */
  reason?: 'not-in-list' | 'own-folder' | 'running' | 'unsafe' | 'footage-inside';
  target?: string;
  files?: number;
  bytes?: number;
  /** her recordings the project points at: they stay */
  keep?: string[];
  inside?: string[];
}

/** One decision the autopilot took (``vstudio.project decisions``), or one she took back (``asked``). */
export interface AutopilotDecision {
  checkpoint: string;
  item: string;
  kind?: string;
  labels?: { en?: string; zh?: string };
  value?: unknown;
  by?: 'ai' | 'rules';
  reason?: string | null;
  reason_code?: string | null;
  params?: Record<string, unknown>;
  provider?: string | null;
  at?: string | null;
  asked?: boolean;
  /** taste calls (filler-confirm, hook-pick): the options, each ``checked`` as the engine decided */
  options?: InboxOption[];
}

/** The editor brain (``python -m vstudio.brain``): a reason in the two languages the engine writes */
export interface BrainText {
  en: string;
  zh: string;
}
export interface BrainWhy extends BrainText {
  code: string;
  params?: Record<string, unknown>;
}
export interface BrainTemplate {
  template: string;
  recipe: string;
  label: string;
  label_zh: string;
  /** rules: the materials; her: her words or her choice; ai: the routed AI on a close call */
  by: 'rules' | 'her' | 'ai';
  confidence: number;
  reason: BrainText;
  alternatives: { id: string; recipe: string; label: string; label_zh: string; blurb: string }[];
}
export interface BrainShot {
  id: string;
  clip: string;
  file?: string;
  start: number;
  end: number;
  thumb?: string | null;
  score?: number;
  skip: boolean;
  use?: [number, number];
  hold_s?: number;
  speed?: 'normal' | 'slowmo' | 'ramp';
  speed_x?: number;
  reframe?: string;
  transition?: { kind: string; s: number };
  text?: { ok: boolean; where: string | null };
  punch_in?: string;
  stabilize?: boolean;
  why: BrainWhy[];
  /** each decision's candidates with their fit, best first */
  choices?: Record<string, [string, number][]>;
  ambiguous?: string[];
  /** the effect catalogue entries (/api/effects) the choices are made with */
  effects?: string[];
  by: 'rules' | 'her' | 'ai';
}
export interface BrainProposal {
  id: string;
  kind: 'establishing' | 'short' | 'cover' | 'bridge' | 'weak' | 'broll';
  title: BrainText;
  why: BrainText;
  mode: string;
  prompt: string;
  source?: { clip?: string; t?: number; thumb?: string | null; shot?: string } | null;
  seconds: number;
  provider: string;
  model: string;
  estimate: { cny: number | null; unknown?: boolean; verified?: boolean; label?: string | null };
  /** proposed -> (her click in the spend gate) generating -> placed (in the edit) | generated (kept, out of the
   * edit) | failed | unknown-charge (the service did not answer after the request left: maybe charged) */
  status: 'proposed' | 'approved' | 'skipped' | 'generating' | 'generated' | 'placed' | 'failed' | 'unknown-charge';
  /** the confirm code an Approve carries (this proposal at this price) */
  code: string;
  stale?: boolean;
  /** the generated take (state/brain/gen/) */
  file?: string | null;
  placed?: { items: { item: string; file: string | null }[]; file: string; seconds: number; at: string } | null;
  run?: { task?: string | null; state: string; cny?: number | null; provider?: string; code?: string | null } | null;
  error?: string | null;
}
/** POST /api/brain/<item>/estimate: the Create spend gate's sheet for one proposal (nothing is sent) */
export interface BrainEstimate {
  id: string;
  confirm_code: string;
  max_cny: number;
  subtotal_cny: number;
  expires_at: number;
  lines: { provider: string; model: string; label: string; kind: string; seconds?: number; seconds_billed?: number | null; native_units?: number | null; cny: number | null; verified?: boolean; resolution?: string | null }[];
  /** every reason the gate would refuse now (create.provider-not-ready, create.over-cap ...) */
  codes: { code: string; params: Record<string, unknown> }[];
  month: { cap: number | null; used: number; left_after: number | null };
  proposal: { id: string; code: string; kind: string; title: BrainText; why: BrainText; mode: string; seconds: number; provider: string; model: string };
}
/** GET /api/brain/<item>/shots?clip=: the clip's per-shot edit list joined with the plan */
export interface ClipShot {
  i: number;
  t0: number;
  t1: number;
  src?: string | null;
  file?: string | null;
  src_in?: number | null;
  src_out?: number | null;
  join?: string | null;
  speed?: number | null;
  role?: string | null;
  ramp?: string | null;
  ai?: boolean;
  brain: (Partial<BrainShot> & { id: string }) | null;
  gen: { id: string; kind: string; title: BrainText; why: BrainText; status: string; mode?: string; provider?: string } | null;
}
export interface ClipShots {
  item: string;
  supported: boolean;
  builder?: string;
  duration?: number | null;
  shots: ClipShot[];
  fresh?: boolean;
  reason?: string;
}
export interface BrainDoc {
  template: BrainTemplate | null;
  plan: { template: string; shots: BrainShot[]; summary: Record<string, unknown> & { used: number; shots: number; seconds: number } } | null;
  proposals: BrainProposal[];
  cost: { n: number; cny: number; unknown: number };
  stage: 'planned' | 'cut' | 'review';
}
/** GET /api/brain/<item> */
export interface BrainState {
  item: string;
  supported: boolean;
  state?: 'ready' | 'computing' | 'failed';
  doc?: BrainDoc | null;
  error?: string;
  /** generations running / just ended in this desk session: proposal id -> {state, error?, code?, params?} */
  generating?: Record<string, { state: string; error?: string | null; code?: string | null; params?: Record<string, unknown> | null }>;
}

/** GET /api/autopilot/<item> */
export interface AutopilotDoc {
  item: string;
  supported: boolean;
  running: boolean;
  queued: number | null;
  autopilot: { on: boolean; spend_cap?: number; judge?: boolean; lang?: string; ask?: string[] } | null;
  decisions: AutopilotDecision[];
  /** standing per-video settings among the answers (vertical framing, which post copy), whoever chose them; and a
   * finished clip's part that can be made again (an explainer's visuals: ``remake_as: 'visuals'``) */
  choices?: AutopilotChoice[];
  /** how the last run / remake failed (a remake whose visuals no model drew), or null */
  failure?: import('./v02').PilotFailure | null;
}

export interface AutopilotChoice {
  checkpoint: string;
  kind: string;
  item: string;
  /** null: nobody picked (a project made before the recipe asked: its post copy was never written) */
  pick: number | null;
  /** the picked option's kind (framing: follow | blur; copy: ai | rules) */
  choice: string | null;
  /** the option kinds in their order (the answer is an option index) */
  options?: string[];
  /** before: made before the recipe asked - read from the clip's files (its exports) */
  by: 'ai' | 'rules' | 'her' | 'before';
  /** a part of the finished clip the engine can make again under this name (``visuals``: the explainer's scenes) */
  remake_as?: string;
  /** the visuals: the scenes the last redo could not draw and kept (``before``: its old version, ``diagram``: a
   * simple diagram from its cues) - "13 of 14 scenes redrawn; scene 14 kept as before" + Redraw scene 14
   * (``options: ['missing']``) */
  kept?: { id: string; n: number; how: 'before' | 'diagram'; why?: string }[];
  total?: number | null;
  /** the cast voice (``remake_as: 'voice'``, ``choice`` = the speaker): its name in en / zh and why it was picked */
  label?: string | null;
  label_zh?: string | null;
  reason?: string | null;
}

// ---------------------------------------------------------------- inbox
export type InboxGroup = 'failed' | 'choose' | 'review' | 'spend' | 'other';

/** One plain-language choice of an inbox item: what it is about (label / quote), what it saves, where to watch it. */
export interface InboxOption {
  id: string;
  clip?: string | null;
  /** the desk clip id (editor link + preview) and its title */
  clip_id?: string | null;
  clip_title?: string | null;
  /** the engine's own note (kept for search; never shown when a label exists) */
  text: string;
  checked?: boolean;
  kind?: string;
  label?: EngineMsg | null;
  detail?: EngineMsg | null;
  quote?: string | null;
  /** seconds this edit saves (negative) */
  secs?: number | null;
  approx?: boolean;
  /** seconds in the clip where the cut sits (the after preview plays ±3 s around it) */
  at?: number | null;
  /** the source recording around the cut (before preview), when it is in the folder */
  before?: { file: string; at: number } | null;
  file?: string | null;
  cover?: string | null;
  choices?: { id: string; label: EngineMsg; secs?: number | null; recommended?: boolean }[] | null;
  choice?: string | null;
  recommended?: boolean;
  /** an engine filler cut: the words around it (finds it in the clip's transcript) */
  ctx?: { before?: string | null; after?: string | null } | null;
  /** a publish option: the platform id and the frame shape ("3:4") it is made for */
  platform?: string | null;
  aspect?: string | null;
}

export interface TakeScorecard {
  hard: Record<string, boolean | null>;
  soft: Record<string, boolean | null>;
  scores: Record<string, number | null>;
  evidence?: Record<string, { reason: string; time?: number | null }>;
  references?: { id: string; path: string }[];
}
export interface TakeCandidate {
  file: string;
  sheet: string;
  review: string;
  reasons: string[];
  scorecard: TakeScorecard;
  revision: string | null;
  stale: boolean;
}
export interface TakeUnit { unit: string; takes: TakeCandidate[] }

export interface InboxItem {
  take_review?: { state: "running" | "done" | "failed" } | null;
  take_units?: TakeUnit[] | null;
  key: string;
  kind: string;
  group: InboxGroup;
  project: { id: string | null; name: string | null; kind?: string; thumb?: string | null; type?: string; video?: string | null };
  code: string | null;
  params: Record<string, string | number>;
  text: string | null;
  label?: EngineMsg | null;
  options?: InboxOption[];
  reasons?: { code: string; n: number }[];
  jobs?: string[];
  minutes?: number;
  failure?: import('./v02').PilotFailure;
  source: 'picks' | 'batch' | 'live' | 'engine' | 'pilot' | 'create' | 'feedback';
  /** the item's project is archived: only that project's page lists it (not the Inbox, Home, badge, triage) */
  archived?: boolean;
  at?: number | null;
  /** Create items open their own screen (#/create/...) instead of being answered here */
  href?: string;
  /** the checkpoint's own label (author checkpoints: "Keep spans" / "保留片段") */
  labels?: { zh?: string; en?: string } | null;
  /** kind "author": the engine's draft she checks; answered {done: true} (+ spans: what she keeps) */
  author?: InboxAuthor | null;
  /** kind "needs": what a request from Home waits for (her recordings, her Notion pages) */
  need?: EngineMsg | null;
  /** kind "failed" (a request): the plan's own reason code */
  error_code?: string | null;
  /** an engine review (a layout check): the pictures to look at (its stills) and the step's own help line */
  pictures?: string[];
  help?: { en?: string; zh?: string; fr?: string } | null;
  /** the step's default answer (what the AI / the rules would choose) */
  default?: unknown;
  /** an engine question about one clip: which (its title, else its place in the project) */
  clip?: { id: string; title?: string | null; n: number } | null;
  /** the voice question when the chosen paid voice has no key: the service, and the free voice this computer has
   * (null: none, so adding the key is the way). "Use the free voice" answers the default; "Add a key" opens Settings */
  no_key?: InboxNoKey | null;
}

export interface InboxNoKey {
  /** "OpenAI" */
  service: string;
  /** the paid engine chosen ("openai") */
  engine?: string | null;
  /** the free voice installed here ("kokoro"), null when there is none */
  free_engine?: string | null;
  free_voice?: string | null;
}

/** A message the engine words with a code + params (the desk has the text in each UI language). */
export interface DraftMsg {
  code: string;
  params: Record<string, unknown>;
}

/** One sentence of her recording in a keep-spans review: kept or cut (with the AI's label for the cut). */
export interface DraftSegment {
  i: number;
  t: number;
  te: number;
  text: string;
  keep: boolean;
  label?: string | null;
}

/** The engine's plain-language view of a drafted file (vstudio.project.drafts): what the Inbox shows instead of it. */
export interface DraftReview {
  kind: 'keep-spans' | 'package' | 'outline' | 'text';
  by?: 'ai' | 'rules' | 'her';
  provider?: string | null;
  summary: DraftMsg;
  lines?: DraftMsg[];
  /** keep spans: the transcript as sentences, each kept or cut */
  segments?: DraftSegment[];
  kept_s?: number;
  total_s?: number;
  hooks?: number;
  speeds?: { body?: number; hooks?: number };
  /** a script: its text (what she reads) */
  text?: string;
  ai_summary?: string;
  ai_error?: string;
}

/** An author checkpoint (engine/desk_engine/inbox.py author_block): the engine drafts the file; she checks the draft
 * in plain words. ``file`` is only for "Advanced: open the file". */
export interface InboxAuthor {
  labels?: { zh?: string; en?: string };
  recipe?: string | null;
  checkpoint?: string | null;
  /** missing | template (the seeded example: not a draft) | drafted | hers */
  state?: 'missing' | 'template' | 'notes' | 'drafted' | 'hers';
  review?: DraftReview | null;
  /** the engine can draft it ("Draft it for me", "ask in plain words") */
  can_draft?: boolean;
  /** a draft is being written now */
  drafting?: boolean;
  draft_error?: string | null;
  /** ai-needs-model: the step needs an AI model and none answered (the desk words it: ``draft_error_params.what``
   * visuals | script, ``provider``) */
  draft_error_code?: string | null;
  draft_error_params?: Record<string, string>;
  /** the step needs an AI model (the explainer's script / storyboard / scenes): a rules draft is not enough */
  needs_ai?: boolean;
  /** the routed model's provider id (claude-code ...) */
  ai_provider?: string | null;
  /** who wrote the draft now in the file */
  draft_by?: 'ai' | 'rules' | 'her' | null;
  file: string | null;
  exists: boolean;
  is_dir?: boolean;
  doc?: string | null;
}

export interface InboxDoc {
  items: InboxItem[];
  at: number;
  /** answered today (the "Done today" row) */
  done_today?: number;
}

// ---------------------------------------------------------------- calendar
/** One clip on one platform at one time (the board groups a clip's rows of one day into one card). */
export interface CalendarPost {
  /** Publishing session/channel label, scoped to this post's platform. */
  account?: string | null;
  /** Explicit finished file for this post; null/unset uses platform defaults. */
  video_path?: string | null;
  id: string;
  item: string;
  clip: string;
  title: string;
  cover: string | null;
  platform: string;
  at: string;
  /** planned = draft; filled = the upload form is filled, waiting for her to press publish */
  state: 'planned' | 'ready' | 'filled' | 'uploaded' | 'scheduled' | 'posted';
  // decorated by the engine (older engines leave them out)
  status?: 'draft' | 'ready' | 'filled' | 'uploaded' | 'scheduled' | 'posted';
  enabled?: boolean;
  /** her text for this platform, else the clip's post copy */
  caption?: string;
  caption_custom?: boolean;
  /** caption length counted the platform's way (X: CJK = 2) and the platform's limit */
  length?: number;
  limit?: number | null;
  warnings?: PostWarning[];
  project?: string | null;
  duration?: number | null;
  stats?: { views?: number; likes?: number };
  /** the platform's title limit (null: the platform has no title) and this title's length, counted its way */
  title_limit?: number | null;
  title_length?: number;
  /** her own title for this platform (wins over the card's `title` there); title_custom = it is set */
  platform_title?: string;
  title_custom?: boolean;
  /** posted: the post's page when it was detected / typed, when, and how (her click in the built-in browser, an
   * official API, or marked by hand) */
  url?: string;
  posted_at?: string;
  /** Last confirmed official API response, retained across restarts. */
  api_result?: YtPublishResult;
  via?: 'assisted' | 'api' | 'manual';
}

export interface PostWarning {
  kind: 'caption_too_long' | 'no_caption' | 'slot_clash' | 'title_too_long';
  platform: string;
  n?: number;
  max?: number;
  at?: string;
  other?: string;
}

export interface QueueClip {
  item: string;
  clip: string;
  title: string;
  project: string | null;
  cover: string | null;
  aspects: string[];
  duration?: number | null;
  has_post?: boolean;
}

export interface NewPost {
  account?: string | null;
  video_path?: string | null;
  platform_title?: string;
  item: string;
  clip: string;
  platform: string;
  at: string;
  caption?: string;
}

/** 「一句话排期」 preview (never written; Apply = scheduleMany(drafts)). */
export interface SchedulePlan {
  ok: boolean;
  reason: 'not_understood' | 'no_clips' | 'no_days' | null;
  text: string;
  start: string;
  drafts: (NewPost & { title?: string; cover?: string | null; project?: string | null })[];
  adjustments: { kind: 'moved'; platform: string; frm: string; to: string }[];
  platforms?: string[];
  time?: string | null;
  days?: number[];
  per_day?: number;
  clips?: number;
  from_selection?: boolean;
}

export interface CalendarDoc {
  posts: CalendarPost[];
  queue: QueueClip[];
  at: number;
}

/** One line of a job's live transcript (GET /api/live/...; desk_engine.live): a model CLI's turn as it streamed
 * (``src: agent``: turn | prompt | info | thinking | tool | tool-result | say | result | error) or the engine's own
 * stages and log (``src: engine``: stage | progress | event | log | cmd | done | error | stop). Redacted. */
export interface LiveLine {
  at?: number | null;
  src: 'agent' | 'engine';
  kind: string;
  text: string;
  turn?: string;
  task?: string;
  provider?: string;
  model?: string;
  tool?: string;
  data?: Record<string, unknown>;
}

export interface LiveDoc {
  key: string;
  lines: LiveLine[];
  /** where the next read starts (opaque) */
  cursor: string;
  /** more was written than one read returns: read again from ``cursor`` */
  more: boolean;
  running: boolean;
}

/** GET /api/home/suggestions (engine/desk_engine/homesuggest.py): Home's chips, from her own signals only. */
export interface HomeSuggestions {
  /** requests she sent more than once (the newest wording), the most repeated first */
  recurring: { prompt: string; n: number; at: number | null }[];
  /** fresh recordings in a watched folder that no project or request uses yet, newest first */
  recordings: { path: string; name: string; folder: string; at: number; size: number }[];
}
