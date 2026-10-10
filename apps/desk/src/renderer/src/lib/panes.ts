// Every split of the app can be resized (studio-polish): the Studio's video list, the clip page's player column, the
// AI conversation's width, the editor's clip info above the chat. One size per pane, kept inside its min / max (and
// whatever room the window leaves), folded to the edge where that makes sense, saved on this Mac (localStorage
// `ui.panes`). The editor's player / lower split and chat width stay in `ce.layout` (useSplit), with the same rules.
import { useCallback, useEffect, useRef, useState } from 'react';

export interface PaneSpec {
  /** the size when nothing was chosen (double-click puts it back) */
  def: number;
  min: number;
  max: number;
  /** can fold to the edge (dragging well past the min, or its toggle) */
  collapsible?: boolean;
}

export interface PaneState {
  size: number;
  collapsed: boolean;
}

/** how far past the min a drag has to go before the pane folds (px) */
export const FOLD_PAST = 64;
/** arrow-key steps (px): plain and with Shift */
export const STEP = 16;
export const BIG_STEP = 64;
const KEY = 'ui.panes';

export const PANES = {
  /** the Studio's list of every video (left) */
  'studio.list': { def: 300, min: 232, max: 480, collapsible: true },
  /** the clip page's player / cover / captions / versions column */
  'studio.player': { def: 380, min: 280, max: 720 },
  /** the AI conversation over the clip page's right side */
  'studio.ai': { def: 440, min: 320, max: 760 },
  /** the editor's clip info above the chat (its height) */
  'editor.info': { def: 360, min: 96, max: 900 },
} satisfies Record<string, PaneSpec>;
export type PaneId = keyof typeof PANES;

/** a size inside [min, max] (any unit: px, or a share); `room` (what the window leaves for this pane) lowers the max, never below the min */
export function clampSize(v: number, spec: Pick<PaneSpec, 'min' | 'max'>, room?: number): number {
  const hi = Math.max(spec.min, Math.min(spec.max, room ?? Infinity));
  const x = Number.isFinite(v) ? v : spec.min;
  return Math.min(hi, Math.max(spec.min, x)); // not rounded: the editor's split is a share of its height
}

/** where a drag lands: `start` + how far the pointer moved (signed: +1 when moving right / down grows the pane).
 * A collapsible pane folds when dragged FOLD_PAST beyond its min, and opens again when dragged back out. */
export function dragTo(start: number, delta: number, sign: 1 | -1, spec: PaneSpec, room?: number): PaneState {
  const raw = start + delta * sign;
  if (spec.collapsible && raw < spec.min - FOLD_PAST) return { size: clampSize(start, spec, room), collapsed: true };
  return { size: clampSize(raw, spec, room), collapsed: false };
}

/** the keyboard on a focused divider: arrows step (Shift: a bigger step), Home / End the min / max, Enter folds or
 * opens a collapsible pane. `grow` is the arrow that makes the pane bigger. Null when the key is not ours. */
export function keyTo(key: string, shift: boolean, cur: PaneState, spec: PaneSpec, grow: 'ArrowRight' | 'ArrowLeft' | 'ArrowDown' | 'ArrowUp', room?: number, step = STEP, bigStep = BIG_STEP): PaneState | null {
  const shrink = ({ ArrowRight: 'ArrowLeft', ArrowLeft: 'ArrowRight', ArrowDown: 'ArrowUp', ArrowUp: 'ArrowDown' } as const)[grow];
  const d = shift ? bigStep : step;
  if (key === grow) return { size: clampSize(cur.collapsed ? spec.min : cur.size + d, spec, room), collapsed: false };
  if (key === shrink) {
    if (cur.collapsed) return cur;
    if (spec.collapsible && cur.size <= spec.min) return { ...cur, collapsed: true };
    return { size: clampSize(cur.size - d, spec, room), collapsed: false };
  }
  if (key === 'Home') return spec.collapsible ? { ...cur, collapsed: true } : { size: clampSize(spec.min, spec, room), collapsed: false };
  if (key === 'End') return { size: clampSize(spec.max, spec, room), collapsed: false };
  if (key === 'Enter' && spec.collapsible) return { ...cur, collapsed: !cur.collapsed };
  return null;
}

type Store = Pick<Storage, 'getItem' | 'setItem'>;

export function loadPanes(store: Pick<Storage, 'getItem'> = localStorage): Partial<Record<PaneId, PaneState>> {
  let raw: unknown;
  try {
    raw = JSON.parse(store.getItem(KEY) ?? '{}');
  } catch {
    return {};
  }
  if (!raw || typeof raw !== 'object') return {};
  const out: Partial<Record<PaneId, PaneState>> = {};
  for (const [id, spec] of Object.entries(PANES) as [PaneId, PaneSpec][]) {
    const v = (raw as Record<string, Partial<PaneState> | undefined>)[id];
    if (!v || typeof v !== 'object') continue;
    out[id] = { size: clampSize(Number(v.size ?? spec.def), spec), collapsed: !!(spec.collapsible && v.collapsed) };
  }
  return out;
}

export function loadPane(id: PaneId, store: Pick<Storage, 'getItem'> = localStorage): PaneState {
  return loadPanes(store)[id] ?? { size: PANES[id].def, collapsed: false };
}

export function savePane(id: PaneId, st: PaneState, store: Store = localStorage) {
  let all: Record<string, PaneState>;
  try {
    const v: unknown = JSON.parse(store.getItem(KEY) ?? '{}');
    all = v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, PaneState>) : {};
  } catch {
    all = {};
  }
  all[id] = { size: Math.round(st.size), collapsed: st.collapsed };
  store.setItem(KEY, JSON.stringify(all));
}

/** one pane's size + folded state, saved as it changes; `room` caps the size to what the window leaves */
export function usePane(id: PaneId, room?: number) {
  const spec: PaneSpec = PANES[id];
  const [st, setSt] = useState<PaneState>(() => loadPane(id));
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    savePane(id, st);
  }, [id, st]);
  // another window / tab of the same profile changed it
  useEffect(() => {
    const on = (e: StorageEvent) => e.key === KEY && setSt(loadPane(id));
    window.addEventListener('storage', on);
    return () => window.removeEventListener('storage', on);
  }, [id]);
  const set = useCallback((n: PaneState) => setSt((o) => (o.size === n.size && o.collapsed === n.collapsed ? o : n)), []);
  const reset = useCallback(() => setSt({ size: spec.def, collapsed: false }), [spec.def]);
  const toggle = useCallback(() => setSt((o) => ({ ...o, collapsed: !o.collapsed })), []);
  return { spec, size: clampSize(st.size, spec, room), saved: st.size, collapsed: !!spec.collapsible && st.collapsed, set, reset, toggle };
}

/** an element's live size (ResizeObserver) */
export function useBox<T extends HTMLElement>() {
  const [box, setBox] = useState({ w: 0, h: 0 });
  const ro = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    ro.current?.disconnect();
    ro.current = null;
    if (!el) return;
    const read = () => setBox((b) => (b.w === el.clientWidth && b.h === el.clientHeight ? b : { w: el.clientWidth, h: el.clientHeight }));
    read();
    ro.current = new ResizeObserver(read);
    ro.current.observe(el);
  }, []);
  return [ref, box] as const;
}
