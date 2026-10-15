// Goal mode in the UI: the groups of videos one request asked for (engine/desk_engine/goals.py). Pure helpers (unit
// tested) + one hook that keeps the goals fresh (engine events; a short poll while one is going).
import { useEffect, useMemo } from 'react';
import type { Goal, GoalVersion, GoalVideo } from '../../../shared/goal';
import type { OpenRequest } from '../../../shared/v04';
import type { PilotFailure } from '../../../shared/v02';
import { getLang, has, t, tk, type MessageKey } from '../i18n';
import { useEngine, useLoad } from './engine';
import { failureReason } from '../v4/Failure';

export const GOAL_POLL_MS = 4000;

/** Going: being read, waiting for her plan approval, or being made. */
export function goalActive(g: Pick<Goal, 'state'>): boolean {
  return g.state === 'surveying' || g.state === 'planned' || g.state === 'running';
}

/** The goal's title: the AI's one line (the rule planner's stock line in the UI's language), else her request. */
export function goalTitle(g: Pick<Goal, 'goal' | 'prompt' | 'goal_code'>): string {
  const s = (g.goal_code === 'default' ? t('goal.defaultLine') : g.goal || g.prompt || '').trim();
  return s.length > 80 ? `${s.slice(0, 79)}…` : s;
}

/** A video's title in the UI's language (the Chinese title when the UI is Chinese and the AI gave one). */
export function videoTitle(v: Pick<GoalVideo, 'title' | 'title_zh'>, lang = getLang()): string {
  return (lang === 'zh-CN' && v.title_zh) || v.title;
}

/** The videos of the group (the ones dropped on the plan card are not part of it, nor new plan cards of 「再做几条」
 * until she makes them). */
export function groupVideos(g: Pick<Goal, 'videos' | 'state'>): GoalVideo[] {
  return g.videos.filter((v) => v.state !== 'skipped' && !v.proposed && !(g.state === 'planned' && v.planned_out));
}

/** The new plan cards of 「再做几条」 (not part of the group yet). */
export function proposedVideos(g: Pick<Goal, 'videos'>): GoalVideo[] {
  return g.videos.filter((v) => v.proposed);
}

/** One chip per platform and file: a file listed twice (the primary render and the platform's own export of the same
 * canvas, both "YouTube 1920×1080 · 1:20") is shown once - the platform's own file when there is one. ``key``: what
 * the chip says (its platforms, size, length). */
export function dedupeFiles<F extends { path: string; platform?: string | null; w?: number | null; h?: number | null; aspect?: string | null; duration?: number | null }>(files: F[], platformsOf: (f: F) => string[]): F[] {
  const at = new Map<string, number>();
  const out: F[] = [];
  for (const f of files) {
    const pls = [...platformsOf(f)].sort().join(',');
    const key = pls ? `${pls}|${f.w && f.h ? `${f.w}x${f.h}` : (f.aspect ?? '')}|${Math.round(f.duration ?? 0)}` : `path|${f.path}`;
    const k = at.get(key) ?? at.get(`path|${f.path}`);
    if (k !== undefined) {
      if (f.platform && !out[k].platform) out[k] = f;
      continue;
    }
    at.set(key, out.length);
    at.set(`path|${f.path}`, out.length);
    out.push(f);
  }
  return out;
}

/** "8 made of the 12 you asked for (at least 10)" when the group is short of her number, else null. */
export function fillLine(g: Pick<Goal, 'fill'>): string | null {
  const f = g.fill;
  if (!f || f.need <= 0) return null;
  return f.min && f.min !== f.target ? t('ge.fillShortMin', { have: f.have, target: f.target, min: f.min }) : t('ge.fillShort', { have: f.have, target: f.target });
}

/** 0..1 for the group's bar: made and dropped count whole, a video being made its own share. */
export function goalPct(g: Pick<Goal, 'videos' | 'state'>): number {
  const vs = groupVideos(g);
  if (!vs.length) return 0;
  const n = vs.reduce((a, v) => a + (v.state === 'made' || v.state === 'dropped' ? 1 : v.state === 'making' || v.state === 'you' ? Math.min(0.95, v.progress ?? 0.1) : v.state === 'planning' ? 0.05 : 0), 0);
  return Math.max(0, Math.min(1, n / vs.length));
}

/** The dot of a video's row. */
export function videoTone(v: Pick<GoalVideo, 'state' | 'queued' | 'versions'>): 'run' | 'you' | 'error' | 'done' | 'off' {
  switch (v.state) {
    case 'made':
      return 'done';
    case 'you':
      return 'you';
    case 'dropped':
      return v.versions?.some((x) => x.state === 'made') ? 'you' : 'error';
    case 'planning':
    case 'making':
      return v.queued ? 'off' : 'run';
    default:
      return 'off';
  }
}

/** The dot of the group's header. */
export function goalTone(g: Pick<Goal, 'state' | 'videos' | 'counts'>): 'run' | 'you' | 'error' | 'done' | 'off' {
  if (g.state === 'failed') return 'error';
  if (g.state === 'planned' || g.counts.you > 0) return 'you';
  if (g.state === 'surveying' || g.state === 'running') return 'run';
  if (g.state === 'stopped') return 'off';
  return g.counts.made ? 'done' : 'error';
}

const GOAL_CODES = new Set(['by-you', 'stopped', 'app-closed', 'stalled', 'lost', 'plan', 'apply', 'intake', 'items-failed', 'missing', 'needs-input', 'needs-model']);

/** Why a video was dropped, in her words (the engine's failure code; goal codes have their own words). */
export function dropReason(v: Pick<GoalVideo, 'reason_code'>): string {
  const c = v.reason_code ?? '';
  if (GOAL_CODES.has(c)) return t(`goal.why.${c}` as MessageKey);
  if (/^plan-/.test(c)) return has(`goal.why.${c}`) ? tk(`goal.why.${c}`) : t('goal.why.plan');
  return failureReason({ code: c || 'unknown', state: 'failed' } as unknown as PilotFailure);
}

/** Why a video is being tried again, in a few plain words ("Planning took too long"); ``making``: it failed while
 * being made (not planned). */
export function retryWhy(code: string | null | undefined, making = false): string {
  const c = code ?? '';
  if (c === 'stalled') return making ? t('goal.retryWhy.stalledMaking') : t('goal.retryWhy.stalled');
  if (c === 'lost') return t('goal.retryWhy.lost');
  if (c === 'app-closed') return t('goal.retryWhy.appClosed');
  if (c === 'plan' || /^plan-/.test(c)) return t('goal.retryWhy.plan');
  if (/^ai-/.test(c) || c === 'needs-model') return t('goal.retryWhy.ai');
  if (!c || c === 'unknown' || c === 'stopped') return t('goal.retryWhy.other');
  return t('goal.retryWhy.failed');
}

/** "Planning took too long — trying again (1 of 1)": a failure the group is retrying, and what happens next. */
function retrying(v: Pick<GoalVideo, 'retried' | 'attempts' | 'state'>): string {
  return t('goal.v.retryLine', { why: retryWhy(v.retried, v.state === 'making'), n: Math.max(1, (v.attempts ?? 2) - 1), of: 1 });
}

/** One plain line for a video's row: where it is. */
export function videoLine(v: GoalVideo): string {
  switch (v.state) {
    case 'planned':
      return t('goal.v.planned');
    case 'waiting':
      return t('goal.v.waiting');
    case 'planning':
      return v.retried ? `${t('goal.v.planning')} · ${retrying(v)}` : t('goal.v.planning');
    case 'making': {
      if (v.queued) return t('goal.v.queued');
      const pct = v.progress != null ? Math.round(v.progress * 100) : null;
      const base = pct ? t('goal.v.makingPct', { pct }) : t('goal.v.making');
      return v.retried ? `${base} · ${retrying(v)}` : base;
    }
    case 'you':
      return t('goal.v.you');
    case 'made':
      return t('goal.v.made');
    case 'dropped': {
      const made = v.versions?.filter((x) => x.state === 'made').length ?? 0;
      return made ? t('goal.v.partial', { made, total: v.versions!.length }) : `${t('goal.v.dropped')} — ${dropReason(v)}`;
    }
    default:
      return '';
  }
}

/** A language version's name: English / 中文 / Français (a video with one language: "Video"). */
export function versionLabel(x: Pick<GoalVersion, 'lang'>): string {
  return x.lang && has(`goal.ver.${x.lang}`) ? tk(`goal.ver.${x.lang}`) : t('goal.ver.one');
}

/** Where one language version is - in the group's words (never a loose "Stopped" while the group goes on). */
export function versionLine(x: GoalVersion): string {
  switch (x.state) {
    case 'made':
      return t('goal.v.made');
    case 'you':
      return t('goal.v.you');
    case 'failed':
      return x.code ? failureReason({ code: x.code, state: 'failed' } as PilotFailure) : t('goal.ver.failed');
    case 'stopped':
      return t('goal.ver.stopped');
    default: {
      if (x.queued) return t('goal.v.queued');
      const pct = x.progress != null ? Math.round(x.progress * 100) : null;
      return pct ? t('goal.v.makingPct', { pct }) : t('goal.v.making');
    }
  }
}

export function versionTone(x: Pick<GoalVersion, 'state' | 'queued'>): 'run' | 'you' | 'error' | 'done' | 'off' {
  return x.state === 'made' ? 'done' : x.state === 'you' ? 'you' : x.state === 'failed' ? 'error' : x.state === 'stopped' || x.queued ? 'off' : 'run';
}

/** A goal's request row: the video's title (never the raw request words "Title: … Make a 110-second …"). */
export function requestTitle(r: Pick<OpenRequest, 'goal_title' | 'goal_title_zh' | 'name' | 'prompt'>, lang = getLang()): string {
  if (r.goal_title) return (lang === 'zh-CN' && r.goal_title_zh) || r.goal_title;
  return r.name || r.prompt || '';
}

/** How many she asked for against what was planned (the plan card says why when it is fewer), or null. */
export function countNote(g: Pick<Goal, 'count'>): string | null {
  const c = g.count;
  if (!c || !(c.min || c.max || c.asked)) return null;
  if (c.short && c.min) {
    const why = c.reason || [c.photo_only ? t('goal.countPhotos', { n: c.photo_only }) : null, c.thin ? t('goal.countThin', { n: c.thin }) : null].filter(Boolean).join(' · ');
    return [t('goal.countShort', { min: c.min, n: c.planned }), why].filter(Boolean).join(' ');
  }
  if (c.min && c.max && c.min !== c.max) return t('goal.countOk', { min: c.min, max: c.max, n: c.planned });
  if (c.asked) return t('goal.countAbout', { want: c.asked, n: c.planned });
  return null;
}

/** The group's one line: "4 of 6 made · 1 making · 1 dropped" (or what it is doing before the videos exist). */
export function goalLine(g: Goal): string {
  if (g.state === 'surveying') return surveyLine(g);
  if (g.state === 'failed') return t('goal.failed');
  if (g.state === 'planned') return t('goal.planReady', { n: groupVideos(g).length });
  const c = g.counts;
  const bits = [t('goal.made', { made: c.made, total: c.total })];
  if (c.making) bits.push(t('goal.making', { n: c.making }));
  if (c.you) bits.push(t('goal.you', { n: c.you }));
  if (c.dropped) bits.push(t('goal.dropped', { n: c.dropped }));
  if (g.state === 'stopped') bits.push(t('goal.stopped'));
  return bits.join(' · ');
}

/** What the survey is doing right now. */
export function surveyLine(g: Pick<Goal, 'progress'>): string {
  const p = g.progress ?? {};
  switch (p.stage) {
    case 'probe':
      return p.kind === 'image' ? t('goal.step.probeImg', { i: p.i ?? 0, n: p.n ?? 0 }) : t('goal.step.probe', { i: p.i ?? 0, n: p.n ?? 0 });
    case 'cluster':
      return t('goal.step.cluster');
    case 'model':
      return t('goal.step.model');
    case 'write':
      return t('goal.step.write');
    default:
      return t('goal.step.scan');
  }
}

/** Where a video opens: its project once it has one, else the goal's page with the video picked. */
export function videoHref(gid: string, v: Pick<GoalVideo, 'id' | 'projects' | 'versions' | 'intake'>): string {
  const item = v.versions?.find((x) => x.state === 'made' && x.item)?.item ?? v.projects?.[0]?.item;
  return item ? `#/studio/${item}` : v.intake ? `#/studio?sel=${v.intake}` : goalHref(gid, v.id);
}

export function goalHref(gid: string, vid?: string): string {
  return `#/studio?goal=${gid}${vid ? `&v=${vid}` : ''}`;
}

/** The goals of the lists, fresh: engine events, and a poll every few seconds while one is going. */
export function useGoals(): { goals: Goal[]; loaded: boolean; reload: () => void } {
  const { subscribe } = useEngine();
  const { data, reload } = useLoad((c) => c.goals().catch(() => ({ goals: [] as Goal[] })), []);
  useEffect(() => subscribe((e) => void ((e.type === 'goals' || e.type === 'batches') && reload())), [subscribe]); // eslint-disable-line react-hooks/exhaustive-deps
  const goals = useMemo(() => data?.goals ?? [], [data]);
  const going = goals.some((g) => g.state === 'surveying' || g.state === 'running' || g.videos.some((v) => v.state === 'making'));
  useEffect(() => {
    if (!going) return;
    const tm = window.setInterval(reload, GOAL_POLL_MS);
    return () => window.clearInterval(tm);
  }, [going]); // eslint-disable-line react-hooks/exhaustive-deps
  return { goals, loaded: data !== null, reload };
}
