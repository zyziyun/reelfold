// 「Review in a row」 walks every review waiting for her across all her projects, in the Inbox's order ("3 of 12").
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { InboxItem } from '../../src/shared/v04';
import { reviewInRow, reviewQueue, triageState } from '../../src/renderer/src/lib/nav';

const item = (key: string, kind: string, pid: string, clip?: string): InboxItem =>
  ({ key, kind, project: { id: pid, name: pid }, options: clip ? [{ id: '0', clip_id: clip, text: '' }] : [] }) as unknown as InboxItem;

describe('review in a row', () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    vi.stubGlobal('sessionStorage', { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v), removeItem: (k: string) => store.delete(k) });
    vi.stubGlobal('location', { hash: '#/studio' });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('queues every project’s reviews in the Inbox order, not only the first project’s', () => {
    const items = [item('a1', 'publish', 'A', 's1'), item('q', 'filler', 'A', 's2'), item('b1', 'publish', 'B', 's1'), item('a2', 'review', 'A', 's3'), item('c1', 'publish', 'C', 's9')];
    expect(reviewQueue(items).map((x) => x.key)).toEqual(['a1', 'b1', 'a2', 'c1']);
    reviewInRow(items);
    expect(triageState()).toEqual({ keys: ['a1', 'b1', 'a2', 'c1'], i: 0 });
    expect(location.hash).toContain('/A/clip/s1');
    expect(location.hash).toContain('triage=1');
  });

  it('one project’s clip reviews keep the full-screen review; no review: the other questions in a row', () => {
    reviewInRow([item('a1', 'review', 'A'), item('a2', 'publish', 'A', 's2')]);
    expect(location.hash).toBe('#/p/A/focus');
    reviewInRow([item('q1', 'filler', 'A', 's1'), item('q2', 'music', 'B')]);
    expect(triageState()?.keys).toEqual(['q1', 'q2']);
  });
});
