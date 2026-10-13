// A chat edit's progress (lib/editProgress): the step from the request's live transcript (engine steps + the model's
// streamed lines) and the panel's own apply, failure / stop, "still working" after a long silence, the log tail, and
// the time-left estimate from her past edits on the same model (none under two of them, none once past it).
import { describe, expect, it } from 'vitest';
import { editEstimate, editProgress, logTail, QUIET_S, secondsLeft, timeKey } from '../../src/renderer/src/lib/editProgress';
import type { LiveLine } from '../../src/shared/v04';

const E = (stage: string, at: number, data: Record<string, unknown> = {}): LiveLine => ({ src: 'engine', kind: 'stage', text: stage, at, data: { stage, ...data } });
const A = (kind: string, at: number, x: Partial<LiveLine> = {}): LiveLine => ({ src: 'agent', kind, text: kind, at, ...x });

describe('editProgress', () => {
  it('starts on reading the clip, before any line', () => {
    const p = editProgress([], {}, 100, 101);
    expect([p.phase, p.step, p.steps, p.quiet]).toEqual(['read', 1, 4, false]);
  });
  it('moves only when a line says so: read -> think (engine step or the model streaming) -> check -> done', () => {
    expect(editProgress([E('start', 100), E('read', 101)], {}, 100, 102).phase).toBe('read');
    const think = editProgress([E('read', 101), E('think', 102, { provider: 'claude-code', model: 'sonnet' })], {}, 100, 103);
    expect([think.phase, think.step, think.provider, think.model]).toEqual(['think', 2, 'claude-code', 'sonnet']);
    // an older engine without step lines: the model's first streamed line is the AI at work
    expect(editProgress([E('start', 100), A('turn', 102, { provider: 'codex' })], {}, 100, 103)).toMatchObject({ phase: 'think', provider: 'codex' });
    expect(editProgress([E('think', 102), A('say', 110), E('check', 111)], {}, 100, 112).phase).toBe('check');
    expect(editProgress([E('think', 102), E('rules', 111)], {}, 100, 112).phase).toBe('check');
    expect(editProgress([E('check', 111), E('done', 112, { n: 2 })], {}, 100, 112).phase).toBe('done');
    // never back: a late agent line after the check does not return to think
    expect(editProgress([E('check', 111), A('result', 111.5)], {}, 100, 112).phase).toBe('check');
  });
  it('the panel applying the answer is the apply step; applied is done', () => {
    const lines = [E('think', 102), E('done', 112)];
    expect(editProgress(lines, { applying: 3 }, 100, 113)).toMatchObject({ phase: 'apply', step: 4 });
    expect(editProgress(lines, { applying: 3, applied: true }, 100, 113)).toMatchObject({ phase: 'done', step: 4 });
  });
  it('an error line names the step it failed on; a stop line is a stop', () => {
    const f = editProgress([E('think', 102), A('tool', 103), { src: 'engine', kind: 'error', text: 'x', at: 104, data: { code: 'ask-failed' } }], {}, 100, 105);
    expect([f.failedAt, f.quiet]).toEqual(['think', false]);
    expect(editProgress([E('think', 102), { src: 'engine', kind: 'stop', text: 'stopped', at: 103 }], {}, 100, 200)).toMatchObject({ stopped: true, quiet: false });
  });
  it('the AI she picked failed and another took over: the fallback line says who and why', () => {
    const fb: LiveLine = { src: 'engine', kind: 'fallback', text: 'claude-code failed (timeout) -> trying codex', at: 290, data: { from: 'claude-code', to: 'codex', code: 'timeout' } };
    const p = editProgress([E('think', 102, { provider: 'claude-code' }), fb, A('turn', 291, { provider: 'codex', model: 'gpt-6-luna' })], {}, 100, 292);
    expect(p).toMatchObject({ phase: 'think', fallback: { from: 'claude-code', to: 'codex', code: 'timeout' }, provider: 'codex', model: 'gpt-6-luna' });
    expect(editProgress([E('think', 102)], {}, 100, 103).fallback).toBeNull();
  });
  it('a long silence while the AI works reads "still working" (from the newest line, not the start)', () => {
    const lines = [E('think', 102), A('thinking', 110)];
    expect(editProgress(lines, {}, 100, 110 + QUIET_S - 1).quiet).toBe(false);
    expect(editProgress(lines, {}, 100, 110 + QUIET_S + 1)).toMatchObject({ quiet: true, quietFor: QUIET_S + 1 });
    expect(editProgress([E('done', 102)], {}, 100, 500).quiet).toBe(false);
  });
});

describe('logTail', () => {
  it('the newest lines with text, progress counters left out', () => {
    const lines = [A('turn', 1), A('thinking', 2), { ...A('progress', 3) }, A('tool', 4), { ...A('say', 5), text: '  ' }, A('result', 6)];
    expect(logTail(lines, 3).map((l) => l.kind)).toEqual(['thinking', 'tool', 'result']);
  });
});

describe('time left', () => {
  it('the median of her past edits on the same model, none under two', () => {
    const k = timeKey('claude-code', 'sonnet');
    expect(k).toBe('claude-code/sonnet');
    expect(timeKey(null, 'x')).toBeNull();
    expect(editEstimate(k, { [k!]: [80] })).toBeNull();
    expect(editEstimate(k, { [k!]: [60, 100] })).toBe(80);
    expect(editEstimate(k, { [k!]: [60, 90, 300] })).toBe(90);
    expect(editEstimate('codex/', { [k!]: [60, 90] })).toBeNull();
  });
  it('rounded to 5 s; nothing once it is (almost) past the estimate', () => {
    expect(secondsLeft(90, 10)).toBe(80);
    expect(secondsLeft(90, 77)).toBe(15);
    expect(secondsLeft(90, 88)).toBeNull();
    expect(secondsLeft(90, 200)).toBeNull();
    expect(secondsLeft(null, 1)).toBeNull();
  });
});
