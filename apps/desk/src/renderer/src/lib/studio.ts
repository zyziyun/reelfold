// The Studio list (2026-10 review step 6): one row per VIDEO - every clip of every recent project, plus a row for a
// request still being planned and for a project that has no clips yet - in four groups: needs you (要你看), in
// progress (进行中), ready to post (可以发), scheduled (已排期, posted ones too). Pure (unit-tested): the Studio, its
// keys (↑ ↓ ⌘1–9), the Dock badge and the notifications share it.
import type { HistoryItem } from '../../../shared/v02';
import type { CalendarPost, Clip, InboxItem, OpenRequest } from '../../../shared/v04';
import { itemPipeline, requestPipeline, type Pipeline } from './pipeline';
import { clipStatus } from './status';

import { STUDIO_GROUPS as GROUPS } from '../../../shared/videoStatus';

export type StudioGroup = (typeof GROUPS)[number];
export type StudioFilter = 'all' | StudioGroup;
export const STUDIO_GROUPS: StudioGroup[] = [...GROUPS];
export const STUDIO_FILTERS: StudioFilter[] = ['all', ...STUDIO_GROUPS];

export interface StudioRow {
  /** `<project>/<clip>` | `p:<project>` | `r:<request>` */
  key: string;
  kind: 'clip' | 'project' | 'request';
  item: string | null;
  clip: string | null;
  title: string;
  /** the project's name (the row's second line says which project, 1/3) */
  project: string | null;
  /** n of N clips in its project */
  pos: [number, number] | null;
  thumb: string | null;
  /** the thumb's version (a render's cover replaced in place) */
  thumbV?: string | number | null;
  video: string | null;
  duration: number | null;
  /** a clip row: its state in the run (a clip with no file that is not made yet is not an empty video) */
  clipState?: Clip['state'];
  group: StudioGroup;
  /** the dot: run (making), you (waits for her), error, done, off (queued) */
  tone: 'run' | 'you' | 'error' | 'done' | 'off';
  p: Pipeline;
  /** the question waiting for her about this video (the page shows it at the top) */
  ask: InboxItem | null;
  /** its next post (scheduled) or its last one (posted) */
  post: CalendarPost | null;
  posted: boolean;
  /** sort: newest first inside a group */
  at: number;
  i?: HistoryItem;
  r?: OpenRequest;
  /** a project with several videos: its row is the header its videos sit under (the whole-project question as its
   * badge), never a sibling row of its own */
  header?: boolean;
}

const RECENT_S = 14 * 86400;

/** The inbox items about one clip (an option names it, or the item lists its job) and the ones about its project. */
export function asksFor(items: InboxItem[], project: string, clip: string | null): InboxItem[] {
  return items.filter((x) => x.project.id === project && (clip == null ? !clipOf(x) : clipOf(x) === clip));
}

/** The clip an inbox item is about (its first option with a clip, else its only job), or null for the project. */
export function clipOf(x: InboxItem): string | null {
  const o = (x.options ?? []).find((y) => y.clip_id);
  if (o?.clip_id) return o.clip_id;
  return x.jobs?.length === 1 ? x.jobs[0] : null;
}

function clipGroup(c: Clip, mine: CalendarPost[], ask: boolean, projectRunning: boolean): { group: StudioGroup; tone: StudioRow['tone']; post: CalendarPost | null; posted: boolean } {
  const st = clipStatus(c);
  const made = c.files.length > 0 && c.state !== 'running' && c.state !== 'queued' && c.state !== 'planned';
  const on = mine.filter((p) => p.enabled !== false);
  const next = on.filter((p) => p.state !== 'posted').sort((a, b) => a.at.localeCompare(b.at))[0] ?? null;
  const last = on.filter((p) => p.state === 'posted').sort((a, b) => b.at.localeCompare(a.at))[0] ?? null;
  if (ask) return { group: 'you', tone: 'you', post: next, posted: false };
  // its project's run is still going (on autopilot it answers its own checks, and a step that failed in an earlier
  // round is being made again): in progress - never "Needs you" / "Stopped" while the run goes on
  if (projectRunning && (st === 'you' || st === 'error') && !made) return { group: 'run', tone: 'run', post: null, posted: false };
  if (st === 'you') return { group: 'you', tone: 'you', post: next, posted: false };
  if (st === 'error') return { group: 'you', tone: 'error', post: null, posted: false };
  if (!made) return { group: 'run', tone: c.state === 'running' || projectRunning ? 'run' : 'off', post: null, posted: false };
  if (next) return { group: 'scheduled', tone: 'done', post: next, posted: false };
  if (last) return { group: 'scheduled', tone: 'done', post: last, posted: true };
  return { group: 'ready', tone: 'done', post: null, posted: false };
}

const MADE: Clip['state'][] = ['done', 'approved', 'packaged', 'failed'];

/** A video with no file because it is not made yet (waiting its turn, parked at a question, being made) - not an
 * empty recording: its page says where it is instead of "nothing was made". */
export function notMadeYet(r: Pick<StudioRow, 'kind' | 'video' | 'clipState'>): boolean {
  return r.kind === 'clip' && !r.video && !!r.clipState && !MADE.includes(r.clipState);
}

/** What the Studio's rows are made from, each loaded or not yet. */
export interface StudioSources {
  history: boolean;
  requests: boolean;
  inbox: boolean;
  calendar: boolean;
  /** the recent projects whose clips the list shows */
  projects: string[];
  clips: Record<string, Clip[] | undefined>;
}

/**
 * True once every source of the rows has answered: the history, the open requests, the inbox, the calendar, and
 * the clips of every recent project. Until then the counts are not shown (and nothing is notified): a project
 * whose clips are still loading is one row that becomes one row per video a moment later ("All 55 · Ready to post
 * 51" turning into "All 58 · Ready to post 54" right after launch), and a post or a question arriving late moves
 * rows between groups.
 */
export function studioSettled(s: StudioSources): boolean {
  return s.history && s.requests && s.inbox && s.calendar && s.projects.every((id) => s.clips[id] !== undefined);
}

/**
 * Every video, grouped. `clips[project]`: the project's clips once loaded (undefined: not loaded yet -> one project
 * row). Projects finished more than 14 days ago are left out unless something about them still waits for her.
 */
export function studioRows(
  items: HistoryItem[],
  requests: OpenRequest[],
  clips: Record<string, Clip[] | undefined>,
  posts: CalendarPost[],
  inbox: InboxItem[],
  now = Date.now() / 1000,
): StudioRow[] {
  const out: StudioRow[] = [];
  // a goal's video that a project made after all: an earlier stopped / failed request for it is history, not a row
  const madeVideos = new Set(items.filter((i) => i.goal && i.goal_video).map((i) => `${i.goal}/${i.goal_video}`));
  for (const r of requests) {
    if ((r.state === 'stopped' || r.state === 'error') && r.goal && r.goal_video && madeVideos.has(`${r.goal}/${r.goal_video}`)) continue;
    const p = requestPipeline(r);
    const you = p.state === 'failed' || p.state === 'plan-ready' || p.state === 'you';
    out.push({
      key: `r:${r.id}`,
      kind: 'request',
      item: null,
      clip: null,
      // a goal's request: its video's title, never the request's raw words ("Title: … Make a 110-second …")
      title: r.goal_title || r.name || r.prompt || '',
      project: null,
      pos: null,
      thumb: null,
      video: null,
      duration: null,
      group: you ? 'you' : 'run',
      tone: p.state === 'failed' ? 'error' : you ? 'you' : p.state === 'stopped' ? 'off' : 'run',
      p,
      ask: null,
      post: null,
      posted: false,
      at: r.started ?? now,
      r,
    });
  }
  const deciding = new Set(inbox.filter((x) => x.kind !== 'failed' && x.project.id).map((x) => x.project.id!));
  for (const i of items) {
    const p = itemPipeline(i, posts, deciding.has(i.id));
    const at = i.updated ?? i.created ?? 0;
    const projAsks = asksFor(inbox, i.id, null);
    const old = now - at > RECENT_S && p.state !== 'you' && p.state !== 'failed' && p.state !== 'run' && p.state !== 'queued';
    if (old) continue;
    const cl = (clips[i.id] ?? []).filter((c) => !c.extra);
    const projectRow = (): StudioRow => ({
      key: `p:${i.id}`,
      kind: 'project',
      item: i.id,
      clip: null,
      title: i.name,
      project: null,
      pos: null,
      thumb: i.thumb ?? null,
      video: null,
      duration: null,
      group: p.state === 'you' || p.state === 'failed' ? 'you' : p.state === 'run' || p.state === 'queued' || p.state === 'stopped' ? 'run' : p.state === 'idle' && !i.missing_outputs ? 'draft' : p.state === 'idle' ? 'you' : p.state === 'scheduled' || p.state === 'out' ? 'scheduled' : 'ready',
      tone: p.state === 'failed' ? 'error' : p.state === 'you' ? 'you' : p.state === 'run' ? 'run' : p.state === 'queued' || p.state === 'idle' || p.state === 'stopped' ? 'off' : 'done',
      p,
      ask: projAsks[0] ?? null,
      post: null,
      posted: p.state === 'out',
      at,
      i,
    });
    if (!cl.length) {
      out.push(projectRow());
      continue;
    }
    // one row per video: a question about the whole project (its failure, a plan to approve, a budget) is pinned on
    // its only video; with several videos it is the badge of the project's header, the videos under it
    const single = cl.length === 1;
    const projAsk = projAsks[0] ?? null;
    if (projAsk && !single) out.push({ ...projectRow(), group: 'you', tone: projAsk.kind === 'failed' ? 'error' : 'you', header: true });
    const running = p.state === 'run';
    const at0 = out.length;
    cl.forEach((c, k) => {
      const ask = asksFor(inbox, i.id, c.id)[0] ?? (single ? projAsk : null);
      const mine = posts.filter((x) => x.item === i.id && x.clip === c.id);
      const g = clipGroup(c, mine, !!ask, running);
      if (ask?.kind === 'failed') g.tone = 'error';
      out.push({
        key: `${i.id}/${c.id}`,
        kind: 'clip',
        item: i.id,
        clip: c.id,
        title: c.title,
        project: i.name,
        pos: cl.length > 1 ? [k + 1, cl.length] : null,
        thumb: c.cover,
        thumbV: c.cover_v ?? null,
        video: c.files[0]?.path ?? null,
        duration: c.duration,
        clipState: c.state,
        group: g.group,
        tone: g.tone,
        p: g.group === 'run' ? p : { ...p, state: g.group === 'scheduled' ? (g.posted ? 'out' : 'scheduled') : g.group === 'ready' ? 'ready' : p.state },
        ask,
        post: g.post,
        posted: g.posted,
        at: at - k / 1000, // a project's clips in their own order
        i,
      });
    });
    // still making the next videos while every listed one is made (they are listed once they exist): the project
    // stays In progress as its own row - Watch all, the time left and its run page keep it until it ends
    if (running && !out.slice(at0).some((x) => x.group === 'run')) out.push(projectRow());
  }
  return out;
}

/** The list as shown for a filter: each group's pieces; a project with a question is one header in Needs you with all
 * its videos under it (they leave their own groups while Needs you is on screen). */
export function screenPieces(rows: StudioRow[], order: StudioGroup[]): { g: StudioGroup; pieces: ListPiece[] }[] {
  const groups = grouped(rows);
  const pulled = new Set(order.includes('you') ? rows.filter((r) => r.header && r.group === 'you').map((r) => r.item!) : []);
  return order.map((g) => ({ g, pieces: listPieces(groups[g].filter((r) => g === 'you' || r.kind !== 'clip' || !pulled.has(r.item!)), g === 'you' ? rows : undefined) }));
}

/** The selectable rows in screen order (↑ ↓, ⌘1–9, ⇧-click ranges). */
export function screenRows(rows: StudioRow[], order: StudioGroup[]): StudioRow[] {
  return screenPieces(rows, order).flatMap((x) => x.pieces.flatMap((p) => (p.kind === 'row' ? [p.r] : p.r ? [p.r] : [])));
}

/** Rows in screen order: needs you, in progress (making first, then queued), ready, scheduled; newest first. */
export function grouped(rows: StudioRow[]): Record<StudioGroup, StudioRow[]> {
  const g: Record<StudioGroup, StudioRow[]> = { you: [], run: [], draft: [], ready: [], scheduled: [] };
  for (const r of rows) g[r.group].push(r);
  for (const k of STUDIO_GROUPS) g[k].sort((a, b) => b.at - a.at);
  g.run.sort((a, b) => runRank(a) - runRank(b) || b.at - a.at);
  // scheduled: the next post first, posted ones after
  g.scheduled.sort((a, b) => Number(a.posted) - Number(b.posted) || (a.posted ? (b.post?.at ?? '').localeCompare(a.post?.at ?? '') : (a.post?.at ?? '').localeCompare(b.post?.at ?? '')));
  return g;
}

function runRank(r: StudioRow): number {
  if (r.kind === 'request') return 1;
  if (r.tone === 'run') return 0;
  return 2 + (r.i?.queued ?? 0) / 1000;
}

/** The rows a filter shows, in screen order (`all`: every group in turn). */
export function visible(rows: StudioRow[], f: StudioFilter): StudioRow[] {
  const g = grouped(rows);
  return f === 'all' ? STUDIO_GROUPS.flatMap((k) => g[k]) : g[f];
}

/** How many videos wait for her (the Dock badge, the filter count); a project's question counts once. */
export function needsYou(rows: StudioRow[]): number {
  return rows.filter((r) => r.group === 'you').length;
}

export type ListPiece = { kind: 'row'; r: StudioRow; nested: boolean } | { kind: 'head'; item: string; name: string; n: number; r: StudioRow | null };

/** A group's rows as the list shows them: a project with several videos once, as a header (its question row when it
 * has one, else a plain label) with its videos under it, in the place of its first video. ``pool``: where a header's
 * videos are taken from (every row: a project's question gathers all its videos under it in Needs you). */
export function listPieces(rows: StudioRow[], pool: StudioRow[] = rows): ListPiece[] {
  const out: ListPiece[] = [];
  const done = new Set<string>();
  for (const r of rows) {
    const id = r.item;
    const multi = id && (r.header || (r.kind === 'clip' && r.pos));
    if (!multi) {
      out.push({ kind: 'row', r, nested: false });
      continue;
    }
    if (done.has(id)) continue;
    done.add(id);
    const head = rows.find((x) => x.item === id && x.header) ?? null;
    const kids = (head ? pool : rows).filter((x) => x.item === id && x.kind === 'clip');
    out.push({ kind: 'head', item: id, name: head?.title ?? kids[0]?.project ?? '', n: kids[0]?.pos?.[1] ?? kids.length, r: head });
    for (const k of kids) out.push({ kind: 'row', r: k, nested: true });
  }
  return out;
}

/** Time left in a group (seconds), when the engine says for the running ones. */
export function timeLeft(rows: StudioRow[]): number | null {
  const s = new Set<string>();
  let n = 0;
  for (const r of rows) {
    const k = r.item ?? r.key;
    if (r.p.eta && !s.has(k)) {
      s.add(k);
      n = Math.max(n, r.p.eta);
    }
  }
  return n || null;
}

/** Projects created by one intake series stay together across languages and states. */
export function seriesGroups(rows: StudioRow[]): {id: string; name: string; rows: StudioRow[]}[] {
  const groups = new Map<string, {id: string; name: string; rows: StudioRow[]}>();
  for (const r of rows) {
    const id = r.i?.series;
    if (!id || r.header) continue;
    let g = groups.get(id);
    if (!g) { g = {id, name: r.i?.series_name || r.i?.name || id, rows: []}; groups.set(id, g); }
    g.rows.push(r);
  }
  return [...groups.values()].filter(g => g.rows.length > 1);
}
