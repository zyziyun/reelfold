// Home as triage and All projects for hundreds of videos: the chips come from her own signals only, today's posts
// read as one entry per clip in plain words, the list's search / filters, and what the bulk bar can do with a pick.
import { describe, expect, it } from 'vitest';
import { setLang } from '../../src/renderer/src/i18n';
import { approveAnswer, bulkWork, canApprove, chunks, count, schedulePlan } from '../../src/renderer/src/lib/bulk';
import { homeSignals, seriesTitle, shareSignals, workSignals } from '../../src/renderer/src/lib/homeSignals';
import { selHref } from '../../src/renderer/src/lib/nav';
import type { StudioRow } from '../../src/renderer/src/lib/studio';
import { setStudioPrefs } from '../../src/renderer/src/lib/studioFlag';
import { findOptions, findRows, NO_FIND } from '../../src/renderer/src/lib/studioFind';
import type { ActionTarget } from '../../src/renderer/src/lib/rowActions';
import { outGroups, outState } from '../../src/renderer/src/v4/HomeTriage';
import type { HistoryItem } from '../../src/shared/v02';
import type { CalendarPost, Clip, InboxItem } from '../../src/shared/v04';

const NOW = new Date('2026-10-11T12:00:00').getTime();
const post = (o: Partial<CalendarPost>): CalendarPost => ({ id: o.id ?? 'p', item: 'a', clip: 'c1', title: 'Tips', cover: null, platform: 'tiktok', at: '2026-10-11T09:00', state: 'planned', ...o });
const item = (id: string, o: Partial<HistoryItem> = {}): HistoryItem =>
  ({ kind: 'project', id, dir: `/p/${id}`, name: `P ${id}`, recipe: null, client: null, created: 0, updated: 0, counts: { total: 0, green: 0, red: 0, approved: 0, done: 0, failed: 0 }, status: 'done', thumb: null, sources: ['desk'], opened: false, openable: true, ...o }) as HistoryItem;
const ask = (o: Partial<InboxItem>): InboxItem => ({ key: o.key ?? 'k', kind: 'filler-confirm', group: 'choose', project: { id: 'a', name: 'A' }, code: null, params: {}, text: null, source: 'live', ...o }) as InboxItem;
const row = (o: Partial<StudioRow>): StudioRow =>
  ({ key: o.key ?? 'a/c1', kind: 'clip', item: 'a', clip: 'c1', title: 'Tips', project: 'Weekly', pos: null, thumb: null, video: '/v.mp4', duration: 20, group: 'ready', tone: 'done', p: { state: 'ready' }, ask: null, post: null, posted: false, at: NOW / 1000, ...o }) as StudioRow;

describe('Home chips: her own signals only', () => {
  it('a post out on some of her platforms offers the others (international first); nothing posted, nothing', () => {
    const s = shareSignals([post({ id: '1', state: 'posted', platform: 'tiktok' }), post({ id: '2', platform: 'instagram', state: 'filled' })], ['xiaohongshu', 'youtube-shorts', 'tiktok', 'instagram'], NOW);
    expect(s).toHaveLength(1);
    expect(s[0]).toMatchObject({ kind: 'share', item: 'a', clip: 'c1', missing: ['youtube-shorts', 'xiaohongshu'] });
    expect(shareSignals([post({ state: 'planned' })], ['youtube'], NOW)).toEqual([]);
    // already everywhere she posts
    expect(shareSignals([post({ state: 'posted' })], ['tiktok'], NOW)).toEqual([]);
    // posted long ago: not a signal any more
    expect(shareSignals([post({ state: 'posted', at: '2026-08-01T09:00' })], ['youtube'], NOW)).toEqual([]);
  });

  it('strongest first: a new recording, a repeated request, a post to share, the next episode', () => {
    const s = homeSignals(
      { recordings: [{ path: '/w/a.mp4', name: 'a.mp4', folder: 'Rec', at: 1, size: 9 }], recurring: [{ prompt: 'weekly Q&A', n: 2, at: 1 }] },
      [item('s', { series: 'Tips' })],
      [post({ state: 'posted' })],
      ['tiktok', 'youtube'],
      NOW,
    );
    expect(s.map((x) => x.kind)).toEqual(['recording', 'again', 'share', 'series']);
  });
});

describe('Home chips: in her words, and they do the thing', () => {
  it("a series chip says the series' own name or the project's title, never a folder id", () => {
    expect(seriesTitle({ name: 'Workshop talk → 4 clips', series: 'intake-Cut-this-week-s-reco-10111539', series_name: "Cut this week's recordings int" })).toBe('Workshop talk → 4 clips');
    expect(seriesTitle({ name: 'Ep 3', series: 'tips-2026', series_name: 'Weekly tips' })).toBe('Weekly tips');
    expect(seriesTitle({ name: 'Ep 3', series: 'Weekly tips' })).toBe('Weekly tips');
    const s = workSignals([item('a', { series: 'intake-Cut-this-week-s-reco-10111539', name: 'Workshop talk → 4 clips' })]);
    expect(s[0]).toMatchObject({ kind: 'series', text: 'Workshop talk → 4 clips' });
  });
  it('a project with clips left points at that project (the chip runs it on, never an empty request)', () => {
    const s = workSignals([item('s', { series: 'Tips' }), item('u', { name: 'Office hours', counts: { total: 5, green: 0, red: 0, approved: 0, done: 2, failed: 0 } })]);
    expect(s.find((x) => x.kind === 'finish')).toMatchObject({ item: 'u', text: 'Office hours', n: 3 });
  });
  it("a post out on YouTube via her 'youtube-studio' account counts as YouTube (no raw ids in the chip)", () => {
    const s = shareSignals([post({ state: 'posted', platform: 'tiktok' })], ['tiktok', 'youtube-studio'], NOW);
    expect(s[0].missing).toEqual(['youtube']);
  });
});

describe("Home: today's posts", () => {
  it('one entry per clip and time, its platforms side by side, where it is in words', () => {
    setLang('en');
    const g = outGroups([post({ id: '1', platform: 'tiktok', state: 'posted', stats: { views: 1240 } }), post({ id: '2', platform: 'instagram', state: 'posted', stats: { views: 60 } }), post({ id: '3', clip: 'c2', at: '2026-10-11T18:30', platform: 'linkedin', state: 'filled' }), post({ id: '4', enabled: false })]);
    expect(g.map((x) => x.platforms)).toEqual([['tiktok', 'instagram'], ['linkedin']]);
    expect(outState(g[0]).text).toBe('Posted · 1,300 views');
    expect(outState(g[1]).text).toBe('Waiting on LinkedIn…');
    expect(outState(outGroups([post({})])[0]).text).toBe('Scheduled');
    expect(outState(outGroups([post({ state: 'ready' })])[0]).text).toBe('Ready to post');
  });
});

describe('All projects: search and filters', () => {
  const rows = [
    row({ key: 'a/c1', title: 'Captions people read', project: 'Weekly tips', item: 'a', i: item('a', { name: 'Weekly tips' }) }),
    row({ key: 'b/c1', item: 'b', title: 'A calmer cover', project: 'Covers', at: NOW / 1000 - 10 * 86400, i: item('b', { name: 'Covers' }) }),
    row({ key: 'r:x', kind: 'request', item: null, clip: null, title: '', r: { id: 'x', prompt: 'cut my weekly Q&A', state: 'running' } as StudioRow['r'] }),
  ];
  const posts = [post({ item: 'a', clip: 'c1', platform: 'youtube-shorts:9x16' })];
  it('words in any order, across title, project and request', () => {
    expect(findRows(rows, { ...NO_FIND, q: 'weekly' }, posts, NOW).map((r) => r.key)).toEqual(['a/c1', 'r:x']);
    expect(findRows(rows, { ...NO_FIND, q: 'cover calmer' }, posts, NOW).map((r) => r.key)).toEqual(['b/c1']);
    expect(findRows(rows, NO_FIND, posts, NOW)).toBe(rows);
  });
  it('a platform it has a post on, one project, a date', () => {
    expect(findRows(rows, { ...NO_FIND, platform: 'youtube-shorts' }, posts, NOW).map((r) => r.key)).toEqual(['a/c1']);
    expect(findRows(rows, { ...NO_FIND, project: 'b' }, posts, NOW).map((r) => r.key)).toEqual(['b/c1']);
    expect(findRows(rows, { ...NO_FIND, date: 'week' }, posts, NOW).map((r) => r.key)).toEqual(['a/c1', 'r:x']);
    expect(findOptions(rows, posts)).toEqual({ platforms: ['youtube-shorts'], projects: [['b', 'Covers'], ['a', 'Weekly tips']] });
  });
});

describe('All projects: bulk Schedule at scale', () => {
  const clip = (id: string, platforms: string[]): Clip => ({ id, title: id, files: platforms.map((p) => ({ platform: p, path: `/v/${id}-${p}.mp4` })) }) as unknown as Clip;
  it('plans from the clips the list has (no request per project), leaves scheduled ones and says what has no platform', () => {
    const by = new Map([
      ['a', ['c1', 'c2']],
      ['b', ['c1']],
      ['c', ['c9']],
    ]);
    const clips = { a: [clip('c1', ['tiktok']), clip('c2', ['youtube', 'tiktok'])], b: [clip('c1', [])], c: undefined };
    const plan = schedulePlan(by, clips, [post({ item: 'a', clip: 'c1' })], (c) => c.files.map((f) => f.platform!).filter(Boolean));
    expect(plan.todo).toEqual([{ item: 'a', clip: 'c2', platforms: ['youtube', 'tiktok'] }]);
    expect(plan.noPlatform).toBe(1);
  });
  it('hundreds of videos go in a few requests', () => {
    const xs = Array.from({ length: 230 }, (_, i) => i);
    expect(chunks(xs).map((c) => c.length)).toEqual([100, 100, 30]);
    expect(chunks([])).toEqual([]);
  });
  it('the button counts the made videos picked, the same ones Ready to post lists', () => {
    const rows = Array.from({ length: 216 }, (_, k) => row({ key: `p${k}/c1`, item: `p${k}` }));
    expect(count(bulkWork(rows, []).schedule)).toBe(216);
  });
});

describe('All projects: the bulk bar', () => {
  it('Approve takes the questions with a recommended answer, once each; Schedule the made ones not out yet', () => {
    const q = ask({ key: 'q1', options: [{ id: 'o1', text: 'cut', checked: true }, { id: 'o2', text: 'keep', checked: false }] as InboxItem['options'] });
    const fail = ask({ key: 'f', kind: 'failed', failure: { code: 'engine' } as InboxItem['failure'] });
    const rs = [row({ key: 'a/c1', ask: q, group: 'you' }), row({ key: 'a/c2', clip: 'c2', ask: q, group: 'you' }), row({ key: 'a/c3', clip: 'c3' }), row({ key: 'b/c1', item: 'b', ask: fail, group: 'you', video: null })];
    const w = bulkWork(rs, []);
    expect(w.approve.map((x) => x.key)).toEqual(['q1']);
    expect(approveAnswer(q)).toEqual({ approve: ['o1'], keep: ['o2'] });
    expect(canApprove(fail)).toBe(false);
    expect(canApprove(ask({ kind: 'needs' }))).toBe(false);
    expect([...w.schedule.entries()]).toEqual([['a', ['c3']]]);
    expect(count(w.change)).toBe(3);
  });
  it('Try again once per failed project', () => {
    const i = item('a', { failure: { code: 'engine' } as HistoryItem['failure'] });
    const xs: ActionTarget[] = [
      { key: 'a/c1', kind: 'clip', title: 'x', i },
      { key: 'a/c2', kind: 'clip', title: 'y', i },
    ];
    expect(bulkWork([], xs).retry).toHaveLength(1);
  });
});

describe('links', () => {
  it('a request picked in All projects (the Studio: its whole list)', () => {
    setStudioPrefs({ studio: true });
    expect(selHref('abc')).toBe('#/studio?f=all&sel=abc');
    setStudioPrefs({ studio: false });
    expect(selHref('abc')).toBe('#/projects?sel=abc');
  });
});
