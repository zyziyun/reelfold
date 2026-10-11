// The live pane's model (lib/live): ANSI-safe spans, the gutter tags, search, the text Copy puts on the clipboard, the
// filter, the cap, "what happened" per stage for a plan and for a run, and Watch all's one tile per running job.
import { describe, expect, it } from 'vitest';
import { ansiSpans, appendLines, filterLines, lineTag, planStory, plain, runningJobs, runStory, searchHits, transcriptText } from '../../src/renderer/src/lib/live';
import type { StudioRow } from '../../src/renderer/src/lib/studio';
import type { LiveLine } from '../../src/shared/v04';

const L = (x: Partial<LiveLine>): LiveLine => ({ src: 'agent', kind: 'say', text: '', at: 100, ...x });

describe('ansiSpans', () => {
  it('turns SGR colours into classes and drops every other escape and control character', () => {
    expect(ansiSpans('\x1b[31mfail\x1b[0m ok')).toEqual([{ text: 'fail', cls: 'a-r' }, { text: ' ok' }]);
    expect(ansiSpans('\x1b[1;34mbold blue\x1b[22m')).toEqual([{ text: 'bold blue', cls: 'a-bl a-bold' }]);
    expect(ansiSpans('a\x1b[2Kb\x1b]0;title\x07c\x07\x08d')).toEqual([{ text: 'a' }, { text: 'b' }, { text: 'cd' }]);
    expect(plain('\x1b[32m<b>x</b>\x1b[0m')).toBe('<b>x</b>'); // text, never HTML
  });
});

describe('tags, search, copy, filter', () => {
  const lines = [
    L({ src: 'engine', kind: 'stage', text: 'scan · 27 files', at: 1791000000 }),
    L({ kind: 'turn', provider: 'claude-code', text: 'intake · claude-code' }),
    L({ kind: 'tool', text: 'Read  inventory.json' }),
    L({ kind: 'say', provider: 'codex', text: '\x1b[33mTwo projects\x1b[0m' }),
    L({ src: 'engine', kind: 'progress', text: 'transcribe · 1:00 / 4:00' }),
  ];
  it('labels each line by its CLI or its kind', () => {
    expect(lines.map(lineTag)).toEqual(['engine', 'claude', 'tool', 'codex', 'engine']);
    expect(lineTag(L({ src: 'engine', kind: 'error' }))).toBe('error');
  });
  it('finds lines by text or tag, case-insensitive, without colour codes', () => {
    expect(searchHits(lines, 'INVENTORY')).toEqual([2]);
    expect(searchHits(lines, 'two projects')).toEqual([3]);
    expect(searchHits(lines, 'codex')).toEqual([3]);
    expect(searchHits(lines, 'claude')).toEqual([1]);
    expect(searchHits(lines, '  ')).toEqual([]);
  });
  it('copies time, tag and text, one line each, no colour codes', () => {
    const txt = transcriptText(lines.slice(0, 4));
    expect(txt.split('\n')).toHaveLength(4);
    expect(txt).toMatch(/^\d\d:\d\d:\d\d {2}engine {7}scan · 27 files/);
    expect(txt).toContain('codex        Two projects');
    expect(txt).not.toContain('\x1b');
  });
  it('filters by source and keeps the counters out of the log', () => {
    expect(filterLines(lines, 'all')).toHaveLength(4);
    expect(filterLines(lines, 'agent').every((l) => l.src === 'agent')).toBe(true);
    expect(filterLines(lines, 'engine')).toHaveLength(1);
  });
  it('keeps the newest lines under the cap', () => {
    const many = Array.from({ length: 10 }, (_, i) => L({ text: String(i) }));
    expect(appendLines(many, [L({ text: 'x' })], 5).map((l) => l.text)).toEqual(['6', '7', '8', '9', 'x']);
    expect(appendLines(many, [])).toBe(many);
  });
});

describe('planStory', () => {
  const E = (at: number, data: Record<string, unknown>, kind = 'stage'): LiveLine => ({ src: 'engine', kind, text: '', at, data });
  it('one entry per plan step: files found, each file read, minutes heard, the model asked and what it answered', () => {
    const s = planStory(
      [
        E(10, { stage: 'scan', files: 3 }),
        E(12, { stage: 'probe', file: 'a.mp4', i: 1, n: 3 }),
        E(13, { stage: 'faces', file: 'b.mp4', i: 2, n: 3 }),
        E(20, { stage: 'transcribe', file: 'a.mp4', total_s: 600 }),
        E(22, { stage: 'transcribe', done_s: 300, total_s: 600 }, 'progress'),
        E(40, { stage: 'model', provider: 'claude-code' }),
        L({ kind: 'turn', at: 40 }),
        L({ kind: 'say', at: 45, text: 'Two projects: a montage and three calm clips.', provider: 'claude-code' }),
        L({ kind: 'say', at: 46, text: '{"projects": 2}' }),
        L({ kind: 'result', at: 47, text: '900 in · 60 out · 7.0 s · subscription' }),
      ],
      50,
    );
    expect(s.map((e) => [e.step, e.state])).toEqual([['scan', 'done'], ['media', 'done'], ['transcribe', 'done'], ['model', 'now']]);
    expect(s[0].facts[0]).toEqual({ key: 'run.f.found', params: { n: 3 } });
    expect(s[1].files).toEqual([{ name: 'a.mp4', state: 'done' }, { name: 'b.mp4', state: 'done' }]);
    expect(s[1].start).toBe(12);
    expect(s[1].end).toBe(20);
    expect(s[2].facts[0]).toEqual({ key: 'run.f.transcribe', params: { m: 10 } });
    expect(s[3].ai.map((a) => a.text)).toEqual(['Two projects: a montage and three calm clips.']); // JSON replies are not words
    expect(s[3].facts.map((f) => f.key)).toEqual(['run.f.asked', 'run.f.tokens']);
    expect(s[3].end).toBeNull();
  });
  it('the file being read now is marked; the plan written closes the story', () => {
    const now = planStory([E(1, { stage: 'probe', file: 'a.mp4', i: 1, n: 2 }), E(2, { stage: 'probe', file: 'b.mp4', i: 2, n: 2 })], 3);
    expect(now[0].files.map((f) => f.state)).toEqual(['done', 'now']);
    const done = planStory([E(1, { stage: 'model', provider: 'codex' }), { src: 'engine', kind: 'done', text: 'plan ready', at: 9, data: { projects: 2 } }], 10);
    expect(done.map((e) => [e.step, e.state])).toEqual([['model', 'done'], ['write', 'done']]);
    expect(done[1].facts[0]).toEqual({ key: 'run.f.planned', params: { n: 2 } });
  });
});

describe('runStory', () => {
  const ev = (at: number, data: Record<string, unknown>): LiveLine => ({ src: 'engine', kind: 'event', text: '', at, data });
  it('one entry per pipeline step: clips past it, the clip on it now, decisions and the AI inline', () => {
    const s = runStory(
      [
        ev(1, { event: 'stage-start', job: 's01', stage: 'asr' }),
        ev(2, { event: 'stage-start', job: 's01', stage: 'cleanup' }),
        L({ kind: 'say', at: 3, text: 'Cut 3, keep the pause.', provider: 'claude-code' }),
        ev(4, { event: 'auto-answer', job: 's01', kind: 'filler-confirm', by: 'ai' }),
        ev(5, { event: 'stage-start', job: 's02', stage: 'asr' }),
      ],
      10,
      3,
    );
    expect(s.map((e) => [e.step, e.state])).toEqual([['transcribe', 'now'], ['cut', 'now']]);
    expect(s[0].facts[0]).toEqual({ key: 'run.f.clips', params: { done: 1, n: 3 } });
    expect(s[0].files).toEqual([{ name: 's01', state: 'done' }, { name: 's02', state: 'now' }]);
    expect(s[1].files.map((f) => f.state)).toEqual(['now', 'todo']);
    expect(s[1].ai[0].text).toBe('Cut 3, keep the pause.');
    expect(s[1].decided).toEqual([{ kind: 'filler-confirm', by: 'ai', job: 's01', at: 4 }]);
  });
  it('a finished clip is past every step', () => {
    const s = runStory([ev(1, { event: 'stage-start', job: 's01', stage: 'export' }), ev(2, { event: 'job-done', job: 's01', state: 'done' })], 5, 1);
    expect(s[0]).toMatchObject({ step: 'render', state: 'done' });
    expect(s[0].files).toEqual([{ name: 's01', state: 'done' }]);
  });
});

describe('runningJobs', () => {
  const row = (x: Partial<StudioRow>): StudioRow => ({ key: 'k', kind: 'project', item: 'p1', clip: null, title: 't', project: null, pos: null, thumb: null, video: null, duration: null, group: 'run', tone: 'run', p: { state: 'run', current: 'cut', progress: 0.2, eta: null }, ask: null, post: null, posted: false, at: 0, ...x });
  it('one tile per running request / project, never twice for a project listed by clip, not queued or done ones', () => {
    const rows = [
      row({ key: 'r:a', kind: 'request', item: null, r: { id: 'aaaaaaaaaaaa' } as StudioRow['r'] }),
      row({ key: 'p1/c1', kind: 'clip', item: 'p1', clip: 'c1' }),
      row({ key: 'p1/c2', kind: 'clip', item: 'p1', clip: 'c2' }),
      row({ key: 'p:p2', item: 'p2', tone: 'off' }),
      row({ key: 'p:p3', item: 'p3', group: 'ready', tone: 'done' }),
      row({ key: 'p:p4', item: 'p4' }),
    ];
    expect(runningJobs(rows).map((r) => r.key)).toEqual(['r:a', 'p1/c1', 'p:p4']);
  });
});
