// The Studio's rows for the whole app: the list itself and (step 8) the Dock badge, the notifications that open the
// exact video and ⌘K all read the same rows. Loaded only with the Studio on.
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { CalendarPost, Clip } from '../../../shared/v04';
import { ClipsRounds, type ClipsAsk } from './clipsRounds';
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
 * few projects at a time (``ClipsRounds``: a refresh of the list never throws away an answer still coming). A clip
 * edit reloads that project only; a calendar change reloads none (a clip's posts are not in its clips). A project
 * whose clips could not be read is asked again on its next change or a minute later - never shown as "no videos" for
 * good. */
function useClipsOf(ids: ClipsAsk[], on: boolean) {
  const { client, subscribe } = useEngine();
  const [clips, setClips] = useState<Record<string, Clip[] | undefined>>({});
  const rounds = useRef(new ClipsRounds<Clip[]>(CLIPS_AT_ONCE));
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => void (mounted.current = false);
  }, []);
  const [n, setN] = useState(0);
  useEffect(
    () =>
      subscribe((e) => {
        if (e.type !== 'output-edit') return;
        rounds.current.forget(e.item);
        setN((x) => x + 1);
      }),
    [subscribe],
  );
  const key = ids.map((x) => `${x.id}:${x.v}`).join('|');
  useEffect(() => {
    if (!client || !on) return;
    // the answers are put in together a few times a second, not one re-render of the whole list per project
    let pending: Record<string, Clip[]> = {};
    let flushT = 0;
    const flush = () => {
      flushT = 0;
      const p = pending;
      pending = {};
      if (mounted.current && Object.keys(p).length) setClips((c) => ({ ...c, ...p }));
    };
    const r = rounds.current.round(
      ids,
      async (id) => (await client.clips(id)).clips,
      (id, cl) => {
        pending[id] = cl;
        if (!flushT) flushT = window.setTimeout(flush, 150);
      },
      // not read this time (the engine busy, a project being moved): no videos for now, asked again later
      (id) => mounted.current && setClips((c) => (c[id] ? c : { ...c, [id]: [] })),
    );
    void r.done.then(({ failed }) => {
      window.clearTimeout(flushT);
      flush();
      if (failed) window.setTimeout(() => mounted.current && setN((k) => k + 1), 60_000);
    });
    return r.cancel;
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
