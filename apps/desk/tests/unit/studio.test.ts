// The Studio list model (lib/studio): one row per video across projects, grouped needs you / in progress / ready /
// scheduled; a question about a clip lands on that clip, one about the project on the project's own row.
import { describe, expect, it } from 'vitest';
import { grouped, listPieces, needsYou, notMadeYet, screenPieces, screenRows, studioRows, studioSettled, visible } from '../../src/renderer/src/lib/studio';
import type { HistoryItem } from '../../src/shared/v02';
import type { CalendarPost, Clip, InboxItem, OpenRequest } from '../../src/shared/v04';

const NOW = 1_800_000_000;
const item = (id: string, x: Partial<HistoryItem> = {}): HistoryItem => ({
  kind: 'project',
  id,
  dir: `/p/${id}`,
  name: `Project ${id}`,
  recipe: 'talkinghead',
  client: null,
  created: NOW - 100,
  updated: NOW - 50,
  counts: { total: 3, green: 3, red: 0, approved: 3, done: 3, failed: 0 },
  status: 'done',
  thumb: null,
  sources: ['engine'],
  opened: false,
  openable: true,
  ...x,
});
const clip = (id: string, x: Partial<Clip> = {}): Clip => ({ id, title: `Clip ${id}`, state: 'done', files: [{ path: `/v/${id}.mp4`, aspect: '9:16' }], cover: null, post: null, duration: 20, ...x });
const post = (item: string, c: string, state: CalendarPost['state'], at = '2026-10-12T19:00'): CalendarPost => ({ id: `${item}-${c}-${state}`, item, clip: c, title: 't', cover: null, platform: 'youtube', at, state });
const ask = (key: string, project: string, clipId: string | null): InboxItem => ({ key, kind: 'confirm', group: 'choose', project: { id: project, name: project }, code: null, params: {}, text: null, options: clipId ? [{ id: '1', text: '', clip_id: clipId }] : [], source: 'engine' });
const req = (id: string, x: Partial<OpenRequest> = {}): OpenRequest => ({ id, state: 'running', mode: 'autopilot', inputs: [], prompt: 'cut it', started: NOW - 10, ...x });

describe('studio rows', () => {
  const items = [item('aaaaaaaaaaaa'), item('bbbbbbbbbbbb', { status: 'in-progress', live: { state: 'running', status: 'running', stage: 'export', progress: 0.5, eta: 240, needs_you: false, heartbeat: NOW } })];
  const clips = {
    aaaaaaaaaaaa: [clip('a1'), clip('a2'), clip('a3')],
    bbbbbbbbbbbb: undefined,
  };
  const posts = [post('aaaaaaaaaaaa', 'a2', 'planned'), post('aaaaaaaaaaaa', 'a3', 'posted', '2026-10-01T19:00')];
  const inbox = [ask('k1', 'aaaaaaaaaaaa', 'a1')];
  const rows = studioRows(items, [req('rrrrrrrrrrrr')], clips, posts, inbox, NOW);

  it('one row per clip; a project without clips yet (or a request) is one row', () => {
    expect(rows.map((r) => r.key).sort()).toEqual(['aaaaaaaaaaaa/a1', 'aaaaaaaaaaaa/a2', 'aaaaaaaaaaaa/a3', 'p:bbbbbbbbbbbb', 'r:rrrrrrrrrrrr']);
    expect(rows.find((r) => r.key === 'aaaaaaaaaaaa/a2')!.pos).toEqual([2, 3]);
  });

  it('groups: the asked clip needs her, running work is in progress, scheduled and posted ones are scheduled', () => {
    const g = grouped(rows);
    expect(g.you.map((r) => r.key)).toEqual(['aaaaaaaaaaaa/a1']);
    expect(g.you[0].ask?.key).toBe('k1');
    expect(g.run.map((r) => r.key)).toEqual(['p:bbbbbbbbbbbb', 'r:rrrrrrrrrrrr']); // making first, then planning
    expect(g.run[0].p.eta).toBe(240);
    expect(g.ready.map((r) => r.key)).toEqual([]);
    expect(g.scheduled.map((r) => [r.key, r.posted])).toEqual([
      ['aaaaaaaaaaaa/a2', false],
      ['aaaaaaaaaaaa/a3', true],
    ]);
    expect(needsYou(rows)).toBe(1);
    expect(visible(rows, 'all').map((r) => r.group)).toEqual(['you', 'run', 'run', 'scheduled', 'scheduled']);
  });

  it('one row per video: a whole-project question is pinned on its only video; old finished work stays out', () => {
    const r2 = studioRows([item('aaaaaaaaaaaa'), item('cccccccccccc', { updated: NOW - 30 * 86400 })], [], { aaaaaaaaaaaa: [clip('a1')], cccccccccccc: [clip('c1')] }, [], [ask('k2', 'aaaaaaaaaaaa', null)], NOW);
    expect(r2.map((r) => [r.key, r.group, r.ask?.key])).toEqual([['aaaaaaaaaaaa/a1', 'you', 'k2']]);
    // a failed project with one video: one row, red, the failure on it ("为什么有两个task")
    const fail: InboxItem = { ...ask('k3', 'aaaaaaaaaaaa', null), kind: 'failed' };
    const r3 = studioRows([item('aaaaaaaaaaaa')], [], { aaaaaaaaaaaa: [clip('a1', { state: 'error' })] }, [], [fail], NOW);
    expect(r3.map((r) => [r.key, r.group, r.tone])).toEqual([['aaaaaaaaaaaa/a1', 'you', 'error']]);
  });

  it('several videos: the project once, as a header with its question as the badge and every video under it', () => {
    const rows = studioRows([item('aaaaaaaaaaaa')], [], { aaaaaaaaaaaa: [clip('a1'), clip('a2'), clip('a3')] }, [post('aaaaaaaaaaaa', 'a3', 'planned')], [ask('k4', 'aaaaaaaaaaaa', null)], NOW);
    expect(rows.filter((r) => r.header).map((r) => r.key)).toEqual(['p:aaaaaaaaaaaa']);
    expect(needsYou(rows)).toBe(1);
    const all = screenPieces(rows, ['you', 'run', 'ready', 'scheduled']);
    const you = all.find((x) => x.g === 'you')!.pieces;
    expect(you.map((p) => (p.kind === 'head' ? `head:${p.r?.key}:${p.n}` : `${p.r.key}${p.nested ? ' (nested)' : ''}`))).toEqual([
      'head:p:aaaaaaaaaaaa:3',
      'aaaaaaaaaaaa/a1 (nested)',
      'aaaaaaaaaaaa/a2 (nested)',
      'aaaaaaaaaaaa/a3 (nested)',
    ]);
    // they are not listed a second time in their own groups
    expect(all.filter((x) => x.g !== 'you').flatMap((x) => x.pieces)).toEqual([]);
    expect(screenRows(rows, ['you', 'run', 'ready', 'scheduled']).map((r) => r.key)).toEqual(['p:aaaaaaaaaaaa', 'aaaaaaaaaaaa/a1', 'aaaaaaaaaaaa/a2', 'aaaaaaaaaaaa/a3']);
    // the Ready filter alone: its videos under a plain label (no question there)
    const ready = screenPieces(rows, ['ready'])[0].pieces;
    expect(ready.map((p) => (p.kind === 'head' ? `head:${p.r ? 'q' : 'label'}` : p.r.key))).toEqual(['head:label', 'aaaaaaaaaaaa/a1', 'aaaaaaaaaaaa/a2']);
    // no question: the header is a label in each group, never a row
    const quiet = studioRows([item('aaaaaaaaaaaa')], [], { aaaaaaaaaaaa: [clip('a1'), clip('a2')] }, [], [], NOW);
    expect(listPieces(grouped(quiet).ready).map((p) => p.kind)).toEqual(['head', 'row', 'row']);
  });
});

describe('a project still making its next videos', () => {
  const live = { state: 'running', status: 'running', stage: 's02:asr', progress: 0.4, eta: 14, needs_you: false, heartbeat: NOW } as const;
  const running = item('cccccccccccc', { status: 'in-progress', live });

  it('every listed video made: the project stays In progress as its own row, its made videos ready', () => {
    const rows = studioRows([running], [], { cccccccccccc: [clip('01_clip')] }, [], [], NOW);
    const g = grouped(rows);
    expect(g.run.map((r) => [r.key, r.tone])).toEqual([['p:cccccccccccc', 'run']]);
    expect(g.ready.map((r) => r.key)).toEqual(['cccccccccccc/01_clip']);
  });

  it('a video of it still being made is the In progress row: no extra project row', () => {
    const rows = studioRows([running], [], { cccccccccccc: [clip('01_clip'), clip('02_clip', { state: 'running', files: [] })] }, [], [], NOW);
    expect(grouped(rows).run.map((r) => r.key)).toEqual(['cccccccccccc/02_clip']);
  });

  it('once it ends: only its videos', () => {
    const rows = studioRows([item('cccccccccccc')], [], { cccccccccccc: [clip('01_clip')] }, [], [], NOW);
    expect(rows.map((r) => r.key)).toEqual(['cccccccccccc/01_clip']);
  });
});

describe('studio counts settle before they show', () => {
  // right after launch: the project with four videos was one row until its clips came in, so "All" and "Ready to
  // post" grew by three a few seconds later. The counts wait for every source instead.
  const items = [item('aaaaaaaaaaaa'), item('dddddddddddd')];
  const full = { aaaaaaaaaaaa: [clip('a1')], dddddddddddd: [clip('d1'), clip('d2'), clip('d3'), clip('d4')] };
  const src = { history: true, requests: true, inbox: true, calendar: true, projects: items.map((i) => i.id) };

  it('a project whose clips are still loading is one row: not settled, the count would be wrong', () => {
    const early = { aaaaaaaaaaaa: full.aaaaaaaaaaaa, dddddddddddd: undefined };
    const g0 = grouped(studioRows(items, [], early, [], [], NOW));
    const g1 = grouped(studioRows(items, [], full, [], [], NOW));
    expect([g0.ready.length, g1.ready.length]).toEqual([2, 5]);
    expect(studioSettled({ ...src, clips: early })).toBe(false);
    expect(studioSettled({ ...src, clips: full })).toBe(true);
  });

  it('waits for the history, the open requests, the inbox and the calendar too', () => {
    for (const k of ['history', 'requests', 'inbox', 'calendar'] as const) expect(studioSettled({ ...src, clips: full, [k]: false })).toBe(false);
    // a project whose clips failed to load reads [] (one project row): that is an answer, not "loading"
    expect(studioSettled({ ...src, clips: { ...full, dddddddddddd: [] } })).toBe(true);
    expect(studioSettled({ ...src, projects: [], clips: {} })).toBe(true);
  });
});

describe('a video with no file', () => {
  it('is "not made yet" while its run has not made it (waiting, queued, planned, running), "empty" only once made', () => {
    for (const s of ['waiting', 'queued', 'planned', 'running', 'needs-replan']) expect(notMadeYet({ kind: 'clip', video: null, clipState: s })).toBe(true);
    for (const s of ['done', 'approved', 'packaged', 'failed']) expect(notMadeYet({ kind: 'clip', video: null, clipState: s })).toBe(false);
    expect(notMadeYet({ kind: 'clip', video: '/v.mp4', clipState: 'waiting' })).toBe(false);
    expect(notMadeYet({ kind: 'project', video: null, clipState: 'planned' })).toBe(false);
  });
});

describe('a project whose run still goes (her DJI goal, 2026-10-13)', () => {
  const live = { state: 'running' as const, status: 'running', stage: 'en:render', progress: 0.3, eta: 120, needs_you: false, heartbeat: NOW };
  const it2 = item('cccccccccccc', { status: 'in-progress', live, autopilot: true });
  it('a version that failed in an earlier round, or waits at a check autopilot answers, is in progress - not Stopped / Needs you', () => {
    const rows = studioRows([it2], [], { cccccccccccc: [clip('en', { state: 'failed', files: [] })] }, [], [], NOW);
    expect(rows.map((r) => [r.key, r.group, r.tone])).toEqual([['cccccccccccc/en', 'run', 'run']]);
    const waiting = studioRows([it2], [], { cccccccccccc: [clip('en', { state: 'waiting', files: [] })] }, [], [], NOW);
    expect(waiting[0].group).toBe('run');
    // a question the Inbox really holds for it is hers, run or not
    const asked = studioRows([it2], [], { cccccccccccc: [clip('en', { state: 'waiting', files: [] })] }, [], [ask('q', 'cccccccccccc', 'en')], NOW);
    expect(asked[0].group).toBe('you');
  });
  it('a goal\'s request row is titled by its video', () => {
    const rows = studioRows([], [req('dddddddddddd', { prompt: 'Title: "The Needle After Dark". Make a 110-second history explainer', goal: 'g', goal_title: 'The Needle After Dark' })], {}, [], [], NOW);
    expect(rows[0].title).toBe('The Needle After Dark');
  });
});
