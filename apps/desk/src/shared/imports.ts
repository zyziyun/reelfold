// Import finished videos (and their footage) for second-pass editing: the engine's answers (desk_engine/imports.py).

export interface ImportVersionCheck {
  file: string;
  platform: string | null;
  aspect: string | null;
  w: number;
  h: number;
  duration: number;
  cover: string | null;
  post: boolean;
  /** why it reads as finished: platform-name, export-name, output-folder, cover-or-post-beside, editor-tags ... */
  why: string[];
}

export interface ImportClipCheck {
  key: string;
  title: string;
  folder: string;
  versions: ImportVersionCheck[];
  /** footage files that go with it */
  sources: number;
}

export interface ImportCheck {
  ok: boolean;
  verdict: 'finished' | 'raw' | 'mixed' | 'none';
  counts: { finished: number; raw: number; covers: number; posts: number; clips: number };
  clips: ImportClipCheck[];
  sources: string[];
  raw: { path: string; why: string[] }[];
}

export interface ImportJob {
  job: string;
  state: 'copying' | 'done' | 'failed';
  progress?: number;
  item?: string;
  clip?: string;
  error?: { code?: string; message?: string; params?: Record<string, unknown> };
}

export interface ImportMatchState {
  state: 'none' | 'idle' | 'running' | 'done' | 'failed';
  progress?: number;
  matched?: number;
  shots?: number;
  coverage?: number | null;
  error?: string;
}

export interface ImportInfoClip {
  id: string;
  title: string;
  sources: string[];
  versions: { file: string; platform: string | null; original: string | null; rewritten: boolean }[];
  match: ImportMatchState;
  transcribe?: string | null;
  copy?: string | null;
}

export interface ImportInfo {
  ok: boolean;
  item: string;
  dir: string;
  title: string;
  clips: ImportInfoClip[];
}

export interface ImportTake {
  source: string;
  name: string;
  t: number;
  dur?: number;
  why?: 'same-source-after' | 'same-source-before' | 'other-source' | string;
  still: string | null;
}

export interface ImportTakes {
  ok: boolean;
  shot: number;
  original: ImportTake | null;
  takes: ImportTake[];
}

/** what an imported clip's editor document carries (``imported`` of the output doc) */
export interface ImportedDoc {
  clip: string;
  original: string | null;
  platform: string | null;
  sources: string[];
  shots: { i: number; start: number; end: number; source: string | null; t: number | null; score: number | null; swap: { source: string; t: number } | null }[] | null;
  coverage: number | null;
}
