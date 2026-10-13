// The Studio's row menu (lib/rowActions): which actions each kind of row offers, how a selection splits into engine
// calls (Delete: requests, whole folders, single videos), ⌘ / ⇧ picking, an empty clip, a stopped request / run in the
// list, the Delete dialog's sizes, and main/trash.ts moving a pending delete's paths to the Trash (each checked again).
import { describe, expect, it, vi } from 'vitest';
import { alsoGoes, bulkActions, deleteSel, emptyClip, rangePick, rowActions, split, togglePick, type ActionTarget } from '../../src/renderer/src/lib/rowActions';
import { deleteTitle, fmtSize, okItems, refusedItems } from '../../src/renderer/src/lib/purge';
import { requestPipeline, itemPipeline } from '../../src/renderer/src/lib/pipeline';
import { studioRows } from '../../src/renderer/src/lib/studio';
import { fmtLen } from '../../src/renderer/src/i18n';
import type { HistoryItem } from '../../src/shared/v02';
import type { OpenRequest } from '../../src/shared/v04';

vi.mock('electron', () => ({ dialog: {}, shell: {} }));

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
  counts: { total: 1, green: 1, red: 0, approved: 1, done: 1, failed: 0 },
  status: 'done',
  thumb: null,
  sources: ['engine'],
  opened: false,
  openable: true,
  ...x,
});
const req = (id: string, x: Partial<OpenRequest> = {}): OpenRequest => ({
  id,
  state: 'error',
  mode: 'ask',
  inputs: [],
  prompt: 'cut it',
  started: NOW - 10,
  ...x,
});
const R = (r: OpenRequest): ActionTarget => ({
  key: `r:${r.id}`,
  kind: 'request',
  title: r.prompt ?? '',
  r,
});
const P = (i: HistoryItem): ActionTarget => ({
  key: `p:${i.id}`,
  kind: 'project',
  title: i.name,
  i,
});
const C = (i: HistoryItem, c: string): ActionTarget => ({
  key: `${i.id}/${c}`,
  kind: 'clip',
  title: c,
  i,
  clip: c,
  video: `/v/${c}.mp4`,
});

describe('row actions', () => {
  it('requests: failed / stopped try again or go; a draft goes; a planning one stops; archived restores', () => {
    expect(rowActions(R(req('a')))).toEqual(['retry', 'archive', 'delete']);
    expect(rowActions(R(req('a', { state: 'stopped' })))).toEqual(['retry', 'archive', 'delete']);
    expect(rowActions(R(req('a', { state: 'done', mode: 'ask' })))).toEqual(['archive', 'delete']);
    expect(rowActions(R(req('a', { state: 'needs' })))).toEqual(['archive', 'delete']);
    expect(rowActions(R(req('a', { state: 'running' })))).toEqual(['stop', 'archive']);
    expect(rowActions(R(req('a', { state: 'done', mode: 'autopilot' })))).toEqual(['stop', 'archive']);
    expect(rowActions(R(req('a', { archived: true })))).toEqual(['restore', 'delete']);
  });

  it('projects: running ones only stop; stopped ones try again; every kind can be deleted (Reelfold-made files only)', () => {
    expect(rowActions(P(item('a')))).toEqual(['open-folder', 'rename', 'archive', 'delete']);
    const going = item('b', {
      pilot: { started: NOW, provider: null },
      live: { state: 'running' } as HistoryItem['live'],
    });
    expect(rowActions(P(going))).toEqual(['open-folder', 'rename', 'stop']);
    expect(rowActions(P(item('q', { queued: 2 })))).toEqual(['open-folder', 'rename', 'stop']);
    // a run started outside the desk: nothing to stop from here, and it is not archived while it runs
    expect(rowActions(P(item('o', { live: { state: 'running' } as HistoryItem['live'] })))).toEqual(['open-folder', 'rename']);
    expect(rowActions(P(item('s', { stopped: NOW })))).toEqual(['open-folder', 'rename', 'retry', 'archive', 'delete']);
    expect(rowActions(P(item('w', { kind: 'work' })))).toEqual(['open-folder', 'rename', 'archive', 'delete']);
    expect(rowActions(P(item('b', { kind: 'batch' })))).toEqual(['open-folder', 'rename', 'archive', 'delete']);
    expect(rowActions(P(item('z', { archived: true })))).toEqual(['open-folder', 'rename', 'restore', 'delete']);
    expect(rowActions(P(item('y', { archived: true, kind: 'batch' })))).toEqual(['open-folder', 'rename', 'restore', 'delete']);
    expect(rowActions(C(item('v', { kind: 'batch' }), 'ep01'))).toEqual(['open-folder', 'rename', 'archive', 'delete']);
  });

  it('a selection: requests by id, one folder per project, siblings named; bulk = what every row offers', () => {
    const a = item('a');
    const xs = [R(req('r1')), C(a, 'c1'), C(a, 'c2'), P(item('b'))];
    const s = split(xs);
    expect(s.requests).toEqual(['r1']);
    expect(s.dirs).toEqual(['/p/a', '/p/b']);
    expect(alsoGoes([C(a, 'c1')], [C(a, 'c1'), C(a, 'c2'), C(a, 'c3')])).toBe(2);
    expect(bulkActions(xs)).toEqual(['archive', 'delete']);
    expect(bulkActions([...xs, R(req('r2', { state: 'running' }))])).toEqual(['archive']);
    expect(bulkActions([R(req('x', { archived: true })), P(item('y', { archived: true }))])).toEqual(['restore', 'delete']);
  });

  it('⌘-click toggles, ⇧-click picks the range from the anchor', () => {
    const order = ['a', 'b', 'c', 'd', 'e'];
    expect([...togglePick(new Set(['a']), 'c')]).toEqual(['a', 'c']);
    expect([...togglePick(new Set(['a', 'c']), 'c')]).toEqual(['a']);
    expect([...rangePick(order, 'b', 'd', new Set())].sort()).toEqual(['b', 'c', 'd']);
    expect([...rangePick(order, 'd', 'b', new Set(['a']))].sort()).toEqual(['a', 'b', 'c', 'd']);
    expect([...rangePick(order, null, 'e', new Set())]).toEqual(['e']);
  });

  it('an empty clip (no file, or an almost empty recording) is said plainly; its length is never 0:00', () => {
    expect(emptyClip(null, null)).toBe('none');
    expect(emptyClip('/v/zmian.mp4', 0.9)).toBe('short');
    expect(emptyClip('/v/ok.mp4', 12)).toBeNull();
    expect(fmtLen(0.9)).toBe('0:00.9');
    expect(fmtLen(65)).toBe('1:05');
  });

  it('stopped: a request and a run she stopped read Stopped (in progress, grey), never Not started or Needs you', () => {
    expect(requestPipeline(req('a', { state: 'stopped' })).state).toBe('stopped');
    expect(itemPipeline(item('a', { stopped: NOW, status: 'in-progress' })).state).toBe('stopped');
    const rows = studioRows([item('bbbbbbbbbbbb', { stopped: NOW, status: 'in-progress' })], [req('cccccccccccc', { state: 'stopped' })], {}, [], [], NOW);
    expect(rows.map((r) => [r.kind, r.group, r.tone])).toEqual([
      ['request', 'run', 'off'],
      ['project', 'run', 'off'],
    ]);
  });
});

describe('delete', () => {
  it('a selection -> what Delete picks: a video alone, its project whole when nothing of it is left on screen', () => {
    const a = item('a', { kind: 'batch' });
    const b = item('b');
    const all = [C(a, 'ep01'), C(a, 'ep02'), C(a, 'ep03'), C(b, 'only'), P(item('c')), R(req('r1'))];
    // one video of a 3-video batch: that video only
    expect(deleteSel([C(a, 'ep01')], all)).toEqual({ clips: [{ item: 'a', clip: 'ep01' }] });
    // every video of it picked: the batch whole
    expect(deleteSel([C(a, 'ep01'), C(a, 'ep02'), C(a, 'ep03')], all)).toEqual({ dirs: ['/p/a'] });
    // a one-video project's video: the project
    expect(deleteSel([C(b, 'only')], all)).toEqual({ dirs: ['/p/b'] });
    // a group header + one of its videos: the folder (the video goes with it); requests by id
    expect(deleteSel([P(a), C(a, 'ep02'), R(req('r1'))], all)).toEqual({ dirs: ['/p/a'], requests: ['r1'] });
  });

  it('the dialog: sizes in the right units (a comma in French), the title, ok / refused', () => {
    expect(fmtSize(2_500_000, 'en')).toBe('2.5 MB');
    expect(fmtSize(2_500_000, 'fr')).toBe('2,5 MB');
    expect(fmtSize(35_400_000, 'en')).toBe('35 MB');
    expect(fmtSize(1_230_000_000, 'en')).toBe('1.2 GB');
    expect(fmtSize(12_000, 'en')).toBe('12 KB');
    const it_ = (name: string, ok: boolean) => ({ key: name, kind: 'project' as const, name, ok, targets: [], files: 0, bytes: 0, keep: [], other: [] });
    const plan = { items: [it_('a', true), it_('b', false), it_('c', true)], keep: [], files: 0, bytes: 0, sig: 'x' };
    expect(okItems(plan).map((x) => x.name)).toEqual(['a', 'c']);
    expect(refusedItems(plan).map((x) => x.name)).toEqual(['b']);
    expect(deleteTitle([it_('a', true)])).toBe('Delete “a”?');
    expect(deleteTitle(okItems(plan))).toBe('Delete 2 items?');
  });

  it('main moves only the engine’s own paths of a pending delete to the Trash, each checked again', async () => {
    const fs = await import('node:fs');
    const os = await import('node:os');
    const path = await import('node:path');
    const { trashPending, trashStale } = await import('../../src/main/trash');
    const home = fs.mkdtempSync(path.join(os.tmpdir(), 'trash-home-'));
    const made = path.join(home, 'a', 'b', 'jobs');
    fs.mkdirSync(made, { recursive: true });
    const report = path.join(home, 'a', 'b', 'REPORT.md');
    fs.writeFileSync(report, 'x');
    const top = path.join(home, 'Desktop');
    fs.mkdirSync(top);
    const committed: [string, string[], string[]][] = [];
    const client = {
      deletePendingOne: async (id: string) => ({ id, at: 0, targets: [made, report, top, '/', 'relative/x'] }),
      deletePending: async () => ({ items: [{ id: 'aaaaaaaaaaaa', at: 0, stale: true, targets: [] }, { id: 'bbbbbbbbbbbb', at: 0, stale: false, targets: [] }] }),
      deleteCommit: async (id: string, trashed: string[], failed: string[]) => {
        committed.push([id, trashed, failed]);
        return { ok: true, deleted: [], back: failed.length ? [{ key: 'k', name: 'n' }] : [] };
      },
    } as unknown as import('../../src/shared/engineClient').EngineClient;
    const moved: string[] = [];
    const trash = async (p: string) => {
      moved.push(p);
      fs.rmSync(p, { recursive: true, force: true });
    };
    const r = await trashPending('aaaaaaaaaaaa', { client, trash, home });
    expect(moved).toEqual([made, report]); // a non-media file too (the engine named it as Reelfold's own)
    expect(r.failed).toEqual([top, '/']); // never a top folder or the root, even if asked
    expect(fs.existsSync(top)).toBe(true);
    expect(r.back).toHaveLength(1);
    expect(committed[0][0]).toBe('aaaaaaaaaaaa');
    committed.length = 0;
    expect((await trashStale({ client, trash, home })).n).toBe(1); // only the stale one
    expect(committed.map((c) => c[0])).toEqual(['aaaaaaaaaaaa']);
  });
});
