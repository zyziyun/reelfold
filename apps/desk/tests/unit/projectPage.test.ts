// The project page (2026-10-11, her finished Seattle vlog): a finished project with its files is Ready to post (never
// "Not started" under In progress), the step bar reaches Ready, and the pieces of the making are said in her words.
import { afterEach, describe, expect, it } from 'vitest';
import { setLang } from '../../src/renderer/src/i18n';
import { pieceLabel } from '../../src/renderer/src/lib/pieces';
import { itemPipeline, stepState, STEPS } from '../../src/renderer/src/lib/pipeline';
import { grouped, studioRows } from '../../src/renderer/src/lib/studio';
import type { HistoryItem } from '../../src/shared/v02';
import type { Clip } from '../../src/shared/v04';

const NOW = 1_800_000_000;
const vlog: HistoryItem = {
  kind: 'project',
  id: 'aaaaaaaaaaaa',
  dir: '/p/vlog',
  name: 'Seattle Red Leaves Film',
  recipe: 'vlog',
  client: null,
  created: NOW - 100,
  updated: NOW - 50,
  counts: { total: 1, green: 0, red: 0, approved: 1, done: 1, failed: 0 },
  status: 'done',
  thumb: '/p/vlog/items/main/exports/youtube-horizontal.cover.jpg',
  sources: ['engine'],
  opened: false,
  openable: true,
  live: { state: 'done', status: 'done', stage: null, progress: 1, eta: null, needs_you: false, heartbeat: NOW - 60 },
};
const made: Clip = { id: 'main', title: 'Seattle in Red', state: 'done', review: 'approved', files: [{ path: '/p/vlog/items/main/exports/youtube-horizontal.mp4', aspect: '16:9' }, { path: '/p/vlog/items/main/exports/tiktok-vertical.mp4', aspect: '9:16' }], cover: '/p/vlog/items/main/exports/youtube-horizontal.cover.jpg', post: null, duration: 59.5 };

afterEach(() => setLang('en'));

describe('a finished project', () => {
  it('is Ready to post with its cover, never Not started', () => {
    const rows = studioRows([vlog], [], { [vlog.id]: [made] }, [], [], NOW);
    const g = grouped(rows);
    expect(g.ready.map((r) => [r.key, r.tone, r.thumb, r.video])).toEqual([['aaaaaaaaaaaa/main', 'done', made.cover, made.files[0].path]]);
    expect(g.run).toEqual([]);
  });

  it('without a file (what her vlog looked like before the engine collect) is not counted as made', () => {
    const rows = studioRows([vlog], [], { [vlog.id]: [{ ...made, files: [], cover: null }] }, [], [], NOW);
    expect(rows[0].group).toBe('run');
  });

  it('the step bar reaches Ready to post; Posted waits for a post', () => {
    const p = itemPipeline(vlog, []);
    expect(p.state).toBe('ready');
    const st = STEPS.map((s) => stepState(s, p));
    expect(st.slice(0, STEPS.indexOf('ready') + 1).every((x) => x === 'done')).toBe(true);
    expect(stepState('out', p)).toBe('todo');
  });
});

describe('pieces in words', () => {
  const seg = { stage: 'render', kind: 'videos' as const, n: 3, of: 10, label: { en: 'Graded segment', zh: '调色片段', fr: 'Plan étalonné' } };
  it('the recipe label, numbered, in her language', () => {
    expect(pieceLabel(seg)).toBe('Graded segment 3');
    setLang('zh-CN');
    expect(pieceLabel(seg)).toBe('调色片段 3');
    setLang('fr');
    expect(pieceLabel(seg)).toBe('Plan étalonné 3');
    expect(pieceLabel({ ...seg, label: { en: 'Cover options', zh: '封面候选' }, n: 1, of: 1 })).toBe('Cover options');
  });
  it('no label: the step and what it is', () => {
    expect(pieceLabel({ stage: 'export', kind: 'video', n: 1, of: 1, label: null })).toBe('Render · Video');
    expect(pieceLabel({ stage: 'sheets', kind: 'images', n: 2, of: 4 })).toBe('Picture 2');
  });
});
