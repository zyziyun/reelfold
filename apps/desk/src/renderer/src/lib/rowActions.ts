// The Studio's row menu (「任务的删除怎么没了」): which actions a row offers - a planning request, a failed / stopped
// one, a draft, a project, one of its videos, an archived one - and how a selection splits into engine calls (requests
// by id, projects by folder, one folder per project however many of its videos are picked). Pure: unit-tested; the
// list's hover ⋯, its right-click menu, the bulk bar, ⌫ and the page header's ⋯ all read it.
import type { HistoryItem } from '../../../shared/v02';
import type { OpenRequest } from '../../../shared/v04';

export type RowAction = 'open-folder' | 'rename' | 'stop' | 'retry' | 'archive' | 'restore' | 'delete';

export interface ActionTarget {
  /** the row's key (`r:<id>` | `p:<id>` | `<project>/<clip>`) */
  key: string;
  kind: 'request' | 'project' | 'clip';
  title: string;
  r?: OpenRequest;
  i?: HistoryItem;
  /** a video's id in its project (Rename names the video, not the project) */
  clip?: string | null;
  /** a video's file (Show in Finder points at it) */
  video?: string | null;
}

/** A project's run is going (or waits in line): it is stopped first, never archived or deleted while it runs. */
export function busy(i: HistoryItem | undefined): boolean {
  return !!i && (i.live?.state === 'running' || !!i.pilot || !!i.queued);
}

/** A request still being planned (an autopilot one that planned is being made into a project). */
export function planning(r: OpenRequest): boolean {
  return r.state === 'running' || (r.state === 'done' && r.mode === 'autopilot');
}

export function archivedTarget(x: ActionTarget): boolean {
  return !!(x.r?.archived || x.i?.archived);
}

/** The actions of one row, in menu order (Archive is the default; Delete last). */
export function rowActions(x: ActionTarget): RowAction[] {
  if (x.kind === 'request') {
    const r = x.r;
    if (!r) return [];
    if (r.archived) return ['restore', 'delete'];
    if (planning(r)) return ['stop', 'archive'];
    if (r.state === 'error' || r.state === 'stopped') return ['retry', 'archive', 'delete'];
    return ['archive', 'delete']; // a plan waiting for her Start, a request waiting for her files: drafts
  }
  const i = x.i;
  if (!i) return [];
  const out: RowAction[] = ['open-folder', 'rename'];
  if (i.archived) return [...out, 'restore', ...(i.kind === 'project' ? (['delete'] as const) : [])];
  const going = busy(i);
  if (going && (i.pilot || i.queued)) out.push('stop'); // a run the desk started (an outside one is its own)
  if (!going && (i.stopped || i.failure)) out.push('retry');
  if (!going) out.push('archive');
  // only a project the app made or found goes to the Trash; a plain work folder / batch is her own folder
  if (!going && i.kind === 'project') out.push('delete');
  return out;
}

/** The actions every picked row offers (the bulk bar, ⌫): archive / restore / delete only. */
export function bulkActions(xs: ActionTarget[]): RowAction[] {
  if (!xs.length) return [];
  const sets = xs.map((x) => new Set(rowActions(x)));
  return (['archive', 'restore', 'delete'] as RowAction[]).filter((a) => sets.every((s) => s.has(a)));
}

export interface Split {
  /** request ids */
  requests: string[];
  /** project folders, one per project */
  dirs: string[];
  /** the projects (one per folder) */
  items: HistoryItem[];
}

/** A selection -> the engine's calls: requests by id, projects by folder (a project's videos are one folder). */
export function split(xs: ActionTarget[]): Split {
  const requests: string[] = [];
  const items = new Map<string, HistoryItem>();
  for (const x of xs) {
    if (x.kind === 'request' && x.r) requests.push(x.r.id);
    else if (x.i && !items.has(x.i.dir)) items.set(x.i.dir, x.i);
  }
  return {
    requests: [...new Set(requests)],
    dirs: [...items.keys()],
    items: [...items.values()],
  };
}

/** How many other videos of the same project go with a picked one (archive / delete work on the whole project). */
export function alsoGoes(xs: ActionTarget[], all: ActionTarget[]): number {
  const dirs = new Set(split(xs).dirs);
  const picked = new Set(xs.map((x) => x.key));
  return all.filter((y) => y.kind === 'clip' && y.i && dirs.has(y.i.dir) && !picked.has(y.key)).length;
}

/** ⇧-click: the rows from the anchor to this one (screen order), added to what was picked. */
export function rangePick(order: string[], anchor: string | null, key: string, picked: Set<string>): Set<string> {
  const a = anchor ? order.indexOf(anchor) : -1;
  const b = order.indexOf(key);
  if (a < 0 || b < 0) return new Set([...picked, key]);
  const [lo, hi] = a < b ? [a, b] : [b, a];
  return new Set([...picked, ...order.slice(lo, hi + 1)]);
}

/** ⌘-click: this row in or out. */
export function togglePick(picked: Set<string>, key: string): Set<string> {
  const n = new Set(picked);
  if (n.has(key)) n.delete(key);
  else n.add(key);
  return n;
}

/** A clip that has nothing to show: no file, or a file shorter than a second (an empty recording). */
export function emptyClip(video: string | null | undefined, duration: number | null | undefined): 'none' | 'short' | null {
  if (!video) return 'none';
  if (duration != null && duration < 1.5) return 'short';
  return null;
}
