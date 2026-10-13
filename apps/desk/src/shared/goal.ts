// Goal mode (engine/desk_engine/goals.py): one request that asks for several videos -> a survey of the footage, a plan
// of videos, and a group that makes them (each video an ordinary autopilot request) until every one is made or
// dropped.

export type GoalState = 'surveying' | 'planned' | 'running' | 'done' | 'failed' | 'stopped';
export type GoalVideoState = 'planned' | 'skipped' | 'waiting' | 'planning' | 'making' | 'you' | 'made' | 'dropped';
export type GoalKind = 'history' | 'film' | 'reel' | 'vlog' | 'essay' | 'photos';
export const GOAL_KINDS: GoalKind[] = ['history', 'film', 'reel', 'vlog', 'essay', 'photos'];

export interface GoalStory {
  id: string;
  place: { en: string; zh: string; km?: number } | null;
  date: string | null;
  start: string | null;
  end: string | null;
  time_of_day: string | null;
  videos: number;
  photos: number;
  panoramas: number;
  seconds: number;
  aerial: boolean;
  thumbs: string[];
  sheet?: string | null;
  /** the folder its files are in (a story with no time or place is named by it) */
  folder?: string | null;
}

export interface GoalProject {
  dir: string;
  name?: string | null;
  /** the history item id of the project (its run store's id) */
  item: string;
}

/** One language version of a video (its own project: the YouTube English cut, the Chinese cut). */
export interface GoalVersion {
  item?: string | null;
  dir?: string | null;
  name?: string | null;
  /** en | zh | fr, from the project's name; null when it has one language */
  lang?: string | null;
  state: 'made' | 'running' | 'you' | 'failed' | 'stopped';
  /** failed: the engine's failure code */
  code?: string | null;
  queued?: boolean | null;
  progress?: number | null;
}

export interface GoalVideo {
  /** the AI this video runs on (its own, else the group's; absent = the app's default); own_ai: a choice of its own */
  ai?: import('./projectAi').ProjectAi | null;
  own_ai?: boolean;
  id: string;
  title: string;
  title_zh?: string | null;
  kind: GoalKind;
  theme?: string | null;
  why?: string | null;
  /** the longest of its per-platform lengths */
  length_s: number;
  /** seconds per platform (each platform's habit for this kind, capped by the footage; her own numbers win) */
  lengths?: Record<string, number> | null;
  /** the lengths she set herself on the plan card */
  lengths_own?: Record<string, number> | null;
  /** one render per length: a long cut (YouTube / B站, chapters) and a short one (Shorts / 小红书 / TikTok) */
  cuts?: import('./platformLengths').GoalCut[] | null;
  /** the longest sensible video its usable footage carries (s) */
  possible_s?: number | null;
  /** a length she set is longer than the footage carries */
  over_footage?: boolean | null;
  clips: number;
  /** photos in its stories */
  stills?: number | null;
  stories: string[];
  platforms: string[];
  /** the sentence its own request starts from */
  request: string;
  state: GoalVideoState;
  intake?: string | null;
  projects?: GoalProject[] | null;
  attempts?: number | null;
  /** a failure it was tried again after (its code) */
  retried?: string | null;
  /** dropped: why (an engine failure code, stalled, stopped, by-you) */
  reason_code?: string | null;
  progress?: number | null;
  live?: { stage?: string; message?: string; eta?: number; code?: string; params?: Record<string, unknown> } | null;
  /** in line for a free run slot */
  queued?: boolean | null;
  started?: number | null;
  finished?: number | null;
  /** dropped on the plan card */
  planned_out?: boolean | null;
  merged_into?: string | null;
  /** the unfinished video was cleared (request deleted / project archived) */
  cleared?: boolean | null;
  /** its language versions while / once they are made (one project each) */
  versions?: GoalVersion[] | null;
  /** the last failure's words (scrubbed): shown under "details", never as the reason */
  last_error?: string | null;
  /** asked for after the group was made (the round of 「再做几条」), and her words on what about */
  extra?: number | null;
  about?: string | null;
  /** a new plan card of the group (「再做几条」): not part of the group until 「Make these」 */
  proposed?: boolean | null;
  /** its last re-cut (more / other shots): making | made | failed | undone */
  recut?: GoalRecut | null;
  /** the cut before its re-cut can come back */
  can_undo_recut?: boolean | null;
}

export interface GoalRecut {
  at: number;
  add: string[];
  drop: string[];
  shots?: number[];
  state: 'making' | 'made' | 'failed' | 'undone';
  ai?: boolean;
}

/** How far the group is from what she asked for (「补够」 makes ``need`` more). */
export interface GoalFill {
  target: number;
  min?: number | null;
  have: number;
  need: number;
}

/** Her last ask for more videos: planning -> ready (new plan cards) | empty (nothing unused left) | failed; made /
 * discarded once she answered. */
export interface GoalMore {
  state: 'planning' | 'ready' | 'empty' | 'failed' | 'made' | 'discarded';
  n: number;
  about?: string | null;
  ids?: string[];
  error?: string | null;
  error_code?: string | null;
  left?: number | null;
  at?: number;
}

export type FanRowState = 'waiting' | 'asking' | 'applying' | 'rendering' | 'proposed' | 'done' | 'nothing' | 'failed' | 'undone';

/** One edit across the group (「全部加水印」): per video, each version's clip through its own AI. */
export interface GoalFanout {
  id: string;
  prompt: string;
  scope?: { lang?: string | null } | null;
  at: number;
  state: 'running' | 'done';
  mode?: 'autopilot' | 'ask' | null;
  videos: {
    video: string;
    title?: string | null;
    title_zh?: string | null;
    state: FanRowState;
    rows: { item: string; clip?: string | null; lang?: string | null; state: FanRowState; describe?: (import('./v04').EngineMsg | string | null)[] | null; summary?: string | null; error?: string | null; step?: string | null; hold?: string | null; provider?: string | null }[];
  }[];
  counts: { done: number; nothing: number; failed: number; proposed: number; undone: number; total: number };
}

/** What one video's re-cut can pick from: its shots now and the clips no video of the group plays. */
export interface GoalCandidates {
  video: string;
  shots: { i: number; src: string; name: string; src_in?: number | null; src_out?: number | null; thumb?: string | null }[];
  free: { path: string; name: string; dur?: number | null; story?: string | null; place?: { en: string; zh: string } | null; date?: string | null; start?: string | null; same: boolean; thumb?: string | null }[];
  used_elsewhere?: number;
}

export type GoalIntent =
  | { kind: 'more'; n?: number | null; to?: number | null; about?: string | null }
  | { kind: 'recut'; video?: string | null; shot?: number | null; mode: 'add' | 'replace' | 'swap' }
  | { kind: 'fanout'; scope?: { lang?: string } | null }
  | { kind: 'empty' };

/** How many videos she asked for, and whether the plan reached it (lib/vstudio/intake/goal.py ``count``). */
export interface GoalCount {
  asked?: number | null;
  min?: number | null;
  max?: number | null;
  planned: number;
  /** fewer than her minimum: the footage cannot carry more */
  short?: boolean | null;
  /** the AI's own line on why (in the UI language) */
  reason?: string | null;
  /** stories that are photos / panoramas only, and stories with too little video */
  photo_only?: number | null;
  thin?: number | null;
}

export interface GoalCounts {
  total: number;
  made: number;
  dropped: number;
  making: number;
  you: number;
  waiting: number;
}

export interface GoalProgress {
  stage?: string;
  file?: string;
  i?: number;
  n?: number;
  kind?: string;
  files?: number;
  provider?: string;
  seen?: string[];
}

export interface Goal {
  /** the group's AI (the composer's choice; absent = the app's default) */
  ai?: import('./projectAi').ProjectAi | null;
  id: string;
  prompt: string;
  inputs: string[];
  platforms?: string[] | null;
  lang?: string | null;
  mode: 'autopilot' | 'ask';
  state: GoalState;
  step?: string | null;
  /** the goal in one line (the AI's words, in the UI language) */
  goal?: string | null;
  /** "default": the rule planner's stock line - shown in the UI's language, not as stored */
  goal_code?: 'default' | null;
  survey?: {
    totals?: { videos: number; photos: number; panoramas: number; seconds: number; days: string[] } | null;
    /** what no video uses: stories left out, and the photos / panoramas (videos are cut from clips) */
    unused?: { stories: string[]; photos: number; panoramas: number } | null;
    notes?: string[] | null;
    stories: GoalStory[];
  } | null;
  planner?: { provider?: string | null; model?: string | null; fallback?: boolean | null; reason?: string | null } | null;
  error?: string | null;
  error_code?: string | null;
  progress?: GoalProgress | null;
  created: number;
  updated?: number | null;
  approved?: number | null;
  finished?: number | null;
  dismissed_at?: number | null;
  videos: GoalVideo[];
  counts: GoalCounts;
  count?: GoalCount | null;
  fill?: GoalFill | null;
  more?: GoalMore | null;
  fanouts?: GoalFanout[] | null;
}

export type GoalEditOp =
  | { op: 'drop' | 'restore'; video: string }
  | { op: 'rename'; video: string; title: string }
  | { op: 'kind'; video: string; kind: GoalKind }
  | { op: 'length'; video: string; length_s: number; platform?: string; cut?: string }
  | { op: 'merge'; videos: string[] }
  | { op: 'platforms'; video?: string; platforms: string[] };
