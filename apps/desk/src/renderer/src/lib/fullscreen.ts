// System-level full screen for the app's players: the HTML Fullscreen API on the player's own box, which Electron turns
// into the OS's full screen (macOS: a native full-screen Space, menu bar and Dock hidden; main/index.ts). Only when the
// request is refused (it should not be: main allows 'fullscreen' for the app's window) does the box fill the window.
//
// While a player has the screen it owns the keyboard: one window capture listener, installed when this module loads
// (before any page's own), hands every key to that player and stops it there, so the page underneath (the review's
// Space = approve, Esc = leave, the editor's shortcuts) never sees it.
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';

/** Esc that ended a native full screen must not also close what is underneath (the key can arrive after the
 * fullscreenchange): within this many ms of an exit, Esc is spent. */
export const ESC_GRACE_MS = 500;

export function escSpent(lastExit: number, now: number): boolean {
  return lastExit > 0 && now - lastExit < ESC_GRACE_MS;
}

/** macOS animates into and out of a full-screen Space (~0.6 s). A request while the window is still moving is lost
 * or undone when the move lands (the player drops out while the window stays full screen, or stays full screen when
 * she asked to leave): each request waits for the last change to settle. The click's user activation lasts 5 s. */
export const SETTLE_MS = 900;

export function settleWait(lastChange: number, now: number): number {
  return lastChange > 0 ? Math.max(0, lastChange + SETTLE_MS - now) : 0;
}

const settle = async () => {
  const wait = settleWait(lastChangeAt, performance.now());
  if (wait) await new Promise((r) => setTimeout(r, wait));
};

type KeyFn = (e: KeyboardEvent) => void;
const owners = new Map<Element, KeyFn>();
let fallbackEl: Element | null = null;
let lastExitAt = 0;
let lastChangeAt = 0;
let wasFull: Element | null = null;

/** The element that has the screen right now (system full screen, or the in-window fallback). */
export function screenOwner(): Element | null {
  return (typeof document !== 'undefined' && document.fullscreenElement) || fallbackEl;
}

/** Route a key: to the player that has the screen (and nobody else), or swallow the Esc that just ended it. */
export function routeKey(e: KeyboardEvent, owner: Element | null, handler: KeyFn | undefined, lastExit: number, now: number): 'owner' | 'spent' | 'page' {
  if (owner && handler) return 'owner';
  if (!owner && e.key === 'Escape' && escSpent(lastExit, now)) return 'spent';
  return 'page';
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  document.addEventListener('fullscreenchange', () => {
    const now = document.fullscreenElement;
    lastChangeAt = performance.now();
    if (wasFull && !now) lastExitAt = lastChangeAt;
    wasFull = now;
  });
  window.addEventListener(
    'keydown',
    (e) => {
      const owner = screenOwner();
      const handler = owner ? owners.get(owner) : undefined;
      const r = routeKey(e, owner, handler, lastExitAt, performance.now());
      if (r === 'page') return;
      e.stopImmediatePropagation();
      if (r === 'spent') e.preventDefault();
      else handler?.(e);
    },
    true,
  );
}

export interface NativeFullscreen {
  /** the box is the document's full-screen element (system level) */
  native: boolean;
  /** the request was refused: the box fills the window instead */
  fallback: boolean;
  /** either of the above */
  on: boolean;
  enter: () => Promise<boolean>;
  exit: () => Promise<void>;
  toggle: () => void;
  /** an Esc right now would be the one that ended full screen */
  escSpent: () => boolean;
}

/** onKey: the player's own key handler, called for every key while it has the screen. onExit: full screen ended. */
export function useNativeFullscreen(ref: RefObject<HTMLElement | null>, o: { onExit?: () => void; onKey?: KeyFn } = {}): NativeFullscreen {
  const [native, setNative] = useState(false);
  const [fallback, setFallback] = useState(false);
  const was = useRef(false);
  const onExit = useRef(o.onExit);
  onExit.current = o.onExit;
  const onKey = useRef(o.onKey);
  onKey.current = o.onKey;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    owners.set(el, (e) => onKey.current?.(e));
    return () => {
      owners.delete(el);
      if (fallbackEl === el) fallbackEl = null;
    };
  }, [ref]);

  useEffect(() => {
    const on = () => {
      const now = !!ref.current && document.fullscreenElement === ref.current;
      if (was.current && !now) onExit.current?.();
      was.current = now;
      setNative(now);
    };
    document.addEventListener('fullscreenchange', on);
    return () => {
      document.removeEventListener('fullscreenchange', on);
      // leaving the page mid full screen (route change, overlay closed): give the screen back
      if (was.current && document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
    };
  }, [ref]);

  const enter = useCallback(async () => {
    const el = ref.current;
    if (!el) return false;
    if (document.fullscreenElement === el) return true;
    await settle();
    if (document.fullscreenElement === el) return true;
    try {
      await el.requestFullscreen({ navigationUI: 'hide' });
      setFallback(false);
      el.focus({ preventScroll: true }); // Space must play / pause, not press the ⤢ button again
      return true;
    } catch {
      fallbackEl = el;
      setFallback(true);
      return false;
    }
  }, [ref]);

  const exit = useCallback(async () => {
    if (fallbackEl === ref.current) {
      fallbackEl = null;
      lastExitAt = performance.now();
    }
    setFallback(false);
    if (!document.fullscreenElement) return;
    await settle();
    if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined);
  }, [ref]);

  const toggle = useCallback(() => {
    if (native || fallback) void exit();
    else void enter();
  }, [native, fallback, enter, exit]);

  return useMemo(
    () => ({ native, fallback, on: native || fallback, enter, exit, toggle, escSpent: () => escSpent(lastExitAt, performance.now()) }),
    [native, fallback, enter, exit, toggle],
  );
}
