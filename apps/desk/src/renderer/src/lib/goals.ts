// Goal mode in the UI: the groups of videos one request asked for (engine/desk_engine/goals.py). Pure helpers (unit
// tested) + one hook that keeps the goals fresh (engine events; a short poll while one is going).
import { useEffect, useMemo } from 'react';
import type { Goal, GoalVideo } from '../../../shared/goal';
import type { PilotFailure } from '../../../shared/v02';
import { getLang, has, t, tk, type MessageKey } from '../i18n';
import { useEngine, useLoad } from './engine';
import { failureReason } from '../v4/Failure';

export const GOAL_POLL_MS = 4000;

/** Going: being read, waiting for her plan approval, or being made. */
export function goalActive(g: Pick<Goal, 'state'>): boolean {
  return g.state === 'surveying' || g.state === 'planned' || g.state === 'running';
}

/** The goal's title: the AI's one line, else her request. */
export function goalTitle(g: Pick<Goal, 'goal' | 'prompt'>): string {
  const s = (g.goal || g.prompt || '').trim();
  return s.length > 80 ? `${s.slice(0, 79)}…` : s;
}

/** A video's title in the UI's language (the Chinese title when the UI is Chinese and the AI gave one). */
export function videoTitle(v: Pick<GoalVideo, 'title' | 'title_zh'>, lang = getLang()): string {
  return (lang === 'zh-CN' && v.title_zh) || v.title;
}

/** The videos of the group (the ones dropped on the plan card are not part of it). */
export function groupVideos(g: Pick<Goal, 'videos' | 'state'>): GoalVideo[] {
  return g.videos.filter((v) => v.state !== 'skipped' && !(g.state === 'planned' && v.planned_out));
}

/** 0..1 for the group's bar: made and dropped count whole, a video being made its own share. */
export function goalPct(g: Pick<Goal, 'videos' | 'state'>): number {
  const vs = groupVideos(g);
  if (!vs.length) return 0;
  const n = vs.reduce((a, v) => a + (v.state === 'made' || v.state === 'dropped' ? 1 : v.state === 'making' || v.state === 'you' ? Math.min(0.95, v.progress ?? 0.1) : v.state === 'planning' ? 0.05 : 0), 0);
  return Math.max(0, Math.min(1, n / vs.length));
}

/** The dot of a video's row. */
export function videoTone(v: Pick<GoalVideo, 'state' | 'queued'>): 'run' | 'you' | 'error' | 'done' | 'off' {
  switch (v.state) {
    case 'made':
      return 'done';
    case 'you':
      return 'you';
    case 'dropped':
      return 'error';
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

const GOAL_CODES = new Set(['by-you', 'stopped', 'stalled', 'lost', 'plan', 'apply', 'intake', 'items-failed', 'missing', 'needs-input', 'needs-model']);

/** Why a video was dropped, in her words (the engine's failure code; goal codes have their own words). */
export function dropReason(v: Pick<GoalVideo, 'reason_code'>): string {
  const c = v.reason_code ?? '';
  if (GOAL_CODES.has(c)) return t(`goal.why.${c}` as MessageKey);
  if (/^plan-/.test(c)) return has(`goal.why.${c}`) ? tk(`goal.why.${c}`) : t('goal.why.plan');
  return failureReason({ code: c || 'unknown', state: 'failed' } as unknown as PilotFailure);
}

/** One plain line for a video's row: where it is. */
export function videoLine(v: GoalVideo): string {
  switch (v.state) {
    case 'planned':
      return t('goal.v.planned');
    case 'waiting':
      return t('goal.v.waiting');
    case 'planning':
      return v.retried ? `${t('goal.v.planning')} · ${t('goal.v.retrying')}` : t('goal.v.planning');
    case 'making': {
      if (v.queued) return t('goal.v.queued');
      const pct = v.progress != null ? Math.round(v.progress * 100) : null;
      const base = pct ? t('goal.v.makingPct', { pct }) : t('goal.v.making');
      return v.retried ? `${base} · ${t('goal.v.retrying')}` : base;
    }
    case 'you':
      return t('goal.v.you');
    case 'made':
      return t('goal.v.made');
    case 'dropped':
      return `${t('goal.v.dropped')} — ${dropReason(v)}`;
    default:
      return '';
  }
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
export function videoHref(gid: string, v: Pick<GoalVideo, 'id' | 'projects'>): string {
  const item = v.projects?.[0]?.item;
  return item ? `#/studio/${item}` : goalHref(gid, v.id);
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
  const going = goals.some((g) => g.state === 'surveying' || g.state === 'running');
  useEffect(() => {
    if (!going) return;
    const tm = window.setInterval(reload, GOAL_POLL_MS);
    return () => window.clearInterval(tm);
  }, [going]); // eslint-disable-line react-hooks/exhaustive-deps
  return { goals, loaded: data !== null, reload };
}
