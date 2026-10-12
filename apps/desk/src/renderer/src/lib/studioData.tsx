// The Studio's rows for the whole app: the list itself and (step 8) the Dock badge, the notifications that open the
// exact video and ⌘K all read the same rows. Loaded only with the Studio on.
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { CalendarPost, Clip } from '../../../shared/v04';
import { useEngine, useLoad } from './engine';
import { useHistory } from './history';
import { useInbox } from './inbox';
import { href } from './router';
import { studioRows, studioSettled, type StudioRow } from './studio';
import { useStudioEnabled } from './studioFlag';

interface Ctx {
  rows: StudioRow[];
  posts: CalendarPost[];
  /** every source of the rows loaded (``studioSettled``): the counts are final, an empty list means no videos */
  ready: boolean;
  /** every recent project's clips as loaded so far (the bulk Schedule reads them instead of asking per project) */
  clips: Record<string, Clip[] | undefined>;
}

const StudioCtx = createContext<Ctx>({ rows: [], posts: [], ready: false, clips: {} });

/** A source that never answers (a stuck clips call) does not hide the counts for ever. */
export const SETTLE_GIVE_UP_MS = 15_000;

/** How many projects' clips are asked for at once (200+ projects at start-up: a few at a time, newest first). */
export const CLIPS_AT_ONCE = 6;

/** Every recent project's clips, loaded once per project version (a run's new clip shows as soon as it exists), a
 * few projects at a time. A clip edit reloads that project only; a calendar change reloads none (a clip's posts are
 * not in its clips). A project whose clips could not be read is asked again on its next change or a minute later -
 * never shown as "no videos" for good. */
function useClipsOf(ids: { id: string; v: string }[], on: boolean) {
  const { client, subscribe } = useEngine();
  const [clips, setClips] = useState<Record<string, Clip[] | undefined>>({});
  const seen = useRef<Record<string, string>>({});
  const [n, setN] = useState(0);
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type !== 'output-edit') return;
        delete seen.current[e.item];
        setN((x) => x + 1);
      }),
    [subscribe],
  );
  const key = ids.map((x) => `${x.id}:${x.v}`).join('|');
  useEffect(() => {
    if (!client || !on) return;
    let alive = true;
    const marks = seen.current;
    const todo = ids.filter(({ id, v }) => marks[id] !== v);
    for (const { id, v } of todo) marks[id] = v;
    let failed = false;
    // the answers are put in together a few times a second, not one re-render of the whole list per project
    let pending: Record<string, Clip[]> = {};
    let flushT = 0;
    const flush = () => {
      flushT = 0;
      const p = pending;
      pending = {};
      if (alive && Object.keys(p).length) setClips((c) => ({ ...c, ...p }));
    };
    const put = (id: string, cl: Clip[]) => {
      pending[id] = cl;
      if (!flushT) flushT = window.setTimeout(flush, 150);
    };
    const going = new Set<{ id: string; v: string }>();
    const next = async (): Promise<void> => {
      const x = todo.shift();
      if (!x || !alive) return;
      going.add(x);
      try {
        const d = await client.clips(x.id);
        put(x.id, d.clips);
      } catch {
        // not read this time (the engine busy, a project being moved): no videos for now, asked again later
        if (marks[x.id] === x.v) delete marks[x.id];
        failed = true;
        if (alive) setClips((c) => (c[x.id] ? c : { ...c, [x.id]: [] }));
      }
      going.delete(x);
      return next();
    };
    void Promise.all(Array.from({ length: Math.min(CLIPS_AT_ONCE, todo.length) }, next)).then(() => {
      window.clearTimeout(flushT);
      flush();
      if (alive && failed) window.setTimeout(() => alive && setN((k) => k + 1), 60_000);
    });
    return () => {
      window.clearTimeout(flushT);
      flush();
      alive = false;
      // what this round did not get to (or got after it was over) is the next round's
      for (const x of [...todo, ...going]) if (marks[x.id] === x.v) delete marks[x.id];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, key, n, on]);
  return clips;
}

const RECENT_S = 14 * 86400;

export function StudioProvider({ children }: { children: ReactNode }) {
  const on = useStudioEnabled();
  const { data: hist, requests = [], requestsLoaded = true } = useHistory();
  const inbox = useInbox();
  const { subscribe } = useEngine();
  const { data: cal, error: calError, reload: reloadCal } = useLoad((c) => (on ? c.calendar(undefined, { queue: false }).catch(() => c.calendar()) : Promise.resolve(null)), [on]);
  useEffect(() => subscribe((e) => void (e.type === 'calendar' && reloadCal())), [subscribe]); // eslint-disable-line react-hooks/exhaustive-deps
  const posts = useMemo(() => cal?.posts ?? [], [cal]);
  const items = useMemo(() => hist?.items ?? [], [hist]);
  const recent = useMemo(() => {
    const now = Date.now() / 1000;
    return items.filter((i) => now - (i.updated ?? i.created ?? 0) < RECENT_S || i.live?.state === 'running' || i.live?.state === 'waiting');
  }, [items]);
  const clips = useClipsOf(
    recent.map((i) => ({ id: i.id, v: `${i.updated ?? 0}:${i.status}:${i.live?.state ?? ''}` })),
    on,
  );
  const rows = useMemo(() => (on ? studioRows(recent, requests, clips, posts, inbox.items) : []), [on, recent, requests, clips, posts, inbox.items]);
  const settled = studioSettled({
    history: !!hist,
    requests: requestsLoaded,
    inbox: inbox.loaded ?? !inbox.loading,
    calendar: !on || cal !== null || calError !== null,
    projects: recent.map((i) => i.id),
    clips,
  });
  // give up waiting on a source that does not answer, counted from when the history came in
  const [gaveUp, setGaveUp] = useState(false);
  useEffect(() => {
    if (!hist || settled || gaveUp) return;
    const tm = window.setTimeout(() => setGaveUp(true), SETTLE_GIVE_UP_MS);
    return () => window.clearTimeout(tm);
  }, [!!hist, settled, gaveUp]); // eslint-disable-line react-hooks/exhaustive-deps
  // once the first full picture is in, it stays: a project started later shows as it comes (no counts blinking off)
  const now = settled || (gaveUp && !!hist);
  const [latched, setLatched] = useState(false);
  useEffect(() => {
    if (now && !latched) setLatched(true);
  }, [now, latched]);
  const ready = now || latched;
  const value = useMemo(() => ({ rows, posts, ready, clips }), [rows, posts, ready, clips]);
  return <StudioCtx.Provider value={value}>{children}</StudioCtx.Provider>;
}

export function useStudioData(): Ctx {
  return useContext(StudioCtx);
}

/** Where a row opens in the Studio (a question about it: pinned there). */
export function rowHref(r: StudioRow, withAsk = false): string {
  const ask = withAsk && r.ask ? `?item=${encodeURIComponent(r.ask.key)}` : '';
  if (r.kind === 'clip') return href({ name: 'studio', id: r.item!, clip: r.clip! }) + ask;
  if (r.kind === 'project') return href({ name: 'studio', id: r.item! }) + ask;
  return `${href({ name: 'studio' })}?sel=${r.r!.id}`;
}
