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

export interface GoalVideo {
  id: string;
  title: string;
  title_zh?: string | null;
  kind: GoalKind;
  theme?: string | null;
  why?: string | null;
  length_s: number;
  clips: number;
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
  survey?: { totals?: { videos: number; photos: number; panoramas: number; seconds: number; days: string[] } | null; notes?: string[] | null; stories: GoalStory[] } | null;
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
}

export type GoalEditOp =
  | { op: 'drop' | 'restore'; video: string }
  | { op: 'rename'; video: string; title: string }
  | { op: 'kind'; video: string; kind: GoalKind }
  | { op: 'length'; video: string; length_s: number }
  | { op: 'merge'; videos: string[] }
  | { op: 'platforms'; video?: string; platforms: string[] };
