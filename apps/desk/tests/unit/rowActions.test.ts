// The Studio's row menu (lib/rowActions): which actions each kind of row offers, how a selection splits into engine
// calls, ⌘ / ⇧ picking, an empty clip, a stopped request / run in the list, and the Trash confirm (main/trash.ts) that
// names what goes and the recordings that stay.
import { describe, expect, it, vi } from 'vitest';
import { alsoGoes, bulkActions, emptyClip, rangePick, rowActions, split, togglePick, type ActionTarget } from '../../src/renderer/src/lib/rowActions';
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

  it('projects: running ones only stop; stopped ones try again; her own folder never goes to the Trash', () => {
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
    expect(rowActions(P(item('w', { kind: 'work' })))).toEqual(['open-folder', 'rename', 'archive']);
    expect(rowActions(P(item('z', { archived: true })))).toEqual(['open-folder', 'rename', 'restore', 'delete']);
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

describe('trash confirm', () => {
  it('names every folder with its size and the recordings that stay', async () => {
    const { trashDialogText } = await import('../../src/main/trash');
    const items = [
      {
        dir: '/h/p/01-x',
        name: 'talkinghead-1',
        ok: true,
        target: '/h/p',
        files: 12,
        bytes: 2_500_000,
        keep: ['/h/rec/assembled.mp4'],
      },
    ];
    const en = trashDialogText(items, 'en');
    expect(en.message).toBe('Move “talkinghead-1” to the Trash?');
    expect(en.detail).toContain('/h/p  (12 files, 2.5 MB)');
    expect(en.detail).toContain('Your recordings stay where they are:\n• /h/rec/assembled.mp4');
    expect(en.buttons).toEqual(['Cancel', 'Move to Trash']);
    const zh = trashDialogText([...items, { ...items[0], name: 'b', target: '/h/q' }], 'zh');
    expect(zh.message).toBe('把这 2 个项目移到废纸篓？');
    expect(trashDialogText(items, 'fr').detail).toContain('2,5 MB');
  });
});
