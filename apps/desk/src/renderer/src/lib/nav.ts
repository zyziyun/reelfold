// How the pages connect (ux/home-redesign M1): one object model - Project › Clip › Post - where every mention is the
// same link to the same place; ⌘[ / ⌘] back and forward like a browser; and the Inbox triage queue ("Review all in
// a row"): one item after another, in the editor when the item is about a clip, with ← Inbox · n of N · Skip · Next.
import { useEffect, useState } from 'react';
import type { InboxItem } from '../../../shared/v04';
import { go, href } from './router';

export function projectHref(id: string): string {
  return href({ name: 'project', id });
}

/** A clip in the editor; `t` seeks there on open, `item` + `triage` pin an inbox question in the editor's chat. */
export function clipHref(id: string, clip: string, opts: { t?: number | null; item?: string | null; triage?: boolean; v?: string | null } = {}): string {
  const q = new URLSearchParams();
  if (opts.v) q.set('v', opts.v); // the export version (aspect) to open on
  if (opts.t != null && Number.isFinite(opts.t)) q.set('t', String(Math.round(opts.t * 100) / 100));
  if (opts.item) q.set('item', opts.item);
  if (opts.triage) q.set('triage', '1');
  return withQuery(href({ name: 'clip', id, clip }), q);
}

/** A hash + more query (the Studio's #/studio?f=you already has one). */
function withQuery(h: string, q: URLSearchParams): string {
  const s = q.toString();
  return s ? `${h}${h.includes('?') ? '&' : '?'}${s}` : h;
}

/** A request / project selected in All projects (the Studio's whole list, or the control room). */
export function selHref(id: string): string {
  return withQuery(href({ name: 'projects' }), new URLSearchParams({ sel: id }));
}

/** A scheduled post on the Publish board. */
export function postHref(id: string): string {
  return `${href({ name: 'calendar' })}?post=${encodeURIComponent(id)}`;
}

export function inboxHref(opts: { item?: string | null; triage?: boolean } = {}): string {
  const q = new URLSearchParams();
  if (opts.item) q.set('item', opts.item);
  if (opts.triage) q.set('triage', '1');
  return withQuery(href({ name: 'inbox' }), q);
}

/** Where an inbox item opens: the editor at its first clip (and the moment it is about), else the Inbox itself. */
export function itemTarget(x: InboxItem, triage = false): string {
  if (x.href) return x.href; // an item that owns its screen (Create: takes to pick, a paused run)
  const pid = x.project.id;
  const o = (x.options ?? []).find((y) => y.clip_id);
  if (pid && o?.clip_id) return clipHref(pid, o.clip_id, { t: o.at ?? null, item: x.key, triage });
  return inboxHref({ item: x.key, triage });
}

// ---------------------------------------------------------------- triage queue (sessionStorage: survives reloads)
export interface TriageState {
  keys: string[];
  i: number;
}

const TRIAGE = 'ux.triage';
const listeners = new Set<() => void>();

export function triageState(): TriageState | null {
  try {
    const v = JSON.parse(sessionStorage.getItem(TRIAGE) ?? 'null') as TriageState | null;
    return v && Array.isArray(v.keys) && v.keys.length ? v : null;
  } catch {
    return null;
  }
}

function setTriage(v: TriageState | null) {
  if (v) sessionStorage.setItem(TRIAGE, JSON.stringify(v));
  else sessionStorage.removeItem(TRIAGE);
  for (const f of listeners) f();
}

export function useTriageState(): TriageState | null {
  const [s, setS] = useState(triageState);
  useEffect(() => {
    const on = () => setS(triageState());
    listeners.add(on);
    window.addEventListener('hashchange', on);
    return () => {
      listeners.delete(on);
      window.removeEventListener('hashchange', on);
    };
  }, []);
  return s;
}

/** Start "Review all in a row" over these items (in the Inbox's order) and open the first. */
export function startTriage(items: InboxItem[], from = 0) {
  if (!items.length) return;
  setTriage({ keys: items.map((x) => x.key), i: Math.min(from, items.length - 1) });
  location.hash = itemTarget(items[Math.min(from, items.length - 1)], true);
}

/** The reviews waiting for her (a clip's review, its publish check), every project's, in the Inbox's order. */
export function reviewQueue(items: InboxItem[]): InboxItem[] {
  return items.filter((x) => x.kind === 'review' || x.kind === 'publish');
}

/** 「连着看」 Review in a row: every review waiting for her, across all her projects in the Inbox's order, one after
 * another where each is answered (the clip's page with its question pinned, "3 of 12" on top); with no review
 * waiting, the other questions the same way. */
export function reviewInRow(items: InboxItem[]) {
  const reviews = reviewQueue(items);
  // Linked videos always use the same inline queue, including while a filler question becomes a
  // publish check. The number of projects / a polling snapshot must not change the review UI.
  // An aggregate project review without a linked video still owns the full-screen review.
  const pids = new Set(reviews.map((x) => x.project.id));
  const linked = reviews.some((x) => (x.options ?? []).some((o) => o.clip_id));
  if (reviews.length && !linked && pids.size === 1 && reviews[0].project.id) location.hash = href({ name: 'focus', id: reviews[0].project.id });
  else startTriage(reviews.length ? reviews : items);
}

export function endTriage(toInbox = true) {
  setTriage(null);
  if (toInbox) go({ name: 'inbox' });
}

/** Move to the next item still open (answered ones drop out of `items`); past the end the queue ends in the Inbox. */
export function triageStep(items: InboxItem[], dir: 1 | -1 = 1, resolved?: string) {
  const s = triageState();
  if (!s) return;
  const open = new Set(items.map((x) => x.key));
  if (resolved) open.delete(resolved);
  let i = s.i + dir;
  while (i >= 0 && i < s.keys.length && !open.has(s.keys[i])) i += dir;
  if (i < 0 || i >= s.keys.length) {
    endTriage(true);
    return;
  }
  setTriage({ keys: s.keys, i });
  const x = items.find((y) => y.key === s.keys[i]);
  if (x) location.hash = itemTarget(x, true);
}

// ---------------------------------------------------------------- ⌘[ / ⌘] back and forward
export function backForwardKey(e: Pick<KeyboardEvent, 'metaKey' | 'ctrlKey' | 'altKey' | 'shiftKey' | 'key'>): -1 | 1 | 0 {
  if (!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey) return 0;
  return e.key === '[' ? -1 : e.key === ']' ? 1 : 0;
}

export function useBackForwardKeys() {
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const d = backForwardKey(e);
      if (!d) return;
      e.preventDefault();
      if (d < 0) history.back();
      else history.forward();
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, []);
}
