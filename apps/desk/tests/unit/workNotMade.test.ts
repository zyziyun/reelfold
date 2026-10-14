// A folder in a watched folder with only her brief and footage (promo-027-v2, 2026-10-12): Reelfold never ran
// anything there, so it is "not made yet" - never a run stuck at "Making · Plan" because the folder was edited lately.
import { describe, expect, it } from 'vitest';
import type { HistoryItem } from '../../src/shared/v02';
import { itemPipeline, workNotMade } from '../../src/renderer/src/lib/pipeline';
import { itemStatus } from '../../src/renderer/src/lib/status';
import { studioRows } from '../../src/renderer/src/lib/studio';

const NOW = 1_791_800_000;
const zero = { total: 0, green: 0, red: 0, approved: 0, done: 0, failed: 0 };
const folder = (o: Partial<HistoryItem> = {}): HistoryItem =>
  ({ kind: 'work', id: 'aaaaaaaaaaaa', dir: '/demos/promo-027-v2', name: 'promo-027-v2', recipe: 'promo-recut', client: null, created: NOW - 4000, updated: NOW - 600, counts: zero, status: 'in-progress', thumb: null, sources: ['watch'], opened: false, openable: false, live: null, ...o }) as HistoryItem;

describe('a watched folder with nothing made in it', () => {
  it('is not running, however recently it was edited', () => {
    expect(itemStatus(folder(), NOW)).toBeNull();
    expect(itemStatus(folder({ updated: NOW - 5 }), NOW)).toBeNull();
  });

  it('is "not made yet" (idle), not a run at Plan', () => {
    expect(workNotMade(folder())).toBe(true);
    expect(itemPipeline(folder())).toEqual({ state: 'idle', current: 'plan', progress: null, eta: null });
    const [row] = studioRows([folder()], [], {}, [], [], NOW);
    expect(row.tone).toBe('off');
    expect(row.p.state).toBe('idle');
  });

  it('runs only when its own status file says so (an external run of the skill), and is ready once it has outputs', () => {
    const live = { state: 'running', status: 'running', stage: 'render', progress: 0.4, eta: 60, needs_you: false, heartbeat: NOW } as HistoryItem['live'];
    expect(workNotMade(folder({ live }))).toBe(false);
    expect(itemStatus(folder({ live }), NOW)).toBe('run');
    expect(itemPipeline(folder({ live })).state).toBe('run');
    const made = folder({ status: 'done', counts: { ...zero, total: 2, done: 2 } });
    expect(workNotMade(made)).toBe(false);
    expect(itemPipeline(made).state).toBe('ready');
  });
});

it('missing recorded outputs cannot inherit a stale Made state', () => {
  const missing = folder({ status: 'done', missing_outputs: true, live: { state: 'interrupted', heartbeat: NOW - 90000 } as HistoryItem['live'] });
  expect(itemStatus(missing, NOW)).toBe('error');
  expect(itemPipeline(missing).state).toBe('idle');
  const [row] = studioRows([missing], [], {}, [], [], NOW);
  expect(row.tone).not.toBe('done');
  expect(row.group).not.toBe('ready');
});
