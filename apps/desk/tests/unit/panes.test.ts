// Every split can be resized (studio-polish): sizes stay inside min / max and the room the window leaves, a drag far
// past the min folds a pane that can fold, the keyboard steps on a focused divider, the sizes saved on this Mac.
import { describe, expect, it } from 'vitest';
import { BIG_STEP, FOLD_PAST, PANES, STEP, clampSize, dragTo, keyTo, loadPane, loadPanes, savePane, type PaneSpec } from '../../src/renderer/src/lib/panes';

const spec: PaneSpec = { def: 300, min: 232, max: 480, collapsible: true };
const fixed: PaneSpec = { def: 380, min: 280, max: 720 };

function store(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), m };
}

describe('clampSize', () => {
  it('keeps a size inside min and max', () => {
    expect(clampSize(100, spec)).toBe(232);
    expect(clampSize(900, spec)).toBe(480);
    expect(clampSize(300.6, spec)).toBe(300.6);
    expect(clampSize(0.9, { min: 0.2, max: 0.8 })).toBe(0.8); // a share of the height stays a share
    expect(clampSize(Number.NaN, spec)).toBe(232);
  });
  it('the room the window leaves lowers the max, never below the min', () => {
    expect(clampSize(450, spec, 400)).toBe(400);
    expect(clampSize(450, spec, 100)).toBe(232);
    expect(clampSize(300, spec, undefined)).toBe(300);
  });
});

describe('dragTo', () => {
  it('moves with the pointer; a pane right of the line grows when dragged left', () => {
    expect(dragTo(300, 50, 1, spec)).toEqual({ size: 350, collapsed: false });
    expect(dragTo(440, -100, -1, { def: 440, min: 320, max: 760 })).toEqual({ size: 540, collapsed: false });
  });
  it('stops at the min; folds only when dragged FOLD_PAST beyond it (and keeps its size for later)', () => {
    expect(dragTo(300, -100, 1, spec)).toEqual({ size: 232, collapsed: false });
    expect(dragTo(300, -(300 - 232 + FOLD_PAST + 1), 1, spec)).toEqual({ size: 300, collapsed: true });
    expect(dragTo(400, -400, 1, fixed)).toEqual({ size: 280, collapsed: false }); // not foldable
  });
  it('a drag out of a folded pane opens it at its min', () => {
    expect(dragTo(spec.min - FOLD_PAST, 4, 1, spec)).toEqual({ size: 232, collapsed: false });
  });
  it('respects the room', () => {
    expect(dragTo(300, 400, 1, spec, 360)).toEqual({ size: 360, collapsed: false });
  });
});

describe('keyTo', () => {
  const cur = { size: 300, collapsed: false };
  it('arrows step, Shift steps more, the other arrow shrinks', () => {
    expect(keyTo('ArrowRight', false, cur, spec, 'ArrowRight')).toEqual({ size: 300 + STEP, collapsed: false });
    expect(keyTo('ArrowLeft', true, cur, spec, 'ArrowRight')).toEqual({ size: 300 - BIG_STEP, collapsed: false });
    expect(keyTo('ArrowLeft', false, cur, fixed, 'ArrowLeft')).toEqual({ size: 316, collapsed: false });
    expect(keyTo('ArrowDown', false, { size: 0.5, collapsed: false }, { def: 0.5, min: 0.2, max: 0.8 }, 'ArrowDown', undefined, 0.04, 0.12)!.size).toBeCloseTo(0.54);
  });
  it('Home / End: min (or fold) / max within the room; Enter folds and opens', () => {
    expect(keyTo('End', false, cur, spec, 'ArrowRight', 420)).toEqual({ size: 420, collapsed: false });
    expect(keyTo('Home', false, cur, spec, 'ArrowRight')).toEqual({ size: 300, collapsed: true });
    expect(keyTo('Home', false, { size: 500, collapsed: false }, fixed, 'ArrowRight')).toEqual({ size: 280, collapsed: false });
    expect(keyTo('Enter', false, cur, spec, 'ArrowRight')).toEqual({ size: 300, collapsed: true });
    expect(keyTo('Enter', false, cur, fixed, 'ArrowRight')).toBeNull();
  });
  it('shrinking at the min folds a foldable pane; growing opens it again', () => {
    expect(keyTo('ArrowLeft', false, { size: 232, collapsed: false }, spec, 'ArrowRight')).toEqual({ size: 232, collapsed: true });
    expect(keyTo('ArrowRight', false, { size: 400, collapsed: true }, spec, 'ArrowRight')).toEqual({ size: 232, collapsed: false });
  });
  it('other keys are not ours (the page keeps them)', () => {
    expect(keyTo('ArrowUp', false, cur, spec, 'ArrowRight')).toBeNull();
    expect(keyTo('a', false, cur, spec, 'ArrowRight')).toBeNull();
  });
});

describe('saved sizes', () => {
  it('round-trips each pane and keeps the others', () => {
    const s = store();
    savePane('studio.list', { size: 360, collapsed: true }, s);
    savePane('studio.ai', { size: 512.4, collapsed: false }, s);
    expect(loadPane('studio.list', s)).toEqual({ size: 360, collapsed: true });
    expect(loadPane('studio.ai', s)).toEqual({ size: 512, collapsed: false });
    expect(loadPane('studio.player', s)).toEqual({ size: PANES['studio.player'].def, collapsed: false });
  });
  it('bad or out-of-range data falls back safely; only foldable panes stay folded', () => {
    expect(loadPanes(store({ 'ui.panes': '{nope' }))).toEqual({});
    expect(loadPanes(store({ 'ui.panes': '7' }))).toEqual({});
    const bad = store({ 'ui.panes': '7' });
    savePane('studio.ai', { size: 400, collapsed: false }, bad);
    expect(loadPane('studio.ai', bad)).toEqual({ size: 400, collapsed: false });
    const s = store({ 'ui.panes': JSON.stringify({ 'studio.list': { size: 99999 }, 'studio.player': { size: 10, collapsed: true }, junk: { size: 1 } }) });
    expect(loadPanes(s)).toEqual({ 'studio.list': { size: 480, collapsed: false }, 'studio.player': { size: 280, collapsed: false } });
  });
});
